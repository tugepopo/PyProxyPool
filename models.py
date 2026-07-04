"""
PyProxyPool — SQLAlchemy ORM Models (PostgreSQL)

替换原 dataclass 模型，新增评分/分级字段
"""
import json
from datetime import datetime

from sqlalchemy import (
    Column, String, Integer, Float, Boolean, Text, DateTime,
    Index, UniqueConstraint, ForeignKey,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """ORM 基类"""
    pass


# ==================== Proxy ====================

class Proxy(Base):
    """
    Proxy 数据模型 — 兼容原 ProxyIP 所有字段 + 新增评分字段
    """
    __tablename__ = 'proxies'

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    # 基础字段（原 ProxyIP 全部保留）
    ip: Mapped[str] = mapped_column(String(45), nullable=False)
    port: Mapped[int] = mapped_column(Integer, nullable=False)
    protocol: Mapped[str] = mapped_column(String(10), default='http', nullable=False)
    username: Mapped[str] = mapped_column(String(100), default='', nullable=False)
    password: Mapped[str] = mapped_column(String(200), default='', nullable=False)

    # 匿名级别
    anonymity: Mapped[str] = mapped_column(String(20), default='unknown', nullable=False)

    # 地理位置
    country: Mapped[str] = mapped_column(String(100), default='', nullable=False)
    area: Mapped[str] = mapped_column(String(200), default='', nullable=False)

    # 性能指标
    speed: Mapped[float] = mapped_column(Float, default=0.0)
    score: Mapped[int] = mapped_column(Integer, default=10)
    last_verified: Mapped[float] = mapped_column(Float, default=0.0)
    use_count: Mapped[int] = mapped_column(Integer, default=0)

    # 来源
    source: Mapped[str] = mapped_column(String(200), default='', nullable=False)

    # 出口 IP（通过代理访问后的出口 IP）
    outlet_ip: Mapped[str] = mapped_column(String(45), default='', nullable=False)

    # 出口 IP 与源 IP 不同（匿名性验证）
    is_outbound_ip: Mapped[bool] = mapped_column(Boolean, default=False)

    # ---- IP 纯净度检测字段 ----
    purity_score: Mapped[int] = mapped_column(Integer, default=0)
    purity_class: Mapped[str] = mapped_column(String(50), default='', nullable=False)
    is_datacenter: Mapped[bool] = mapped_column(Boolean, default=False)
    is_proxy: Mapped[bool] = mapped_column(Boolean, default=False)
    is_vpn: Mapped[bool] = mapped_column(Boolean, default=False)
    is_tor: Mapped[bool] = mapped_column(Boolean, default=False)
    abuse_confidence: Mapped[int] = mapped_column(Integer, default=0)
    isp: Mapped[str] = mapped_column(String(200), default='', nullable=False)
    asn: Mapped[str] = mapped_column(String(50), default='', nullable=False)
    asn_owner: Mapped[str] = mapped_column(String(200), default='', nullable=False)
    org_name: Mapped[str] = mapped_column(String(200), default='', nullable=False)
    ip_type: Mapped[str] = mapped_column(String(50), default='', nullable=False)
    is_native: Mapped[bool] = mapped_column(Boolean, default=False)
    shared_users: Mapped[str] = mapped_column(String(50), default='', nullable=False)
    risk_score: Mapped[int] = mapped_column(Integer, default=0)
    risk_level: Mapped[str] = mapped_column(String(20), default='', nullable=False)
    rdns: Mapped[str] = mapped_column(String(200), default='', nullable=False)
    scenes: Mapped[str] = mapped_column(Text, default='', nullable=False)
    ping0_location: Mapped[str] = mapped_column(String(200), default='', nullable=False)
    ping0_latitude: Mapped[float] = mapped_column(Float, default=0.0)
    ping0_longitude: Mapped[float] = mapped_column(Float, default=0.0)

    # ---- 新增：四维度加权评分 ----
    scan_score: Mapped[float] = mapped_column(Float, default=0.0, comment='四维度加权综合评分')
    grade: Mapped[str] = mapped_column(String(1), default='', nullable=False, comment='等级 A/B/C/D')

    # 标签（JSON 存储）
    tags: Mapped[str] = mapped_column(String(500), default='[]', nullable=False)

    # 时间戳
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow,
    )

    # 索引
    __table_args__ = (
        UniqueConstraint('ip', 'port', name='uq_proxy_ip_port'),
        Index('idx_proxy_score', 'score'),
        Index('idx_proxy_grade', 'grade'),
        Index('idx_proxy_protocol', 'protocol'),
        Index('idx_proxy_country', 'country'),
        Index('idx_proxy_last_verified', 'last_verified'),
        Index('idx_proxy_purity_class', 'purity_class'),
    )

    @property
    def proxy_url(self) -> str:
        """返回代理 URL"""
        url = f'{self.protocol}://{self.ip}:{self.port}'
        if self.username:
            url = f'{self.protocol}://{self.username}:{self.password}@{self.ip}:{self.port}'
        return url

    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            'ip': self.ip,
            'port': self.port,
            'protocol': self.protocol,
            'username': self.username,
            'password': self.password,
            'anonymity': self.anonymity,
            'country': self.country,
            'area': self.area,
            'speed': self.speed,
            'score': self.score,
            'scan_score': self.scan_score,
            'grade': self.grade,
            'source': self.source,
            'last_verified': self.last_verified,
            'use_count': self.use_count,
            'purity_score': self.purity_score,
            'purity_class': self.purity_class,
            'is_datacenter': self.is_datacenter,
            'is_proxy': self.is_proxy,
            'is_vpn': self.is_vpn,
            'is_tor': self.is_tor,
            'abuse_confidence': self.abuse_confidence,
            'isp': self.isp,
            'asn': self.asn,
            'asn_owner': self.asn_owner,
            'org_name': self.org_name,
            'ip_type': self.ip_type,
            'is_native': self.is_native,
            'shared_users': self.shared_users,
            'risk_score': self.risk_score,
            'risk_level': self.risk_level,
            'rdns': self.rdns,
            'scenes': self.scenes,
            'ping0_location': self.ping0_location,
            'ping0_latitude': self.ping0_latitude,
            'ping0_longitude': self.ping0_longitude,
            'tags': self.tags,
            'outlet_ip': self.outlet_ip,
            'is_outbound_ip': self.is_outbound_ip,
        }


# ==================== Scan Task ====================

class ScanTask(Base):
    """扫描任务记录"""
    __tablename__ = 'scan_tasks'

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    task_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default='pending', nullable=False)
    total: Mapped[int] = mapped_column(Integer, default=0)
    processed: Mapped[int] = mapped_column(Integer, default=0)
    valid: Mapped[int] = mapped_column(Integer, default=0)
    invalid: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow,
    )

    results: Mapped[list['ScanResult']] = relationship(
        back_populates='task', cascade='all, delete-orphan',
    )


# ==================== Scan Result ====================

class ScanResult(Base):
    """扫描详细结果"""
    __tablename__ = 'scan_results'

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    task_id: Mapped[str] = mapped_column(String(64), ForeignKey('scan_tasks.task_id'), nullable=False)
    ip: Mapped[str] = mapped_column(String(45), nullable=False)
    port: Mapped[int] = mapped_column(Integer, nullable=False)
    protocol: Mapped[str] = mapped_column(String(10), default='')
    is_valid: Mapped[bool] = mapped_column(Boolean, default=False)
    latency_ms: Mapped[float] = mapped_column(Float, default=0.0)
    outlet_ip: Mapped[str] = mapped_column(String(45), default='')
    country: Mapped[str] = mapped_column(String(100), default='', nullable=False)
    isp: Mapped[str] = mapped_column(String(200), default='')
    asn: Mapped[str] = mapped_column(String(50), default='')
    error: Mapped[str] = mapped_column(String(500), default='')
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    task: Mapped['ScanTask'] = relationship(back_populates='results')

    __table_args__ = (
        Index('idx_scan_result_task', 'task_id'),
    )


# ==================== Whitelist ====================

class WhitelistEntry(Base):
    """白名单条目"""
    __tablename__ = 'whitelist'

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    ip: Mapped[str] = mapped_column(String(45), nullable=False)
    port: Mapped[int] = mapped_column(Integer, nullable=False)
    protocol: Mapped[str] = mapped_column(String(10), default='http')
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint('ip', 'port', name='uq_whitelist_ip_port'),
    )


# ==================== Blacklist ====================

class BlacklistEntry(Base):
    """黑名单条目"""
    __tablename__ = 'blacklist'

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    ip: Mapped[str] = mapped_column(String(45), nullable=False)
    port: Mapped[int] = mapped_column(Integer, nullable=False)
    protocol: Mapped[str] = mapped_column(String(10), default='http')
    reason: Mapped[str] = mapped_column(String(500), default='')
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint('ip', 'port', name='uq_blacklist_ip_port'),
    )


# Re-export for backward compatibility
ProxyIP = Proxy  # alias for backward compatibility