"""
PyProxyPool 数据库层 — async engine + session factory

支持 SQLite（aiosqlite）和 PostgreSQL（asyncpg）双模式。
自动根据 DATABASE_URL 判断数据库类型。
"""
import os
import logging
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy import text

from config import get_settings

logger = logging.getLogger(__name__)

# 全局 engine 和 session factory
_engine = None
_session_factory = None


def _is_sqlite(database_url: str) -> bool:
    """检测是否为 SQLite"""
    return database_url.startswith('sqlite')


def create_engine(dsn: str = None) -> None:
    """
    创建异步数据库引擎和会话工厂（全局单例）

    Args:
        dsn: 数据库连接字符串（可选，默认从配置读取）
    """
    global _engine, _session_factory

    settings = get_settings()
    database_url = dsn or settings.DATABASE_URL

    is_sqlite = _is_sqlite(database_url)

    # SQLite 使用 aiosqlite 驱动，不需要连接池参数
    if is_sqlite:
        _engine = create_async_engine(database_url)
    else:
        _engine = create_async_engine(
            database_url,
            pool_size=settings.DATABASE_POOL_SIZE,
            max_overflow=settings.DATABASE_MAX_OVERFLOW,
            pool_recycle=settings.DATABASE_POOL_RECYCLE,
            pool_pre_ping=True,  # 自动检测连接有效性
        )

    _session_factory = async_sessionmaker(
        bind=_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    db_label = 'SQLite' if is_sqlite else 'PostgreSQL'
    logger.info(f'Database engine created ({db_label}): {database_url.split("@")[-1] if "@" in database_url else database_url}')


def get_session_factory() -> async_sessionmaker:
    """获取会话工厂（延迟初始化）"""
    global _engine, _session_factory
    if _engine is None:
        create_engine()
    return _session_factory


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI 依赖注入：提供数据库会话
    用法: async def endpoint(db: AsyncSession = Depends(get_db)):
    """
    factory = get_session_factory()
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def get_db_session() -> AsyncSession:
    """
    直接获取数据库会话（非依赖注入场景，如调度器中使用）
    注意：调用方需要手动 commit/close
    """
    factory = get_session_factory()
    session = factory()
    return session


async def init_db() -> None:
    """
    初始化数据库连接并检查可用性
    表结构创建由 Alembic 迁移完成
    """
    global _engine, _session_factory
    if _engine is None:
        create_engine()

    # 测试连接
    try:
        async with _engine.connect() as conn:
            result = await conn.execute(text("SELECT 1"))
            result.scalar()
        logger.info('Database connection initialized successfully')
    except Exception as e:
        logger.error(f'Database initialization failed: {e}')
        raise


async def dispose_db() -> None:
    """关闭所有数据库连接"""
    global _engine
    if _engine is not None:
        await _engine.dispose()
        _engine = None
        _session_factory = None
        logger.info('Database connections disposed')


# ---- 同步辅助函数（迁移脚本使用）----

def get_sync_engine(dsn: str = None):
    """获取同步 SQLAlchemy engine（用于迁移脚本和 Alembic）"""
    from sqlalchemy import create_engine as sync_create_engine
    settings = get_settings()
    database_url = dsn or settings.DATABASE_URL
    # 替换 asyncpg 前缀为 pg8000（同步驱动）
    if database_url.startswith('postgresql+asyncpg://'):
        database_url = database_url.replace('postgresql+asyncpg://', 'postgresql://', 1)
    return sync_create_engine(database_url, echo=False)


def get_sync_session(dsn: str = None):
    """获取同步 SQLAlchemy session（用于迁移脚本）"""
    from sqlalchemy.orm import sessionmaker
    engine = get_sync_engine(dsn)
    return sessionmaker(bind=engine)()


# ── GeoIP 初始化 ──────────────────────────────────────────────────
_geoip_reader: 'GeoIPReader | None' = None


def init_geoip() -> None:
    """初始化 GeoIP 本地数据库 Reader（单例模式）"""
    global _geoip_reader
    try:
        from config import get_settings
        from services.geo import GeoIPReader

        _settings = get_settings()
        _geoip_reader = GeoIPReader(_settings.GEOIP_DB_PATH)
        if _geoip_reader.is_available():
            logger.info(f'GeoIP database initialized: {_settings.GEOIP_DB_PATH}')
        else:
            logger.warning('GeoIP database not available, will fallback to online API')
    except Exception as e:
        logger.error(f'Failed to initialize GeoIP: {e}')
        _geoip_reader = None


def get_geoip_reader() -> 'GeoIPReader | None':
    """获取 GeoIPReader 单例"""
    return _geoip_reader