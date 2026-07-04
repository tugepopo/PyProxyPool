"""
PyProxyPool — 代理池分级管理服务

按等级 A/B/C/D 管理代理池，支持分级查询、随机获取、剔除 D 级
"""
import logging
import random
from typing import Optional, List

from sqlalchemy import select, func, desc, asc
from sqlalchemy.ext.asyncio import AsyncSession

from models import Proxy
from scoring import get_scoring_engine
from config import get_settings

logger = logging.getLogger(__name__)


class ProxyPool:
    """
    代理池分级管理服务
    基于 scan_score 和 grade 进行分级管理
    """

    GRADE_ORDER = {'A': 0, 'B': 1, 'C': 2, 'D': 3}

    async def get_by_grade(
        self,
        session: AsyncSession,
        grade: str = 'A',
        limit: int = 100,
        offset: int = 0,
    ) -> List[Proxy]:
        """
        按等级获取代理列表

        Args:
            session: 异步数据库会话
            grade: 等级筛选 (A/B/C/D)，传 'all' 则不筛选
            limit: 返回数量上限
            offset: 分页偏移

        Returns:
            Proxy 列表
        """
        stmt = select(Proxy)
        if grade and grade != 'all':
            stmt = stmt.where(Proxy.grade == grade)

        stmt = stmt.order_by(desc(Proxy.scan_score)).offset(offset).limit(limit)
        result = await session.execute(stmt)
        return list(result.scalars().all())

    async def get_random(
        self,
        session: AsyncSession,
        count: int = 1,
        grade: str = 'all',
    ) -> List[Proxy]:
        """
        随机获取代理

        Args:
            session: 异步数据库会话
            count: 获取数量
            grade: 等级筛选 (A/B/C/D/all)

        Returns:
            随机 Proxy 列表
        """
        stmt = select(Proxy)
        if grade and grade != 'all':
            stmt = stmt.where(Proxy.grade == grade)

        # 按等级优先排序
        stmt = stmt.order_by(
            Proxy.grade.asc(),
            desc(Proxy.scan_score),
        )

        result = await session.execute(stmt)
        all_proxies = list(result.scalars().all())

        if not all_proxies:
            return []

        # 优先从高等级中随机选取
        grade_pools = {}
        for p in all_proxies:
            g = p.grade or 'D'
            if g not in grade_pools:
                grade_pools[g] = []
            grade_pools[g].append(p)

        selected = []
        # 按等级优先选择
        for grade_key in sorted(grade_pools.keys(), key=lambda x: self.GRADE_ORDER.get(x, 99)):
            if len(selected) >= count:
                break
            pool = grade_pools[grade_key]
            available = count - len(selected)
            picks = random.sample(pool, min(available, len(pool)))
            selected.extend(picks)

        return selected

    async def remove_degraded(
        self,
        session: AsyncSession,
        min_grade: str = 'D',
    ) -> int:
        """
        剔除低于指定等级的代理

        Args:
            session: 异步数据库会话
            min_grade: 保留的最低等级 (A/B/C/D)，默认剔除 D 级

        Returns:
            删除的代理数量
        """
        grade_order = self.GRADE_ORDER.get(min_grade, 3)

        stmt = select(Proxy).where(
            Proxy.grade.in_([g for g, o in self.GRADE_ORDER.items() if o > grade_order])
        )
        result = await session.execute(stmt)
        degraded = list(result.scalars().all())

        if not degraded:
            return 0

        for proxy in degraded:
            await session.delete(proxy)
        await session.flush()

        deleted = len(degraded)
        logger.info(f'Removed {deleted} degraded proxies (grade < {min_grade})')
        return deleted

    async def update_pool(
        self,
        session: AsyncSession,
        scored_proxies: List[Proxy],
    ) -> int:
        """
        更新代理池评分和等级

        Args:
            session: 异步数据库会话
            scored_proxies: 已评分的 Proxy 列表

        Returns:
            更新的代理数量
        """
        engine = get_scoring_engine()
        updated = 0

        for proxy in scored_proxies:
            # 重新计算评分
            proxy.scan_score = engine.calculate(proxy)
            proxy.grade = engine.grade_from_score(proxy.scan_score)
            updated += 1

        if updated:
            await session.flush()
            logger.info(f'Updated {updated} proxies with new scores and grades')

        return updated

    async def get_stats(self, session: AsyncSession) -> dict:
        """
        获取代理池统计信息

        Args:
            session: 异步数据库会话

        Returns:
            统计信息字典
        """
        # 总数
        total = await session.scalar(select(func.count(Proxy.id)))

        # 按等级统计
        grade_counts = {}
        for grade in ['A', 'B', 'C', 'D']:
            count = await session.scalar(
                select(func.count(Proxy.id)).where(Proxy.grade == grade)
            )
            grade_counts[grade] = count or 0

        # 按协议统计
        protocol_counts = {}
        for protocol in ['http', 'https', 'socks5']:
            count = await session.scalar(
                select(func.count(Proxy.id)).where(Proxy.protocol == protocol)
            )
            protocol_counts[protocol] = count or 0

        # 平均评分
        avg_score = await session.scalar(
            select(func.avg(Proxy.scan_score)).where(Proxy.scan_score > 0)
        )

        return {
            'total': total or 0,
            'grade_a': grade_counts.get('A', 0),
            'grade_b': grade_counts.get('B', 0),
            'grade_c': grade_counts.get('C', 0),
            'grade_d': grade_counts.get('D', 0),
            'http': protocol_counts.get('http', 0),
            'https': protocol_counts.get('https', 0),
            'socks5': protocol_counts.get('socks5', 0),
            'avg_score': round(avg_score or 0, 1),
        }

    async def get_available_count(self, session: AsyncSession) -> int:
        """获取可用代理数量（排除 D 级）"""
        stmt = select(func.count(Proxy.id)).where(Proxy.grade != 'D')
        result = await session.scalar(stmt)
        return result or 0