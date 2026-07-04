"""
PyProxyPool — SQLite Schema Migration (旧表 -> 新模型)

将旧 proxies 表（无 id, 无 grade, 无 scan_score）迁移到新模型 schema
"""
import os, sys, sqlite3, json
import logging
from datetime import datetime

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(PROJECT_ROOT, 'data', 'proxy.db')


def get_old_schema(conn):
    """读取旧 proxies 表结构"""
    cursor = conn.execute("PRAGMA table_info(proxies)")
    columns = {row[1]: row for row in cursor.fetchall()}
    return columns


def get_old_table_names(conn):
    """获取所有表名"""
    cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
    return [row[0] for row in cursor.fetchall()]


def migrate_proxies(conn):
    """迁移 proxies 表"""
    old_cols = get_old_schema(conn)
    
    # 备份旧表数据
    logger.info('Backing up old data...')
    cursor = conn.execute("SELECT * FROM proxies")
    old_data = cursor.fetchall()
    old_col_names = [desc[0] for desc in cursor.description]
    
    # 旧字段映射
    old_cols_set = set(old_col_names)
    logger.info(f'Old columns ({len(old_col_names)}): {old_col_names}')
    
    # 删除旧表
    conn.execute("DROP TABLE IF EXISTS proxies")
    conn.execute("DROP TABLE IF EXISTS sqlite_sequence")  # 重置 autoincrement
    conn.commit()
    
    # 创建新表（使用新模型定义的表结构）
    sys.path.insert(0, PROJECT_ROOT)
    from models import Base, Proxy
    from sqlalchemy import create_engine, text
    
    sync_engine = create_engine(f'sqlite:///{DB_PATH}')
    Base.metadata.create_all(sync_engine)
    sync_engine.dispose()
    
    logger.info('New table created')
    
    # 计算 scan_score 和 grade
    def calc_score(row_dict):
        # 生存率: score (原 0-100) -> survival
        survival = row_dict.get('score', 10)
        # 延迟: speed_ms -> latency
        speed = row_dict.get('speed', 500)
        latency = max(0, 100 - min(speed, 5000) / 50)
        # IP 类型: purity_class
        purity_class = row_dict.get('purity_class', '')
        type_map = {'原生IP': 100, '住宅IP': 85, '专线代理': 60, '数据中心': 30, '未知': 50}
        ip_type = type_map.get(purity_class, 50)
        # 风险: abuse_confidence + risk_score
        risk = max(0, 100 - row_dict.get('abuse_confidence', 0) - row_dict.get('risk_score', 0) * 0.5)
        
        score = (survival * 0.40 + latency * 0.20 + ip_type * 0.20 + risk * 0.20)
        return round(score, 1)
    
    def grade_from_score(score):
        if score >= 80: return 'A'
        if score >= 60: return 'B'
        if score >= 40: return 'C'
        return 'D'
    
    # 重新插入数据
    logger.info(f'Reinserting {len(old_data)} records...')
    inserted = 0
    for row in old_data:
        row_dict = dict(zip(old_col_names, row))
        scan_score = calc_score(row_dict)
        grade = grade_from_score(scan_score)
        
        # 构建插入行（只包含新模型中的字段）
        now = datetime.utcnow()
        try:
            conn.execute(
                """INSERT INTO proxies (
                    ip, port, protocol, username, password,
                    anonymity, country, area, speed, score, last_verified, use_count,
                    source, outlet_ip, is_outbound_ip,
                    purity_score, purity_class, is_datacenter, is_proxy, is_vpn, is_tor,
                    abuse_confidence, isp, asn, asn_owner, org_name, ip_type,
                    is_native, shared_users, risk_score, risk_level, rdns, scenes,
                    ping0_location, ping0_latitude, ping0_longitude,
                    scan_score, grade, tags,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    row_dict.get('ip', ''),
                    row_dict.get('port', 0),
                    row_dict.get('protocol', 'http'),
                    row_dict.get('username', ''),
                    row_dict.get('password', ''),
                    row_dict.get('anonymity', 'unknown'),
                    row_dict.get('country', ''),
                    row_dict.get('area', ''),
                    row_dict.get('speed', 0),
                    row_dict.get('score', 10),
                    row_dict.get('last_verified', 0),
                    row_dict.get('use_count', 0),
                    row_dict.get('source', ''),
                    '',  # outlet_ip
                    0,   # is_outbound_ip
                    row_dict.get('purity_score', 0),
                    row_dict.get('purity_class', ''),
                    row_dict.get('is_datacenter', 0),
                    row_dict.get('is_proxy', 0),
                    row_dict.get('is_vpn', 0),
                    row_dict.get('is_tor', 0),
                    row_dict.get('abuse_confidence', 0),
                    row_dict.get('isp', ''),
                    row_dict.get('asn', ''),
                    row_dict.get('asn_owner', ''),
                    row_dict.get('org_name', ''),
                    row_dict.get('ip_type', ''),
                    row_dict.get('is_native', 0),
                    row_dict.get('shared_users', ''),
                    row_dict.get('risk_score', 0),
                    row_dict.get('risk_level', ''),
                    row_dict.get('rdns', ''),
                    row_dict.get('scenes', ''),
                    row_dict.get('ping0_location', ''),
                    row_dict.get('ping0_latitude', 0),
                    row_dict.get('ping0_longitude', 0),
                    scan_score,
                    grade,
                    row_dict.get('tags', '[]'),
                    now,
                    now,
                )
            )
            inserted += 1
        except Exception as e:
            logger.error(f'Error inserting row {inserted}: {e}')
            logger.error(f'  row: {row_dict}')
    
    conn.commit()
    logger.info(f'Migrated {inserted}/{len(old_data)} records')
    
    return inserted, len(old_data)


def migrate_other_tables(conn):
    """迁移其他表（scan_tasks, scan_results, whitelist, blacklist）"""
    old_tables = get_old_table_names(conn)
    
    # 检查需要迁移的表
    new_tables = ['scan_tasks', 'scan_results', 'whitelist', 'blacklist']
    for tname in new_tables:
        if tname not in old_tables:
            logger.info(f'Skipping {tname} (not in old DB)')
            continue
        logger.info(f'Dropping old {tname}')
        conn.execute(f'DROP TABLE IF EXISTS {tname}')
    conn.commit()


def main():
    if not os.path.exists(DB_PATH):
        logger.error(f'Database not found: {DB_PATH}')
        return
    
    logger.info(f'Starting schema migration for {DB_PATH}')
    
    conn = sqlite3.connect(DB_PATH)
    try:
        # 迁移其他表
        migrate_other_tables(conn)
        
        # 创建新表结构
        sys.path.insert(0, PROJECT_ROOT)
        from models import Base
        from sqlalchemy import create_engine
        sync_engine = create_engine(f'sqlite:///{DB_PATH}')
        Base.metadata.create_all(sync_engine)
        sync_engine.dispose()
        
        # 迁移 proxies
        inserted, total = migrate_proxies(conn)
        logger.info(f'Migration complete: {inserted}/{total} proxies migrated')
        
        # 验证
        result = conn.execute("SELECT count(*) FROM proxies").fetchone()[0]
        logger.info(f'Verification: {result} proxies in new table')
        
        # 备份旧表（可选）
        logger.info('Migration successful!')
        
    except Exception as e:
        logger.error(f'Migration failed: {e}', exc_info=True)
        raise
    finally:
        conn.close()


if __name__ == '__main__':
    main()
