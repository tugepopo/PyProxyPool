"""
PyProxyPool — 多格式导出服务

支持 JSON / TXT / CSV 三种格式导出代理列表
"""
import csv
import io
import json
import logging
from datetime import datetime
from typing import List

from models import Proxy
from config import get_settings

logger = logging.getLogger(__name__)


class Exporter:
    """
    多格式导出服务
    """

    def export(
        self,
        proxies: List[Proxy],
        fmt: str = 'json',
    ) -> bytes:
        """
        导出代理列表

        Args:
            proxies: Proxy 对象列表
            fmt: 导出格式 ('json' / 'txt' / 'csv')

        Returns:
            导出内容（bytes）
        """
        if fmt == 'json':
            return self._export_json(proxies)
        elif fmt == 'txt':
            return self._export_txt(proxies)
        elif fmt == 'csv':
            return self._export_csv(proxies)
        else:
            raise ValueError(f'Unsupported format: {fmt}. Use json, csv, or txt')

    def _export_json(self, proxies: List[Proxy]) -> bytes:
        """导出为 JSON 格式"""
        data = {
            'count': len(proxies),
            'exported_at': datetime.now().isoformat(),
            'proxies': [p.to_dict() for p in proxies],
        }
        return json.dumps(data, ensure_ascii=False, indent=2).encode('utf-8')

    def _export_txt(self, proxies: List[Proxy]) -> bytes:
        """导出为 TXT 格式（ip:port 每行一个）"""
        lines = [f'{p.ip}:{p.port}' for p in proxies]
        return '\n'.join(lines).encode('utf-8')

    def _export_csv(self, proxies: List[Proxy]) -> bytes:
        """导出为 CSV 格式"""
        output = io.StringIO()
        writer = csv.writer(output)

        # 表头
        writer.writerow([
            'ip', 'port', 'protocol', 'username', 'password',
            'anonymity', 'country', 'area', 'speed', 'score',
            'scan_score', 'grade', 'source', 'last_verified',
            'use_count', 'purity_score', 'purity_class',
            'abuse_confidence', 'isp', 'asn', 'asn_owner',
            'risk_score', 'risk_level',
        ])

        # 数据行
        for p in proxies:
            writer.writerow([
                p.ip, p.port, p.protocol, p.username, p.password,
                p.anonymity, p.country, p.area, p.speed, p.score,
                p.scan_score, p.grade, p.source, p.last_verified,
                p.use_count, p.purity_score, p.purity_class,
                p.abuse_confidence, p.isp, p.asn, p.asn_owner,
                p.risk_score, p.risk_level,
            ])

        return output.getvalue().encode('utf-8')