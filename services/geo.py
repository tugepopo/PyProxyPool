"""
PyProxyPool — 出口 IP 地理分析服务

通过代理获取出口 IP，查询 ip-api.com 获取地理位置
Redis 缓存 TTL=1h
本地 GeoIP 数据库支持（GeoIPReader 封装 geoip2）
三层降级：Redis → 本地 GeoIP → 在线 API
"""
import json
import logging
import os
import asyncio
from datetime import datetime
from typing import Optional, Dict, Any

import aiohttp
import geoip2.database
import geoip2.errors

from config import get_settings
from cache import cache_get, cache_set

logger = logging.getLogger(__name__)

# Redis 缓存键前缀
GEO_CACHE_PREFIX = 'geo:'


class GeoIPReader:
    """
    GeoIP 本地数据库管理器
    封装 geoip2.database.Reader，提供统一的查询接口
    不依赖异步，同步 API
    """

    def __init__(self, db_path: str):
        self._db_path = db_path
        self._reader: geoip2.database.Reader | None = None
        self._try_open()

    def _try_open(self) -> None:
        """尝试打开数据库文件，失败则不报错（降级在线 API）"""
        try:
            if os.path.isfile(self._db_path):
                self._reader = geoip2.database.Reader(self._db_path)
                file_size_mb = os.path.getsize(self._db_path) / 1024 / 1024
                logger.info(f'GeoIP database loaded: {self._db_path} ({file_size_mb:.1f} MB)')
            else:
                logger.warning(f'GeoIP database not found: {self._db_path} (will fallback to online API)')
                self._reader = None
        except Exception as e:
            logger.error(f'Failed to open GeoIP database {self._db_path}: {e}')
            self._reader = None

    def lookup(self, ip: str) -> Dict[str, Any]:
        """
        查询 IP 地理位置（同步）

        返回格式与 _normalize_geo() 一致：
        {ip, country, region, city, org, as, timezone, lat, lon}

        org 字段：GeoLite2 City 不含 ISP，固定返回 ''
        """
        if self._reader is None:
            return {}

        try:
            resp = self._reader.city(ip)

            country = resp.country.iso_code if resp.country and resp.country.iso_code else ''

            region = ''
            if resp.subdivisions and resp.subdivisions.most_specific:
                region = resp.subdivisions.most_specific.name or ''

            city_name = resp.city.name if resp.city and resp.city.name else ''

            timezone = resp.location.time_zone if resp.location and resp.location.time_zone else ''
            latitude = str(resp.location.latitude or '') if resp.location else ''
            longitude = str(resp.location.longitude or '') if resp.location else ''

            return {
                'ip': ip,
                'country': country,
                'region': region,
                'city': city_name,
                'org': '',           # GeoLite2 City 不含 ISP
                'as': '',            # GeoLite2 City 不含 ASN 名称
                'timezone': timezone,
                'lat': latitude,
                'lon': longitude,
            }
        except geoip2.errors.AddressNotFoundError:
            return {}
        except Exception as e:
            logger.debug(f'GeoIP lookup failed for {ip}: {e}')
            return {}

    def close(self) -> None:
        """关闭 Reader，释放文件句柄"""
        if self._reader:
            try:
                self._reader.close()
            except Exception as e:
                logger.warning(f'Failed to close GeoIP Reader: {e}')
            finally:
                self._reader = None

    def is_available(self) -> bool:
        """数据库是否可用"""
        return self._reader is not None

    def get_status(self) -> Dict[str, Any]:
        """返回数据库状态信息"""
        status = {
            'source': 'geolite2',
            'path': self._db_path,
            'available': self.is_available(),
            'size_mb': 0.0,
            'mtime': '',
            'mtime_iso': '',
        }

        if os.path.isfile(self._db_path):
            stat = os.stat(self._db_path)
            status['size_mb'] = round(stat.st_size / 1024 / 1024, 1)
            status['mtime'] = stat.st_mtime
            status['mtime_iso'] = datetime.fromtimestamp(stat.st_mtime).isoformat()

        return status


class IPGeoService:
    """
    出口 IP 地理分析服务
    通过代理获取出口 IP，查询免费地理 IP 服务获取详细信息
    支持本地 GeoIP 数据库加速（GeoIPReader）
    三层降级：Redis 缓存 → 本地 GeoIP → 在线 API
    """

    GEO_API_URLS = [
        'http://ip-api.com/json/{ip}',
        'http://ipinfo.io/{ip}/json',
    ]

    def __init__(self, timeout: int = 10, geoip_reader: 'GeoIPReader | None' = None):
        self.timeout = aiohttp.ClientTimeout(total=timeout)
        self._session: aiohttp.ClientSession = None
        self._geoip_reader = geoip_reader  # 从外部注入，支持 hot-reload

    async def __aenter__(self):
        self._session = aiohttp.ClientSession(timeout=self.timeout)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self._session:
            await self._session.close()

    async def lookup_outbound_ip(self, proxy: object) -> Optional[str]:
        """
        通过代理获取出口 IP

        Args:
            proxy: Proxy 对象，需包含 ip, port, protocol 属性

        Returns:
            出口 IP 字符串，失败返回 None
        """
        try:
            # 构建代理 URL
            proxy_url = self._build_proxy_url(proxy)
            if not proxy_url:
                return None

            async with self._session.get(
                'http://ip.sb',
                proxy=proxy_url,
                headers={'User-Agent': 'Mozilla/5.0'},
            ) as resp:
                if resp.status == 200:
                    body = await resp.text()
                    ip = body.strip().split('\n')[0] if body else ''
                    return ip
        except Exception as e:
            logger.debug(f'Failed to lookup outbound IP for {proxy.ip}:{proxy.port}: {e}')

        return None

    async def lookup_geo(self, ip: str) -> Dict[str, Any]:
        """
        查询 IP 地理位置信息（带 Redis 缓存 + 本地 GeoIP 数据库）

        三层降级策略：
        1. Redis 缓存 → 命中则直接返回
        2. 本地 GeoIP 数据库 → 查到则写入缓存并返回
        3. 在线 API → 降级方案，查到则写入缓存并返回
        """
        if not ip:
            return {}

        # Step 1: Redis 缓存
        cache_key = f'{GEO_CACHE_PREFIX}{ip}'
        try:
            cached = await cache_get(cache_key)
            if cached:
                try:
                    return json.loads(cached)
                except json.JSONDecodeError:
                    logger.warning(f'GeoIP cache corrupt for {ip}, will re-query')
        except Exception as e:
            logger.debug(f'Redis cache get failed for {ip}: {e}')

        # Step 2: 本地 GeoIP 数据库
        if self._geoip_reader and self._geoip_reader.is_available():
            geo_data = self._geoip_reader.lookup(ip)
            if geo_data:
                try:
                    await cache_set(cache_key, json.dumps(geo_data, ensure_ascii=False), ttl=3600)
                except Exception as e:
                    logger.debug(f'Redis cache set failed for {ip}: {e}')
                return geo_data

        # Step 3: 降级在线 API
        geo_data = await self._query_geo_api(ip)
        if geo_data:
            try:
                await cache_set(cache_key, json.dumps(geo_data, ensure_ascii=False), ttl=3600)
            except Exception as e:
                logger.debug(f'Redis cache set failed for {ip}: {e}')

        return geo_data or {}

    async def _query_geo_api(self, ip: str) -> Optional[Dict[str, Any]]:
        """
        查询多个地理 IP API（失败自动降级）

        Args:
            ip: IP 地址

        Returns:
            地理位置字典
        """
        for api_url in self.GEO_API_URLS:
            try:
                url = api_url.format(ip=ip)
                async with self._session.get(url, timeout=self.timeout) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        return self._normalize_geo(data, url)
            except Exception as e:
                logger.debug(f'Geo API failed ({url}): {e}')
                continue

        return None

    def _normalize_geo(self, raw: Dict[str, Any], api_url: str) -> Dict[str, Any]:
        """
        统一不同 API 的地理数据格式

        Args:
            raw: API 原始返回数据
            api_url: API URL（用于识别 API 类型）

        Returns:
            标准化的地理数据字典
        """
        if 'ipinfo.io' in api_url:
            # ipinfo.io 格式
            return {
                'ip': raw.get('ip', ''),
                'country': raw.get('country', ''),
                'region': raw.get('region', ''),
                'city': raw.get('city', ''),
                'org': raw.get('org', ''),
                'as': raw.get('org', ''),
                'timezone': raw.get('timezone', ''),
                'lat': raw.get('loc', '').split(',')[0] if raw.get('loc') else '',
                'lon': raw.get('loc', '').split(',')[1] if raw.get('loc') else '',
            }
        else:
            # ip-api.com 格式
            return {
                'ip': raw.get('query', ''),
                'country': raw.get('country', ''),
                'region': raw.get('regionName', ''),
                'city': raw.get('city', ''),
                'org': raw.get('isp', raw.get('org', '')),
                'as': raw.get('isp', ''),
                'timezone': raw.get('timezone', ''),
                'lat': str(raw.get('lat', '')),
                'lon': str(raw.get('lon', '')),
            }

    def _build_proxy_url(self, proxy) -> Optional[str]:
        """构建代理 URL"""
        protocol = getattr(proxy, 'protocol', 'http')
        ip = getattr(proxy, 'ip', '')
        port = getattr(proxy, 'port', 0)

        if not ip or not port:
            return None

        if protocol == 'socks5':
            if getattr(proxy, 'username', ''):
                return f'socks5://{proxy.username}:{proxy.password}@{ip}:{port}'
            return f'socks5://{ip}:{port}'

        base_url = f'http://{ip}:{port}'
        if getattr(proxy, 'username', ''):
            base_url = f'http://{proxy.username}:{proxy.password}@{ip}:{port}'
        return base_url

    async def enrich_proxy_geo(self, proxy) -> bool:
        """
        为单个代理补充地理位置信息

        Args:
            proxy: Proxy 对象

        Returns:
            是否成功补充
        """
        if getattr(proxy, 'country', ''):
            return True

        outbound_ip = getattr(proxy, 'outlet_ip', '')
        if not outbound_ip:
            outbound_ip = await self.lookup_outbound_ip(proxy)
            proxy.outlet_ip = outbound_ip or ''

        if not outbound_ip:
            return False

        geo_data = await self.lookup_geo(outbound_ip)
        if geo_data:
            proxy.country = geo_data.get('country', '')
            proxy.area = geo_data.get('region', '')
            proxy.isp = geo_data.get('org', '')
            return True

        return False

    def reload_geoip_reader(self, db_path: str | None = None) -> bool:
        """热重载 GeoIP 数据库 Reader"""
        try:
            from database import get_geoip_reader
            reader = get_geoip_reader()
            if reader:
                self._geoip_reader = reader
                logger.info('GeoIP reader reloaded successfully')
                return True
            else:
                logger.warning('No GeoIP reader available for reload')
                return False
        except Exception as e:
            logger.error(f'Failed to reload GeoIP reader: {e}')
            return False