"""
SQLite 数据库实现 - 优化版
优化点：WAL模式、单事务批量写入、批量更新、线程安全连接池
"""
import os
import time
import sqlite3
import logging
import threading
from typing import List, Optional
from db.base import BaseDB
from models import ProxyIP

logger = logging.getLogger('db.sqlite')


class SqliteHelper(BaseDB):

    def __init__(self, config: dict):
        self.db_path = config.get('path', 'data/proxy.db')
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self._local = threading.local()  # 线程本地连接
        self._lock = threading.Lock()

    def _get_conn(self) -> sqlite3.Connection:
        """获取当前线程的数据库连接（线程安全）"""
        conn = getattr(self._local, 'conn', None)
        if conn is None:
            conn = sqlite3.connect(self.db_path, check_same_thread=False, timeout=30)
            conn.row_factory = sqlite3.Row
            conn.execute('PRAGMA journal_mode=WAL')      # WAL 模式，并发读写
            conn.execute('PRAGMA synchronous=NORMAL')      # 平衡性能和安全
            conn.execute('PRAGMA cache_size=-8000')        # 8MB 缓存
            conn.execute('PRAGMA busy_timeout=5000')       # 忙等待 5 秒
            self._local.conn = conn
        return conn

    def init_db(self):
        conn = self._get_conn()
        conn.execute('''
            CREATE TABLE IF NOT EXISTS proxies (
                ip TEXT NOT NULL,
                port INTEGER NOT NULL,
                protocol TEXT DEFAULT 'http',
                anonymity TEXT DEFAULT 'unknown',
                country TEXT DEFAULT '',
                area TEXT DEFAULT '',
                speed REAL DEFAULT 0,
                score INTEGER DEFAULT 10,
                source TEXT DEFAULT '',
                last_verified REAL DEFAULT 0,
                created_at REAL DEFAULT 0,
                PRIMARY KEY (ip, port)
            )
        ''')
        conn.execute('CREATE INDEX IF NOT EXISTS idx_score ON proxies(score DESC)')
        conn.execute('CREATE INDEX IF NOT EXISTS idx_protocol ON proxies(protocol)')
        conn.execute('CREATE INDEX IF NOT EXISTS idx_anonymity ON proxies(anonymity)')
        conn.commit()
        logger.info(f'SQLite initialized: {self.db_path}')

    def insert(self, proxy: ProxyIP) -> bool:
        try:
            conn = self._get_conn()
            now = time.time()
            conn.execute('''
                INSERT INTO proxies (ip, port, protocol, anonymity, country, area,
                    speed, score, source, last_verified, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(ip, port) DO UPDATE SET
                    protocol=excluded.protocol,
                    anonymity=excluded.anonymity,
                    speed=excluded.speed,
                    score=excluded.score,
                    source=excluded.source,
                    last_verified=excluded.last_verified
            ''', (proxy.ip, proxy.port, proxy.protocol, proxy.anonymity,
                  proxy.country, proxy.area, proxy.speed, proxy.score,
                  proxy.source, proxy.last_verified, proxy.created_at or now))
            conn.commit()
            return True
        except Exception as e:
            logger.error(f'Insert failed {proxy.address}: {e}')
            return False

    def batch_insert(self, proxies: List[ProxyIP]) -> int:
        """单事务批量插入，性能提升 10-50 倍"""
        if not proxies:
            return 0
        conn = self._get_conn()
        now = time.time()
        count = 0
        try:
            with self._lock:
                conn.execute('BEGIN')
                for proxy in proxies:
                    try:
                        conn.execute('''
                            INSERT INTO proxies (ip, port, protocol, anonymity, country, area,
                                speed, score, source, last_verified, created_at)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                            ON CONFLICT(ip, port) DO UPDATE SET
                                protocol=excluded.protocol,
                                score=excluded.score,
                                source=excluded.source
                        ''', (proxy.ip, proxy.port, proxy.protocol, proxy.anonymity,
                              proxy.country, proxy.area, proxy.speed, proxy.score,
                              proxy.source, proxy.last_verified, proxy.created_at or now))
                        count += 1
                    except Exception as e:
                        logger.debug(f'Batch insert skip {proxy.address}: {e}')
                conn.commit()
        except Exception as e:
            logger.error(f'Batch insert failed: {e}')
            try:
                conn.rollback()
            except Exception:
                pass
        return count

    def batch_update_score(self, updates: List[tuple]) -> int:
        """批量更新评分 [(ip, port, score), ...]，单事务完成"""
        if not updates:
            return 0
        conn = self._get_conn()
        count = 0
        try:
            with self._lock:
                conn.execute('BEGIN')
                for ip, port, score in updates:
                    conn.execute('UPDATE proxies SET score=? WHERE ip=? AND port=?', (score, ip, port))
                    count += 1
                conn.commit()
        except Exception as e:
            logger.error(f'Batch update score failed: {e}')
            try:
                conn.rollback()
            except Exception:
                pass
        return count

    def batch_update_speed(self, updates: List[tuple]) -> int:
        """批量更新速度 [(ip, port, speed), ...]，单事务完成"""
        if not updates:
            return 0
        conn = self._get_conn()
        count = 0
        try:
            with self._lock:
                conn.execute('BEGIN')
                for ip, port, speed in updates:
                    conn.execute('UPDATE proxies SET speed=? WHERE ip=? AND port=?', (speed, ip, port))
                    count += 1
                conn.commit()
        except Exception as e:
            logger.error(f'Batch update speed failed: {e}')
            try:
                conn.rollback()
            except Exception:
                pass
        return count

    def get_all(self) -> List[ProxyIP]:
        conn = self._get_conn()
        rows = conn.execute('SELECT * FROM proxies ORDER BY score DESC, speed ASC').fetchall()
        return [self._row_to_proxy(r) for r in rows]

    def get_by_protocol(self, protocol: str) -> List[ProxyIP]:
        conn = self._get_conn()
        rows = conn.execute(
            'SELECT * FROM proxies WHERE protocol=? ORDER BY score DESC, speed ASC',
            (protocol,)
        ).fetchall()
        return [self._row_to_proxy(r) for r in rows]

    def get_random(self, count: int = 1, protocol: str = None,
                   anonymity: str = None, min_score: int = 0) -> List[ProxyIP]:
        conn = self._get_conn()
        conditions = ['score >= ?']
        params: list = [min_score]
        if protocol:
            conditions.append('protocol = ?')
            params.append(protocol)
        if anonymity:
            conditions.append('anonymity = ?')
            params.append(anonymity)
        where = ' AND '.join(conditions)
        rows = conn.execute(
            f'SELECT * FROM proxies WHERE {where} ORDER BY RANDOM() LIMIT ?',
            params + [count]
        ).fetchall()
        return [self._row_to_proxy(r) for r in rows]

    def get_stats(self) -> dict:
        """获取统计信息（单次查询，高效）"""
        conn = self._get_conn()
        row = conn.execute('''
            SELECT
                COUNT(*) as total,
                SUM(CASE WHEN protocol='http' THEN 1 ELSE 0 END) as http_count,
                SUM(CASE WHEN protocol='https' THEN 1 ELSE 0 END) as https_count,
                SUM(CASE WHEN anonymity='high' THEN 1 ELSE 0 END) as high_anon,
                SUM(CASE WHEN anonymity='transparent' THEN 1 ELSE 0 END) as transparent,
                COALESCE(AVG(score), 0) as avg_score,
                COALESCE(AVG(CASE WHEN speed > 0 THEN speed END), 0) as avg_speed,
                SUM(CASE WHEN last_verified > 0 THEN 1 ELSE 0 END) as verified,
                MIN(score) as min_score,
                MAX(score) as max_score
            FROM proxies
        ''').fetchone()
        return {
            'total': row['total'],
            'http': row['http_count'],
            'https': row['https_count'],
            'high_anon': row['high_anon'],
            'transparent': row['transparent'],
            'avg_score': round(row['avg_score'], 1),
            'avg_speed': round(row['avg_speed'], 1),
            'verified': row['verified'],
            'min_score': row['min_score'],
            'max_score': row['max_score'],
        }

    def delete(self, ip: str, port: int = None) -> int:
        conn = self._get_conn()
        if port:
            cur = conn.execute('DELETE FROM proxies WHERE ip=? AND port=?', (ip, port))
        else:
            cur = conn.execute('DELETE FROM proxies WHERE ip=?', (ip,))
        conn.commit()
        return cur.rowcount

    def delete_by_score(self, min_score: int) -> int:
        conn = self._get_conn()
        cur = conn.execute('DELETE FROM proxies WHERE score < ?', (min_score,))
        conn.commit()
        return cur.rowcount

    def delete_batch(self, keys: List[tuple]) -> int:
        """批量删除 [(ip, port), ...]"""
        if not keys:
            return 0
        conn = self._get_conn()
        count = 0
        try:
            with self._lock:
                conn.execute('BEGIN')
                for ip, port in keys:
                    conn.execute('DELETE FROM proxies WHERE ip=? AND port=?', (ip, port))
                    count += 1
                conn.commit()
        except Exception as e:
            logger.error(f'Batch delete failed: {e}')
            try:
                conn.rollback()
            except Exception:
                pass
        return count

    def update_score(self, ip: str, port: int, score: int):
        conn = self._get_conn()
        conn.execute('UPDATE proxies SET score=? WHERE ip=? AND port=?', (score, ip, port))
        conn.commit()

    def update_speed(self, ip: str, port: int, speed: float):
        conn = self._get_conn()
        conn.execute('UPDATE proxies SET speed=? WHERE ip=? AND port=?', (speed, ip, port))
        conn.commit()

    def count(self) -> int:
        conn = self._get_conn()
        row = conn.execute('SELECT COUNT(*) as cnt FROM proxies').fetchone()
        return row['cnt']

    def exists(self, ip: str, port: int) -> bool:
        conn = self._get_conn()
        row = conn.execute(
            'SELECT 1 FROM proxies WHERE ip=? AND port=?', (ip, port)
        ).fetchone()
        return row is not None

    def close(self):
        conn = getattr(self._local, 'conn', None)
        if conn:
            conn.close()
            self._local.conn = None

    @staticmethod
    def _row_to_proxy(row) -> ProxyIP:
        return ProxyIP(
            ip=row['ip'],
            port=row['port'],
            protocol=row['protocol'],
            anonymity=row['anonymity'],
            country=row['country'],
            area=row['area'],
            speed=row['speed'],
            score=row['score'],
            source=row['source'],
            last_verified=row['last_verified'],
            created_at=row['created_at'],
        )
