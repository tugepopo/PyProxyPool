"""
PyProxyPool — API 鉴权中间件

X-API-Key SHA256 鉴权
兼容原 API_KEY 明文校验
"""
import hashlib
import logging
from typing import Optional

from fastapi import Request, HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from config import get_settings

logger = logging.getLogger(__name__)

# Bearer Token 安全方案
security = HTTPBearer()


async def verify_token(key: str) -> bool:
    """
    验证 API Key（SHA256 哈希匹配）

    逻辑：
    1. 如果配置的 API_KEY 为空，跳过鉴权
    2. 支持两种格式：
       - 明文密钥直接匹配（兼容旧配置）
       - SHA256 哈希匹配（更安全）

    Args:
        key: 请求提供的 API Key

    Returns:
        验证是否通过
    """
    settings = get_settings()
    configured_key = settings.API_KEY

    # 空密钥 = 不鉴权
    if not configured_key:
        logger.debug('API Key 未配置，跳过鉴权')
        return True

    # 明文匹配（兼容旧配置）
    if key == configured_key:
        return True

    # SHA256 哈希匹配（更安全）
    # 配置项形如 "sha256:hash_value"
    if configured_key.startswith('sha256:'):
        stored_hash = configured_key[7:]  # 去掉 "sha256:" 前缀
        computed_hash = hashlib.sha256(key.encode('utf-8')).hexdigest()
        return computed_hash == stored_hash

    return False


async def authenticate(request: Request) -> str:
    """
    FastAPI 依赖注入函数 — 用于路由鉴权

    从请求头或查询参数中提取 API Key 并验证

    Args:
        request: FastAPI 请求对象

    Returns:
        验证通过的 API Key 值

    Raises:
        HTTPException: 401 未授权
    """
    # 优先从 X-API-Key 请求头读取
    api_key = request.headers.get('X-API-Key', '')

    # 备选：从 api_key 查询参数读取
    if not api_key:
        api_key = request.query_params.get('api_key', '')

    # 备选：从 Authorization Bearer Token 读取
    if not api_key:
        try:
            creds = await security(request)
            api_key = creds.credentials
        except Exception:
            pass

    if not api_key:
        logger.warning(f'鉴权失败（缺少 API Key）: {request.client.host} → {request.method} {request.url.path}')
        raise HTTPException(
            status_code=401,
            detail={
                'error': 'Unauthorized',
                'message': 'Missing API key. Provide X-API-Key header or api_key query parameter.',
            },
        )

    if not await verify_token(api_key):
        logger.warning(f'鉴权失败（API Key 无效）: {request.client.host} → {request.method} {request.url.path}')
        raise HTTPException(
            status_code=401,
            detail={
                'error': 'Unauthorized',
                'message': 'Invalid API key.',
            },
        )

    logger.debug(f'鉴权成功: {request.client.host} → {request.method} {request.url.path}')
    return api_key


def optional_auth(request: Request) -> Optional[str]:
    """
    可选鉴权 — 不强制，通过则返回 key，否则返回 None

    Args:
        request: FastAPI 请求对象

    Returns:
        验证通过的 API Key，或 None
    """
    api_key = request.headers.get('X-API-Key', '')
    if not api_key:
        api_key = request.query_params.get('api_key', '')
    if api_key and verify_token(api_key):
        logger.debug(f'可选鉴权通过: {request.client.host} → {request.method} {request.url.path}')
        return api_key
    logger.debug(f'可选鉴权未通过（无 API Key）: {request.client.host} → {request.method} {request.url.path}')
    return None