"""
PyProxyPool — 代理导入服务

处理代理解析、去重、批量导入数据库
"""
import json
import logging
from typing import Optional, List, Dict, Any

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from models import Proxy
from utils.proxy_parser import parse_proxy, parse_proxy_list
from config import get_settings

logger = logging.getLogger(__name__)


class ProxyImporter:
    """代理导入服务 — 解析 + 去重 + 批量入库"""

    def parse(self, raw: str) -> Optional[Dict[str, Any]]:
        """
        解析单行代理字符串（委托给 proxy_parser）

        Args:
            raw: 原始代理字符串

        Returns:
            解析后的字典，失败返回 None
        """
        return parse_proxy(raw)

    def deduplicate(self, proxies: List[Proxy]) -> List[Proxy]:
        """
        基于 ip:port 去重

        Args:
            proxies: Proxy 对象列表

        Returns:
            去重后的 Proxy 列表（保留第一个出现的）
        """
        seen = set()
        unique = []
        for p in proxies:
            key = f'{p.ip}:{p.port}'
            if key not in seen:
                seen.add(key)
                unique.append(p)
        logger.debug(f'Deduplication: {len(proxies)} → {len(unique)} unique')
        return unique

    async def import_proxies(
        self,
        session: AsyncSession,
        raw_list: List[str],
        source: str = 'manual',
        existing_scan: bool = True,
    ) -> int:
        """
        批量导入代理到数据库

        流程：解析 → 去重 → 检查数据库已有 → 批量插入

        Args:
            session: 异步数据库会话
            raw_list: 原始代理字符串列表
            source: 来源标识
            existing_scan: 是否先检查数据库中已存在的记录

        Returns:
            实际插入的代理数量
        """
        parsed = parse_proxy_list(raw_list)
        if not parsed:
            return 0

        # 构建 Proxy 对象
        settings = get_settings()
        proxies = [
            Proxy(
                ip=item['ip'],
                port=item['port'],
                protocol=item.get('protocol', 'http'),
                username=item.get('username', ''),
                password=item.get('password', ''),
                source=source,
                score=settings.INITIAL_SCORE,
                grade='',
                scan_score=0.0,
            )
            for item in parsed
        ]

        # 去重
        proxies = self.deduplicate(proxies)
        if not proxies:
            return 0

        # 检查数据库中已存在的代理（避免重复插入）
        if existing_scan:
            existing_keys = set()
            addresses = [(p.ip, p.port) for p in proxies]
            if addresses:
                result = await session.execute(
                    select(Proxy.ip, Proxy.port).where(
                        Proxy.ip.in_([p.ip for p in proxies])
                    )
                )
                existing_keys = set(result.all())

            # 过滤掉已存在的
            new_proxies = [
                p for p in proxies
                if (p.ip, p.port) not in existing_keys
            ]
            if not new_proxies:
                logger.info('All proxies already exist in database, skipping import')
                return 0
            proxies = new_proxies

        # 批量插入
        session.add_all(proxies)
        await session.flush()

        inserted = len(proxies)
        logger.info(f'Imported {inserted} proxies from source={source}')
        return inserted

    async def import_from_raw(
        self,
        session: AsyncSession,
        raw_text: str,
        source: str = 'manual',
    ) -> int:
        """
        从多行文本导入代理

        Args:
            session: 异步数据库会话
            raw_text: 多行代理文本
            source: 来源标识

        Returns:
            实际插入的代理数量
        """
        lines = raw_text.strip().split('\n')
        return await self.import_proxies(session, lines, source=source)