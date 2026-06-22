"""
代理验证器 - 优化版
优化点：批量更新评分/速度、采样检查、更好的错误处理
"""
import time
import random
import logging
from typing import List, Tuple, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

from models import ProxyIP
from config import (
    VERIFY_URLS, VERIFY_TIMEOUT, INITIAL_SCORE,
    SCORE_ADD_SUCCESS, SCORE_DEDUCT_FAIL, speed_score,
    USER_AGENTS
)

logger = logging.getLogger('validator')


class ProxyValidator:
    """代理验证器"""

    def __init__(self):
        self.my_ip = self._get_my_ip()
        self._session_pool: dict = {}  # 线程安全的 session 池

    def _get_my_ip(self) -> str:
        """获取本机IP，用于匿名性检测"""
        for url in ['http://httpbin.org/ip', 'http://ip.sb']:
            try:
                resp = requests.get(url, timeout=10)
                if resp.status_code == 200:
                    try:
                        return resp.json().get('origin', '')
                    except Exception:
                        return resp.text.strip()
            except Exception:
                continue
        logger.warning('无法获取本机IP，匿名性检测将跳过')
        return ''

    def _get_session(self) -> requests.Session:
        """获取线程本地 session（连接复用）"""
        tid = id(threading.current_thread()) if 'threading' in dir() else 0
        if tid not in self._session_pool:
            s = requests.Session()
            s.headers.update({'Connection': 'keep-alive'})
            self._session_pool[tid] = s
        return self._session_pool[tid]

    def validate_one(self, proxy: ProxyIP) -> Tuple[bool, ProxyIP]:
        """
        验证单个代理
        返回: (是否有效, 更新后的代理)
        """
        start_time = time.time()
        verify_url = random.choice(VERIFY_URLS)
        try:
            headers = {
                'User-Agent': random.choice(USER_AGENTS),
                'Accept': 'text/html,application/json,*/*',
            }
            proxies = {
                'http': f'http://{proxy.ip}:{proxy.port}',
                'https': f'http://{proxy.ip}:{proxy.port}',
            }

            resp = requests.get(
                verify_url,
                headers=headers,
                proxies=proxies,
                timeout=VERIFY_TIMEOUT,
                allow_redirects=True,
            )

            elapsed_ms = (time.time() - start_time) * 1000

            if resp.status_code == 200:
                # 检测匿名性
                try:
                    body = resp.json()
                    origin_ip = body.get('origin', '')
                except Exception:
                    origin_ip = resp.text.strip()

                if origin_ip and self.my_ip:
                    if proxy.ip in origin_ip or origin_ip in proxy.ip:
                        proxy.anonymity = 'transparent'
                    else:
                        proxy.anonymity = 'high'
                else:
                    proxy.anonymity = 'anonymous'

                # 更新速度
                proxy.speed = round(elapsed_ms, 2)

                # 计算评分
                proxy.score = min(
                    proxy.score + SCORE_ADD_SUCCESS + speed_score(elapsed_ms),
                    100
                )

                proxy.last_verified = time.time()
                logger.debug(f'VALID {proxy} ({elapsed_ms:.0f}ms)')
                return True, proxy
            else:
                proxy.score = max(proxy.score - SCORE_DEDUCT_FAIL, 0)
                logger.debug(f'INVALID {proxy} status={resp.status_code}')
                return False, proxy

        except Exception as e:
            elapsed_ms = (time.time() - start_time) * 1000
            proxy.score = max(proxy.score - SCORE_DEDUCT_FAIL, 0)
            logger.debug(f'FAIL {proxy} error={e} ({elapsed_ms:.0f}ms)')
            return False, proxy

    def validate_batch(self, proxies: List[ProxyIP],
                       max_workers: int = 100) -> Tuple[List[ProxyIP], List[ProxyIP], List[tuple], List[tuple]]:
        """
        并发验证一批代理
        返回: (有效列表, 无效列表, score_updates, speed_updates)
        返回批量更新数据，由调用方统一提交数据库
        """
        valid = []
        invalid = []
        score_updates = []
        speed_updates = []

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_proxy = {
                executor.submit(self.validate_one, p): p
                for p in proxies
            }
            for future in as_completed(future_to_proxy):
                try:
                    is_valid, updated_proxy = future.result()
                    if is_valid:
                        valid.append(updated_proxy)
                        score_updates.append((updated_proxy.ip, updated_proxy.port, updated_proxy.score))
                        speed_updates.append((updated_proxy.ip, updated_proxy.port, updated_proxy.speed))
                    else:
                        invalid.append(updated_proxy)
                        score_updates.append((updated_proxy.ip, updated_proxy.port, updated_proxy.score))
                except Exception as e:
                    proxy = future_to_proxy[future]
                    proxy.score = max(proxy.score - SCORE_DEDUCT_FAIL, 0)
                    invalid.append(proxy)
                    score_updates.append((proxy.ip, proxy.port, proxy.score))

        logger.info(f'Batch validate: {len(valid)} valid / {len(invalid)} invalid out of {len(proxies)}')
        return valid, invalid, score_updates, speed_updates

    def validate_sample(self, proxies: List[ProxyIP],
                        sample_ratio: float = 0.3,
                        max_workers: int = 100) -> Tuple[List[tuple], List[tuple]]:
        """
        采样验证：只检查部分代理，根据结果推断整体质量
        适用于健康检查场景，减少全量验证开销
        返回: (score_updates, speed_updates)
        """
        if not proxies:
            return [], []

        sample_size = max(int(len(proxies) * sample_ratio), 5)
        sample_size = min(sample_size, len(proxies))
        sample = random.sample(proxies, sample_size)

        logger.info(f'Sample validate: {sample_size}/{len(proxies)} proxies')
        _, _, score_updates, speed_updates = self.validate_batch(sample, max_workers=max_workers)

        return score_updates, speed_updates

    def cleanup(self):
        """清理 session 池"""
        self._session_pool.clear()


import threading
