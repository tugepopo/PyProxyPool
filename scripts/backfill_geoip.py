#!/usr/bin/env python3
"""
回溯填充已有代理的 country 和 area 字段
使用 GeoIP 本地数据库查询
"""
import time
import sqlite3
import logging
import sys
from pathlib import Path

# 确保项目根目录在 Python path 中
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from database import init_geoip, get_geoip_reader
from config import get_settings

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)


def backfill_geoip():
    """回溯填充已有代理的 country 和 area"""
    settings = get_settings()
    reader = get_geoip_reader()

    if reader is None or not reader.is_available():
        logger.error("GeoIP 数据库不可用，请确保 data/geoip/GeoLite2-City.mmdb 存在")
        return

    db_path = settings.DATABASE_URL.replace('sqlite+aiosqlite:///', '')
    conn = sqlite3.connect(db_path)

    cur = conn.cursor()
    cur.execute("SELECT id, ip, port, country FROM proxies WHERE country = ''")
    rows = cur.fetchall()
    total = len(rows)

    if total == 0:
        logger.info("所有代理已有国家信息，无需回溯")
        conn.close()
        return

    logger.info(f"开始回溯填充 {total} 个代理的地理位置...")

    updated = 0
    failed = 0
    start = time.time()

    for i, row in enumerate(rows):
        row_id = row[0]
        ip = row[1]
        geo = reader.lookup(ip)
        country_code = geo.get('country', '') or ''
        region = geo.get('region', '') or ''
        city = geo.get('city', '') or ''

        # 构建 country 字段：优先用 region，否则用 ISO 国家代码
        if country_code and region:
            country = region
        elif country_code:
            country = country_code
        else:
            country = ''

        area = city

        if country or area:
            cur.execute(
                "UPDATE proxies SET country=?, area=? WHERE id=?",
                (country, area, row_id)
            )
            updated += 1
        else:
            failed += 1

        if (i + 1) % 100 == 0 or i == total - 1:
            elapsed = time.time() - start
            speed = (i + 1) / elapsed if elapsed > 0 else 0
            logger.info(f"进度: {i+1}/{total} ({(i+1)/total*100:.1f}%), "
                        f"成功={updated}, 失败={failed}, "
                        f"速度={speed:.0f}条/秒")

    conn.commit()
    conn.close()

    logger.info(f"回溯完成: 总{total}, 成功{updated}, 失败{failed}, "
                f"耗时{time.time()-start:.1f}秒")


if __name__ == '__main__':
    init_geoip()
    backfill_geoip()