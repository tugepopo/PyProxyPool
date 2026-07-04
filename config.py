"""
PyProxyPool 配置文件 — Pydantic Settings 重构版
保留所有现有环境变量兼容，新增异步基础设施配置
"""
import os
from typing import List, Dict, Any, Optional
import logging
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field

logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    """
    PyProxyPool 全局配置（Pydantic Settings）
    兼容原 config.py 所有常量名，可通过环境变量或 .env 文件覆盖
    """
    model_config = SettingsConfigDict(
        env_file='.env',
        env_file_encoding='utf-8',
        case_sensitive=False,
        extra='ignore',
    )

    # ==================== 基础路径 ====================
    BASE_DIR: str = Field(
        default_factory=lambda: os.path.dirname(os.path.abspath(__file__)),
        description='项目根目录',
    )

    # ==================== 数据库配置 ====================
    DATABASE_URL: str = Field(
        default='sqlite+aiosqlite:///data/proxy.db',
        description='数据库连接 URL。默认 SQLite(aiosqlite)，可改为 postgresql+asyncpg:// 使用 PostgreSQL',
    )
    DATABASE_POOL_SIZE: int = Field(default=20, description='连接池大小（PostgreSQL 专用）')
    DATABASE_MAX_OVERFLOW: int = Field(default=10, description='连接池最大溢出（PostgreSQL 专用）')
    DATABASE_POOL_RECYCLE: int = Field(default=3600, description='连接回收秒数（PostgreSQL 专用）')

    # 保留原 DB_TYPE / DB_CONFIG 兼容
    DB_TYPE: str = Field(default='sqlite', description='数据库类型（兼容）')
    SQLITE_PATH: Optional[str] = Field(
        default=None,
        description='SQLite 数据库路径（兼容旧配置）',
    )

    # ==================== Redis 配置 ====================
    REDIS_URL: str = Field(
        default='redis://localhost:6379/0',
        description='Redis 连接 URL',
    )
    REDIS_CACHE_TTL: int = Field(default=3600, description='Redis 缓存默认 TTL（秒）')

    # ==================== API 配置 ====================
    API_HOST: str = Field(default='0.0.0.0', description='API 绑定地址')
    API_PORT: int = Field(default=8000, description='API 端口')
    API_KEY: str = Field(default='', description='API 认证密钥（空则不认证）')

    # ==================== 代理源配置 ====================
    GITHUB_API_TOKEN: str = Field(default='', description='GitHub API Token')

    # ==================== 验证配置 ====================
    VERIFY_URLS: List[str] = Field(
        default=['http://httpbin.org/ip', 'http://ip.sb', 'http://ip-api.com/json'],
        description='验证目标 URL 列表',
    )
    VERIFY_TIMEOUT: int = Field(default=8, description='验证超时（秒）')
    MAX_SPEED_MS: int = Field(default=3000, description='最大可接受速度（毫秒）')
    MIN_SCORE: int = Field(default=2, description='最低评分，低于此值的代理将被清除')

    # ==================== 调度配置 ====================
    MIN_PROXY_NUM: int = Field(default=50, description='代理池最小数量')
    CHECK_INTERVAL: int = Field(default=600, description='健康检查间隔（秒）')
    CRAWL_INTERVAL: int = Field(default=600, description='采集间隔（秒）')
    VALIDATOR_CONCURRENCY: int = Field(default=100, description='验证并发数')
    SCAN_CONCURRENCY: int = Field(default=100, description='扫描并发数（Semaphore）')
    MAX_RETRY: int = Field(default=2, description='单个采集源最大重试次数')

    # ==================== Ping0 并发数 ====================
    PING0_CONCURRENCY: int = Field(default=50, description='Ping0 查询并发数')
    PING0_MAX_PER_CYCLE: int = Field(default=200, description='每轮采集最大 Ping0 查询数')
    PING0_LOOKUP_TIMEOUT: int = Field(default=12, description='Ping0 查询超时（秒）')

    # ==================== 评分规则 ====================
    INITIAL_SCORE: int = Field(default=10, description='初始评分')
    SCORE_ADD_SUCCESS: int = Field(default=2, description='验证成功加分')
    SCORE_DEDUCT_FAIL: int = Field(default=3, description='验证失败扣分')

    # ==================== HTTP 请求配置 ====================
    USER_AGENTS: List[str] = Field(
        default=[
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36',
            'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36',
            'Mozilla/5.0 Firefox/121.0',
        ],
        description='请求 User-Agent 列表',
    )
    REQUEST_TIMEOUT: int = Field(default=10, description='HTTP 请求超时（秒）')

    # ==================== 日志配置 ====================
    LOG_LEVEL: str = Field(default='INFO', description='日志级别')
    LOG_FORMAT: str = Field(
        default='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
        description='日志格式',
    )
    LOG_FILE: Optional[str] = Field(
        default=None,
        description='日志文件路径',
    )
    LOG_ROTATE_BY_SIZE: bool = Field(default=True, description='按大小轮转')
    LOG_MAX_BYTES: int = Field(default=50 * 1024 * 1024, description='最大日志文件大小')
    LOG_BACKUP_COUNT: int = Field(default=10, description='保留日志文件数')
    LOG_ROTATE_WHEN: str = Field(default='midnight', description='时间轮转周期')
    LOG_LEVEL_CONSOLE: str = Field(default='DEBUG', description='控制台日志级别')
    LOG_LEVEL_FILE: str = Field(default='INFO', description='文件日志级别')

    # ==================== IP 纯净度检测配置 ====================
    ENABLE_PURITY_CHECK: bool = Field(default=True, description='是否启用纯净度检测')
    MIN_PURITY_SCORE: int = Field(default=20, description='最低纯净度评分')
    ABUSEIPDB_API_KEY: str = Field(default='', description='AbuseIPDB API Key')
    IPQUALITYSCORE_API_KEY: str = Field(default='', description='IpQualityScore API Key')
    IPINFO_TOKEN: str = Field(default='', description='IPInfo API Token')
    IPGEOAPI_TOKEN: str = Field(default='', description='IPGeoAPI API Token')
    ENABLE_TOR_CACHE: bool = Field(default=True, description='是否启用 Tor 出口节点缓存')

    # 纯净度评分权重
    PURITY_WEIGHTS: Dict[str, float] = Field(
        default={
            'datacenter': 0.30,
            'proxy': 0.25,
            'vpn': 0.20,
            'tor': 0.15,
            'abuse': 0.10,
        },
        description='纯净度评分权重',
    )

    # ==================== Rate Limiting ====================
    RATE_LIMIT_ENABLED: bool = Field(default=True, description='是否启用频率限制')
    RATE_LIMIT_REQUESTS: int = Field(default=60, description='每分钟最大请求数')
    RATE_LIMIT_WINDOW: int = Field(default=60, description='频率限制窗口（秒）')

    # ==================== 监控告警 ====================
    ALERT_WEBHOOK_URL: str = Field(default='', description='告警 Webhook URL')
    ALERT_WEBHOOK_SECRET: str = Field(default='', description='告警 Webhook Secret')
    ALERT_MIN_PROXIES: int = Field(default=10, description='触发告警的最小代理数量')
    ALERT_COOLDOWN: int = Field(default=300, description='告警冷却时间（秒）')

    # ==================== Alembic ====================
    ALEMBIC_CONFIG_PATH: str = Field(
        default='migrations/alembic.ini',
        description='Alembic 配置文件路径',
    )

    # ==================== GeoIP 配置 ====================
    GEOIP_DB_SOURCE: str = Field(default='geolite2', description='GeoIP 数据源: geolite2 / metacubex')
    GEOIP_DB_PATH: str = Field(default='', description='GeoIP 数据库路径（留空自动计算）')
    GEOIP_DB_UPDATE_INTERVAL: int = Field(default=604800, description='数据库自动更新间隔（秒），默认 7 天')
    GEOIP_DB_DOWNLOAD_URL: str = Field(
        default='https://github.com/P3TERX/GeoLite.mmdb/releases/latest/download/GeoLite2-City.mmdb',
        description='数据库下载地址（默认 P3TERX 社区镜像，无需注册）',
    )
    GEOIP_DB_AUTO_UPDATE: bool = Field(default=True, description='是否启用自动更新')

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # 初始化日志文件路径（兼容原 config.LOG_FILE）
        if self.LOG_FILE is None:
            self.LOG_FILE = os.path.join(self.BASE_DIR, 'logs', 'proxypool.log')
        # 初始化 SQLite 路径
        if self.SQLITE_PATH is None:
            self.SQLITE_PATH = os.path.join(self.BASE_DIR, 'data', 'proxy.db')
        # 自动计算 GeoIP 数据库路径
        if not self.GEOIP_DB_PATH:
            self.GEOIP_DB_PATH = os.path.join(self.BASE_DIR, 'data', 'geoip', 'GeoLite2-City.mmdb')

    # ---- 兼容原 config.py 常量名（作为属性别名） ----
    @property
    def DB_CONFIG(self) -> Dict[str, Any]:
        """兼容原 config.DB_CONFIG"""
        return {
            'sqlite': {'path': self.SQLITE_PATH or os.path.join(self.BASE_DIR, 'data', 'proxy.db')},
        }

    @property
    def REQUEST_HEADERS(self) -> Dict[str, str]:
        """兼容原 config.REQUEST_HEADERS"""
        return {
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
            'Accept-Encoding': 'gzip, deflate',
            'Connection': 'keep-alive',
        }

    @property
    def PROXY_SOURCES(self) -> List[Dict[str, Any]]:
        """兼容原 config.PROXY_SOURCES — 代理源配置"""
        return [
            # GitHub 纯文本代理列表
            {
                'name': 'mmpx1988',
                'type': 'github',
                'urls': ['https://raw.githubusercontent.com/mmpx123/proxy-list/main/http.txt'],
            },
            {
                'name': 'TheRealProxies-https',
                'type': 'github',
                'urls': ['https://raw.githubusercontent.com/TheRealProxies/https-proxies/main/https-proxy.txt'],
            },
            {
                'name': 'TheRealProxies-http',
                'type': 'github',
                'urls': ['https://raw.githubusercontent.com/TheRealProxies/http-proxies/main/http-proxy.txt'],
            },
            {
                'name': 'TheRealProxies-socks',
                'type': 'github',
                'urls': ['https://raw.githubusercontent.com/TheRealProxies/socks-proxies/main/socks-proxy.txt'],
            },
            {
                'name': 'erikgahm',
                'type': 'github',
                'urls': ['https://raw.githubusercontent.com/erikgahm/proxy-list/main/raw/http.txt'],
            },
            {
                'name': 'roosterkid',
                'type': 'github',
                'urls': ['https://raw.githubusercontent.com/roosterkid/openproxylist/main/HTTPS_RAW.txt'],
            },
            {
                'name': 'JohanChang',
                'type': 'github',
                'urls': [
                    'https://raw.githubusercontent.com/JohanChang/proxy-list/master/http.txt',
                    'https://raw.githubusercontent.com/JohanChang/proxy-list/master/https.txt',
                ],
            },
            {
                'name': 'freeproxymedia',
                'type': 'github',
                'urls': ['https://raw.githubusercontent.com/freeproxymedia/proxy-list/main/http.txt'],
            },
            {
                'name': 'Shifty369',
                'type': 'github',
                'urls': ['https://raw.githubusercontent.com/Shifty369/proxy-list/master/http.txt'],
            },
            {
                'name': 'proxylistdownload',
                'type': 'github',
                'urls': ['https://raw.githubusercontent.com/proxylistdownload/proxy-list/main/http.txt'],
            },
            # HTML 表格类型代理源
            {
                'name': 'spys.one',
                'type': 'table',
                'urls': ['https://spys.one/ru/proxy-list/', 'https://spys.one/ru/proxy-list/2/', 'https://spys.one/ru/proxy-list/3/'],
            },
            {
                'name': 'free-proxy.cz',
                'type': 'table',
                'urls': ['https://free-proxy.cz/ru/proxylist/main'],
            },
            {
                'name': 'proxydb.net',
                'type': 'table',
                'urls': ['https://proxydb.net/'],
            },
            {
                'name': 'proxies.org',
                'type': 'table',
                'urls': ['https://proxies.org/proxy-list/'],
            },
            {
                'name': 'proxy-list.org',
                'type': 'table',
                'urls': ['https://proxy-list.org/english/index.php'],
            },
            {
                'name': 'us-proxy.org',
                'type': 'table',
                'urls': ['https://us-proxy.org/'],
            },
        ]


# 全局单例
_settings: Optional[Settings] = None


def get_settings() -> Settings:
    """获取全局配置单例"""
    global _settings
    if _settings is None:
        _settings = Settings()
        db_url = _settings.DATABASE_URL.split("@")[-1] if "@" in _settings.DATABASE_URL else _settings.DATABASE_URL
        logger.info(f'配置加载完成: 数据库={db_url}, 日志级别={_settings.LOG_LEVEL}')
    return _settings


def reload_settings() -> Settings:
    """重新加载配置（用于 SIGHUP 热重载）"""
    global _settings
    _settings = Settings()
    db_url = _settings.DATABASE_URL.split("@")[-1] if "@" in _settings.DATABASE_URL else _settings.DATABASE_URL
    logger.info(f'配置已重载: 数据库={db_url}')
    return _settings


# 默认实例（供直接导入使用）
settings = get_settings()

# 兼容原 config.py 直接导入常量名
PROXY_SOURCES = settings.PROXY_SOURCES
DB_TYPE = settings.DB_TYPE
DB_CONFIG = settings.DB_CONFIG
VERIFY_URLS = settings.VERIFY_URLS
VERIFY_TIMEOUT = settings.VERIFY_TIMEOUT
MAX_SPEED_MS = settings.MAX_SPEED_MS
MIN_SCORE = settings.MIN_SCORE
MIN_PROXY_NUM = settings.MIN_PROXY_NUM
CHECK_INTERVAL = settings.CHECK_INTERVAL
CRAWL_INTERVAL = settings.CRAWL_INTERVAL
VALIDATOR_CONCURRENCY = settings.VALIDATOR_CONCURRENCY
MAX_RETRY = settings.MAX_RETRY
API_HOST = settings.API_HOST
API_PORT = settings.API_PORT
API_KEY = settings.API_KEY
INITIAL_SCORE = settings.INITIAL_SCORE
SCORE_ADD_SUCCESS = settings.SCORE_ADD_SUCCESS
SCORE_DEDUCT_FAIL = settings.SCORE_DEDUCT_FAIL
USER_AGENTS = settings.USER_AGENTS
REQUEST_TIMEOUT = settings.REQUEST_TIMEOUT
REQUEST_HEADERS = settings.REQUEST_HEADERS
LOG_LEVEL = settings.LOG_LEVEL
LOG_FORMAT = settings.LOG_FORMAT
LOG_FILE = settings.LOG_FILE
LOG_ROTATE_BY_SIZE = settings.LOG_ROTATE_BY_SIZE
LOG_MAX_BYTES = settings.LOG_MAX_BYTES
LOG_BACKUP_COUNT = settings.LOG_BACKUP_COUNT
LOG_ROTATE_WHEN = settings.LOG_ROTATE_WHEN
LOG_LEVEL_CONSOLE = settings.LOG_LEVEL_CONSOLE
LOG_LEVEL_FILE = settings.LOG_LEVEL_FILE
ENABLE_PURITY_CHECK = settings.ENABLE_PURITY_CHECK
PING0_MAX_PER_CYCLE = settings.PING0_MAX_PER_CYCLE
MIN_PURITY_SCORE = settings.MIN_PURITY_SCORE
ABUSEIPDB_API_KEY = settings.ABUSEIPDB_API_KEY
IPQUALITYSCORE_API_KEY = settings.IPQUALITYSCORE_API_KEY
IPINFO_TOKEN = settings.IPINFO_TOKEN
IPGEOAPI_TOKEN = settings.IPGEOAPI_TOKEN
PING0_LOOKUP_TIMEOUT = settings.PING0_LOOKUP_TIMEOUT
PING0_CONCURRENCY = settings.PING0_CONCURRENCY
ENABLE_TOR_CACHE = settings.ENABLE_TOR_CACHE
PURITY_WEIGHTS = settings.PURITY_WEIGHTS
RATE_LIMIT_ENABLED = settings.RATE_LIMIT_ENABLED
RATE_LIMIT_REQUESTS = settings.RATE_LIMIT_REQUESTS
RATE_LIMIT_WINDOW = settings.RATE_LIMIT_WINDOW
ALERT_WEBHOOK_URL = settings.ALERT_WEBHOOK_URL
ALERT_WEBHOOK_SECRET = settings.ALERT_WEBHOOK_SECRET
ALERT_MIN_PROXIES = settings.ALERT_MIN_PROXIES
ALERT_COOLDOWN = settings.ALERT_COOLDOWN
GITHUB_API_TOKEN = settings.GITHUB_API_TOKEN

# 速度评分函数（兼容原 config.speed_score）
def speed_score(speed_ms: float) -> int:
    """根据响应速度（毫秒）返回速度评分调整值"""
    if speed_ms < 500:
        return 2
    elif speed_ms < 1000:
        return 1
    elif speed_ms < 2000:
        return 0
    else:
        return -1