"""
PyProxyPool — Pydantic v2 Schemas (Request / Response)
"""
from datetime import datetime
from typing import Optional, List, Any, Dict, TypeVar, Generic
from pydantic import BaseModel, Field, ConfigDict
from pydantic.generics import GenericModel


# ==================== Proxy Schemas ====================

class ProxyBase(BaseModel):
    """Proxy 基础字段"""
    model_config = ConfigDict(from_attributes=True)
    ip: str
    port: int
    protocol: str = 'http'
    username: str = ''
    password: str = ''


class ProxyCreate(ProxyBase):
    """创建 Proxy 请求"""
    source: str = ''
    score: int = Field(default=10, ge=0, le=100)
    anonymity: str = 'unknown'
    country: str = ''
    area: str = ''
    speed: float = Field(default=0.0, ge=0)
    tags: str = ''  # JSON string


class ProxyUpdate(BaseModel):
    """更新 Proxy 请求"""
    score: Optional[int] = None
    speed: Optional[float] = None
    anonymity: Optional[str] = None
    country: Optional[str] = None
    area: Optional[str] = None
    last_verified: Optional[float] = None
    use_count: Optional[int] = None
    purity_score: Optional[int] = None
    purity_class: Optional[str] = None
    abuse_confidence: Optional[int] = None
    risk_score: Optional[int] = None
    grade: Optional[str] = None
    scan_score: Optional[float] = None


class ProxyResponse(BaseModel):
    """Proxy 响应"""
    model_config = ConfigDict(from_attributes=True)
    ip: str
    port: int
    protocol: str = 'http'
    username: str = ''
    password: str = ''
    anonymity: str = 'unknown'
    country: str = ''
    area: str = ''
    speed: float = 0.0
    score: int = 10
    scan_score: float = 0.0
    grade: str = ''
    source: str = ''
    last_verified: float = 0.0
    use_count: int = 0
    purity_score: int = 0
    purity_class: str = ''
    is_datacenter: bool = False
    is_proxy: bool = False
    is_vpn: bool = False
    is_tor: bool = False
    abuse_confidence: int = 0
    isp: str = ''
    asn: str = ''
    asn_owner: str = ''
    org_name: str = ''
    ip_type: str = ''
    is_native: bool = False
    shared_users: str = ''
    risk_score: int = 0
    risk_level: str = ''
    rdns: str = ''
    scenes: str = ''
    ping0_location: str = ''
    ping0_latitude: float = 0.0
    ping0_longitude: float = 0.0
    tags: str = ''
    created_at: datetime | None = None
    outlet_ip: str = ''
    is_outbound_ip: bool = False

    @property
    def proxy_url(self) -> str:
        """返回代理 URL"""
        url = f'{self.protocol}://{self.ip}:{self.port}'
        if self.username:
            url = f'{self.protocol}://{self.username}:{self.password}@{self.ip}:{self.port}'
        return url


# ==================== Scan Schemas ====================

class ScanRequest(BaseModel):
    """触发扫描请求"""
    task_id: Optional[str] = None
    batch_size: int = Field(default=500, ge=1, le=2000)


class ScanResponse(BaseModel):
    """扫描结果响应"""
    task_id: str
    status: str  # pending / running / completed / failed
    total: int = 0
    processed: int = 0
    valid: int = 0
    invalid: int = 0
    created_at: datetime | None = None
    updated_at: datetime | None = None


class ScanStatusResponse(BaseModel):
    """扫描状态查询响应"""
    task_id: str
    status: str
    total: int
    processed: int
    valid: int
    invalid: int
    progress_percent: float = 0.0
    created_at: datetime | None = None
    updated_at: datetime | None = None


# ==================== Stats Schemas ====================

class StatsResponse(BaseModel):
    """系统统计响应"""
    total: int = 0
    http: int = 0
    https: int = 0
    socks5: int = 0
    avg_score: float = 0.0
    min_score: float = 0.0
    max_score: float = 0.0
    avg_speed: float = 0.0
    grade_a: int = 0
    grade_b: int = 0
    grade_c: int = 0
    grade_d: int = 0
    recent_24h_added: int = 0
    recent_24h_removed: int = 0
    uptime_seconds: float = 0.0
    uptime_human: str = ''


class SourceStatsResponse(BaseModel):
    """采集源统计"""
    source: str
    count: int = 0
    avg_score: float = 0.0
    avg_speed: float = 0.0
    status: str = 'active'
    consecutive_failures: int = 0


class CountryStatsResponse(BaseModel):
    """国家统计"""
    country: str
    count: int = 0
    avg_score: float = 0.0


class SpeedDistributionResponse(BaseModel):
    """速度分布"""
    untested: int = 0
    fast: int = 0        # <= 200ms
    good: int = 0        # 200-500ms
    medium: int = 0      # 500-1000ms
    slow: int = 0        # 1000-3000ms
    very_slow: int = 0   # > 3000ms


class ScoreDistributionResponse(BaseModel):
    """评分分布"""
    excellent: int = 0   # >= 80
    good: int = 0        # 60-80
    fair: int = 0        # 40-60
    poor: int = 0        # 20-40
    bad: int = 0         # < 20


# ==================== Export Schemas ====================

class ExportRequest(BaseModel):
    """导出请求"""
    format: str = 'json'  # json / csv / txt
    grade: str = 'all'
    protocol: str = 'all'
    min_score: int = 0


class ExportResponse(BaseModel):
    """导出响应（仅用于元数据）"""
    count: int = 0
    exported_at: str = ''
    format: str = 'json'


# ==================== Common Schemas ====================

T = TypeVar('T')


class PaginatedResponse(GenericModel):
    """分页响应基类"""
    total: int = 0
    page: int = 1
    page_size: int = 20
    pages: int = 1
    has_next: bool = False
    has_prev: bool = False
    items: List[T] = []


class ErrorResponse(BaseModel):
    """错误响应"""
    error: str
    message: str = ''
    code: int = 500


class SuccessResponse(BaseModel):
    """通用成功响应"""
    success: bool = True
    message: str = 'OK'
    data: Any = None