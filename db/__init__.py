from db.sqlite_helper import SqliteHelper
from db.mysql_helper import MySqlHelper
from db.redis_helper import RedisHelper
from config import DB_TYPE, DB_CONFIG

__all__ = ['get_db', 'SqliteHelper', 'MySqlHelper', 'RedisHelper']


def get_db():
    """根据配置返回对应的数据库实例"""
    if DB_TYPE == 'sqlite':
        return SqliteHelper(DB_CONFIG['sqlite'])
    elif DB_TYPE == 'mysql':
        return MySqlHelper(DB_CONFIG['mysql'])
    elif DB_TYPE == 'redis':
        return RedisHelper(DB_CONFIG['redis'])
    else:
        raise ValueError(f'Unsupported DB type: {DB_TYPE}')
