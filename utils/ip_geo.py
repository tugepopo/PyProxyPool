"""
IP 地理位置查询 - 使用 ip-api.com 免费接口
支持批量查询，内置缓存，避免重复请求
"""
import time
import logging
import threading
from typing import List, Dict, Optional

import requests

logger = logging.getLogger('ip_geo')

# ip-api.com 免费接口：每分钟最多 45 次请求
GEO_API_URL = 'http://ip-api.com/batch'
GEO_FIELDS = 'status,country,regionName,city,isp,query'
GEO_LANG = 'zh-CN'

# 内存缓存：ip → {country, region, city, isp}
_geo_cache: Dict[str, dict] = {}
_cache_lock = threading.Lock()
_cache_ttl = 86400  # 缓存 24 小时
_cache_timestamps: Dict[str, float] = {}


def _clean_cache():
    """清理过期缓存"""
    now = time.time()
    expired = [ip for ip, ts in _cache_timestamps.items() if now - ts > _cache_ttl]
    for ip in expired:
        _geo_cache.pop(ip, None)
        _cache_timestamps.pop(ip, None)


def query_batch(ips: List[str]) -> Dict[str, dict]:
    """
    批量查询 IP 地理位置
    返回: {ip: {country, region, city, isp}}
    """
    if not ips:
        return {}

    # 去重 + 过滤已缓存
    unique_ips = list(set(ips))
    result = {}
    to_query = []

    with _cache_lock:
        for ip in unique_ips:
            if ip in _geo_cache and time.time() - _cache_timestamps.get(ip, 0) < _cache_ttl:
                result[ip] = _geo_cache[ip]
            else:
                to_query.append(ip)

    if not to_query:
        return result

    # 分批查询（每批最多 100 个）
    for i in range(0, len(to_query), 100):
        batch = to_query[i:i + 100]
        try:
            resp = requests.post(
                GEO_API_URL,
                json=batch,
                timeout=10,
                params={'lang': GEO_LANG},
            )
            if resp.status_code == 200:
                data = resp.json()
                for item in data:
                    ip = item.get('query', '')
                    if item.get('status') == 'success' and ip:
                        geo = {
                            'country': item.get('country', ''),
                            'region': item.get('regionName', ''),
                            'city': item.get('city', ''),
                            'isp': item.get('isp', ''),
                        }
                        result[ip] = geo
                        with _cache_lock:
                            _geo_cache[ip] = geo
                            _cache_timestamps[ip] = time.time()
            else:
                logger.warning(f'Geo API returned {resp.status_code}')
        except Exception as e:
            logger.warning(f'Geo batch query failed: {e}')

        # 限流：每批间隔 1.5 秒
        if i + 100 < len(to_query):
            time.sleep(1.5)

    # 定期清理缓存
    with _cache_lock:
        if len(_geo_cache) > 5000:
            _clean_cache()

    return result


def query_single(ip: str) -> Optional[dict]:
    """查询单个 IP"""
    result = query_batch([ip])
    return result.get(ip)


def format_location(geo: dict) -> str:
    """格式化地理位置为简短字符串"""
    if not geo:
        return ''
    parts = []
    if geo.get('country'):
        parts.append(geo['country'])
    if geo.get('region') and geo['region'] != geo.get('country'):
        parts.append(geo['region'])
    if geo.get('city') and geo['city'] != geo.get('region'):
        parts.append(geo['city'])
    return ' / '.join(parts) if parts else ''


def enrich_proxies(proxies) -> None:
    """
    批量为代理对象添加地理位置信息（原地修改）
    """
    if not proxies:
        return

    ips = [p.ip for p in proxies]
    geo_data = query_batch(ips)

    for p in proxies:
        geo = geo_data.get(p.ip)
        if geo:
            p.country = format_location(geo)
            if geo.get('isp'):
                # 用 area 字段存 ISP 信息
                p.area = geo['isp']
