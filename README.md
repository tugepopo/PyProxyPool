# PyProxyPool - 高性能Python代理池

融合 henson/proxypool 和 qiyeboy/IPProxyPool 优点的代理池系统。

## 架构

```
Getter(多源采集) → Validator(并发验证) → Storage(持久化) → API Server
```

## 特性

- 多进程隔离，采集/验证/存储/API 互不阻塞
- **7 个代理源**：3 个传统网页源 + 4 个 GitHub 纯文本源（实时采集，无需手动维护）
- 支持 xpath / regex / github 三种解析方式
- **IP 纯净度检测**：采集后立即检测住宅/数据中心/代理/VPN/Tor/恶意IP，集成 5 个数据源（ipapi.co/iplog/AbuseIPDB/TorExit/IQScore）
- 多维评分：速度 + 匿名性 + IP 纯净度，低于阈值自动淘汰
- **生产级管理仪表盘**：深色工业运维风格，7 个页面模块，零外部依赖，实时刷新
- **15 个 REST API 端点**：代理查询/删除/导出/统计/系统监控/实时日志/API文档
- 支持 SQLite / MySQL / Redis 三种存储后端
- 容错机制：单个采集器失败不影响整体运行
- 定时健康检查：周期性验证库中代理可用性

## 快速开始

```bash
pip install -r requirements.txt
python3 main.py
```

## 管理仪表盘

运行后访问 `http://localhost:8000/dashboard` 进入管理仪表盘。

### 仪表盘功能

| 模块 | 说明 |
|------|------|
| **Dashboard** | 总览：代理数量、评分分布、速度分布、来源分布 |
| **Proxies** | 代理列表：搜索、筛选、排序、选择、批量删除 |
| **Sources** | 来源分析：各采集源的代理数量、平均评分、平均速度 |
| **Geography** | 地理分布：按国家统计代理分布和平均评分 |
| **Quality** | 质量分析：评分分布、速度分布饼图 |
| **Logs** | 实时日志：尾部 500 行日志，自动刷新 |
| **System** | 系统信息：运行时间、平台、内存、磁盘使用 |

### 快捷工具

- **Export**：导出为 TXT / JSON / CSV 格式
- **Trigger Crawl**：手动触发采集
- **Cleanup**：批量清理低分代理

### 键盘快捷键

| 快捷键 | 功能 |
|--------|------|
| `/` | 聚焦搜索框 |
| `r` | 刷新数据 |
| `e` | 打开导出对话框 |
| `Esc` | 关闭弹窗 |

```bash
# 启动完整系统（API + 采集调度器）
python3 main.py

# 只启动API（适合已有代理数据，只需查询）
python3 main.py --api-only

# 只启动调度器（采集+验证，不启动API）
python3 main.py --scheduler-only

# 指定API端口
python3 main.py --port 9000
```

## API 接口

完整 API 文档可通过 `/api-docs` 访问。

| 端点 | 方法 | 说明 |
|------|------|------|
| `/status` | GET | 代理池状态（总数、协议分布、运行时间） |
| `/proxy` | GET | 随机获取代理 |
| `/proxy/all` | GET | 获取所有代理 |
| `/proxy/http` | GET | 获取 HTTP 代理 |
| `/proxy/https` | GET | 获取 HTTPS 代理 |
| `/delete` | GET | 删除单个代理 |
| `/delete/batch` | GET | 批量删除（keys=ip:port,ip:port） |
| `/cleanup` | GET | 清理低分代理（min_score） |
| `/stats` | GET | 基础统计 |
| `/stats/extended` | GET | 扩展统计（含评分/速度分布） |
| `/sources` | GET | 按来源统计 |
| `/countries` | GET | 按国家统计 |
| `/speed-distribution` | GET | 速度分布 |
| `/score-distribution` | GET | 评分分布 |
| `/export` | GET | 导出代理（format=json/csv/txt） |
| `/logs` | GET | 日志尾部 |
| `/system` | GET | 系统信息（运行时间、内存、磁盘） |
| `/api-docs` | GET | API 文档 |
| `/crawl` | POST | 手动触发采集 |
| `/cleanup-batch` | POST | 批量清理低分代理 |

## 配置说明

编辑 `config.py` 可修改：

- `PROXY_SOURCES` — 代理采集源列表，新增源只需加一段配置
- `DB_TYPE` — 存储后端：`sqlite` / `mysql` / `redis`
- `MIN_PROXY_NUM` — 有效代理低于此值触发采集（默认50）
- `CRAWL_INTERVAL` — 采集周期（秒，默认600）
- `CHECK_INTERVAL` — 健康检查周期（秒，默认600）
- `VALIDATOR_CONCURRENCY` — 验证并发数（默认100）
- `MIN_SCORE` — 最低评分，低于此值清除（默认2）
- `VERIFY_TIMEOUT` — 验证超时（秒，默认8）

## 添加新的代理源

### 传统网页源（xpath/regex）

在 `config.py` 的 `PROXY_SOURCES` 列表中添加：

```python
{
    'name': 'my-source',
    'urls': ['http://example.com/proxy/page/%d' % i for i in range(1, 5)],
    'type': 'xpath',
    'pattern': "//table//tr",
    'position': {'ip': './td[1]', 'port': './td[2]', 'type': './td[3]', 'protocol': ''}
},
```

### GitHub 纯文本源（raw text）

对于托管在 GitHub 上的纯文本代理列表（`protocol://ip:port` 或 `ip:port` 格式）：

```python
{
    'name': 'github-source',
    'urls': ['https://raw.githubusercontent.com/user/repo/main/proxy.txt'],
    'type': 'github',
},
```

目前内置的 GitHub 源包括：

| 源名称 | 说明 | Stars | 更新频率 |
|--------|------|-------|----------|
| proxifly_http | Proxifly HTTP 代理 | ⭐6K+ | 每5分钟 |
| proxifly_https | Proxifly HTTPS 代理 | ⭐6K+ | 每5分钟 |
| proxifly_all | Proxifly 全部代理 | ⭐6K+ | 每5分钟 |
| clarketm_proxy_list | clarketm 代理列表 | ⭐2.4K | 每日 |

## 切换数据库

```python
# config.py 中修改 DB_TYPE
DB_TYPE = 'sqlite'   # 默认，零配置
DB_TYPE = 'mysql'    # 需配置 DB_CONFIG['mysql']
DB_TYPE = 'redis'    # 需配置 DB_CONFIG['redis']，适合高并发读取
```

## 项目结构

```
pyproxypool/
├── main.py              # 主入口，多进程启动 + 调度循环
├── config.py            # 全局配置
├── models.py            # ProxyIP 数据模型
├── db/
│   ├── base.py          # 数据库抽象基类
│   ├── sqlite_helper.py # SQLite 实现
│   ├── mysql_helper.py  # MySQL 实现
│   └── redis_helper.py  # Redis 实现
├── getter/
│   ├── proxy_crawler.py # 多源采集器（传统网页源）
│   └── github_sources.py # GitHub 纯文本代理源采集器
├── validator/
│   └── __init__.py      # 代理验证器（速度+匿名性+评分）
└── api/
    └── __init__.py      # HTTP API 服务
```

## IP 纯净度检测

**IP 纯净度检测模块** (`purity_checker/`) 为代理池提供 IP 质量评估能力。采集到的代理会在入库前自动检测纯净度，并将结果持久化到数据库，供前端面板展示和筛选。

### 检测维度

| 维度 | 数据源 | 费用 | 检测内容 |
|------|--------|------|----------|
| ASN / 数据中心 | ipapi.co | 免费（1000次/天） | 是否为数据中心 IP、ISP、ASN |
| VPN / Proxy / Tor | iplog.fr | 免费 | VPN、Proxy、Tor、匿名器检测 |
| Tor 出口节点 | Tor Project 官方 | 免费 | 本地缓存，每小时刷新 |
| 滥用评分 | AbuseIPDB | 需 API Key（免费 10K/月） | 0-100 滥用评分、举报次数 |
| 高级检测 | IpQualityScore | 需 API Key（商业） | 住宅代理、威胁评分、欺诈评分 |

### 评分标准

| 评分区间 | 分类 | 说明 |
|----------|------|------|
| 90-100 | 住宅IP | 完全干净，家庭宽带 |
| 70-89 | 住宅(轻微) / 数据中心(干净) | 轻微问题或干净的数据中心 |
| 40-69 | 数据中心 | 数据中心IP，可正常使用 |
| 20-39 | 代理 / VPN | 代理或VPN出口节点 |
| 0-19 | 恶意IP | 已知滥用、Tor、黑名单 |

### API Key 配置

在 `config.py` 中填写（支持环境变量）：

```python
# AbuseIPDB: https://www.abuseipdb.com/ — 免费 10K/月
ABUSEIPDB_API_KEY = os.environ.get('ABUSEIPDB_API_KEY', '')

# IpQualityScore: https://www.ipqualityscore.com/ — 商业级
IPQUALITYSCORE_API_KEY = os.environ.get('IPQUALITYSCORE_API_KEY', '')

# ipinfo.io: https://ipinfo.io/signup — 免费 50K/月（ip-api.com 不可用时的地理查询备选）
IPINFO_TOKEN = os.environ.get('IPINFO_TOKEN', '')

# ipgeolocation.io: https://ipgeolocation.io/signup.html — 免费 1000/月
IPGEOAPI_TOKEN = os.environ.get('IPGEOAPI_TOKEN', '')
```

#### 地理位置查询故障排除

如果你的网络环境无法访问 ip-api.com（HTTP 80 端口被屏蔽），可以在 `config.py` 中填入 ipinfo.io 或 ipgeolocation.io 的免费 Key。程序会自动按优先级尝试：

```
ip-api.com → ipinfo.io → ipgeolocation.io
```

或在启动前设置环境变量：
```bash
export ABUSEIPDB_API_KEY="your-key-here"
python main.py
```

### 前端面板

管理面板已集成纯净度展示：
- 新增「纯净度」列，显示评分 + 分类标签
- 新增「住宅IP」和「数据中心」统计卡片
- 新增纯净度筛选器（按分类和评分筛选）

---

## License

MIT
# -PyProxyPool
# PyProxyPool
# PyProxyPool
# PyProxyPool
# PyProxyPool
