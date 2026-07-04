"""
PyProxyPool — 四维度加权评分引擎

评分维度：
- 存活率 (survival): 40%
- 延迟 (latency): 20%
- IP 类型 (ip_type): 20%
- 风险 (risk): 20%

评分结果分为 A / B / C / D 四级
"""
import logging
from typing import Union

logger = logging.getLogger(__name__)


class ScoringEngine:
    """
    四维度加权评分引擎

    Score = survival_score * 0.40
          + latency_score * 0.20
          + ip_type_score * 0.20
          + risk_score * 0.20

    分级规则：
    - A: score >= 80
    - B: 60 <= score < 80
    - C: 40 <= score < 60
    - D: score < 40
    """

    # 权重配置
    WEIGHTS = {
        'survival': 0.40,
        'latency': 0.20,
        'ip_type': 0.20,
        'risk': 0.20,
    }

    # IP 类型评分映射
    IP_TYPE_SCORES = {
        'residential': 100.0,           # 住宅 IP — 最纯净
        'residential_minor': 90.0,      # 轻微住宅
        'datacenter_clean': 80.0,       # 干净数据中心
        'datacenter': 50.0,             # 普通数据中心
        'proxy': 20.0,                  # 代理节点
        'vpn': 20.0,                    # VPN 节点
        'anonymizer': 10.0,             # 匿名器
        'tor': 0.0,                     # Tor 出口 — 风险最高
        'malicious': 0.0,               # 恶意 IP
    }

    def calculate(self, proxy: Union[object, dict]) -> float:
        """
        计算代理的综合评分

        Args:
            proxy: Proxy 模型对象或字典，需包含以下属性：
                - score (int): 基础可用性评分
                - speed (float): 响应速度（毫秒）
                - purity_class (str): IP 纯净度分类
                - abuse_confidence (int): AbuseIPDB 滥用置信度
                - risk_score (int): 风控评分
                - last_verified (float): 最后验证时间戳

        Returns:
            综合评分 (float, 0-100)
        """
        scores = {
            'survival': self._score_survival(proxy),
            'latency': self._score_latency(proxy),
            'ip_type': self._score_ip_type(proxy),
            'risk': self._score_risk(proxy),
        }

        weighted = sum(
            scores[k] * self.WEIGHTS[k]
            for k in self.WEIGHTS
        )

        logger.debug(
            f'评分计算: 存活率={scores["survival"]:.1f}×{self.WEIGHTS["survival"]:.0%} + '
            f'延迟={scores["latency"]:.1f}×{self.WEIGHTS["latency"]:.0%} + '
            f'IP类型={scores["ip_type"]:.1f}×{self.WEIGHTS["ip_type"]:.0%} + '
            f'风险={scores["risk"]:.1f}×{self.WEIGHTS["risk"]:.0%} = {weighted:.1f}'
        )

        return round(weighted, 1)

    def _score_survival(self, proxy: Union[object, dict]) -> float:
        """
        存活率评分子项

        基于原始 score 字段映射到 0-100
        score 100 → 100, score 0 → 0

        Args:
            proxy: Proxy 对象/字典

        Returns:
            存活率评分 (0-100)
        """
        try:
            raw_score = getattr(proxy, 'score', None)
            if raw_score is None:
                raw_score = proxy.get('score', 0)
            return max(0.0, min(100.0, float(raw_score)))
        except Exception:
            return 0.0

    def _score_latency(self, proxy: Union[object, dict]) -> float:
        """
        延迟评分子项

        公式: max(0, 100 - min(speed_ms, 5000) / 50)
        - speed < 500ms → score ≈ 90
        - speed < 1000ms → score ≈ 80
        - speed < 3000ms → score ≈ 40
        - speed >= 5000ms → score = 0

        Args:
            proxy: Proxy 对象/字典

        Returns:
            延迟评分 (0-100)
        """
        try:
            speed_ms = getattr(proxy, 'speed', None)
            if speed_ms is None:
                speed_ms = proxy.get('speed', 0)
            if speed_ms is None or speed_ms == 0:
                # 未测试的代理，延迟评分按 50 分计算（中性）
                return 50.0
            speed_ms = float(speed_ms)
            return max(0.0, 100.0 - min(speed_ms, 5000.0) / 50.0)
        except Exception:
            return 0.0

    def _score_ip_type(self, proxy: Union[object, dict]) -> float:
        """
        IP 类型评分子项

        基于 purity_class / ip_type 分类：
        - residential: 100
        - datacenter_clean: 80
        - datacenter: 50
        - proxy / vpn: 20
        - tor: 0

        Args:
            proxy: Proxy 对象/字典

        Returns:
            IP 类型评分 (0-100)
        """
        try:
            purity_class = getattr(proxy, 'purity_class', '')
            if not purity_class:
                purity_class = proxy.get('purity_class', '')

            if not purity_class:
                # 尝试从 ip_type 推断
                ip_type = getattr(proxy, 'ip_type', '')
                if not ip_type:
                    ip_type = proxy.get('ip_type', '')
                type_map = {
                    'residential': 'residential',
                    '住宅': 'residential',
                    '数据中心': 'datacenter',
                    '代理': 'proxy',
                    'vpn': 'vpn',
                    'tor': 'tor',
                }
                purity_class = type_map.get(ip_type, 'datacenter')

            if purity_class:
                score = self.IP_TYPE_SCORES.get(purity_class, 50.0)
                return float(score)

            # 默认值
            return 50.0
        except Exception:
            return 0.0

    def _score_risk(self, proxy: Union[object, dict]) -> float:
        """
        风险评分子项

        公式: max(0, 100 - risk_score - abuse_confidence * 0.5)
        风险越低评分越高

        Args:
            proxy: Proxy 对象/字典

        Returns:
            风险评分 (0-100)
        """
        try:
            risk_score = getattr(proxy, 'risk_score', 0)
            if risk_score is None:
                risk_score = proxy.get('risk_score', 0)
            abuse_confidence = getattr(proxy, 'abuse_confidence', 0)
            if abuse_confidence is None:
                abuse_confidence = proxy.get('abuse_confidence', 0)

            result = 100.0 - float(risk_score) - float(abuse_confidence) * 0.5
            return max(0.0, min(100.0, result))
        except Exception:
            return 0.0

    def grade_from_score(self, score: float) -> str:
        """
        根据评分返回等级

        Args:
            score: 综合评分 (0-100)

        Returns:
            等级字符串: 'A' | 'B' | 'C' | 'D'
        """
        if score >= 80:
            return 'A'
        elif score >= 60:
            return 'B'
        elif score >= 40:
            return 'C'
        else:
            return 'D'


# 全局单例
_scoring_engine = None


def get_scoring_engine() -> ScoringEngine:
    """获取评分引擎单例"""
    global _scoring_engine
    if _scoring_engine is None:
        _scoring_engine = ScoringEngine()
    return _scoring_engine