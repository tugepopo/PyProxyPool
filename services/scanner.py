"""
PyProxyPool — 异步代理扫描服务

使用 aiohttp + Semaphore 实现真正异步并发存活检测
支持协议识别（HTTP CONNECT vs SOCKS5）
记录 latency, outlet_ip, country, isp, asn
"""
import asyncio
import json
import logging
import time
from datetime import datetime
from typing import Optional, List, Dict, Any

import aiohttp
from aiohttp import ClientTimeout

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models import Proxy
from config import get_settings
from utils.proxy_parser import parse_proxy

logger = logging.getLogger(__name__)


class ProxyScanner:
    """
    异步代理扫描服务
    使用 aiohttp + asyncio.Semaphore 实现高并发存活检测
    """

    VERIFY_URLS = [
        'http://ip.sb',
        'http://httpbin.org/ip',
        'http://api.ipify.org',
    ]

    def __init__(self, timeout: int = None):
        settings = get_settings()
        self.timeout = ClientTimeout(
            total=timeout or settings.VERIFY_TIMEOUT,
            connect=5,
        )
        self.session = None
        logger.info(f'代理验证服务初始化: 超时={self.timeout.total}s, 验证URL={self.VERIFY_URLS}')

    async def __aenter__(self):
        self.session = aiohttp.ClientSession(timeout=self.timeout)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()

    async def validate_batch(
        self,
        proxies: List[Proxy],
        semaphore: asyncio.Semaphore,
    ) -> Dict[str, Any]:
        """
        批量验证代理存活状态

        Args:
            proxies: Proxy 对象列表
            semaphore: 并发控制信号量

        Returns:
            扫描结果字典：{valid, invalid, processed, results}
        """
        logger.info(f'批量验证开始: 共 {len(proxies)} 个代理')
        tasks = []
        for proxy in proxies:
            tasks.append(self.validate_one(proxy, semaphore))

        results = await asyncio.gather(*tasks, return_exceptions=True)

        valid = []
        invalid = []
        scan_results = []

        for i, result in enumerate(results):
            proxy = proxies[i]
            if isinstance(result, Exception):
                invalid.append(proxy)
                scan_results.append({
                    'ip': proxy.ip,
                    'port': proxy.port,
                    'is_valid': False,
                    'error': str(result),
                })
                logger.debug(f'代理验证异常: {proxy.ip}:{proxy.port} — {result}')
                continue

            if result.get('is_valid', False):
                valid.append(proxy)
            else:
                invalid.append(proxy)
            scan_results.append(result)

        logger.info(f'批量验证完成: {len(valid)} 个有效, {len(invalid)} 个无效, 共 {len(proxies)} 个')
        return {
            'valid': valid,
            'invalid': invalid,
            'processed': len(proxies),
            'results': scan_results,
        }

    async def validate_one(
        self,
        proxy: Proxy,
        semaphore: asyncio.Semaphore,
    ) -> Dict[str, Any]:
        """
        验证单个代理存活状态

        通过代理访问验证 URL，检测出口 IP、延迟、协议类型

        Args:
            proxy: Proxy 对象
            semaphore: 并发控制信号量

        Returns:
            扫描结果字典
        """
        result = {
            'ip': proxy.ip,
            'port': proxy.port,
            'protocol': proxy.protocol,
            'is_valid': False,
            'latency_ms': 0.0,
            'outlet_ip': '',
            'country': '',
            'isp': '',
            'asn': '',
            'error': '',
        }

        async with semaphore:
            try:
                start_time = time.time()

                # 构建代理 URL
                proxy_url = self._build_proxy_url(proxy)
                if not proxy_url:
                    result['error'] = 'Invalid proxy format'
                    return result

                # 通过代理访问验证 URL
                for verify_url in self.VERIFY_URLS:
                    try:
                        # 使用代理请求
                        async with self.session.get(
                            verify_url,
                            proxy=proxy_url,
                            headers={
                                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)',
                                'Accept': 'application/json, text/plain, */*',
                            },
                        ) as resp:
                            if resp.status != 200:
                                continue

                            body = await resp.text()
                            elapsed_ms = (time.time() - start_time) * 1000

                            result['is_valid'] = True
                            result['latency_ms'] = round(elapsed_ms, 2)

                            # 提取出口 IP
                            try:
                                data = json.loads(body)
                                result['outlet_ip'] = data.get('ip', data.get('origin', ''))
                            except json.JSONDecodeError:
                                result['outlet_ip'] = body.strip().split('\n')[0] if body else ''

                            # 更新代理对象
                            proxy.speed = result['latency_ms']
                            proxy.outlet_ip = result['outlet_ip']
                            proxy.is_outbound_ip = result['outlet_ip'] != proxy.ip
                            proxy.last_verified = time.time()

                            # 匿名性检测
                            if result['outlet_ip']:
                                if proxy.ip == result['outlet_ip']:
                                    proxy.anonymity = 'transparent'
                                elif result['outlet_ip'] == '':
                                    proxy.anonymity = 'anonymous'
                                else:
                                    proxy.anonymity = 'high'

                            logger.debug(
                                f'代理验证通过: {proxy.ip}:{proxy.port} '
                                f'延迟={result["latency_ms"]:.0f}ms '
                                f'出口IP={result["outlet_ip"]} '
                                f'匿名性={proxy.anonymity} '
                                f'验证URL={verify_url}'
                            )
                            return result

                    except (aiohttp.ClientError, asyncio.TimeoutError, ConnectionError) as e:
                        logger.debug(f'代理 {proxy.ip}:{proxy.port} 请求 {verify_url} 失败: {e}')
                        continue

                result['error'] = '所有验证URL均失败'
                logger.debug(f'代理验证失败: {proxy.ip}:{proxy.port} — {result["error"]}')
                return result

            except Exception as e:
                result['error'] = str(e)
                logger.debug(f'代理验证异常: {proxy.ip}:{proxy.port} — {e}')
                return result

    def _build_proxy_url(self, proxy: Proxy) -> Optional[str]:
        """
        构建代理 URL

        Args:
            proxy: Proxy 对象

        Returns:
            代理 URL 字符串，失败返回 None
        """
        protocol = proxy.protocol
        ip = proxy.ip
        port = proxy.port

        if not ip or not port:
            return None

        # socks5 协议
        if protocol == 'socks5':
            if proxy.username:
                return f'socks5://{proxy.username}:{proxy.password}@{ip}:{port}'
            return f'socks5://{ip}:{port}'

        # http/https 协议
        base_url = f'http://{ip}:{port}'
        if proxy.username:
            base_url = f'http://{proxy.username}:{proxy.password}@{ip}:{port}'
        return base_url