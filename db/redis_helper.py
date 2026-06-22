"""
Redis 数据库实现 - 高速缓存方案
"""
import json
import time
import random
import logging
from typing import List

logger = logging.getLogger('db.redis')


class RedisHelper:
    """Redis实现 - 适合高并发读取场景"""

    def __init__(self, config: dict):
        self.config = config
        self.redis = None
        KEY_PREFIX = 'proxypool'
        self.KEY_ALL = f'{KEY_PREFIX}:all'           # Hash: ip:port → proxy_json
        self.KEY_BY_PROTOCOL = f'{KEY_PREFIX}:protocol'  # Hash: protocol → Set key name

    def init_db(self):
        try:
            import redis
            self.redis = redis.Redis(
                host=self.config['host'],
                port=self.config['port'],
                db=self.config.get('db', 0),
                password=self.config.get('password'),
                decode_responses=True,
            )
            self.redis.ping()
            logger.info('Redis initialized')
        except ImportError:
            logger.error('Redis requires: pip install redis')
            raise

    def _proxy_key(self, proxy) -> str:
        return f'{proxy.ip}:{proxy.port}'

    def insert(self, proxy) -> bool:
        try:
            key = self._proxy_key(proxy)
            data = json.dumps(proxy.to_dict())
            pipe = self.redis.pipeline()
            pipe.hset(self.KEY_ALL, key, data)
            pipe.sadd(f'{self.KEY_BY_PROTOCOL}:{proxy.protocol}', key)
            pipe.execute()
            return True
        except Exception as e:
            logger.error(f'Redis insert failed: {e}')
            return False

    def batch_insert(self, proxies) -> int:
        try:
            pipe = self.redis.pipeline()
            for p in proxies:
                key = self._proxy_key(p)
                data = json.dumps(p.to_dict())
                pipe.hset(self.KEY_ALL, key, data)
                pipe.sadd(f'{self.KEY_BY_PROTOCOL}:{p.protocol}', key)
            pipe.execute()
            return len(proxies)
        except Exception as e:
            logger.error(f'Redis batch insert failed: {e}')
            return 0

    def _get_from_hash(self, key: str):
        data = self.redis.hget(self.KEY_ALL, key)
        if data:
            from models import ProxyIP
            return ProxyIP.from_dict(json.loads(data))
        return None

    def get_all(self) -> list:
        from models import ProxyIP
        all_data = self.redis.hgetall(self.KEY_ALL)
        proxies = []
        for data in all_data.values():
            try:
                proxies.append(ProxyIP.from_dict(json.loads(data)))
            except Exception:
                pass
        proxies.sort(key=lambda p: (-p.score, p.speed))
        return proxies

    def get_by_protocol(self, protocol: str) -> list:
        from models import ProxyIP
        keys = self.redis.smembers(f'{self.KEY_BY_PROTOCOL}:{protocol}')
        proxies = []
        for key in keys:
            data = self.redis.hget(self.KEY_ALL, key)
            if data:
                try:
                    proxies.append(ProxyIP.from_dict(json.loads(data)))
                except Exception:
                    pass
        proxies.sort(key=lambda p: (-p.score, p.speed))
        return proxies

    def get_random(self, count=1, protocol=None, anonymity=None, min_score=0) -> list:
        if protocol:
            keys = list(self.redis.smembers(f'{self.KEY_BY_PROTOCOL}:{protocol}'))
        else:
            keys = list(self.redis.hkeys(self.KEY_ALL))

        if not keys:
            return []

        random.shuffle(keys)
        from models import ProxyIP
        result = []
        for key in keys:
            if len(result) >= count:
                break
            data = self.redis.hget(self.KEY_ALL, key)
            if data:
                try:
                    p = ProxyIP.from_dict(json.loads(data))
                    if p.score >= min_score:
                        if anonymity is None or p.anonymity == anonymity:
                            result.append(p)
                except Exception:
                    pass
        return result

    def delete(self, ip, port=None) -> int:
        if port:
            key = f'{ip}:{port}'
            data = self.redis.hget(self.KEY_ALL, key)
            if data:
                p = json.loads(data)
                pipe = self.redis.pipeline()
                pipe.hdel(self.KEY_ALL, key)
                pipe.srem(f'{self.KEY_BY_PROTOCOL}:{p.get("protocol", "http")}', key)
                pipe.execute()
                return 1
            return 0
        else:
            # 删除该IP的所有端口
            all_keys = self.redis.hkeys(self.KEY_ALL)
            to_delete = [k for k in all_keys if k.startswith(f'{ip}:')]
            if to_delete:
                pipe = self.redis.pipeline()
                for key in to_delete:
                    data = self.redis.hget(self.KEY_ALL, key)
                    if data:
                        p = json.loads(data)
                        pipe.srem(f'{self.KEY_BY_PROTOCOL}:{p.get("protocol", "http")}', key)
                    pipe.hdel(self.KEY_ALL, key)
                pipe.execute()
            return len(to_delete)

    def delete_by_score(self, min_score) -> int:
        from models import ProxyIP
        all_data = self.redis.hgetall(self.KEY_ALL)
        count = 0
        pipe = self.redis.pipeline()
        for key, data in all_data.items():
            try:
                p = ProxyIP.from_dict(json.loads(data))
                if p.score < min_score:
                    pipe.hdel(self.KEY_ALL, key)
                    pipe.srem(f'{self.KEY_BY_PROTOCOL}:{p.protocol}', key)
                    count += 1
            except Exception:
                pass
        pipe.execute()
        return count

    def update_score(self, ip, port, score):
        key = f'{ip}:{port}'
        data = self.redis.hget(self.KEY_ALL, key)
        if data:
            p = json.loads(data)
            p['score'] = score
            self.redis.hset(self.KEY_ALL, key, json.dumps(p))

    def update_speed(self, ip, port, speed):
        key = f'{ip}:{port}'
        data = self.redis.hget(self.KEY_ALL, key)
        if data:
            p = json.loads(data)
            p['speed'] = speed
            self.redis.hset(self.KEY_ALL, key, json.dumps(p))

    def count(self) -> int:
        return self.redis.hlen(self.KEY_ALL)

    def exists(self, ip, port) -> bool:
        return self.redis.hexists(self.KEY_ALL, f'{ip}:{port}')

    def close(self):
        if self.redis:
            self.redis.close()
