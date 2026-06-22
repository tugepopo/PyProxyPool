"""
数据模型定义
"""
from dataclasses import dataclass, field, asdict
from typing import Optional
import time


@dataclass
class ProxyIP:
    """代理IP数据模型"""
    ip: str
    port: int
    protocol: str = 'http'         # http / https
    anonymity: str = 'unknown'     # high(高匿) / anonymous(匿名) / transparent(透明)
    country: str = ''              # 国家/地区
    area: str = ''                 # 地区
    speed: float = 0               # 响应速度(ms)
    score: int = 10                # 评分
    source: str = ''               # 来源
    last_verified: float = 0       # 最后验证时间戳
    created_at: float = field(default_factory=time.time)

    @property
    def proxy_url(self) -> str:
        """返回代理URL"""
        return f'{self.protocol}://{self.ip}:{self.port}'

    @property
    def proxy_dict(self) -> dict:
        """返回 requests 兼容的代理字典"""
        return {
            'http': f'http://{self.ip}:{self.port}',
            'https': f'http://{self.ip}:{self.port}',
        }

    @property
    def address(self) -> str:
        return f'{self.ip}:{self.port}'

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> 'ProxyIP':
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})

    def __str__(self):
        return f'<Proxy {self.ip}:{self.port} {self.protocol} {self.anonymity} score={self.score} speed={self.speed}ms>'
