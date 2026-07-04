"""
PyProxyPool — 数据库初始化脚本

自动检测数据库类型（SQLite / PostgreSQL），分别初始化。
如果本地没有 PostgreSQL，会自动降级到 SQLite。
"""
import os
import sys
import logging
import subprocess

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from config import get_settings
from models import Base

logger = logging.getLogger(__name__)


def _detect_db_type(database_url: str) -> str:
    """检测数据库类型"""
    if database_url.startswith('sqlite'):
        return 'sqlite'
    elif database_url.startswith('postgresql'):
        return 'postgresql'
    else:
        return 'unknown'


def _run_alembic(*args, cwd=None):
    """通过 Python 模块方式运行 alembic，避免依赖系统 PATH"""
    python = sys.executable
    cmd = [python, '-m', 'alembic'] + list(args)
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)


def init_sqlite(database_url: str):
    """使用 SQLite 初始化数据库（不需要 Alembic）"""
    from sqlalchemy import create_engine, text
    from sqlalchemy.orm import sessionmaker

    logger.info(f'Using SQLite: {database_url}')

    # SQLite 使用文件路径（去掉 sqlite:// 前缀）
    db_path = database_url.replace('sqlite:///', '').replace('sqlite://', '')
    db_path = db_path.replace('file://', '')

    # 确保目录存在
    db_dir = os.path.dirname(db_path)
    if db_dir and not os.path.exists(db_dir):
        os.makedirs(db_dir, exist_ok=True)
        logger.info(f'Created directory: {db_dir}')

    # 创建同步引擎
    engine = create_engine(database_url, echo=False)

    # 创建所有表
    Base.metadata.create_all(engine)
    logger.info(f'SQLite database initialized: {db_path}')

    # 验证
    SessionLocal = sessionmaker(bind=engine)
    with SessionLocal() as session:
        result = session.execute(text("SELECT count(*) FROM sqlite_master WHERE type='table'"))
        table_count = result.scalar()
        logger.info(f'Created {table_count} tables')

    engine.dispose()
    return True


def init_postgresql(database_url: str):
    """使用 PostgreSQL + Alembic 初始化数据库"""
    from config import get_settings
    settings = get_settings()
    project_root = settings.BASE_DIR
    migrations_dir = os.path.join(project_root, 'migrations')

    # 检查迁移状态
    logger.info('Checking migration status...')
    result = _run_alembic('current', cwd=migrations_dir)
    logger.info(f'Current migration: {result.stdout.strip()}')

    # 执行迁移
    logger.info('Running migrations...')
    result = _run_alembic('upgrade', 'head', cwd=migrations_dir)
    if result.returncode != 0:
        logger.error(f'Migration failed: {result.stderr}')
        return False

    logger.info('PostgreSQL database initialized successfully')
    return True


def check_status():
    """检查数据库状态"""
    settings = get_settings()
    database_url = settings.DATABASE_URL
    db_type = _detect_db_type(database_url)

    if db_type == 'sqlite':
        db_path = database_url.replace('sqlite:///', '').replace('sqlite://', '')
        print(f'SQLite database: {db_path}')
        if os.path.exists(db_path):
            print(f'File exists: {os.path.getsize(db_path)} bytes')
        else:
            print('File not found')
    elif db_type == 'postgresql':
        result = _run_alembic('current', cwd=os.path.join(settings.BASE_DIR, 'migrations'))
        print(f'Current migration: {result.stdout.strip()}')
        if result.returncode != 0:
            print(f'Error: {result.stderr}')


def main():
    import argparse
    parser = argparse.ArgumentParser(description='Database initialization')
    parser.add_argument('--check', action='store_true', help='Check migration status')
    parser.add_argument('--force-sqlite', action='store_true', help='Force SQLite mode')
    args = parser.parse_args()

    if args.check:
        check_status()
        return

    settings = get_settings()
    database_url = settings.DATABASE_URL

    # 如果强制 SQLite 或检测到没有 PostgreSQL，降级到 SQLite
    if args.force_sqlite or database_url.startswith('sqlite'):
        init_sqlite(database_url)
    else:
        # 尝试检测 PostgreSQL 是否可用
        logger.info(f'Detected database type: {_detect_db_type(database_url)}')
        try:
            success = init_postgresql(database_url)
            if not success:
                logger.warning('PostgreSQL initialization failed.')
                logger.info('Falling back to SQLite...')
                # 降级到 SQLite
                settings.SQLITE_PATH = os.path.join(settings.BASE_DIR, 'data', 'proxy.db')
                sqlite_url = f'sqlite:///{settings.SQLITE_PATH}'
                init_sqlite(sqlite_url)
                print(f'Fallback to SQLite: {settings.SQLITE_PATH}')
        except Exception as e:
            logger.error(f'PostgreSQL initialization failed: {e}')
            logger.info('Falling back to SQLite...')
            settings.SQLITE_PATH = os.path.join(settings.BASE_DIR, 'data', 'proxy.db')
            sqlite_url = f'sqlite:///{settings.SQLITE_PATH}'
            init_sqlite(sqlite_url)
            print(f'Fallback to SQLite: {settings.SQLITE_PATH}')


if __name__ == '__main__':
    main()