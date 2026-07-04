"""
PyProxyPool — IP 风险评估服务

集成 AbuseIPDB API 和 ping0 数据，对代理 IP 进行风险评估
"""
import json
import logging
import asyncio
from typing import Optional, Dict, Any

import aiohttp

from config import get_settings
from cache import cache_get, cache_set

logger = logging.getLogger(__name__)

ABUSEIPDB_CACHE_PREFIX = 'abuseipdb:'
IP_TYPE_CACHE_PREFIX = 'iptype:'


class RiskAnalyzer:
    """
    IP 风险评估服务
    调用 AbuseIPDB API，根据 ASN/ISP 分类 IP 类型
    """

    # IP 类型分类关键词
    IP_TYPE_KEYWORDS = {
        'residential': ['residential', 'residence', 'home', '住宅'],
        'datacenter_clean': ['datacenter', 'idc', 'hosting'],
        'datacenter': ['datacenter', 'idc', 'hosting', 'network'],
        'proxy': ['proxy', 'proxies'],
        'vpn': ['vpn', 'virtual', 'tunnel'],
        'tor': ['tor', 'torproject', 'exit'],
        'malicious': ['malicious', 'botnet', 'spam', 'hacking'],
    }

    def __init__(self, abuseipdb_api_key: str = None):
        settings = get_settings()
        self.abuseipdb_api_key = abuseipdb_api_key or settings.ABUSEIPDB_API_KEY
        self.timeout = aiohttp.ClientTimeout(total=10)
        self._session: aiohttp.ClientSession = None

    async def __aenter__(self):
        self._session = aiohttp.ClientSession(timeout=self.timeout)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self._session:
            await self._session.close()

    async def analyze(self, proxy, geo_result: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        综合风险评估

        Args:
            proxy: Proxy 对象
            geo_result: 地理分析结果

        Returns:
            风险评估字典
        """
        result = {
            'ip': getattr(proxy, 'ip', ''),
            'abuse_confidence': getattr(proxy, 'abuse_confidence', 0),
            'ip_type': getattr(proxy, 'ip_type', ''),
            'risk_score': getattr(proxy, 'risk_score', 0),
            'isp': getattr(proxy, 'isp', ''),
            'asn': getattr(proxy, 'asn', ''),
        }

        # 查询 AbuseIPDB
        abuse_score = await self.check_abuse_ipdb(getattr(proxy, 'ip', ''))
        if abuse_score is not None:
            result['abuse_confidence'] = abuse_score
            proxy.abuse_confidence = abuse_score

        # 根据 ASN/ISP 分类 IP 类型
        ip_type = self.classify_ip_type(proxy)
        if ip_type:
            result['ip_type'] = ip_type
            proxy.ip_type = ip_type

        # 基于纯真/ASN 数据设置纯净度分类
        if not getattr(proxy, 'purity_class', ''):
            proxy.purity_class = self._map_ip_type_to_purity(ip_type)

        return result

    async def check_abuse_ipdb(self, ip: str) -> Optional[int]:
        """
        调用 AbuseIPDB API 查询 IP 滥用评分

        Args:
            ip: IP 地址

        Returns:
            滥用置信度评分 (0-100)，失败返回 None
        """
        if not self.abuseipdb_api_key:
            return None

        # 检查缓存
        cache_key = f'{ABUSEIPDB_CACHE_PREFIX}{ip}'
        cached = await cache_get(cache_key)
        if cached:
            try:
                return int(cached)
            except (ValueError, TypeError):
                pass

        try:
            if not self._session:
                self._session = aiohttp.ClientSession(timeout=self.timeout)

            url = 'https://api.abuseipdb.com/api/v2/check'
            async with self._session.post(
                url,
                headers={
                    'Key': self.abuseipdb_api_key,
                    'Accept': 'application/json',
                },
                params={'ipAddress': ip},
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    confidence = data.get('data', {}).get('abuseConfidenceScore', 0)
                    # 写入缓存（TTL=24h）
                    await cache_set(cache_key, str(confidence), ttl=86400)
                    return confidence
        except Exception as e:
            logger.debug(f'AbuseIPDB API failed for {ip}: {e}')

        return None

    def classify_ip_type(self, proxy) -> str:
        """
        根据 ASN/ISP/Org 信息分类 IP 类型

        Args:
            proxy: Proxy 对象

        Returns:
            IP 类型字符串
        """
        # 优先使用已设置的 ip_type
        ip_type = getattr(proxy, 'ip_type', '')
        if ip_type:
            return ip_type

        # 从纯真/ASN 数据推断
        if getattr(proxy, 'is_native', False):
            return 'residential'
        if getattr(proxy, 'is_proxy', False):
            return 'proxy'
        if getattr(proxy, 'is_vpn', False):
            return 'vpn'
        if getattr(proxy, 'is_tor', False):
            return 'tor'
        if getattr(proxy, 'is_datacenter', False):
            return 'datacenter'

        # 基于 ISP/Org 名称关键词匹配
        isp = getattr(proxy, 'isp', '').lower()
        asn_owner = getattr(proxy, 'asn_owner', '').lower()
        org_name = getattr(proxy, 'org_name', '').lower()
        combined = f'{isp} {asn_owner} {org_name}'

        # 按优先级顺序匹配
        priority_order = ['tor', 'malicious', 'vpn', 'proxy', 'residential', 'datacenter_clean', 'datacenter']
        for ip_type_name in priority_order:
            keywords = self.IP_TYPE_KEYWORDS.get(ip_type_name, [])
            for kw in keywords:
                if kw in combined:
                    return ip_type_name

        # 默认数据中心
        return 'datacenter'

    def _map_ip_type_to_purity(self, ip_type: str) -> str:
        """
        将 IP 类型映射为纯净度分类

        Args:
            ip_type: IP 类型字符串

        Returns:
            纯净度分类字符串
        """
        mapping = {
            'residential': 'residential',
            'datacenter_clean': 'datacenter_clean',
            'datacenter': 'datacenter',
            'proxy': 'proxy',
            'vpn': 'vpn',
            'tor': 'tor',
            'malicious': 'malicious',
        }
        return mapping.get(ip_type, 'datacenter')