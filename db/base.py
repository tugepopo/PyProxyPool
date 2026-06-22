"""
数据库抽象基类
"""
from abc import ABC, abstractmethod
from typing import List, Optional
from models import ProxyIP


class BaseDB(ABC):
    """数据库接口基类"""

    @abstractmethod
    def init_db(self):
        """初始化数据库/表"""
        pass

    @abstractmethod
    def insert(self, proxy: ProxyIP) -> bool:
        """插入一条代理，已存在则更新"""
        pass

    @abstractmethod
    def batch_insert(self, proxies: List[ProxyIP]) -> int:
        """批量插入代理，返回成功数量"""
        pass

    @abstractmethod
    def get_all(self) -> List[ProxyIP]:
        """获取所有代理"""
        pass

    @abstractmethod
    def get_by_protocol(self, protocol: str) -> List[ProxyIP]:
        """按协议获取代理"""
        pass

    @abstractmethod
    def get_random(self, count: int = 1, protocol: str = None,
                   anonymity: str = None, min_score: int = 0) -> List[ProxyIP]:
        """随机获取代理"""
        pass

    @abstractmethod
    def delete(self, ip: str, port: int = None) -> int:
        """删除代理，返回删除数量"""
        pass

    @abstractmethod
    def delete_by_score(self, min_score: int) -> int:
        """删除低于指定评分的代理"""
        pass

    @abstractmethod
    def update_score(self, ip: str, port: int, score: int):
        """更新代理评分"""
        pass

    @abstractmethod
    def update_speed(self, ip: str, port: int, speed: float):
        """更新代理速度"""
        pass

    @abstractmethod
    def count(self) -> int:
        """返回代理总数"""
        pass

    @abstractmethod
    def exists(self, ip: str, port: int) -> bool:
        """检查代理是否存在"""
        pass

    def batch_update_score(self, updates: list) -> int:
        """批量更新评分 [(ip, port, score), ...]"""
        for ip, port, score in updates:
            self.update_score(ip, port, score)
        return len(updates)

    def batch_update_speed(self, updates: list) -> int:
        """批量更新速度 [(ip, port, speed), ...]"""
        for ip, port, speed in updates:
            self.update_speed(ip, port, speed)
        return len(updates)

    def delete_batch(self, keys: list) -> int:
        """批量删除 [(ip, port), ...]"""
        count = 0
        for ip, port in keys:
            count += self.delete(ip, port)
        return count

    def get_stats(self) -> dict:
        """获取统计信息"""
        return {'total': self.count()}

    @abstractmethod
    def close(self):
        """关闭连接"""
        pass
