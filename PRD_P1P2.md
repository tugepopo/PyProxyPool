# PyProxyPool P1+P2 功能 PRD

**日期**: 2026-07-03  
**版本**: v2.1 (P1+P2 功能完善)  
**作者**: 齐活林（Team Lead）

---

## 产品目标

PyProxyPool P0 完成后是一个可用的代理池系统，但存在 **生产稳定性问题**（日志无限增长、失效源持续白重试）和 **运营盲区**（无法追踪代理使用情况、缺乏分组管理、无质量趋势）。P1+P2 完成后，项目达到**运维就绪**状态：日志可控、采集效率优化、代理全生命周期可追踪、仪表盘能支撑日常运营决策。

---

## P1 功能（高优先级）

### P1-1 日志轮转

**用户故事**：作为运维人员，我希望日志文件自动按大小/时间轮转，以便避免因日志无限增长导致磁盘耗尽。

**需求条目**：

| ID | 需求 | 验收标准 |
|----|------|---------|
| P1-1-1 | 将 `main.py` 的 `FileHandler` 替换为 `TimedRotatingFileHandler` | 日志文件每天 00:00 自动轮转 |
| P1-1-2 | 在 `config.py` 新增日志轮转配置项 | `LOG_MAX_BYTES=50*1024*1024`(50MB), `LOG_BACKUP_COUNT=10`, `LOG_ROTATE_WHEN='midnight'`, `LOG_BACKUP_COUNT` 可配 |
| P1-1-3 | 保留现有 `StreamHandler`(console) 不变 | 控制台日志正常输出 |

**变更文件**：`main.py`（setup_logging 函数）+ `config.py`

---

### P1-2 采集源自动降级

**用户故事**：作为运维人员，我希望失效的采集源自动降级（不再每次循环都重试），以便减少无效 HTTP 请求和错误日志噪音。

**需求条目**：

| ID | 需求 | 验收标准 |
|----|------|---------|
| P1-2-1 | 在 `ProxyCrawler` 中添加 `source_failures` 字典（内存维护），记录每个源的连续失败次数 | 每次源失败 +1，成功 -1（重置） |
| P1-2-2 | 连续失败 3 次后，跳过该源（`crawl_all()` 中过滤） | 连续 3 次失败后不再发起请求，仅日志记录 |
| P1-2-3 | 降级源在成功采集一次后自动恢复 | 成功采集后 `source_failures[name]=0` |
| P1-2-4 | API `/sources` 端点返回每个源的 `status`（active/degraded）和 `consecutive_failures` | 前端 Dashboard 的 Sources 页面可见 |

**变更文件**：`getter/proxy_crawler.py` + `api/__init__.py`

---

### P1-3 代理白名单/黑名单

**用户故事**：作为运营人员，我希望将已知可靠的代理加入白名单、将黑名单代理加入排除列表，以便控制代理池的质量下限。

**需求条目**：

| ID | 需求 | 验收标准 |
|----|------|---------|
| P1-3-1 | 新增数据库表 `whitelist` (ip, port, protocol, created_at) 和 `blacklist` (ip, port, protocol, created_at) | 表创建成功，支持 CRUD |
| P1-3-2 | `get_random()` 中排除黑名单代理 | 黑名单中的代理不会出现在 `/proxy` 返回中 |
| P1-3-3 | API 新增白名单/黑名单端点 | POST `/whitelist` 添加, DELETE `/whitelist/<ip>/<port>` 删除, GET `/whitelist` 列表；黑名单同理 |
| P1-3-4 | 仪表盘新增 WhiteList/BlackList 页面 | 可搜索、添加、删除代理；白名单代理在代理列表中高亮显示 |

**变更文件**：`db/sqlite_helper.py` + `db/base.py` + `api/__init__.py` + `api/dashboard.py`

---

## P2 功能（中优先级）

### P2-1 代理使用次数统计

**用户故事**：作为运营人员，我希望追踪每个代理被获取了多少次，以便识别高频低分代理并进行质量分析。

**需求条目**：

| ID | 需求 | 验收标准 |
|----|------|---------|
| P2-1-1 | `proxies` 表新增 `use_count INTEGER DEFAULT 0` 列 | 数据库迁移成功，`idx_use_count` 索引 |
| P2-1-2 | `/proxy` 端点返回代理时，更新 `use_count += 1` | 每次获取代理自动累加 |
| P2-1-3 | API `/stats/extended` 返回 `top_used`（使用次数最多的前 20 个代理） | 前端 Dashboard 可见 |

**变更文件**：`models.py` + `db/sqlite_helper.py` + `api/__init__.py`

---

### P2-2 代理分组/标签

**用户故事**：作为运营人员，我希望为代理添加标签（如 `residential`, `datacenter`, `vpn`, `geo:cn`），以便按场景筛选代理。

**需求条目**：

| ID | 需求 | 验收标准 |
|----|------|---------|
| P2-2-1 | `proxies` 表新增 `tags TEXT DEFAULT '[]'` 列（JSON 数组存储） | 数据库迁移成功 |
| P2-2-2 | 代理入库时根据 IP 类型自动打标签 | `is_datacenter=True → tags=["datacenter"]`, `is_native=True → tags=["residential"]`, `country 在配置中 → tags=["geo:xx"]` |
| P2-2-3 | API `/proxy` 支持 `tags` 查询参数（逗号分隔） | `GET /proxy?tags=residential,geo:cn` 返回匹配标签的代理 |
| P2-2-4 | API 新增 `/tags` 端点（GET 获取所有标签列表及数量） | `GET /tags` 返回 `{"datacenter": 150, "residential": 200, "geo:cn": 30}` |
| P2-2-5 | 仪表盘代理列表页面新增标签筛选器 | 下拉多选标签，前端实时筛选 |

**变更文件**：`models.py` + `db/sqlite_helper.py` + `main.py`（入库逻辑）+ `api/__init__.py` + `api/dashboard.py`

---

### P2-3 历史趋势数据

**用户故事**：作为运营人员，我希望看到代理池的质量变化趋势（评分分布、可用性比例随时间变化），以便评估整体健康度。

**需求条目**：

| ID | 需求 | 验收标准 |
|----|------|---------|
| P2-3-1 | 新建 `proxy_history` 表：(ip, port, verified_at, score, speed, purity_score, country, source) | 表创建成功，`idx_verified_at` 索引 |
| P2-3-2 | 验证器 `validate_one()` 每次验证完成后，写入一条历史记录 | 批量验证时批量写入 history 表 |
| P2-3-3 | API 新增 `/trends` 端点 | `GET /trends?hours=24` 返回每小时的：总代理数、平均分、可用率 |
| P2-3-4 | 仪表盘新增 Trends 页面 | 折线图展示 24h 趋势（使用 Chart.js 或 SVG） |

**变更文件**：`db/sqlite_helper.py` + `db/base.py` + `validator/__init__.py` + `main.py` + `api/__init__.py` + `api/dashboard.py`

---

## UI 设计稿

### 仪表盘新增页面

| 页面 | 路径 | 内容 |
|------|------|------|
| WhiteList/BlackList | `/dashboard#whitelist` | 搜索框 + 表格 + 添加/删除按钮 |
| Tags | `/dashboard#tags` | 标签列表（标签名 + 数量）+ 标签分布饼图 |
| Trends | `/dashboard#trends` | 24h 折线图（总代理数 / 平均分 / 可用率） |

### 现有页面变更

| 页面 | 变更 |
|------|------|
| Dashboard | 新增"白名单"统计卡片 |
| Proxies | 新增标签筛选器；白名单代理行高亮（绿色边框） |
| Sources | 新增 `status` 列（active/degraded） |

---

## 待确认问题

1. **白名单/黑名单存储方式**：当前方案使用独立表，替代方案是 `proxies` 表加 `is_whitelist/is_blacklist` 列。独立表更适合大量黑名单（不污染主表索引），优先使用独立表方案。
2. **历史趋势保留周期**：默认保留 30 天历史数据，超过自动清理。可通过配置调整。
3. **标签自动打标规则**：当前仅基于 IP 类型和地区自动打标。未来可扩展为手动 + 自动混合，本次只实现自动打标。

---

*PRD 生成时间: 2026-07-03 19:10*  
*PyProxyPool v2.1 — 运维就绪*