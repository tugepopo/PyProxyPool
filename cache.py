"""
PyProxyPool — Redis 异步缓存封装

提供 Redis async 连接管理和通用缓存操作
"""
import logging
from typing import Any, Optional, Union

import redis.asyncio as redis

from config import get_settings

logger = logging.getLogger(__name__)

_redis_client: Optional[redis.Redis] = None


def get_redis() -> redis.Redis:
    """
    获取 Redis 异步客户端单例

    Returns:
        Redis async client instance
    """
    global _redis_client
    if _redis_client is None:
        settings = get_settings()
        try:
            _redis_client = redis.from_url(
                settings.REDIS_URL,
                encoding='utf-8',
                decode_responses=True,
            )
            logger.info('Redis client initialized')
        except Exception as e:
            logger.error(f'Failed to connect to Redis ({settings.REDIS_URL}): {e}')
            raise
    return _redis_client


async def close_redis() -> None:
    """关闭 Redis 连接"""
    global _redis_client
    if _redis_client is not None:
        await _redis_client.close()
        _redis_client = None
        logger.info('Redis connection closed')


async def cache_get(key: str) -> Optional[str]:
    """
    从 Redis 获取缓存值

    Args:
        key: 缓存键

    Returns:
        缓存值（字符串），不存在返回 None
    """
    try:
        client = get_redis()
        return await client.get(key)
    except Exception as e:
        logger.debug(f'Redis cache_get failed for key={key}: {e}')
        return None


async def cache_set(key: str, value: Union[str, bytes], ttl: int = None) -> bool:
    """
    设置 Redis 缓存值

    Args:
        key: 缓存键
        value: 缓存值
        ttl: 过期时间（秒），默认使用配置中的 REDIS_CACHE_TTL

    Returns:
        是否设置成功
    """
    try:
        client = get_redis()
        settings = get_settings()
        timeout = ttl or settings.REDIS_CACHE_TTL
        if isinstance(value, str):
            await client.setex(key, timeout, value)
        else:
            await client.setex(key, timeout, value.decode('utf-8'))
        return True
    except Exception as e:
        logger.debug(f'Redis cache_set failed for key={key}: {e}')
        return False


async def cache_delete(key: str) -> bool:
    """
    删除 Redis 缓存键

    Args:
        key: 缓存键

    Returns:
        是否删除成功
    """
    try:
        client = get_redis()
        await client.delete(key)
        return True
    except Exception as e:
        logger.debug(f'Redis cache_delete failed for key={key}: {e}')
        return False


async def cache_exists(key: str) -> bool:
    """检查键是否存在"""
    try:
        client = get_redis()
        return await client.exists(key) > 0
    except Exception as e:
        logger.debug(f'Redis cache_exists failed for key={key}: {e}')
        return False


async def cache_set_hash(key: str, field: str, value: str, ttl: int = None) -> bool:
    """
    设置 Redis Hash 字段

    Args:
        key: Hash 键
        field: 字段名
        value: 字段值
        ttl: 过期时间（秒）

    Returns:
        是否设置成功
    """
    try:
        client = get_redis()
        settings = get_settings()
        await client.hset(key, field, value)
        if ttl:
            await client.expire(key, ttl)
        return True
    except Exception as e:
        logger.debug(f'Redis cache_set_hash failed for key={key}: {e}')
        return False


async def cache_get_hash(key: str, field: str) -> Optional[str]:
    """获取 Hash 字段值"""
    try:
        client = get_redis()
        return await client.hget(key, field)
    except Exception as e:
        logger.debug(f'Reris cache_get_hash failed for key={key}: {e}')
        return None


async def cache_increment(key: str, amount: int = 1) -> int:
    """
    自增 Redis 键的值

    Args:
        key: 键名
        amount: 增量（默认1）

    Returns:
        自增后的值
    """
    try:
        client = get_redis()
        return await client.incrby(key, amount)
    except Exception as e:
        logger.debug(f'Redis cache_increment failed for key={key}: {e}')
        return 0