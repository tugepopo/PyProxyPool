"""
PyProxyPool — GitHub 免费代理源采集器 (异步化)

从 GitHub 上托管的免费代理列表仓库中采集代理
"""
import asyncio
import re
import random
import logging
from typing import List, Dict
from urllib.parse import urlparse

import aiohttp

from models import ProxyIP
from config import get_settings

logger = logging.getLogger(__name__)


class GitHubSourceCrawler:
    """GitHub 免费代理源采集器（异步版）"""

    def __init__(self):
        settings = get_settings()
        self.timeout = aiohttp.ClientTimeout(total=settings.REQUEST_TIMEOUT)
        self._session: aiohttp.ClientSession = None

    async def __aenter__(self):
        self._session = aiohttp.ClientSession(timeout=self.timeout)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self._session:
            await self._session.close()

    async def crawl_source(self, source: dict) -> List[ProxyIP]:
        """
        采集单个 GitHub 代理源（异步版）

        Args:
            source: 源配置字典

        Returns:
            ProxyIP 列表
        """
        settings = get_settings()
        name = source.get('name', 'unknown')
        proxies = []
        session = None

        try:
            async with aiohttp.ClientSession(
                headers={'User-Agent': random.choice(settings.USER_AGENTS)},
                timeout=self.timeout,
            ) as client:
                session = client
                for url in source.get('urls', []):
                    try:
                        async with session.get(url, timeout=self.timeout) as resp:
                            if resp.status != 200:
                                continue
                            text = await resp.text()
                            if not text:
                                continue
                            proxies.extend(self._parse_raw_text(text, source))

                        await asyncio.sleep(random.uniform(0.5, 1.5))
                    except Exception as e:
                        logger.error(f'Crawl {name} url={url} error: {e}')
                        continue

        except Exception as e:
            logger.error(f'GitHubSourceCrawler failed for {name}: {e}')

        logger.info(f'[{name}] crawled {len(proxies)} proxies from GitHub')
        return proxies

    def _parse_raw_text(self, text: str, source: dict) -> List[ProxyIP]:
        """
        解析 proxy list 纯文本格式

        Args:
            text: 原始文本
            source: 源配置

        Returns:
            ProxyIP 列表
        """
        proxies = []
        settings = get_settings()

        for line in text.strip().split('\n'):
            line = line.strip()
            if not line or line.startswith('#'):
                continue

            # 格式1+2: protocol://[user:pass@]ip:port
            m = re.match(r'^(https?|socks[45])://([^@/:]+)(?:@)?(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}):(\d+)$', line)
            if m:
                protocol = m.group(1)
                auth_part = m.group(2)
                ip = m.group(3)
                port = m.group(4)
                username, password = self._parse_auth(auth_part)

                proxies.append(ProxyIP(
                    ip=ip,
                    port=int(port),
                    protocol=protocol,
                    username=username,
                    password=password,
                    source=source.get('name', ''),
                    score=settings.INITIAL_SCORE,
                    last_verified=0,
                ))
                continue

            # 格式3: ip:port
            m = re.match(r'^(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}):(\d+)$', line)
            if m:
                proxies.append(ProxyIP(
                    ip=m.group(1),
                    port=int(m.group(2)),
                    protocol='http',
                    source=source.get('name', ''),
                    score=settings.INITIAL_SCORE,
                    last_verified=0,
                ))

        return proxies

    @staticmethod
    def _parse_auth(auth_part: str) -> tuple:
        """解析认证信息"""
        if ':' in auth_part:
            parts = auth_part.split(':', 1)
            return parts[0], parts[1]
        return '', ''