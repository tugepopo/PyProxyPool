# PyProxyPool - 高性能Python代理池

融合 henson/proxypool 和 qiyeboy/IPProxyPool 优点的代理池系统。

## 架构

```
Getter(多源采集) → Validator(并发验证) → Storage(持久化) → API Server
```

## 特性

- 多进程隔离，采集/验证/存储/API 互不阻塞
- 多代理源采集，支持 xpath/regex 两种解析方式
- 多维评分：速度 + 匿名性 + 协议类型，低于阈值自动淘汰
- 支持 SQLite / MySQL / Redis 三种存储后端
- 丰富的 API 查询参数（匿名类型/协议/评分/地区）
- 容错机制：单个采集器失败不影响整体运行
- 定时健康检查：周期性验证库中代理可用性

## 快速开始

```bash
pip install -r requirements.txt
python3 main.py
```

## 使用方式

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

| 接口 | 说明 | 参数 |
|------|------|------|
| `GET /status` | 代理池状态 | - |
| `GET /proxy` | 随机获取代理 | `count` 数量, `types` 0高匿/1匿名/2透明, `protocol` 0http/1https, `min_score` 最低评分 |
| `GET /proxy/http` | 获取HTTP代理 | `count` |
| `GET /proxy/https` | 获取HTTPS代理 | `count` |
| `GET /proxy/all` | 获取全部代理 | - |
| `GET /delete` | 删除代理 | `ip` 必填, `port` 可选 |

### 示例

```bash
# 获取5个高匿HTTP代理
curl 'http://127.0.0.1:8000/proxy?count=5&types=0&protocol=0'

# 查看状态
curl http://127.0.0.1:8000/status

# 删除指定代理
curl 'http://127.0.0.1:8000/delete?ip=1.2.3.4&port=8080'
```

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
│   └── proxy_crawler.py # 多源采集器
├── validator/
│   └── __init__.py      # 代理验证器（速度+匿名性+评分）
└── api/
    └── __init__.py      # HTTP API 服务
```

## License

MIT
# -PyProxyPool
# PyProxyPool
# PyProxyPool
# PyProxyPool
# PyProxyPool
