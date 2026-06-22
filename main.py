"""
PyProxyPool 主入口 - 优化版
优化点：批量DB操作、采样健康检查、智能调度、API触发采集
"""
import os
import sys
import time
import signal
import logging
import argparse
from multiprocessing import Process, Queue, Value

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import (
    API_HOST, API_PORT, MIN_PROXY_NUM, CRAWL_INTERVAL,
    CHECK_INTERVAL, VALIDATOR_CONCURRENCY, MIN_SCORE,
    LOG_LEVEL, LOG_FORMAT, LOG_FILE
)


def setup_logging():
    """配置日志"""
    os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, LOG_LEVEL, logging.INFO))

    formatter = logging.Formatter(LOG_FORMAT)

    console = logging.StreamHandler()
    console.setFormatter(formatter)
    root_logger.addHandler(console)

    file_handler = logging.FileHandler(LOG_FILE, encoding='utf-8')
    file_handler.setFormatter(formatter)
    root_logger.addHandler(file_handler)


logger = logging.getLogger('main')


def run_api_server():
    """API 服务进程"""
    from api import start_api_server
    start_api_server()


def run_scheduler():
    """调度器进程 - 优化版：批量操作 + 采样检查"""
    from db import get_db
    from getter import ProxyCrawler
    from validator import ProxyValidator
    from api import _crawl_event

    db = get_db()
    db.init_db()
    crawler = ProxyCrawler()
    validator = ProxyValidator()

    stats = db.get_stats()
    logger.info(f'Scheduler started. DB: {stats["total"]} proxies')

    def do_crawl_and_validate():
        """执行一轮采集+验证（批量操作优化）"""
        from utils import enrich_proxies

        logger.info('=== Starting crawl cycle ===')

        # 1. 采集
        crawled = crawler.crawl_all()
        logger.info(f'Crawled {len(crawled)} proxies from sources')

        if crawled:
            # 1.5 查询 IP 地理位置
            try:
                enrich_proxies(crawled)
                logger.info(f'Enriched {len(crawled)} proxies with geo data')
            except Exception as e:
                logger.warning(f'Geo enrichment failed: {e}')

            # 2. 批量入库（单事务）
            inserted = db.batch_insert(crawled)
            logger.info(f'Inserted {inserted} proxies to DB')

        # 3. 分批验证
        all_proxies = db.get_all()
        logger.info(f'Validating {len(all_proxies)} proxies...')

        batch_size = VALIDATOR_CONCURRENCY
        total_valid = 0
        all_score_updates = []
        all_speed_updates = []

        for i in range(0, len(all_proxies), batch_size):
            batch = all_proxies[i:i + batch_size]
            valid, invalid, score_updates, speed_updates = validator.validate_batch(
                batch, max_workers=min(batch_size, 50)
            )
            total_valid += len(valid)
            all_score_updates.extend(score_updates)
            all_speed_updates.extend(speed_updates)

        # 4. 批量更新数据库（单事务）
        if all_score_updates:
            db.batch_update_score(all_score_updates)
        if all_speed_updates:
            db.batch_update_speed(all_speed_updates)

        # 5. 清除低分代理
        deleted = db.delete_by_score(MIN_SCORE)

        final_stats = db.get_stats()
        logger.info(
            f'=== Cycle done. Valid: {total_valid}, Cleaned: {deleted}, '
            f'Total: {final_stats["total"]}, AvgScore: {final_stats["avg_score"]} ==='
        )

    def do_health_check():
        """采样健康检查 - 只验证 30% 的代理，减少开销"""
        logger.info('=== Starting sample health check ===')
        all_proxies = db.get_all()

        if not all_proxies:
            logger.info('No proxies to check')
            return

        # 采样验证
        score_updates, speed_updates = validator.validate_sample(
            all_proxies,
            sample_ratio=0.3,
            max_workers=min(VALIDATOR_CONCURRENCY, 50)
        )

        # 批量更新
        if score_updates:
            db.batch_update_score(score_updates)
        if speed_updates:
            db.batch_update_speed(speed_updates)

        # 清除低分
        deleted = db.delete_by_score(MIN_SCORE)

        final_stats = db.get_stats()
        logger.info(
            f'=== Health check done. Updated: {len(score_updates)}, '
            f'Cleaned: {deleted}, Total: {final_stats["total"]} ==='
        )

    # 主循环
    last_crawl_time = 0
    last_check_time = 0

    while True:
        now = time.time()
        current_count = db.count()

        # 检查 API 触发
        api_triggered = _crawl_event.is_set()
        if api_triggered:
            _crawl_event.clear()
            logger.info('Crawl triggered by API request')

        # 采集条件：API触发 / 数量不足 / 到时间
        if api_triggered or current_count < MIN_PROXY_NUM or (now - last_crawl_time) >= CRAWL_INTERVAL:
            try:
                do_crawl_and_validate()
                last_crawl_time = time.time()
            except Exception as e:
                logger.error(f'Crawl cycle failed: {e}', exc_info=True)
                time.sleep(60)
                continue

        # 健康检查条件：到时间
        elif (now - last_check_time) >= CHECK_INTERVAL:
            try:
                do_health_check()
                last_check_time = time.time()
            except Exception as e:
                logger.error(f'Health check failed: {e}', exc_info=True)

        # 等待下一轮（支持 API 触发中断）
        sleep_time = min(
            CRAWL_INTERVAL - (time.time() - last_crawl_time),
            CHECK_INTERVAL - (time.time() - last_check_time),
            60
        )
        sleep_time = max(sleep_time, 5)
        logger.info(f'Sleeping {sleep_time:.0f}s. Proxies in DB: {db.count()}')

        for _ in range(int(sleep_time)):
            if _crawl_event.is_set():
                break
            time.sleep(1)


def main():
    parser = argparse.ArgumentParser(description='PyProxyPool - Python代理池')
    parser.add_argument('--api-only', action='store_true', help='只启动API服务')
    parser.add_argument('--scheduler-only', action='store_true', help='只启动调度器')
    parser.add_argument('--port', type=int, default=API_PORT, help='API端口')
    args = parser.parse_args()

    setup_logging()
    logger.info('='*50)
    logger.info('PyProxyPool starting...')
    logger.info(f'API: http://{API_HOST}:{args.port}')
    logger.info('='*50)

    processes = []

    if args.api_only:
        run_api_server()
        return

    if args.scheduler_only:
        run_scheduler()
        return

    p_api = Process(target=run_api_server, name='api-server', daemon=True)
    p_api.start()
    processes.append(p_api)
    logger.info(f'API server process started (PID: {p_api.pid})')

    p_scheduler = Process(target=run_scheduler, name='scheduler', daemon=True)
    p_scheduler.start()
    processes.append(p_scheduler)
    logger.info(f'Scheduler process started (PID: {p_scheduler.pid})')

    def shutdown(sig, frame):
        logger.info('Shutting down...')
        for p in processes:
            p.terminate()
            p.join(timeout=5)
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    try:
        for p in processes:
            p.join()
    except KeyboardInterrupt:
        shutdown(None, None)


if __name__ == '__main__':
    main()
