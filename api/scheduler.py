"""
PyProxyPool — APScheduler 定时调度器

从原 main.py run_scheduler() 迁移，使用 APScheduler 管理定时任务
"""
import asyncio
import logging
import os
import shutil
import tempfile
import time
from datetime import datetime

import geoip2.database
import geoip2.errors
import httpx
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import select

from database import get_db_session
from models import Proxy, ScanTask
from services.scanner import ProxyScanner
from services.importer import ProxyImporter
from services.pool import ProxyPool
from services.geo import IPGeoService
from services.risk import RiskAnalyzer
from scoring import get_scoring_engine
from config import get_settings
from getter import ProxyCrawler

logger = logging.getLogger(__name__)

# 全局调度器实例
_scheduler: AsyncIOScheduler = None
_start_time = time.time()


def get_scheduler() -> AsyncIOScheduler:
    """获取全局调度器单例"""
    global _scheduler
    if _scheduler is None:
        _scheduler = AsyncIOScheduler()
    return _scheduler


async def start_scheduler() -> None:
    """启动调度器"""
    global _start_time
    _start_time = time.time()

    scheduler = get_scheduler()

    # 注册定时任务
    settings = get_settings()

    # 1. 定时采集+验证（每 CRAWL_INTERVAL 秒）
    scheduler.add_job(
        func=periodic_crawl,
        trigger='interval',
        seconds=settings.CRAWL_INTERVAL,
        id='periodic_crawl',
        replace_existing=True,
    )
    logger.info(f'Registered periodic_crawl: every {settings.CRAWL_INTERVAL}s')

    # 2. 定时健康检查（每 CHECK_INTERVAL 秒，采样 30%）
    scheduler.add_job(
        func=periodic_health_check,
        trigger='interval',
        seconds=settings.CHECK_INTERVAL,
        id='periodic_health_check',
        replace_existing=True,
    )
    logger.info(f'Registered periodic_health_check: every {settings.CHECK_INTERVAL}s')

    # 3. 定时剔除 D 级代理（每 3600 秒）
    scheduler.add_job(
        func=remove_degraded_proxies,
        trigger='interval',
        seconds=3600,
        id='remove_degraded',
        replace_existing=True,
    )
    logger.info('Registered remove_degraded_proxies: every 3600s')

    # 4. GeoIP 数据库定期更新
    if settings.GEOIP_DB_AUTO_UPDATE:
        scheduler.add_job(
            func=periodic_geoip_update,
            trigger='cron',
            hour=2,  # 每天凌晨 2 点
            minute=0,
            id='geoip_update',
            replace_existing=True,
        )
        logger.info('Scheduled GeoIP database update: daily at 02:00')

    scheduler.start()
    logger.info('Scheduler started')


async def stop_scheduler() -> None:
    """停止调度器"""
    scheduler = get_scheduler()
    if scheduler and scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info('Scheduler stopped')


# ==================== 定时任务实现 ====================

async def periodic_crawl():
    """
    定时采集+验证任务
    流程：采集 → 快速验活 → 评分 → 入库
    """
    logger.info('=== Scheduled crawl started ===')
    settings = get_settings()
    engine = get_scoring_engine()

    try:
        # 1. 采集
        crawler = ProxyCrawler()
        crawled = crawler.crawl_all()
        logger.info(f'Crawled {len(crawled)} proxies')

        if not crawled:
            logger.info('No proxies crawled, skipping')
            return

        # 2. 计算评分
        for p in crawled:
            p.scan_score = engine.calculate(p)
            p.grade = engine.grade_from_score(p.scan_score)

        # 3. 批量入库
        session = await get_db_session()
        try:
            # 去重检查
            addresses = [(p.ip, p.port) for p in crawled]
            existing = await session.execute(
                select(Proxy.ip, Proxy.port).where(Proxy.ip.in_([p.ip for p in crawled]))
            )
            existing_keys = set(existing.all())
            new_proxies = [p for p in crawled if (p.ip, p.port) not in existing_keys]

            if new_proxies:
                session.add_all(new_proxies)
                await session.commit()
                logger.info(f'Inserted {len(new_proxies)} new proxies')

            # 清理低分
            result = await session.execute(select(Proxy).where(Proxy.score < settings.MIN_SCORE))
            low_score = list(result.scalars().all())
            for p in low_score:
                await session.delete(p)
            await session.commit()
            logger.info(f'Cleaned {len(low_score)} low-score proxies')

            # 统计
            total = await session.scalar(select(Proxy).with_only_columns(func.count()))
            logger.info(f'=== Crawl done. Total proxies: {total} ===')
        except Exception as e:
            await session.rollback()
            logger.error(f'Crawl commit failed: {e}', exc_info=True)
        finally:
            await session.close()

    except Exception as e:
        logger.error(f'Periodic crawl failed: {e}', exc_info=True)


async def periodic_health_check():
    """
    定时健康检查（采样 30% 代理）
    更新评分、速度、验证时间
    """
    logger.info('=== Scheduled health check started ===')
    settings = get_settings()

    try:
        session = await get_db_session()
        semaphore = asyncio.Semaphore(min(settings.SCAN_CONCURRENCY, 100))

        # 采样 30%
        total = await session.scalar(select(Proxy).with_only_columns(func.count()))
        if not total:
            logger.info('No proxies to check')
            return

        sample_size = max(int(total * 0.3), 5)
        result = await session.execute(
            select(Proxy).order_by(Proxy.id).limit(sample_size)
        )
        proxies = list(result.scalars().all())

        # 异步验证
        async with ProxyScanner() as scanner:
            valid_proxies = []
            invalid_proxies = []

            for proxy in proxies:
                try:
                    result = await scanner.validate_one(proxy, semaphore)
                    if result.get('is_valid'):
                        valid_proxies.append(proxy)
                    else:
                        proxy.score = max(proxy.score - settings.SCORE_DEDUCT_FAIL, 0)
                        invalid_proxies.append(proxy)
                except Exception as e:
                    logger.debug(f'Health check failed for {proxy.ip}:{proxy.port}: {e}')
                    proxy.score = max(proxy.score - settings.SCORE_DEDUCT_FAIL, 0)
                    invalid_proxies.append(proxy)

            # 重新计算评分
            engine = get_scoring_engine()
            for p in valid_proxies + invalid_proxies:
                p.scan_score = engine.calculate(p)
                p.grade = engine.grade_from_score(p.scan_score)

            # 清理低分
            if valid_proxies:
                session.add_all(valid_proxies)
            await session.commit()

            # 删除低分
            result = await session.execute(select(Proxy).where(Proxy.score < settings.MIN_SCORE))
            low_score = list(result.scalars().all())
            for p in low_score:
                await session.delete(p)
            await session.commit()

            logger.info(
                f'=== Health check done. Valid: {len(valid_proxies)}, '
                f'Invalid: {len(invalid_proxies)}, Cleaned: {len(low_score)} ==='
            )

        await session.close()

    except Exception as e:
        logger.error(f'Periodic health check failed: {e}', exc_info=True)


async def remove_degraded_proxies():
    """定时剔除 D 级代理"""
    logger.info('=== Removing degraded proxies ===')
    settings = get_settings()

    try:
        session = await get_db_session()
        pool = ProxyPool()
        deleted = await pool.remove_degraded(session, min_grade='D')
        await session.commit()
        logger.info(f'Removed {deleted} D-grade proxies')
        await session.close()
    except Exception as e:
        logger.error(f'Remove degraded proxies failed: {e}', exc_info=True)


async def _update_geoip_db() -> bool:
    """
    下载并替换 GeoIP 数据库
    流程：下载 → 校验 → 备份旧文件 → 原子替换 → hot-reload
    """
    settings = get_settings()
    db_path = settings.GEOIP_DB_PATH
    db_dir = os.path.dirname(db_path)
    os.makedirs(db_dir, exist_ok=True)

    download_url = settings.GEOIP_DB_DOWNLOAD_URL

    # 1. 下载最新数据库到临时文件
    logger.info(f'Downloading GeoIP database from {download_url}')
    temp_path = f'{tempfile.gettempdir()}/geoip_tmp_{os.getpid()}.mmdb'

    try:
        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.get(download_url, follow_redirects=True)
            resp.raise_for_status()
            with open(temp_path, 'wb') as f:
                f.write(resp.content)

        file_size = os.path.getsize(temp_path)
        logger.info(f'Downloaded GeoIP database: {file_size / 1024 / 1024:.1f} MB')

        # 2. 校验：尝试用 geoip2 打开
        try:
            test_reader = geoip2.database.Reader(temp_path)
            test_reader.close()
        except Exception as e:
            logger.error(f'GeoIP download validation failed: {e}')
            os.remove(temp_path)
            return False

        # 3. 备份旧文件
        backup_path = db_path + '.backup'
        if os.path.isfile(db_path):
            shutil.copy2(db_path, backup_path)
            logger.info(f'Backed up old GeoIP database to {backup_path}')

        # 4. 原子替换
        os.replace(temp_path, db_path)
        logger.info(f'GeoIP database updated: {db_path} ({os.path.getsize(db_path) / 1024 / 1024:.1f} MB)')

        # 5. Hot-reload: 更新 database.py 中的 _geoip_reader 单例
        try:
            from database import init_geoip, get_geoip_reader

            init_geoip()

            # 同时更新 IPGeoService 实例的引用（如果有活跃的 service 实例）
            geoip_reader = get_geoip_reader()
            if geoip_reader and geoip_reader.is_available():
                logger.info('GeoIP database hot-reloaded successfully')
            else:
                logger.warning('GeoIP database file exists but Reader failed to open')
        except Exception as e:
            logger.error(f'Failed to hot-reload GeoIP reader: {e}')

        return True

    except Exception as e:
        logger.error(f'GeoIP database update failed: {e}')
        # 清理临时文件
        if os.path.isfile(temp_path):
            os.remove(temp_path)
        return False


async def periodic_geoip_update() -> None:
    """APScheduler 定时任务：定期更新 GeoIP 数据库"""
    settings = get_settings()
    if not settings.GEOIP_DB_AUTO_UPDATE:
        return

    logger.info('Starting periodic GeoIP database update...')

    success = await _update_geoip_db()

    if success:
        logger.info('GeoIP 数据库更新完成')
    else:
        logger.error('GeoIP 数据库更新失败（下次周期将重试）')