# PyProxyPool 项目概览

## 已完成

- 阅读了项目入口、配置、数据模型、采集器、验证器、数据库层、API 层、Dashboard 和快速测试脚本。
- 梳理出项目核心链路：代理源配置 → 并发采集解析 → 地理信息补全 → 数据库存储 → 并发验证评分 → API / Dashboard 输出。

## 架构摘要

- `main.py`：主入口，支持完整启动、仅 API、仅调度器三种模式；完整模式下通过多进程启动 API 服务和调度器。
- `config.py`：集中配置代理源、数据库类型、验证 URL、评分规则、调度周期、API 地址和日志。
- `models.py`：定义 `ProxyIP` 数据模型，封装代理 URL、requests 代理字典和序列化。
- `getter/proxy_crawler.py`：配置驱动的多源代理采集器，使用线程池并发抓取，支持简化表格解析和 regex 解析。
- `validator/__init__.py`：代理验证器，并发访问验证 URL，根据可用性、响应速度、匿名性更新评分。
- `db/`：数据库抽象与实现，默认 SQLite；另有 MySQL、Redis 实现。
- `api/__init__.py`：基于标准库 `HTTPServer` 的 API 服务，提供代理查询、删除、清理、状态统计、触发采集等接口。
- `api/dashboard.py`：内嵌零依赖 Web 管理面板，支持统计卡片、筛选、排序、分页、删除、导出和触发采集。
- `utils/ip_geo.py`：调用 ip-api.com 批量补全代理 IP 地理位置和 ISP 信息。
- `test_quick.py`：覆盖模型、SQLite、采集解析、配置、批量操作、统计的快速测试脚本。

## 关键运行链路

1. 启动：`python3 main.py`。
2. API 进程：初始化数据库并监听 `0.0.0.0:8000`。
3. Scheduler 进程：初始化数据库、采集器和验证器。
4. 当代理数量不足、到达采集周期或 API 触发采集时：
   - 从 `PROXY_SOURCES` 并发抓取代理。
   - 对代理做去重和地理信息补全。
   - 批量写入数据库。
   - 取出数据库代理并发验证。
   - 批量更新评分和速度。
   - 删除低于 `MIN_SCORE` 的代理。
5. API 查询从数据库按协议、匿名性、评分随机返回代理。

## 注意点与潜在改进

- README 宣称支持 xpath，但当前实现是标准库表格解析，并非真正 XPath；复杂页面结构可能解析不到。
- `requirements.txt` 只有 `requests`，但 MySQL / Redis 模式还需要额外依赖，当前未列入可选依赖。
- API 的 `_crawl_event` 是线程事件；完整模式下 API 和 Scheduler 在不同进程中，各自持有独立内存，API 触发采集可能无法跨进程通知 Scheduler。
- `main.py --port` 只用于日志展示，实际 API 端口仍来自 `config.API_PORT`，参数没有真正传入 API 服务。
- `ProxyValidator._get_session()` 有 session 池设计，但 `validate_one()` 实际直接使用 `requests.get()`，连接复用未生效。
- Redis 实现缺少 `get_stats()` 的专门实现，使用 API 统计接口时可能只返回基础 `total` 或不满足前端字段需求。
- Dashboard 删除选中代理是逐条请求，后端已有 `/delete/batch`，前端可以改为批量调用以减少请求数。
- 采集源依赖公开免费代理网站，页面结构和反爬策略变化会明显影响成功率。

## 建议下一步

1. 先运行 `test_quick.py` 确认当前本地基础能力是否正常。
2. 修复跨进程触发采集和 `--port` 参数未生效问题。
3. 明确 README 中“xpath”能力描述，或引入真正 HTML/XPath 解析依赖。
4. 补齐 MySQL / Redis 可选依赖说明，并完善 Redis 统计接口。
5. 给 API 参数解析增加容错，避免非法 `count`、`port`、`min_score` 导致 500。
