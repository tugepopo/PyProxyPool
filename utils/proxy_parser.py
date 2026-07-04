"""
PyProxyPool — 代理解析器

支持 5 种格式：
1. IP:PORT
2. http://IP:PORT
3. socks5://IP:PORT
4. user:pass@IP:PORT
5. http://user:pass@IP:PORT
"""
import re
from urllib.parse import urlparse
from typing import Optional, List, Dict, Any


def parse_proxy(raw: str) -> Optional[Dict[str, Any]]:
    """
    解析单行代理字符串

    Args:
        raw: 原始代理字符串

    Returns:
        解析后的字典，包含 ip, port, protocol, username, password
        如果解析失败返回 None
    """
    if not raw or not raw.strip():
        return None

    raw = raw.strip()
    if raw.startswith('#') or raw.startswith('//'):
        return None

    # 格式5: http://user:pass@ip:port
    # 格式2: http://ip:port
    parsed = urlparse(raw)
    if parsed.scheme in ('http', 'https', 'socks4', 'socks5'):
        host = parsed.hostname or ''
        port = parsed.port
        username = parsed.username or ''
        password = parsed.password or ''

        # 如果 host 不是 IP，尝试进一步解析
        if not re.match(r'^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$', host):
            return None

        return {
            'ip': host,
            'port': port,
            'protocol': parsed.scheme,
            'username': username,
            'password': password,
        }

    # 格式4: user:pass@ip:port (无协议)
    m = re.match(r'^([^@:]+):([^@:]+)@(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}):(\d+)$', raw)
    if m:
        return {
            'ip': m.group(3),
            'port': int(m.group(4)),
            'protocol': 'http',
            'username': m.group(1),
            'password': m.group(2),
        }

    # 格式1: ip:port (纯 IP:端口，无协议)
    m = re.match(r'^(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}):(\d+)$', raw)
    if m:
        return {
            'ip': m.group(1),
            'port': int(m.group(2)),
            'protocol': 'http',
            'username': '',
            'password': '',
        }

    # 格式3: socks5://ip:port (已通过格式5的 urlparse 处理)
    # 格式4: 尝试更宽松的匹配（user:pass@ip:port 无协议）
    m = re.match(r'^([^@/]+)@(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}):(\d+)$', raw)
    if m:
        return {
            'ip': m.group(2),
            'port': int(m.group(3)),
            'protocol': 'http',
            'username': m.group(1),
            'password': '',
        }

    # 格式6: 尝试 ip:port 格式但带额外后缀（如 ip:port:anonymity）
    m = re.match(r'^(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}):(\d+)', raw)
    if m:
        return {
            'ip': m.group(1),
            'port': int(m.group(2)),
            'protocol': 'http',
            'username': '',
            'password': '',
        }

    return None


def parse_proxy_list(raw_list: List[str]) -> List[Dict[str, Any]]:
    """
    批量解析代理列表

    Args:
        raw_list: 原始代理字符串列表

    Returns:
        解析后的代理字典列表（排除解析失败的）
    """
    result = []
    for raw in raw_list:
        parsed = parse_proxy(raw)
        if parsed:
            result.append(parsed)
    return result


def format_proxy(parsed: Dict[str, Any]) -> str:
    """
    将解析后的字典格式化为代理字符串

    Args:
        parsed: parse_proxy() 的返回值

    Returns:
        格式化后的代理字符串
    """
    if not parsed:
        return ''
    protocol = parsed.get('protocol', 'http')
    ip = parsed.get('ip', '')
    port = parsed.get('port', 0)
    username = parsed.get('username', '')
    password = parsed.get('password', '')

    if username:
        return f'{protocol}://{username}:{password}@{ip}:{port}'
    return f'{protocol}://{ip}:{port}'


def validate_ip(ip: str) -> bool:
    """验证 IP 地址格式"""
    return bool(re.match(r'^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$', ip))


def validate_port(port: int) -> bool:
    """验证端口号范围"""
    return 1 <= port <= 65535