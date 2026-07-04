"""
PyProxyPool — SQLite → PostgreSQL 数据迁移脚本

将旧 SQLite 数据库中的代理数据迁移到 PostgreSQL
"""
import os
import sys
import sqlite3
import logging
from datetime import datetime
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from config import get_settings
from database import get_sync_engine, get_sync_session
from models import Proxy

logger = logging.getLogger(__name__)


async def migrate_sqlite_to_postgres(
    sqlite_path: str = None,
    dry_run: bool = False,
):
    """
    从 SQLite 迁移数据到 PostgreSQL

    Args:
        sqlite_path: SQLite 数据库路径（默认使用配置中的路径）
        dry_run: 是否仅预览不执行
    """
    settings = get_settings()

    # 获取 SQLite 路径
    if not sqlite_path:
        db_config = settings.DB_CONFIG
        sqlite_path = db_config.get('sqlite', {}).get('path',
            os.path.join(settings.BASE_DIR, 'data', 'proxy.db')
        )

    if not os.path.exists(sqlite_path):
        logger.error(f'SQLite database not found: {sqlite_path}')
        return

    logger.info(f'Reading SQLite database: {sqlite_path}')

    # 1. 从 SQLite 读取数据
    conn = sqlite3.connect(sqlite_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # 检查表是否存在
    try:
        cursor.execute("SELECT COUNT(*) as cnt FROM proxies")
        row = cursor.fetchone()
        total = row['cnt']
    except sqlite3.OperationalError:
        logger.error('Table "proxies" not found in SQLite database')
        return

    logger.info(f'Found {total} proxies in SQLite database')

    if dry_run:
        logger.info('Dry run mode — no changes will be made')
        logger.info(f'Would migrate {total} proxies to PostgreSQL')
        conn.close()
        return

    # 2. 读取所有代理数据
    cursor.execute('SELECT * FROM proxies')
    rows = cursor.fetchall()
    conn.close()

    logger.info(f'Read {len(rows)} rows from SQLite')

    # 3. 写入 PostgreSQL
    engine = get_sync_engine()
    Session = sessionmaker(bind=engine)
    session = Session()

    inserted = 0
    errors = 0

    for row in rows:
        try:
            # 检查是否已存在
            existing = session.query(Proxy).filter_by(
                ip=row['ip'],
                port=row['port'],
            ).first()

            if existing:
                continue

            proxy = Proxy(
                ip=row['ip'],
                port=row['port'],
                protocol=row.get('protocol', 'http'),
                username=row.get('username', ''),
                password=row.get('password', ''),
                anonymity=row.get('anonymity', 'unknown'),
                country=row.get('country', ''),
                area=row.get('area', ''),
                speed=row.get('speed', 0),
                score=row.get('score', 10),
                last_verified=row.get('last_verified', 0),
                use_count=row.get('use_count', 0),
                source=row.get('source', ''),
                purity_score=row.get('purity_score', 0),
                purity_class=row.get('purity_class', ''),
                is_datacenter=bool(row.get('is_datacenter', False)),
                is_proxy=bool(row.get('is_proxy', False)),
                is_vpn=bool(row.get('is_vpn', False)),
                is_tor=bool(row.get('is_tor', False)),
                abuse_confidence=row.get('abuse_confidence', 0),
                isp=row.get('isp', ''),
                asn=row.get('asn', ''),
                asn_owner=row.get('asn_owner', ''),
                org_name=row.get('org_name', ''),
                ip_type=row.get('ip_type', ''),
                is_native=bool(row.get('is_native', False)),
                shared_users=row.get('shared_users', ''),
                risk_score=row.get('risk_score', 0),
                risk_level=row.get('risk_level', ''),
                rdns=row.get('rdns', ''),
                scenes=row.get('scenes', ''),
                ping0_location=row.get('ping0_location', ''),
                ping0_latitude=row.get('ping0_latitude', 0),
                ping0_longitude=row.get('ping0_longitude', 0),
                tags=row.get('tags', '[]'),
            )

            session.add(proxy)
            inserted += 1

        except Exception as e:
            logger.error(f'Failed to insert {row["ip"]}:{row["port"]}: {e}')
            errors += 1

    try:
        session.commit()
        logger.info(f'Migration complete: {inserted} inserted, {errors} errors')
    except Exception as e:
        session.rollback()
        logger.error(f'Commit failed: {e}')

    session.close()


def main():
    """命令行入口"""
    import argparse
    parser = argparse.ArgumentParser(description='SQLite to PostgreSQL migration')
    parser.add_argument('--sqlite', default=None, help='SQLite database path')
    parser.add_argument('--dry-run', action='store_true', help='Preview only')
    args = parser.parse_args()

    import asyncio
    asyncio.run(migrate_sqlite_to_postgres(
        sqlite_path=args.sqlite,
        dry_run=args.dry_run,
    ))


if __name__ == '__main__':
    main()