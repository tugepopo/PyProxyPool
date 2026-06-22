#!/usr/bin/env python3
"""
快速测试脚本 - 验证各模块功能
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from models import ProxyIP
from db.sqlite_helper import SqliteHelper
from config import DB_CONFIG


def test_models():
    """测试数据模型"""
    p = ProxyIP('1.2.3.4', 8080, 'http', 'high', 'CN', 'Beijing', 150.5, 10, 'test')
    assert p.proxy_url == 'http://1.2.3.4:8080'
    assert p.address == '1.2.3.4:8080'
    assert 'http' in p.proxy_dict

    d = p.to_dict()
    p2 = ProxyIP.from_dict(d)
    assert p2.ip == p.ip
    assert p2.port == p.port
    assert p2.speed == p.speed
    print('[PASS] models')


def test_sqlite():
    """测试SQLite数据库"""
    import tempfile
    tmp = tempfile.mktemp(suffix='.db')
    db = SqliteHelper({'path': tmp})
    db.init_db()

    # 插入
    p1 = ProxyIP('1.2.3.4', 8080, 'http', 'high', 'CN', '', 100, 10, 'test')
    p2 = ProxyIP('5.6.7.8', 3128, 'https', 'anonymous', 'US', '', 200, 8, 'test')
    assert db.insert(p1)
    assert db.insert(p2)
    assert db.count() == 2

    # 去重插入
    p1_dup = ProxyIP('1.2.3.4', 8080, 'http', 'high', 'CN', '', 50, 15, 'test2')
    db.insert(p1_dup)
    assert db.count() == 2  # 不应增加

    # 查询
    all_p = db.get_all()
    assert len(all_p) == 2

    http_p = db.get_by_protocol('http')
    assert len(http_p) == 1

    random_p = db.get_random(count=1, min_score=5)
    assert len(random_p) == 1

    random_p2 = db.get_random(count=10, protocol='https')
    assert len(random_p2) == 1

    # 更新评分
    db.update_score('1.2.3.4', 8080, 20)
    p = db.get_random(count=1, min_score=15)
    assert len(p) == 1 and p[0].score == 20

    # 删除低分 (<10 分的被删，score=8 的没了，score=10 的保留)
    deleted = db.delete_by_score(10)
    assert deleted == 1
    assert db.count() == 1

    # 删除剩余
    db.delete('1.2.3.4', 8080)
    assert db.count() == 0

    # 批量插入
    batch = [ProxyIP(f'10.0.0.{i}', 8080, 'http', source='batch') for i in range(10)]
    inserted = db.batch_insert(batch)
    assert inserted == 10
    assert db.count() == 10

    db.close()
    os.unlink(tmp)
    print('[PASS] sqlite')


def test_crawler():
    """测试采集器（只测试解析逻辑，不发网络请求）"""
    from getter.proxy_crawler import ProxyCrawler
    c = ProxyCrawler()

    # 测试XPath解析
    html = '''
    <html><body>
    <table>
        <tr><td>1.2.3.4</td><td>8080</td><td>高匿</td><td>HTTP</td></tr>
        <tr><td>5.6.7.8</td><td>3128</td><td>透明</td><td>HTTPS</td></tr>
    </table>
    </body></html>
    '''
    source = {
        'name': 'test',
        'type': 'xpath',
        'pattern': './/table/tr',
        'position': {'ip': './td[1]', 'port': './td[2]', 'type': './td[3]', 'protocol': './td[4]'}
    }
    proxies = c._parse_table(html, source)
    assert len(proxies) == 2, f'Expected 2, got {len(proxies)}'
    assert proxies[0].ip == '1.2.3.4'
    assert proxies[0].port == 8080
    assert proxies[0].anonymity == 'high'
    assert proxies[1].protocol == 'https'
    print('[PASS] crawler table')

    # 测试正则解析
    html2 = '<tr><td>10.0.0.1</td><td>80</td></tr>'
    source2 = {
        'name': 'test-regex',
        'type': 'regex',
        'pattern': r'<tr><td>(\d+\.\d+\.\d+\.\d+)</td><td>(\d+)</td></tr>',
        'position': {'ip': 0, 'port': 1}
    }
    proxies2 = c._parse_regex(html2, source2)
    assert len(proxies2) == 1
    assert proxies2[0].ip == '10.0.0.1'
    print('[PASS] crawler regex')


def test_config():
    """测试配置完整性"""
    from config import (
        PROXY_SOURCES, DB_TYPE, DB_CONFIG, VERIFY_URLS,
        VERIFY_TIMEOUT, MIN_PROXY_NUM, CRAWL_INTERVAL,
        CHECK_INTERVAL, VALIDATOR_CONCURRENCY, MIN_SCORE,
        API_HOST, API_PORT, INITIAL_SCORE, USER_AGENTS,
        SCORE_ADD_SUCCESS, SCORE_DEDUCT_FAIL, speed_score
    )
    assert DB_TYPE in ('sqlite', 'mysql', 'redis')
    assert len(PROXY_SOURCES) > 0
    assert len(VERIFY_URLS) > 0
    assert VERIFY_TIMEOUT > 0
    assert MIN_PROXY_NUM > 0
    assert len(USER_AGENTS) > 0
    assert speed_score(100) > speed_score(5000)
    print('[PASS] config')


def test_batch_ops():
    """测试批量操作"""
    import tempfile
    tmp = tempfile.mktemp(suffix='.db')
    db = SqliteHelper({'path': tmp})
    db.init_db()

    # 批量插入
    batch = [ProxyIP(f'10.0.0.{i}', 8080, 'http', 'high', 'CN', '', i * 100.0, 10, 'test') for i in range(100)]
    inserted = db.batch_insert(batch)
    assert inserted == 100, f'Expected 100, got {inserted}'
    assert db.count() == 100

    # 批量更新评分
    updates = [(f'10.0.0.{i}', 8080, 20 + i) for i in range(50)]
    updated = db.batch_update_score(updates)
    assert updated == 50

    # 批量更新速度
    speed_updates = [(f'10.0.0.{i}', 8080, 50.0 + i) for i in range(50)]
    db.batch_update_speed(speed_updates)

    # 统计
    stats = db.get_stats()
    assert stats['total'] == 100
    assert stats['http'] == 100
    assert stats['avg_score'] > 0
    assert stats['verified'] == 0  # last_verified 都是 0

    # 批量删除
    del_keys = [(f'10.0.0.{i}', 8080) for i in range(10)]
    deleted = db.delete_batch(del_keys)
    assert deleted == 10
    assert db.count() == 90

    db.close()
    os.unlink(tmp)
    print('[PASS] batch operations')


def test_stats():
    """测试统计接口"""
    import tempfile
    tmp = tempfile.mktemp(suffix='.db')
    db = SqliteHelper({'path': tmp})
    db.init_db()

    # 空库统计
    stats = db.get_stats()
    assert stats['total'] == 0

    # 插入不同协议
    db.insert(ProxyIP('1.1.1.1', 80, 'http', 'high', speed=100, score=10))
    db.insert(ProxyIP('2.2.2.2', 443, 'https', 'transparent', speed=200, score=5))
    stats = db.get_stats()
    assert stats['total'] == 2
    assert stats['http'] == 1
    assert stats['https'] == 1
    assert stats['high_anon'] == 1
    assert stats['transparent'] == 1

    db.close()
    os.unlink(tmp)
    print('[PASS] stats')


if __name__ == '__main__':
    print('Running tests...\n')
    test_models()
    test_sqlite()
    test_crawler()
    test_config()
    test_batch_ops()
    test_stats()
    print('\n✅ All tests passed!')
