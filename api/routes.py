"""
PyProxyPool — REST API 路由

FastAPI 路由实现，兼容旧 API 路径
"""
import logging
from datetime import datetime
from typing import Optional, List

from fastapi import APIRouter, Depends, Query, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse, Response
from sqlalchemy import select, func, desc, asc
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models import Proxy, ScanTask, ScanResult, WhitelistEntry, BlacklistEntry
from schemas import (
    ProxyResponse, ScanResponse, ScanStatusResponse, StatsResponse,
    SourceStatsResponse, CountryStatsResponse, SpeedDistributionResponse,
    PaginatedResponse, ErrorResponse, ExportRequest, SuccessResponse,
)
from api.auth import authenticate, optional_auth
from services.pool import ProxyPool
from services.exporter import Exporter
from config import get_settings, MIN_SCORE
from scoring import get_scoring_engine

logger = logging.getLogger(__name__)

router = APIRouter(prefix='/api/v1')


# ==================== 代理查询 ====================

@router.get('/proxies', response_model=PaginatedResponse)
async def list_proxies(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    grade: Optional[str] = Query(None, description='等级筛选 (A/B/C/D)'),
    protocol: Optional[str] = Query(None, description='协议筛选 (http/https/socks5)'),
    country: Optional[str] = Query(None, description='国家筛选'),
    min_score: Optional[int] = Query(None, description='最低评分'),
    db: AsyncSession = Depends(get_db),
):
    """
    分页查询代理列表
    支持 grade / protocol / country / min_score 筛选
    """
    stmt = select(Proxy)

    if grade:
        stmt = stmt.where(Proxy.grade == grade)
    if protocol:
        stmt = stmt.where(Proxy.protocol == protocol)
    if country:
        stmt = stmt.where(Proxy.country == country)
    if min_score is not None:
        stmt = stmt.where(Proxy.score >= min_score)

    # 总数
    total_stmt = select(func.count(Proxy.id))
    for criteria in []:
        pass  # reuse same conditions
    total_stmt = stmt.with_only_columns(func.count(Proxy.id)).order_by(None)
    total = await db.scalar(total_stmt) or 0

    # 数据
    stmt = stmt.order_by(desc(Proxy.scan_score)).offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(stmt)
    proxies = list(result.scalars().all())

    logger.info(f'查询代理列表: 第{page}页, 每页{page_size}条, 共{total}条, 返回{len(proxies)}条'
                + (f', 等级={grade}' if grade else '')
                + (f', 协议={protocol}' if protocol else '')
                + (f', 国家={country}' if country else ''))

    pages = (total + page_size - 1) // page_size

    return {
        'total': total,
        'page': page,
        'page_size': page_size,
        'pages': pages,
        'has_next': page < pages,
        'has_prev': page > 1,
        'items': [ProxyResponse.model_validate(p) for p in proxies],
    }


@router.post('/proxies', response_model=SuccessResponse)
async def import_proxies(
    proxies_data: List[str],
    source: str = 'manual',
    db: AsyncSession = Depends(get_db),
    auth_token: str = Depends(authenticate),
):
    """
    批量导入代理

    Body: 代理字符串数组，如 ["1.2.3.4:8080", "http://5.6.7.8:3128"]
    """
    from services.importer import ProxyImporter
    importer = ProxyImporter()

    # 解析
    from utils.proxy_parser import parse_proxy_list
    parsed = parse_proxy_list(proxies_data)
    if not parsed:
        raise HTTPException(status_code=400, detail='No valid proxies found')

    # 构建 Proxy 对象
    settings = get_settings()
    proxy_objects = [
        Proxy(
            ip=item['ip'],
            port=item['port'],
            protocol=item.get('protocol', 'http'),
            username=item.get('username', ''),
            password=item.get('password', ''),
            source=source,
            score=settings.INITIAL_SCORE,
        )
        for item in parsed
    ]

    # 检查已有
    addresses = [(p.ip, p.port) for p in proxy_objects]
    if addresses:
        existing = await db.execute(
            select(Proxy.ip, Proxy.port).where(Proxy.ip.in_([p.ip for p in proxy_objects]))
        )
        existing_keys = set(existing.all())
        proxy_objects = [p for p in proxy_objects if (p.ip, p.port) not in existing_keys]

    if not proxy_objects:
        logger.info(f'批量导入代理: 所有 {len(parsed)} 条记录已存在数据库，跳过')
        return SuccessResponse(message='All proxies already exist', data={'imported': 0})

    db.add_all(proxy_objects)
    await db.flush()

    logger.info(f'批量导入代理: 成功导入 {len(proxy_objects)}/{len(parsed)} 条, 来源={source}')
    return SuccessResponse(message='Imported', data={'imported': len(proxy_objects)})


@router.delete('/proxies/{ip}/{port}')
async def delete_proxy(
    ip: str,
    port: int,
    db: AsyncSession = Depends(get_db),
    auth_token: str = Depends(authenticate),
):
    """删除指定代理"""
    result = await db.execute(select(Proxy).where(Proxy.ip == ip, Proxy.port == port))
    proxy = result.scalars().first()
    if not proxy:
        raise HTTPException(status_code=404, detail='Proxy not found')

    await db.delete(proxy)
    await db.flush()

    logger.info(f'删除代理: {ip}:{port} (来源={proxy.source}, 等级={proxy.grade})')

    return SuccessResponse(message='Deleted', data={'ip': ip, 'port': port})


# ==================== 代理获取（兼容旧路径） ====================

@router.get('/proxy', response_model=List[ProxyResponse])
async def get_proxy(
    count: int = Query(1, ge=1, le=100),
    protocol: Optional[str] = Query(None),
    types: Optional[str] = Query(None),  # 兼容旧参数：0=high, 1=anonymous, 2=transparent
    min_score: Optional[int] = Query(MIN_SCORE),
    tags: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    auth_token: str = Depends(authenticate),
):
    """获取随机代理（兼容旧 /proxy 路径）"""
    pool = ProxyPool()
    proxies = await pool.get_random(db, count=count)

    before_filter = len(proxies)
    if protocol:
        proxies = [p for p in proxies if p.protocol == protocol]
    if types is not None:
        anonymity_map = {'0': 'high', '1': 'anonymous', '2': 'transparent'}
        anonymity = anonymity_map.get(types)
        if anonymity:
            proxies = [p for p in proxies if p.anonymity == anonymity]
    if min_score is not None:
        proxies = [p for p in proxies if p.score >= min_score]

    if len(proxies) > count:
        import random
        proxies = random.sample(proxies, count)

    logger.info(f'获取随机代理: 请求{count}个, 命中{before_filter}个, 返回{len(proxies)}个'
                + (f', 协议={protocol}' if protocol else '')
                + (f', 最低评分={min_score}' if min_score else ''))

    return [ProxyResponse.model_validate(p) for p in proxies]


@router.get('/proxy/all', response_model=dict)
async def get_all_proxies(
    db: AsyncSession = Depends(get_db),
    auth_token: str = Depends(authenticate),
):
    """获取所有代理（兼容旧 /proxy/all 路径）"""
    result = await db.execute(select(Proxy).order_by(desc(Proxy.scan_score)))
    proxies = list(result.scalars().all())
    return {
        'total': len(proxies),
        'proxies': [ProxyResponse.model_validate(p).model_dump() for p in proxies],
    }


@router.get('/proxy/http', response_model=List[ProxyResponse])
async def get_http_proxies(
    count: int = Query(10, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    auth_token: str = Depends(authenticate),
):
    """获取 HTTP 代理"""
    pool = ProxyPool()
    proxies = await pool.get_random(db, count=count)
    proxies = [p for p in proxies if p.protocol in ('http', 'https')]
    return [ProxyResponse.model_validate(p) for p in proxies]


@router.get('/proxy/https', response_model=List[ProxyResponse])
async def get_https_proxies(
    count: int = Query(10, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    auth_token: str = Depends(authenticate),
):
    """获取 HTTPS 代理"""
    pool = ProxyPool()
    proxies = await pool.get_random(db, count=count)
    proxies = [p for p in proxies if p.protocol == 'https']
    return [ProxyResponse.model_validate(p) for p in proxies]


# ==================== 扫描任务 ====================

@router.post('/crawl', response_model=ScanResponse)
async def trigger_crawl(
    batch_size: int = Query(500, ge=1, le=2000),
    db: AsyncSession = Depends(get_db),
    auth_token: str = Depends(optional_auth),
):
    """触发采集+验证"""
    import uuid
    task_id = str(uuid.uuid4())[:8]

    task = ScanTask(
        task_id=task_id,
        status='running',
        total=batch_size,
        created_at=datetime.utcnow(),
    )
    db.add(task)
    await db.flush()

    # 异步启动采集任务（后台执行）
    _start_crawl_task(task_id, batch_size)

    logger.info(f'手动触发采集任务: task_id={task_id}, batch_size={batch_size}')
    return ScanResponse(
        task_id=task_id,
        status='running',
        total=batch_size,
        created_at=datetime.utcnow(),
    )


def _start_crawl_task(task_id: str, batch_size: int):
    """启动后台采集任务（异步）"""
    import asyncio
    from services.scanner import ProxyScanner
    from services.importer import ProxyImporter
    from services.pool import ProxyPool
    from scoring import get_scoring_engine
    from getter import ProxyCrawler

    async def _crawl():
        from database import get_db_session

        # 进度回调：每个源完成时更新 processed
        async def _on_progress(completed: int, total: int, proxies_found: int):
            try:
                sess = await get_db_session()
                task_stmt = select(ScanTask).where(ScanTask.task_id == task_id)
                task_result = await sess.execute(task_stmt)
                task = task_result.scalars().first()
                if task:
                    task.processed = completed
                    task.valid = proxies_found
                    await sess.commit()
                await sess.close()
            except Exception as e:
                logger.error(f'Progress update error: {e}')

        session = await get_db_session()
        try:
            logger.info(f'采集任务 {task_id} 开始: 目标采集 {batch_size} 个代理')
            crawler = ProxyCrawler()
            crawled = await crawler.crawl_all_async(on_progress=_on_progress)

            engine = get_scoring_engine()
            for p in crawled:
                p.scan_score = engine.calculate(p)
                p.grade = engine.grade_from_score(p.scan_score)

            # GeoIP 查询：填充 country 和 area
            from database import get_geoip_reader
            geoip_reader = get_geoip_reader()
            if geoip_reader is not None and geoip_reader.is_available():
                geo_success = 0
                for p in crawled:
                    if not p.country:  # 仅填充未设置国家信息的代理
                        geo = geoip_reader.lookup(p.ip)
                        if geo:
                            p.country = geo.get('country', '') or p.country
                            p.area = geo.get('region', '') or geo.get('city', '') or p.area
                            geo_success += 1
                logger.info(f'采集任务 {task_id}: GeoIP 查询完成, 成功填充 {geo_success}/{len(crawled)} 个代理的地理位置')
            else:
                logger.warning(f'采集任务 {task_id}: GeoIP 数据库不可用, 跳过地理位置查询')

            # 使用 INSERT ... ON CONFLICT DO UPDATE 处理重复 (ip, port)
            # 已存在的代理更新评分/等级/更新时间，不存在的直接插入
            from sqlalchemy.dialects.sqlite import insert as sqlite_insert
            from models import Proxy

            data = [
                {
                    'ip': p.ip, 'port': p.port, 'protocol': p.protocol,
                    'username': p.username or '', 'password': p.password or '',
                    'anonymity': p.anonymity or 'unknown', 'country': p.country or '',
                    'area': p.area or '', 'speed': p.speed, 'score': p.score,
                    'last_verified': p.last_verified or 0.0, 'use_count': p.use_count or 0,
                    'source': p.source or '', 'outlet_ip': p.outlet_ip or '',
                    'is_outbound_ip': p.is_outbound_ip or 0,
                    'purity_score': p.purity_score or 0, 'purity_class': p.purity_class or '',
                    'is_datacenter': p.is_datacenter or 0, 'is_proxy': p.is_proxy or 0,
                    'is_vpn': p.is_vpn or 0, 'is_tor': p.is_tor or 0,
                    'abuse_confidence': p.abuse_confidence or 0, 'isp': p.isp or '',
                    'asn': p.asn or '', 'asn_owner': p.asn_owner or '',
                    'org_name': p.org_name or '', 'ip_type': p.ip_type or '',
                    'is_native': p.is_native or 0, 'shared_users': p.shared_users or '',
                    'risk_score': p.risk_score or 0, 'risk_level': p.risk_level or '',
                    'rdns': p.rdns or '', 'scenes': p.scenes or '',
                    'ping0_location': p.ping0_location or '',
                    'ping0_latitude': p.ping0_latitude or 0.0,
                    'ping0_longitude': p.ping0_longitude or 0.0,
                    'scan_score': p.scan_score, 'grade': p.grade,
                    'tags': p.tags or '[]',
                }
                for p in crawled
            ]

            stmt = sqlite_insert(Proxy).values(data)
            stmt = stmt.on_conflict_do_update(
                index_elements=['ip', 'port'],
                set_={
                    'protocol': stmt.excluded.protocol,
                    'username': stmt.excluded.username,
                    'password': stmt.excluded.password,
                    'anonymity': stmt.excluded.anonymity,
                    'country': stmt.excluded.country,
                    'area': stmt.excluded.area,
                    'speed': stmt.excluded.speed,
                    'score': stmt.excluded.score,
                    'last_verified': stmt.excluded.last_verified,
                    'use_count': stmt.excluded.use_count,
                    'source': stmt.excluded.source,
                    'outlet_ip': stmt.excluded.outlet_ip,
                    'purity_score': stmt.excluded.purity_score,
                    'purity_class': stmt.excluded.purity_class,
                    'is_datacenter': stmt.excluded.is_datacenter,
                    'is_proxy': stmt.excluded.is_proxy,
                    'is_vpn': stmt.excluded.is_vpn,
                    'is_tor': stmt.excluded.is_tor,
                    'abuse_confidence': stmt.excluded.abuse_confidence,
                    'isp': stmt.excluded.isp,
                    'asn': stmt.excluded.asn,
                    'asn_owner': stmt.excluded.asn_owner,
                    'org_name': stmt.excluded.org_name,
                    'ip_type': stmt.excluded.ip_type,
                    'is_native': stmt.excluded.is_native,
                    'shared_users': stmt.excluded.shared_users,
                    'risk_score': stmt.excluded.risk_score,
                    'risk_level': stmt.excluded.risk_level,
                    'rdns': stmt.excluded.rdns,
                    'scenes': stmt.excluded.scenes,
                    'ping0_location': stmt.excluded.ping0_location,
                    'ping0_latitude': stmt.excluded.ping0_latitude,
                    'ping0_longitude': stmt.excluded.ping0_longitude,
                    'scan_score': stmt.excluded.scan_score,
                    'grade': stmt.excluded.grade,
                    'tags': stmt.excluded.tags,
                    'updated_at': datetime.utcnow(),
                }
            )
            await session.execute(stmt)
            await session.commit()

            # 更新任务状态
            task_stmt = select(ScanTask).where(ScanTask.task_id == task_id)
            task_result = await session.execute(task_stmt)
            task = task_result.scalars().first()
            if task:
                task.status = 'completed'
                task.valid = len(crawled)
                task.processed = len(crawled)
                await session.commit()
            logger.info(f'采集任务 {task_id} 完成: 共采集 {len(crawled)} 个代理, 评分/等级已更新, 已入库')
        except Exception as e:
            logger.error(f'Crawl task {task_id} failed: {e}', exc_info=True)
            try:
                task_stmt = select(ScanTask).where(ScanTask.task_id == task_id)
                task_result = await session.execute(task_stmt)
                task = task_result.scalars().first()
                if task:
                    task.status = 'failed'
                    await session.commit()
            except Exception:
                pass
        finally:
            await session.close()

    asyncio.create_task(_crawl())


@router.get('/scan/{task_id}', response_model=ScanStatusResponse)
async def get_scan_status(
    task_id: str,
    db: AsyncSession = Depends(get_db),
):
    """查询扫描任务状态"""
    result = await db.execute(select(ScanTask).where(ScanTask.task_id == task_id))
    task = result.scalars().first()

    if not task:
        raise HTTPException(status_code=404, detail='Task not found')

    progress = 0.0
    if task.total > 0:
        progress = round(task.processed / task.total * 100, 1)

    return ScanStatusResponse(
        task_id=task.task_id,
        status=task.status,
        total=task.total,
        processed=task.processed,
        valid=task.valid,
        invalid=task.invalid,
        progress_percent=progress,
        created_at=task.created_at,
        updated_at=task.updated_at,
    )


# ==================== 统计信息 ====================

@router.get('/stats', response_model=StatsResponse)
async def get_stats(
    db: AsyncSession = Depends(get_db),
):
    """系统统计信息"""
    pool = ProxyPool()
    stats = await pool.get_stats(db)

    return StatsResponse(**stats)


@router.get('/stats/sources', response_model=List[SourceStatsResponse])
async def get_source_stats(
    db: AsyncSession = Depends(get_db),
):
    """按来源统计"""
    from sqlalchemy import text
    result = await db.execute(text('''
        SELECT source, COUNT(*) as cnt, AVG(score) as avg_s, AVG(speed) as avg_spd
        FROM proxies WHERE source != ''
        GROUP BY source ORDER BY cnt DESC
    '''))
    rows = result.all()
    return [
        SourceStatsResponse(
            source=r[0], count=r[1], avg_score=round(r[2] or 0, 1), avg_speed=round(r[3] or 0, 1),
        )
        for r in rows
    ]


@router.get('/stats/countries', response_model=List[CountryStatsResponse])
async def get_country_stats(
    db: AsyncSession = Depends(get_db),
):
    """按国家统计"""
    from sqlalchemy import text
    result = await db.execute(text('''
        SELECT country, COUNT(*) as cnt, AVG(score) as avg_s
        FROM proxies WHERE country != ''
        GROUP BY country ORDER BY cnt DESC LIMIT 20
    '''))
    rows = result.all()
    return [
        CountryStatsResponse(country=r[0], count=r[1], avg_score=round(r[2] or 0, 1))
        for r in rows
    ]


@router.get('/stats/speed-distribution', response_model=SpeedDistributionResponse)
async def get_speed_distribution(
    db: AsyncSession = Depends(get_db),
):
    """速度分布统计"""
    from sqlalchemy import text
    result = await db.execute(text('''
        SELECT
            SUM(CASE WHEN speed = 0 THEN 1 ELSE 0 END) as untested,
            SUM(CASE WHEN speed > 0 AND speed <= 200 THEN 1 ELSE 0 END) as fast,
            SUM(CASE WHEN speed > 200 AND speed <= 500 THEN 1 ELSE 0 END) as good,
            SUM(CASE WHEN speed > 500 AND speed <= 1000 THEN 1 ELSE 0 END) as medium,
            SUM(CASE WHEN speed > 1000 AND speed <= 3000 THEN 1 ELSE 0 END) as slow,
            SUM(CASE WHEN speed > 3000 THEN 1 ELSE 0 END) as very_slow
        FROM proxies
    '''))
    row = result.fetchone()
    return SpeedDistributionResponse(
        untested=row[0] or 0, fast=row[1] or 0, good=row[2] or 0,
        medium=row[3] or 0, slow=row[4] or 0, very_slow=row[5] or 0,
    )


@router.get('/stats/score-distribution', response_model=dict)
async def get_score_distribution(
    db: AsyncSession = Depends(get_db),
):
    """评分分布统计"""
    from sqlalchemy import text
    result = await db.execute(text('''
        SELECT
            SUM(CASE WHEN score >= 0 AND score < 20 THEN 1 ELSE 0 END) as "0-19",
            SUM(CASE WHEN score >= 20 AND score < 40 THEN 1 ELSE 0 END) as "20-39",
            SUM(CASE WHEN score >= 40 AND score < 60 THEN 1 ELSE 0 END) as "40-59",
            SUM(CASE WHEN score >= 60 AND score < 80 THEN 1 ELSE 0 END) as "60-79",
            SUM(CASE WHEN score >= 80 AND score <= 100 THEN 1 ELSE 0 END) as "80-100"
        FROM proxies
    '''))
    row = result.fetchone()
    return {
        '0-19': row[0] or 0,
        '20-39': row[1] or 0,
        '40-59': row[2] or 0,
        '60-79': row[3] or 0,
        '80-100': row[4] or 0,
    }


@router.get('/stats/crawl-progress')
async def get_crawl_progress(
    db: AsyncSession = Depends(get_db),
):
    """
    采集进度与调度信息

    返回:
    {
        "current_task": {task_id, status, processed, total, progress_pct, ...} or None,
        "recent_tasks": [{task_id, status, processed, total, created_at, updated_at}],
        "next_scheduled": {
            "periodic_crawl": "2026-07-04T13:00:00Z",
            "periodic_health_check": "2026-07-04T13:05:00Z",
        },
        "schedules": {
            "CRAWL_INTERVAL": 600,
            "CHECK_INTERVAL": 600,
            "DEGRADED_REMOVAL": 3600,
        }
    }
    """
    from api.scheduler import get_scheduler
    from datetime import datetime, timezone

    # 1. 查询最近 5 个任务
    result = await db.execute(
        select(ScanTask).order_by(ScanTask.created_at.desc()).limit(5)
    )
    recent_tasks_raw = list(result.scalars().all())

    recent_tasks = []
    current_task = None
    for t in recent_tasks_raw:
        task_dict = {
            'task_id': t.task_id,
            'status': t.status,
            'processed': t.processed,
            'total': t.total,
            'valid': t.valid,
            'invalid': t.invalid,
            'created_at': t.created_at.isoformat() if t.created_at else '',
            'updated_at': t.updated_at.isoformat() if t.updated_at else '',
        }
        recent_tasks.append(task_dict)

        # 找 running 任务作为 current_task
        if t.status == 'running' and current_task is None:
            current_task = task_dict.copy()
            current_task['progress_pct'] = 0
            if t.total > 0:
                current_task['progress_pct'] = round(t.processed / t.total * 100, 1)

    # 2. 获取下次调度时间
    next_scheduled = {}
    try:
        scheduler = get_scheduler()
        if scheduler:
            for job in scheduler.get_jobs():
                if job.next_run_time:
                    next_scheduled[job.id] = job.next_run_time.isoformat()
    except Exception:
        pass

    # 3. 调度间隔配置
    settings = get_settings()
    schedules = {
        'CRAWL_INTERVAL': settings.CRAWL_INTERVAL,
        'CHECK_INTERVAL': settings.CHECK_INTERVAL,
        'DEGRADED_REMOVAL': 3600,
    }

    return {
        'current_task': current_task,
        'recent_tasks': recent_tasks,
        'next_scheduled': next_scheduled,
        'schedules': schedules,
    }


# ==================== 导出 ====================

@router.get('/export')
async def export_proxies(
    grade: str = Query('all', description='等级筛选 (A/B/C/D/all)'),
    format: str = Query('json', alias='format', description='导出格式 (json/csv/txt)'),
    protocol: str = Query('all', description='协议筛选'),
    min_score: int = Query(0, description='最低评分'),
    db: AsyncSession = Depends(get_db),
    auth_token: str = Depends(authenticate),
):
    """多格式导出代理列表"""
    stmt = select(Proxy)
    if grade != 'all':
        stmt = stmt.where(Proxy.grade == grade)
    if protocol != 'all':
        stmt = stmt.where(Proxy.protocol == protocol)
    if min_score > 0:
        stmt = stmt.where(Proxy.score >= min_score)

    result = await db.execute(stmt)
    proxies = list(result.scalars().all())

    exporter = Exporter()
    data = exporter.export(proxies, fmt=format)

    content_types = {
        'json': 'application/json',
        'csv': 'text/csv',
        'txt': 'text/plain',
    }
    filenames = {
        'json': 'proxies.json',
        'csv': 'proxies.csv',
        'txt': 'proxies.txt',
    }

    return Response(
        content=data,
        media_type=content_types.get(format, 'application/octet-stream'),
        headers={
            'Content-Disposition': f'attachment; filename={filenames.get(format, "proxies.")}',
        },
    )


# ==================== 清理 ====================

@router.post('/cleanup', response_model=SuccessResponse)
async def cleanup_proxies(
    min_score: int = Query(MIN_SCORE),
    db: AsyncSession = Depends(get_db),
    auth_token: str = Depends(authenticate),
):
    """清理低分代理"""
    result = await db.execute(select(Proxy).where(Proxy.score < min_score))
    proxies = list(result.scalars().all())
    for p in proxies:
        await db.delete(p)
    await db.flush()
    return SuccessResponse(message='Cleaned', data={'deleted': len(proxies)})


# ==================== 白名单 / 黑名单 ====================

@router.get('/whitelist', response_model=List[dict])
async def get_whitelist(
    db: AsyncSession = Depends(get_db),
):
    """获取白名单"""
    result = await db.execute(select(WhitelistEntry))
    entries = list(result.scalars().all())
    return [{'ip': e.ip, 'port': e.port, 'protocol': e.protocol} for e in entries]


@router.post('/whitelist')
async def add_whitelist(
    ip: str,
    port: int,
    protocol: str = 'http',
    db: AsyncSession = Depends(get_db),
    auth_token: str = Depends(authenticate),
):
    """添加白名单"""
    entry = WhitelistEntry(ip=ip, port=port, protocol=protocol)
    db.add(entry)
    try:
        await db.flush()
    except Exception:
        raise HTTPException(status_code=409, detail='Already exists')
    return SuccessResponse(message='Added')


@router.get('/blacklist', response_model=List[dict])
async def get_blacklist(
    db: AsyncSession = Depends(get_db),
):
    """获取黑名单"""
    result = await db.execute(select(BlacklistEntry))
    entries = list(result.scalars().all())
    return [{'ip': e.ip, 'port': e.port, 'protocol': e.protocol, 'reason': e.reason} for e in entries]


@router.post('/blacklist')
async def add_blacklist(
    ip: str,
    port: int,
    protocol: str = 'http',
    reason: str = '',
    db: AsyncSession = Depends(get_db),
    auth_token: str = Depends(authenticate),
):
    """添加黑名单"""
    entry = BlacklistEntry(ip=ip, port=port, protocol=protocol, reason=reason)
    db.add(entry)
    try:
        await db.flush()
    except Exception:
        raise HTTPException(status_code=409, detail='Already exists')
    return SuccessResponse(message='Added')


# ==================== 系统信息 ====================

@router.get('/system')
async def get_system_info():
    """获取系统信息"""
    import platform
    import time
    return {
        'platform': platform.platform(),
        'python_version': platform.python_version(),
        'version': '3.0.0',
        'start_time': getattr(get_system_info, '_start_time', time.time()),
    }


get_system_info._start_time = None  # type: ignore

# ==================== 标签 ====================

@router.get('/tags', response_model=List[dict])
async def get_tags(
    db: AsyncSession = Depends(get_db),
):
    """获取标签统计"""
    return []  # 简化实现


# ==================== 兼容旧 API 路径 ====================

compat_router = APIRouter()


@compat_router.get('/stats')
async def compat_stats(db: AsyncSession = Depends(get_db)):
    """兼容 /stats"""
    pool = ProxyPool()
    stats = await pool.get_stats(db)
    return JSONResponse(content=stats)


@compat_router.get('/proxy/all')
async def compat_all(db: AsyncSession = Depends(get_db)):
    """兼容 /proxy/all"""
    result = await db.execute(select(Proxy).order_by(desc(Proxy.scan_score)))
    proxies = list(result.scalars().all())
    return JSONResponse(content={'total': len(proxies), 'proxies': [p.to_dict() for p in proxies]})


@compat_router.get('/export')
async def compat_export(
    format: str = 'json',
    grade: str = 'all',
    db: AsyncSession = Depends(get_db),
):
    """兼容 /export"""
    stmt = select(Proxy)
    if grade != 'all':
        stmt = stmt.where(Proxy.grade == grade)
    result = await db.execute(stmt)
    proxies = list(result.scalars().all())
    exporter = Exporter()
    data = exporter.export(proxies, fmt=format)
    return Response(content=data, media_type='application/json')


# ==================== 管理 API：GeoIP ====================

admin_router = APIRouter(prefix='/api/admin', tags=['admin'])


@admin_router.get('/geoip/status')
async def get_geoip_status():
    """获取 GeoIP 数据库状态"""
    from database import get_geoip_reader
    from config import get_settings
    from datetime import datetime
    import os

    reader = get_geoip_reader()
    settings = get_settings()
    db_path = settings.GEOIP_DB_PATH

    if reader:
        return reader.get_status()

    # 无 GeoIPReader，直接从文件获取信息
    status = {
        'source': 'geolite2',
        'path': db_path,
        'available': False,
        'size_mb': 0.0,
        'mtime': '',
        'mtime_iso': '',
    }
    if os.path.isfile(db_path):
        stat = os.stat(db_path)
        status['size_mb'] = round(stat.st_size / 1024 / 1024, 1)
        status['mtime'] = stat.st_mtime
        status['mtime_iso'] = datetime.fromtimestamp(stat.st_mtime).isoformat()
    return status


@admin_router.post('/geoip/refresh')
async def refresh_geoip():
    """手动触发 GeoIP 数据库更新"""
    from api.scheduler import _update_geoip_db
    success = await _update_geoip_db()
    if success:
        return {'success': True, 'message': 'GeoIP 数据库更新成功'}
    else:
        return {'success': False, 'message': 'GeoIP 数据库更新失败，请查看日志'}