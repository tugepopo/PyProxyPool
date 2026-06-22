"""
API 服务器 - 优化版
优化点：缓存、更多端点、错误处理、统计接口
"""
import json
import time
import logging
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

from db import get_db
from config import API_HOST, API_PORT, MIN_SCORE
from api.dashboard import DASHBOARD_HTML

logger = logging.getLogger('api')

_db = None
_crawl_event = threading.Event()

# 简单缓存：stats 缓存 5 秒
_stats_cache = {'data': None, 'ts': 0}
_cache_lock = threading.Lock()


def _get_db():
    global _db
    if _db is None:
        _db = get_db()
        _db.init_db()
    return _db


def _get_cached_stats():
    """带缓存的统计查询"""
    with _cache_lock:
        if time.time() - _stats_cache['ts'] < 5 and _stats_cache['data']:
            return _stats_cache['data']
    db = _get_db()
    stats = db.get_stats()
    with _cache_lock:
        _stats_cache['data'] = stats
        _stats_cache['ts'] = time.time()
    return stats


class ProxyHandler(BaseHTTPRequestHandler):

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path.rstrip('/')
        params = parse_qs(parsed.query)

        routes = {
            '': self._handle_dashboard,
            '/': self._handle_dashboard,
            '/dashboard': self._handle_dashboard,
            '/proxy': self._handle_get_proxy,
            '/proxy/all': self._handle_get_all,
            '/proxy/http': self._handle_get_http,
            '/proxy/https': self._handle_get_https,
            '/delete': self._handle_delete,
            '/delete/batch': self._handle_delete_batch,
            '/cleanup': self._handle_cleanup,
            '/status': self._handle_status,
            '/stats': self._handle_stats,
        }

        handler = routes.get(path)
        if handler:
            try:
                handler(params)
            except Exception as e:
                logger.error(f'API error {path}: {e}', exc_info=True)
                self._json_response(500, {'error': str(e)})
        else:
            self._json_response(404, {'error': 'Not found'})

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path.rstrip('/')

        if path == '/crawl':
            self._handle_trigger_crawl()
        else:
            self._json_response(404, {'error': 'Not found'})

    # ==================== 页面 ====================

    def _handle_dashboard(self, params):
        self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.end_headers()
        self.wfile.write(DASHBOARD_HTML.encode('utf-8'))

    # ==================== API ====================

    def _handle_get_proxy(self, params):
        db = _get_db()
        count = min(int(params.get('count', [1])[0]), 100)

        anonymity_map = {'0': 'high', '1': 'anonymous', '2': 'transparent'}
        anonymity = anonymity_map.get(params.get('types', [None])[0])

        protocol_map = {'0': 'http', '1': 'https'}
        protocol = protocol_map.get(params.get('protocol', [None])[0])

        min_score = int(params.get('min_score', [MIN_SCORE])[0])

        proxies = db.get_random(count=count, protocol=protocol, anonymity=anonymity, min_score=min_score)
        self._json_response(200, [p.to_dict() for p in proxies])

    def _handle_get_all(self, params):
        db = _get_db()
        proxies = db.get_all()
        self._json_response(200, {'total': len(proxies), 'proxies': [p.to_dict() for p in proxies]})

    def _handle_get_http(self, params):
        db = _get_db()
        count = min(int(params.get('count', [10])[0]), 100)
        proxies = db.get_random(count=count, protocol='http', min_score=MIN_SCORE)
        self._json_response(200, [p.to_dict() for p in proxies])

    def _handle_get_https(self, params):
        db = _get_db()
        count = min(int(params.get('count', [10])[0]), 100)
        proxies = db.get_random(count=count, protocol='https', min_score=MIN_SCORE)
        self._json_response(200, [p.to_dict() for p in proxies])

    def _handle_delete(self, params):
        db = _get_db()
        ip = params.get('ip', [None])[0]
        port = params.get('port', [None])[0]
        if not ip:
            self._json_response(400, {'error': 'ip required'})
            return
        count = db.delete(ip, int(port) if port else None)
        self._json_response(200, {'deleted': count})

    def _handle_delete_batch(self, params):
        """GET /delete/batch?keys=ip:port,ip:port"""
        db = _get_db()
        keys_str = params.get('keys', [''])[0]
        if not keys_str:
            self._json_response(400, {'error': 'keys required (ip:port,ip:port,...)'})
            return
        keys = []
        for k in keys_str.split(','):
            parts = k.strip().split(':')
            if len(parts) == 2:
                keys.append((parts[0], int(parts[1])))
        count = db.delete_batch(keys)
        self._json_response(200, {'deleted': count})

    def _handle_cleanup(self, params):
        db = _get_db()
        min_score = int(params.get('min_score', [2])[0])
        count = db.delete_by_score(min_score)
        logger.info(f'Cleanup: deleted {count} proxies with score < {min_score}')
        self._json_response(200, {'deleted': count})

    def _handle_status(self, params):
        stats = _get_cached_stats()
        self._json_response(200, {
            'status': 'running',
            'total': stats['total'],
            'http': stats['http'],
            'https': stats['https'],
        })

    def _handle_stats(self, params):
        """GET /stats - 详细统计"""
        stats = _get_cached_stats()
        self._json_response(200, stats)

    def _handle_trigger_crawl(self):
        _crawl_event.set()
        logger.info('Crawl triggered via API')
        self._json_response(200, {'message': '采集已触发，请等待几秒后刷新查看'})

    def _json_response(self, status: int, data):
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Cache-Control', 'no-cache')
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False, indent=2).encode('utf-8'))

    def log_message(self, format, *args):
        path = args[0].split(' ')[1] if args else ''
        if path in ('/', '/dashboard', '/status', '/favicon.ico'):
            return
        logger.info(f'{self.client_address[0]} - {format % args}')


def start_api_server():
    db = _get_db()
    db.init_db()
    server = HTTPServer((API_HOST, API_PORT), ProxyHandler)
    logger.info(f'API server started at http://{API_HOST}:{API_PORT}')
    logger.info(f'Dashboard: http://{API_HOST}:{API_PORT}/dashboard')
    server.serve_forever()
