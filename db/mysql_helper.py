"""
MySQL 数据库实现 (使用 pymysql + SQLAlchemy)
"""
import time
import logging
from typing import List

logger = logging.getLogger('db.mysql')


class MySqlHelper:
    """MySQL实现 - 需要安装 pymysql 和 sqlalchemy"""

    def __init__(self, config: dict):
        self.config = config
        self.engine = None
        self._session = None

    def init_db(self):
        try:
            from sqlalchemy import create_engine, text
            from sqlalchemy.orm import sessionmaker
            cfg = self.config
            url = f"mysql+pymysql://{cfg['user']}:{cfg['password']}@{cfg['host']}:{cfg['port']}/{cfg['database']}?charset={cfg.get('charset', 'utf8mb4')}"
            self.engine = create_engine(url, pool_recycle=3600)
            # 创建表
            with self.engine.connect() as conn:
                conn.execute(text('''
                    CREATE TABLE IF NOT EXISTS proxies (
                        ip VARCHAR(45) NOT NULL,
                        port INT NOT NULL,
                        protocol VARCHAR(10) DEFAULT 'http',
                        anonymity VARCHAR(20) DEFAULT 'unknown',
                        country VARCHAR(50) DEFAULT '',
                        area VARCHAR(100) DEFAULT '',
                        speed FLOAT DEFAULT 0,
                        score INT DEFAULT 10,
                        source VARCHAR(50) DEFAULT '',
                        last_verified DOUBLE DEFAULT 0,
                        created_at DOUBLE DEFAULT 0,
                        PRIMARY KEY (ip, port),
                        INDEX idx_score (score),
                        INDEX idx_protocol (protocol)
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                '''))
                conn.commit()
            Session = sessionmaker(bind=self.engine)
            self._session = Session()
            logger.info('MySQL initialized')
        except ImportError:
            logger.error('MySQL requires: pip install pymysql sqlalchemy')
            raise

    def insert(self, proxy) -> bool:
        try:
            from sqlalchemy import text
            now = time.time()
            with self.engine.connect() as conn:
                conn.execute(text('''
                    INSERT INTO proxies (ip, port, protocol, anonymity, country, area,
                        speed, score, source, last_verified, created_at)
                    VALUES (:ip, :port, :protocol, :anonymity, :country, :area,
                        :speed, :score, :source, :last_verified, :created_at)
                    ON DUPLICATE KEY UPDATE
                        protocol=VALUES(protocol), anonymity=VALUES(anonymity),
                        speed=VALUES(speed), score=VALUES(score),
                        source=VALUES(source), last_verified=VALUES(last_verified)
                '''), {
                    'ip': proxy.ip, 'port': proxy.port, 'protocol': proxy.protocol,
                    'anonymity': proxy.anonymity, 'country': proxy.country,
                    'area': proxy.area, 'speed': proxy.speed, 'score': proxy.score,
                    'source': proxy.source, 'last_verified': proxy.last_verified,
                    'created_at': proxy.created_at or now,
                })
                conn.commit()
            return True
        except Exception as e:
            logger.error(f'MySQL insert failed: {e}')
            return False

    def batch_insert(self, proxies) -> int:
        return sum(1 for p in proxies if self.insert(p))

    def get_all(self) -> list:
        from sqlalchemy import text
        with self.engine.connect() as conn:
            rows = conn.execute(text('SELECT * FROM proxies ORDER BY score DESC, speed ASC')).fetchall()
        return [self._row_to_proxy(r) for r in rows]

    def get_by_protocol(self, protocol: str) -> list:
        from sqlalchemy import text
        with self.engine.connect() as conn:
            rows = conn.execute(text('SELECT * FROM proxies WHERE protocol=:p ORDER BY score DESC'), {'p': protocol}).fetchall()
        return [self._row_to_proxy(r) for r in rows]

    def get_random(self, count=1, protocol=None, anonymity=None, min_score=0) -> list:
        from sqlalchemy import text
        conditions = ['score >= :min_score']
        params = {'min_score': min_score, 'limit': count}
        if protocol:
            conditions.append('protocol = :protocol')
            params['protocol'] = protocol
        if anonymity:
            conditions.append('anonymity = :anonymity')
            params['anonymity'] = anonymity
        where = ' AND '.join(conditions)
        with self.engine.connect() as conn:
            rows = conn.execute(text(f'SELECT * FROM proxies WHERE {where} ORDER BY RAND() LIMIT :limit'), params).fetchall()
        return [self._row_to_proxy(r) for r in rows]

    def delete(self, ip, port=None) -> int:
        from sqlalchemy import text
        with self.engine.connect() as conn:
            if port:
                r = conn.execute(text('DELETE FROM proxies WHERE ip=:ip AND port=:port'), {'ip': ip, 'port': port})
            else:
                r = conn.execute(text('DELETE FROM proxies WHERE ip=:ip'), {'ip': ip})
            conn.commit()
            return r.rowcount

    def delete_by_score(self, min_score) -> int:
        from sqlalchemy import text
        with self.engine.connect() as conn:
            r = conn.execute(text('DELETE FROM proxies WHERE score < :s'), {'s': min_score})
            conn.commit()
            return r.rowcount

    def update_score(self, ip, port, score):
        from sqlalchemy import text
        with self.engine.connect() as conn:
            conn.execute(text('UPDATE proxies SET score=:s WHERE ip=:ip AND port=:port'), {'s': score, 'ip': ip, 'port': port})
            conn.commit()

    def update_speed(self, ip, port, speed):
        from sqlalchemy import text
        with self.engine.connect() as conn:
            conn.execute(text('UPDATE proxies SET speed=:s WHERE ip=:ip AND port=:port'), {'s': speed, 'ip': ip, 'port': port})
            conn.commit()

    def count(self) -> int:
        from sqlalchemy import text
        with self.engine.connect() as conn:
            r = conn.execute(text('SELECT COUNT(*) as cnt FROM proxies')).fetchone()
            return r[0]

    def exists(self, ip, port) -> bool:
        from sqlalchemy import text
        with self.engine.connect() as conn:
            r = conn.execute(text('SELECT 1 FROM proxies WHERE ip=:ip AND port=:port'), {'ip': ip, 'port': port}).fetchone()
            return r is not None

    def close(self):
        if self._session:
            self._session.close()
        if self.engine:
            self.engine.dispose()

    @staticmethod
    def _row_to_proxy(row):
        from models import ProxyIP
        return ProxyIP(
            ip=row[0], port=row[1], protocol=row[2], anonymity=row[3],
            country=row[4], area=row[5], speed=row[6], score=row[7],
            source=row[8], last_verified=row[9], created_at=row[10],
        )
