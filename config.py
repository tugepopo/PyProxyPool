"""
PyProxyPool 配置文件
"""
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# ==================== 代理源配置 ====================
# 每个代理源的解析规则
# type: xpath / module / regex
# position: 字段映射 {ip, port, type, protocol}
#   type: 0=高匿, 1=匿名, 2=透明
#   protocol: 0=http, 1=https, 2=http/https

PROXY_SOURCES = [
    {
        'name': 'kuaidaili',
        'urls': ['https://www.kuaidaili.com/free/inha/%d/' % i for i in range(1, 6)],
        'type': 'xpath',
        'pattern': ".//table/tbody/tr",
        'position': {'ip': './td[1]', 'port': './td[2]', 'type': './td[3]', 'protocol': './td[4]'}
    },
    {
        'name': 'ip3366',
        'urls': ['http://www.ip3366.net/?stype=1&page=%d' % i for i in range(1, 7)],
        'type': 'xpath',
        'pattern': ".//div[@id='list']//table/tbody/tr",
        'position': {'ip': './td[1]', 'port': './td[2]', 'type': './td[3]', 'protocol': './td[4]'}
    },
    {
        'name': 'proxylistplus',
        'urls': ['https://list.proxylistplus.com/Fresh-HTTP-Proxy-List-%d' % i for i in [1, 2, 3]],
        'type': 'xpath',
        'pattern': ".//table[@class='bg']//tr[position()>2]",
        'position': {'ip': './td[2]', 'port': './td[3]', 'type': './td[5]', 'protocol': ''}
    },
    {
        'name': '66ip',
        'urls': ['https://www.66ip.cn/%s.html' % n for n in ['index'] + list(range(2, 6))],
        'type': 'xpath',
        'pattern': ".//div[@id='main']//table/tr[position()>1]",
        'position': {'ip': './td[1]', 'port': './td[2]', 'type': './td[4]', 'protocol': ''}
    },
    {
        'name': 'free-proxy-list',
        'urls': ['https://free-proxy-list.net/'],
        'type': 'xpath',
        'pattern': ".//table[@class='table table-striped table-bordered']//tbody/tr",
        'position': {'ip': './td[1]', 'port': './td[2]', 'type': './td[4]', 'protocol': './td[6]'}
    },
    {
        'name': 'data5u',
        'urls': ['http://www.data5u.com/free/gngn/index.shtml'],
        'type': 'xpath',
        'pattern': ".//ul[@class='l2']",
        'position': {'ip': './span[1]', 'port': './span[2]', 'type': '', 'protocol': './span[4]'}
    },
]

# ==================== 数据库配置 ====================
# 支持: sqlite, mysql, redis
DB_TYPE = 'sqlite'
DB_CONFIG = {
    'sqlite': {
        'path': os.path.join(BASE_DIR, 'data', 'proxy.db'),
    },
    'mysql': {
        'host': '127.0.0.1',
        'port': 3306,
        'user': 'root',
        'password': '',
        'database': 'proxypool',
        'charset': 'utf8mb4',
    },
    'redis': {
        'host': '127.0.0.1',
        'port': 6379,
        'db': 0,
        'password': None,
    },
}

# ==================== 验证配置 ====================
# 验证目标URL (用来测试代理是否可用)
VERIFY_URLS = [
    'http://httpbin.org/ip',
    'http://ip.sb',
    'http://ip-api.com/json',
]

# 超时设置(秒)
VERIFY_TIMEOUT = 8

# 响应速度上限(毫秒)，超过此值的代理将被降低评分
MAX_SPEED_MS = 3000

# 最低评分，低于此值的代理将被清除
MIN_SCORE = 2

# ==================== 调度配置 ====================
# 有效代理数量低于此值时触发采集
MIN_PROXY_NUM = 50

# 代理检测周期(秒)
CHECK_INTERVAL = 600  # 10分钟

# 每轮采集后等待时间(秒)
CRAWL_INTERVAL = 600

# 验证并发数
VALIDATOR_CONCURRENCY = 100

# 单个采集源的最大重试次数
MAX_RETRY = 2

# ==================== API 配置 ====================
API_HOST = '0.0.0.0'
API_PORT = 8000

# ==================== 评分规则 ====================
# 初始评分
INITIAL_SCORE = 10

# 验证成功加分
SCORE_ADD_SUCCESS = 2

# 验证失败扣分
SCORE_DEDUCT_FAIL = 3

# 速度评分 (毫秒 → 分)
# < 500ms: +2, < 1000ms: +1, < 2000ms: 0, >= 2000ms: -1
def speed_score(speed_ms):
    if speed_ms < 500:
        return 2
    elif speed_ms < 1000:
        return 1
    elif speed_ms < 2000:
        return 0
    else:
        return -1

# ==================== HTTP请求配置 ====================
USER_AGENTS = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0',
]

REQUEST_TIMEOUT = 10
REQUEST_HEADERS = {
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
    'Accept-Encoding': 'gzip, deflate',
    'Connection': 'keep-alive',
}

# ==================== 日志配置 ====================
LOG_LEVEL = 'INFO'
LOG_FORMAT = '%(asctime)s [%(levelname)s] %(name)s: %(message)s'
LOG_FILE = os.path.join(BASE_DIR, 'logs', 'proxypool.log')
