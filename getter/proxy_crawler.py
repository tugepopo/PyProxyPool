"""
代理采集器 - 纯标准库实现，无第三方HTML解析依赖
支持 xpath(简化) / regex 两种解析方式
融合了 IPProxyPool 的配置驱动和 proxypool 的容错机制
"""
import re
import time
import random
import logging
from html.parser import HTMLParser
from typing import List, Dict, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

from models import ProxyIP
from config import (
    PROXY_SOURCES, USER_AGENTS, REQUEST_TIMEOUT,
    REQUEST_HEADERS, MAX_RETRY, INITIAL_SCORE
)

logger = logging.getLogger('getter')


# ==================== 简易 HTML 表格解析器 ====================

class _TableParser(HTMLParser):
    """解析 HTML 表格，提取所有行的单元格文本"""

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


class _DivTableParser(HTMLParser):
    """解析用 div+class 模拟的表格（如 data5u 的 ul.l2 结构）"""

    def __init__(self, row_tag='ul', row_class='l2', cell_tag='span'):
        super().__init__()
        self.rows: List[List[str]] = []
        self._current_row: List[str] = []
        self._current_cell: str = ''
        self._in_row = False
        self._in_cell = False
        self._row_tag = row_tag
        self._row_class = row_class
        self._cell_tag = cell_tag

    def handle_starttag(self, tag, attrs):
        attrs_dict = dict(attrs)
        if tag == self._row_tag and attrs_dict.get('class', '') == self._row_class:
            self._in_row = True
            self._current_row = []
        elif tag == self._cell_tag and self._in_row:
            self._in_cell = True
            self._current_cell = ''

    def handle_endtag(self, tag):
        if tag == self._cell_tag and self._in_cell:
            self._in_cell = False
            self._current_row.append(self._current_cell.strip())
        elif tag == self._row_tag and self._in_row:
            self._in_row = False
            if self._current_row:
                self.rows.append(self._current_row)

    def handle_data(self, data):
        if self._in_cell:
            self._current_cell += data


def parse_html_table(html: str) -> List[List[str]]:
    """通用 HTML 表格解析，返回 [[cell, ...], ...]"""
    p = _TableParser()
    try:
        p.feed(html)
    except Exception:
        pass
    return p.rows


# ==================== 采集器 ====================

class ProxyCrawler:
    """代理采集器"""

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update(REQUEST_HEADERS)

    def _random_headers(self) -> dict:
        headers = REQUEST_HEADERS.copy()
        headers['User-Agent'] = random.choice(USER_AGENTS)
        return headers

    def _fetch_page(self, url: str, retry: int = MAX_RETRY) -> str:
        """获取页面内容，带重试"""
        for i in range(retry):
            try:
                resp = self.session.get(
                    url,
                    headers=self._random_headers(),
                    timeout=REQUEST_TIMEOUT,
                    allow_redirects=True,
                )
                resp.raise_for_status()
                if resp.encoding and resp.encoding.lower() == 'iso-8859-1':
                    resp.encoding = resp.apparent_encoding or 'utf-8'
                return resp.text
            except Exception as e:
                logger.warning(f'Fetch {url} attempt {i+1}/{retry} failed: {e}')
                time.sleep(1)
        return ''

    def crawl_source(self, source: dict) -> List[ProxyIP]:
        """采集单个代理源"""
        name = source.get('name', 'unknown')
        source_type = source.get('type', 'xpath')
        proxies = []

        for url in source.get('urls', []):
            try:
                html = self._fetch_page(url)
                if not html:
                    continue

                if source_type in ('xpath', 'table'):
                    proxies.extend(self._parse_table(html, source))
                elif source_type == 'regex':
                    proxies.extend(self._parse_regex(html, source))

                time.sleep(random.uniform(0.5, 1.5))
            except Exception as e:
                logger.error(f'Crawl {name} url={url} error: {e}')
                continue

        logger.info(f'[{name}] crawled {len(proxies)} proxies')
        return proxies

    def _parse_table(self, html: str, source: dict) -> List[ProxyIP]:
        """
        表格解析 — 用标准库解析 HTML table，按列索引提取字段
        config 中 position 的值为列索引(从1开始)，如 './td[1]' → 索引0
        """
        proxies = []
        pos = source.get('position', {})

        # 提取列索引 (从 xpath 表达式 './td[N]' 或 './span[N]' 中提取)
        ip_col = self._col_index(pos.get('ip', ''))
        port_col = self._col_index(pos.get('port', ''))
        type_col = self._col_index(pos.get('type', ''))
        proto_col = self._col_index(pos.get('protocol', ''))

        # 解析表格
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

                # 匿名类型
                anonymity = 'unknown'
                if type_col is not None and type_col < len(cells):
                    type_text = cells[type_col].strip()
                    if '高匿' in type_text or 'high' in type_text.lower():
                        anonymity = 'high'
                    elif '匿名' in type_text or 'anonymous' in type_text.lower():
                        anonymity = 'anonymous'
                    elif '透明' in type_text or 'transparent' in type_text.lower():
                        anonymity = 'transparent'

                # 协议
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
                    score=INITIAL_SCORE,
                    last_verified=0,
                ))
            except Exception:
                continue
        return proxies

    @staticmethod
    def _col_index(xpath_expr: str):
        """从 xpath 表达式提取列索引，如 './td[2]' → 1, './span[3]' → 2"""
        if not xpath_expr:
            return None
        m = re.search(r'\[(\d+)\]', xpath_expr)
        if m:
            return int(m.group(1)) - 1  # xpath 索引从1开始
        return None

    def _parse_regex(self, html: str, source: dict) -> List[ProxyIP]:
        """正则表达式解析"""
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
                        score=INITIAL_SCORE,
                    ))
                except Exception:
                    continue
        except Exception as e:
            logger.error(f'Regex parse error: {e}')
        return proxies

    def crawl_all(self, max_workers: int = 5) -> List[ProxyIP]:
        """并发采集所有代理源"""
        all_proxies = []
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_source = {
                executor.submit(self.crawl_source, src): src
                for src in PROXY_SOURCES
            }
            for future in as_completed(future_to_source):
                source = future_to_source[future]
                try:
                    proxies = future.result()
                    all_proxies.extend(proxies)
                except Exception as e:
                    logger.error(f'Source {source.get("name")} failed: {e}')

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
