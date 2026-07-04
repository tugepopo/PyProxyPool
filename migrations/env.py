"""
Alembic 迁移配置
"""
import os
import sys
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from models import Base

# Alembic Config
config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# 从环境变量或配置获取数据库 URL
database_url = os.environ.get('DATABASE_URL', '')
if not database_url:
    from config import get_settings
    settings = get_settings()
    database_url = settings.DATABASE_URL

# Alembic 使用同步引擎，需要去掉异步驱动后缀
# e.g. "postgresql+asyncpg://..." -> "postgresql://..."
if database_url.startswith('postgresql+asyncpg://'):
    database_url = database_url.replace('postgresql+asyncpg://', 'postgresql://', 1)

target_metadata = Base.metadata


def run_migrations_offline():
    """Run migrations in 'offline' mode."""
    url = database_url
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={'paramstyle': 'named'},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online():
    """Run migrations in 'online' mode."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix='sqlalchemy.',
        poolclass=pool.NullPool,
        url=database_url,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()