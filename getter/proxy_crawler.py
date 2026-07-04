"""
PyProxyPool — 代理采集器 (异步化)

支持 aiohttp 异步采集，兼容原格式
"""
import asyncio
import re
import random
import logging
from html.parser import HTMLParser
from typing import List, Dict, Tuple, Optional

import aiohttp

from models import ProxyIP
from config import get_settings

logger = logging.getLogger(__name__)


class _TableParser(HTMLParser):
    """解析 HTML 表格"""

    def __init__(self):
        super().__init__()
        self.rows: List[List[str]] = []
        self._current_row: List[str] = []
        self._current_cell: str = ''
        self._in_td = False
        self._in_script = False

    def handle_starttag(self, tag, attrs):
        if tag in ('td', 'th'):
            self._in_td = True
            self._current_cell = ''
        elif tag == 'tr':
            self._current_row = []
        elif tag == 'script':
            self._in_script = True

    def handle_endtag(self, tag):
        if tag in ('td', 'th'):
            self._in_td = False
            self._current_row.append(self._current_cell.strip())
        elif tag == 'tr':
            if self._current_row:
                self.rows.append(self._current_row)
        elif tag == 'script':
            self._in_script = False

    def handle_data(self, data):
        if self._in_td and not self._in_script:
            self._current_cell += data


def parse_html_table(html: str) -> List[List[str]]:
    """通用 HTML 表格解析"""
    p = _TableParser()
    try:
        p.feed(html)
    except Exception:
        pass
    return p.rows


class ProxyCrawler:
    """代理采集器（异步版）"""

    def __init__(self):
        settings = get_settings()
        self.timeout = aiohttp.ClientTimeout(total=settings.REQUEST_TIMEOUT)
        self.source_failures = {}

    async def _fetch_page_async(self, url: str, retry: int = 2) -> str:
        """异步获取页面内容"""
        settings = get_settings()
        for i in range(retry):
            try:
                async with aiohttp.ClientSession(
                    headers={'User-Agent': random.choice(settings.USER_AGENTS)},
                    timeout=self.timeout,
                ) as session:
                    async with session.get(url, timeout=self.timeout, ssl=False) as resp:
                        resp.raise_for_status()
                        text = await resp.text()
                        if text:
                            return text
            except Exception as e:
                logger.warning(f'Fetch {url} attempt {i+1}/{retry} failed: {e}')
                await asyncio.sleep(1)
        return ''

    async def crawl_source_async(self, source: dict) -> List[ProxyIP]:
        """异步采集单个代理源"""
        settings = get_settings()
        name = source.get('name', 'unknown')
        source_type = source.get('type', 'xpath')
        proxies = []

        if source_type == 'github':
            from getter.github_sources import GitHubSourceCrawler
            gh_crawler = GitHubSourceCrawler()
            result = await gh_crawler.crawl_source(source)
            if result:
                self.source_failures[name] = 0
            else:
                self.source_failures[name] = self.source_failures.get(name, 0) + 1
            return result

        for url in source.get('urls', []):
            try:
                html = await self._fetch_page_async(url)
                if not html:
                    continue

                if source_type in ('xpath', 'table'):
                    proxies.extend(self._parse_table(html, source))
                elif source_type == 'regex':
                    proxies.extend(self._parse_regex(html, source))

                await asyncio.sleep(random.uniform(0.5, 1.5))
            except Exception as e:
                logger.error(f'Crawl {name} url={url} error: {e}')
                continue

        if proxies:
            self.source_failures[name] = 0
        else:
            self.source_failures[name] = self.source_failures.get(name, 0) + 1

        logger.info(f'[{name}] crawled {len(proxies)} proxies')
        return proxies

    def _parse_table(self, html: str, source: dict) -> List[ProxyIP]:
        """表格解析"""
        settings = get_settings()
        proxies = []
        pos = source.get('position', {})

        ip_col = self._col_index(pos.get('ip', ''))
        port_col = self._col_index(pos.get('port', ''))
        type_col = self._col_index(pos.get('type', ''))
        proto_col = self._col_index(pos.get('protocol', ''))

        rows = parse_html_table(html)

        for cells in rows:
            try:
                if ip_col is None or port_col is None:
                    continue
                if max(ip_col, port_col) >= len(cells):
                    continue

                ip = cells[ip_col].strip()
                port = cells[port_col].strip()

                if not re.match(r'^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$', ip):
                    continue
                if not port.isdigit():
                    continue

                anonymity = 'unknown'
                if type_col is not None and type_col < len(cells):
                    type_text = cells[type_col].strip()
                    if '高匿' in type_text or 'high' in type_text.lower():
                        anonymity = 'high'
                    elif '匿名' in type_text or 'anonymous' in type_text.lower():
                        anonymity = 'anonymous'
                    elif '透明' in type_text or 'transparent' in type_text.lower():
                        anonymity = 'transparent'

                protocol = 'http'
                if proto_col is not None and proto_col < len(cells):
                    proto_text = cells[proto_col].strip().lower()
                    if 'https' in proto_text or 'ssl' in proto_text:
                        protocol = 'https'

                proxies.append(ProxyIP(
                    ip=ip,
                    port=int(port),
                    protocol=protocol,
                    anonymity=anonymity,
                    source=source.get('name', ''),
                    score=settings.INITIAL_SCORE,
                    last_verified=0,
                ))
            except Exception:
                continue
        return proxies

    @staticmethod
    def _col_index(xpath_expr: str):
        """从 xpath 提取列索引"""
        if not xpath_expr:
            return None
        m = re.search(r'\[(\d+)\]', xpath_expr)
        if m:
            return int(m.group(1)) - 1
        return None

    def _parse_regex(self, html: str, source: dict) -> List[ProxyIP]:
        """正则表达式解析"""
        settings = get_settings()
        proxies = []
        try:
            pattern = source.get('pattern', '')
            pos = source.get('position', {})
            matches = re.findall(pattern, html, re.S)

            for match in matches:
                try:
                    if isinstance(match, tuple):
                        ip_idx = pos.get('ip', 0)
                        port_idx = pos.get('port', 1)
                        ip = match[ip_idx].strip()
                        port = match[port_idx].strip()
                    else:
                        continue

                    if not re.match(r'^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$', ip):
                        continue
                    if not port.isdigit():
                        continue

                    proxies.append(ProxyIP(
                        ip=ip,
                        port=int(port),
                        source=source.get('name', ''),
                        score=settings.INITIAL_SCORE,
                    ))
                except Exception:
                    continue
        except Exception as e:
            logger.error(f'Regex parse error: {e}')
        return proxies

    async def crawl_all_async(
        self,
        max_workers: int = 5,
        on_progress: callable = None,
    ) -> List[ProxyIP]:
        """异步并发采集所有代理源

        Args:
            max_workers: 最大并发数
            on_progress: 进度回调 (completed_sources, total_sources, proxies_found)
        """
        settings = get_settings()
        DEGRADED_THRESHOLD = 3

        active_sources = []
        for src in settings.PROXY_SOURCES:
            name = src.get('name', 'unknown')
            failures = self.source_failures.get(name, 0)
            if failures >= DEGRADED_THRESHOLD:
                logger.warning(f'Source {name} degraded, skipping')
                continue
            active_sources.append(src)

        if not active_sources:
            logger.warning('All sources degraded, forcing re-check')
            active_sources = settings.PROXY_SOURCES

        total_sources = len(active_sources)
        all_proxies = []
        tasks = [self.crawl_source_async(src) for src in active_sources]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        completed = 0
        for i, result in enumerate(results):
            completed += 1
            if isinstance(result, Exception):
                logger.error(f'Source {active_sources[i].get("name")} failed: {result}')
                if on_progress:
                    on_progress(completed, total_sources, len(all_proxies))
                continue
            all_proxies.extend(result)
            if on_progress:
                on_progress(completed, total_sources, len(all_proxies))

        # 去重
        seen = set()
        unique = []
        for p in all_proxies:
            key = f'{p.ip}:{p.port}'
            if key not in seen:
                seen.add(key)
                unique.append(p)

        logger.info(f'Total crawled: {len(all_proxies)}, unique: {len(unique)}')
        return unique

    # 兼容旧接口（同步版本保留供非异步场景使用）
    def crawl_all(self, max_workers: int = 5) -> List[ProxyIP]:
        """同步采集接口（兼容旧代码）"""
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            # 无事件循环，直接 run
            return asyncio.run(self.crawl_all_async(max_workers))
        else:
            # 已在事件循环中，在线程中执行
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(asyncio.run, self.crawl_all_async(max_workers))
                return future.result()