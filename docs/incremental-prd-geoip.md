# PyProxyPool GeoIP 本地数据库集成 — 增量 PRD

> 版本：v1.0 | 状态：Draft | 日期：2026-06-10  
> 项目：PyProxyPool（FastAPI + SQLAlchemy(async) + SQLite/PostgreSQL + Redis + APScheduler）  
> 原始需求：使用本地 GeoIP 数据库替代在线 API 查询，实现离线、高速的 IP 归属地识别

---

## 1. 产品目标

1. **性能目标**：IP 归属地查询耗时从在线 API 的 2-5s/次 降至本地数据库的 <10ms/次，提升 200-500 倍。
2. **稳定性目标**：消除对外部 API 的依赖，避免因 API 限流、网络波动、服务中断导致的查询失败。
3. **成本目标**：使用免费数据库方案（MaxMind GeoLite2 / MetaCubeX geoip.db），无需付费 API 额度。

---

## 2. 用户故事

- **作为系统**，我希望使用本地 GeoIP 数据库查询 IP 归属地，这样代理验证和地理分析不再依赖外部网络。
- **作为管理员**，我希望 GeoIP 数据库能自动定期更新（建议每周/每月），这样无需手动维护数据库文件。
- **作为管理员**，我希望在 Dashboard 中查看当前 GeoIP 数据库的版本号和上次更新时间，这样我能确认数据库是否最新。
- **作为系统**，我希望在本地数据库查询失败时自动降级到在线 API（原有逻辑保留），这样保证零查询失败率。
- **作为管理员**，我希望能通过配置切换 GeoIP 数据库源（MaxMind GeoLite2 / MetaCubeX geoip.db），以适应不同精度需求。

---

## 3. 需求池（按优先级）

### P0 — Must Have

| ID | 需求 | 说明 |
|----|------|------|
| G001 | GeoIP2 本地数据库集成 | 引入 `geoip2` 或 `geoip2` 兼容库，支持 `.mmdb` 格式数据库本地查询 |
| G002 | 数据库自动下载与更新 | APScheduler 定期下载最新数据库文件（可配置周期），失败有日志告警 |
| G003 | `IPGeoService.lookup_geo()` 迁移到本地查询 | 将现有在线 API 查询替换为本地图库查询，保持返回格式一致 |
| G004 | 降级到在线 API | 本地数据库不可用时自动 fallback 到 ip-api.com / ipinfo.io |
| G005 | Redis 缓存保留 | 保留现有 Redis 缓存机制，减少磁盘读取 |
| G006 | Config 配置扩展 | 新增 `GEOIP_DB_SOURCE`、`GEOIP_DB_PATH`、`GEOIP_DB_UPDATE_INTERVAL` 等配置项 |

### P1 — Should Have

| ID | 需求 | 说明 |
|----|------|------|
| G007 | 数据库版本信息 API | Dashboard API 暴露数据库版本、记录数、更新时间 |
| G008 | Dashboard 管理面板 | 显示 GeoIP 数据库状态（版本/更新时间/大小），提供手动更新按钮 |
| G009 | 多数据源支持 | 支持 MaxMind GeoLite2 和 MetaCubeX geoip.db 两种数据源切换 |
| G010 | 数据库健康检查 | 启动时验证数据库文件完整性和可读写性 |

### P2 — Nice to Have

| ID | 需求 | 说明 |
|----|------|------|
| G011 | 数据库增量更新 | 仅下载差异部分（如 MaxMind 的 CSV 增量包） |
| G012 | IP 归属地批量预查询 | APScheduler 定期为数据库中未填充 country 的代理批量预填 |
| G013 | GeoIP 数据精度对比面板 | 对比本地数据库 vs 在线 API 的查询结果差异 |

---

## 4. 技术方案建议

### 4.1 GeoIP 数据库选型

| 方案 | 优势 | 劣势 | 推荐度 |
|------|------|------|--------|
| **MaxMind GeoLite2-Country/City**（.mmdb） | 社区广泛使用、Python `geoip2` 库成熟、免费版每月更新 | 免费版 City 数据库精度有限，商业使用需付费 | ⭐⭐⭐⭐⭐（推荐默认方案） |
| **MetaCubeX geoip.db**（SQLite） | 专为代理场景优化、包含 ASN 和 ISP 信息、开源免费 | 非标准格式，需定制查询逻辑，无官方 Python 库 | ⭐⭐⭐（备选方案） |
| **IP2Location Lite**（BIN） | 轻量、免费、商业许可宽松 | Python 库生态不如 geoip2 成熟 | ⭐⭐（备选方案） |

**推荐**：默认使用 **MaxMind GeoLite2 City**（`.mmdb` 格式），通过 `geoip2` Python 库查询。同时提供配置项允许切换到 MetaCubeX geoip.db（适配 sing-box-yg 等社区生态）。

### 4.2 依赖安装

```
# requirements.txt 或 pyproject.toml 新增
geoip2>=4.8.0          # MaxMind 官方 Python 客户端
requests>=2.31.0       # 数据库下载（已有 aiohttp 也可复用）
```

### 4.3 数据库下载与更新机制

```
data/
  geoip/
    GeoLite2-City.mmdb              # 当前生效的数据库
    GeoLite2-City.mmdb.backup       # 上一版本备份（下载失败时回滚用）
    GeoLite2-Country.mmdb           # 可选：仅国家级精度（更小更快）
```

**更新流程**：
1. APScheduler 按 `GEOIP_DB_UPDATE_INTERVAL`（默认 7 天）触发下载任务
2. 从 MaxMind 官网下载最新 `.mmdb.gz` 文件到临时目录
3. 解压并校验文件完整性（file size > 0，geoip2 库能正常 open）
4. 原子替换：`mv {temp} data/geoip/GeoLite2-City.mmdb.new` → `mv .new .mmdb`
5. 将旧文件移为 `.backup`，确保回滚可用
6. 重新初始化 `GeoIP2Reader` 实例（hot-reload）
7. 日志记录：`INFO: GeoIP database updated: GeoLite2-City.mmdb (v2026.06, 12.5MB, 13M records)`

**下载源**：
- 免费用户：https://download.maxmind.com/app/geoip_download?edition_id=GeoLite2-City&suffix=tar.gz（需要 MaxMind 账号 + License Key）
- 社区镜像：https://github.com/P3TERX/GeoLite.mmdb/releases（定期同步 MaxMind 官方，无需注册）

### 4.4 查询接口设计

**保持 `IPGeoService.lookup_geo()` 的接口不变**，内部实现替换：

```python
# geo.py 改造后伪代码

class GeoIPReader:
    """GeoIP 本地数据库管理器"""
    def __init__(self, db_path: str):
        self._reader = geoip2.database.Reader(db_path)

    async def lookup(self, ip: str) -> Dict[str, Any]:
        try:
            response = self._reader.city(ip)
            return {
                'ip': ip,
                'country': response.country.iso_code or '',
                'region': response.subdivisions.most_specific.name if response.subdivisions else '',
                'city': response.city.name or '',
                'org': '',        # GeoLite2 City 不含 ISP，需从纯真数据库补充
                'lat': str(response.location.latitude or ''),
                'lon': str(response.location.longitude or ''),
            }
        except geoip2.errors.AddressNotFoundError:
            return {}

class IPGeoService:
    def __init__(self):
        self._geoip_reader = GeoIPReader(settings.GEOIP_DB_PATH)

    async def lookup_geo(self, ip: str) -> Dict[str, Any]:
        # Step 1: Redis 缓存
        cached = await cache_get(f'geo:{ip}')
        if cached:
            return json.loads(cached)

        # Step 2: 本地数据库查询
        geo_data = await self._geoip_reader.lookup(ip)
        if geo_data:
            await cache_set(f'geo:{ip}', json.dumps(geo_data), ttl=3600)
            return geo_data

        # Step 3: 降级到在线 API（原有逻辑保留）
        return await self._query_geo_api(ip)
```

### 4.5 与现有代码的兼容/迁移方案

| 现有组件 | 改动 | 影响 |
|---------|------|------|
| `services/geo.py` | 新增 `GeoIPReader` 类，`lookup_geo()` 改为先本地后在线 | 向后兼容，降级逻辑保证零查询失败 |
| `config.py` | 新增 `GEOIP_DB_SOURCE`、`GEOIP_DB_PATH`、`GEOIP_DB_UPDATE_INTERVAL` 等配置 | 环境变量兼容 |
| `models.py` | **无改动** | 现有字段（country/area/isp）保持不变 |
| `services/pool.py` | **无改动** | 代理池分级管理不受影响 |
| `services/scanner.py` | **无改动** | 扫描逻辑通过 `enrich_proxy_geo()` 间接受益 |
| Redis 缓存 | **无改动** | 缓存键和 TTL 策略不变 |

### 4.6 配置新增项

```python
# config.py Settings 类新增
GEOIP_DB_SOURCE: str = Field(default='geolite2', description='GeoIP 数据源: geolite2 / metacubex')
GEOIP_DB_PATH: str = Field(default='data/geoip/GeoLite2-City.mmdb', description='GeoIP 数据库路径')
GEOIP_DB_UPDATE_INTERVAL: int = Field(default=604800, description='数据库自动更新间隔（秒），默认 7 天')
GEOIP_DB_DOWNLOAD_URL: str = Field(default='', description='数据库下载地址（留空使用默认源）')
GEOIP_DB_LICENSE_KEY: str = Field(default='', description='MaxMind License Key（用于官方下载）')
```

---

## 5. UI 设计稿（Dashboard 相关改动）

### 5.1 系统状态面板（现有 Dashboard 扩展）

在现有 Dashboard 的「系统状态」区域新增 **GeoIP 数据库状态卡片**：

```
┌─────────────────────────────────────────┐
│  GeoIP 数据库状态                        │
├─────────────────────────────────────────┤
│  数据源    │ MaxMind GeoLite2 City      │
│  版本      │ 2026.06                    │
│  文件大小  │ 12.5 MB                    │
│  记录数    │ 13,420,000                 │
│  更新时间  │ 2026-06-10 08:30:00        │
│  下次更新  │ 2026-06-17 08:30:00        │
│  ───────────────────────────────────    │
│  [ 手动更新 ]  [ 切换数据源 ]            │
└─────────────────────────────────────────┘
```

### 5.2 API 端点新增

```
GET /api/admin/geoip/status    — 返回 GeoIP 数据库状态信息
POST /api/admin/geoip/refresh   — 触发手动更新
POST /api/admin/geoip/source    — 切换数据源（geolite2/metacubex）
```

---

## 6. 待确认问题

| Q | 问题 | 建议 | 需确认方 |
|---|------|------|---------|
| Q1 | MaxMind 免费 License Key 是否已申请？ | 建议申请一个，或先用社区镜像 | 用户 |
| Q2 | ISP 信息从哪里获取？GeoLite2 City 不含 ISP | 方案A：GeoLite2 City 返回空 ISP，标记为待补充；方案B：集成纯 QQWry 数据库补充 ISP | 用户 |
| Q3 | 是否需要在 `enrich_proxy_geo()` 中直接填充 ISP 字段？ | 当前代码用 `geo_data.get('org', '')` → ISP；本地数据库需兼容此映射 | 开发 |
| Q4 | 数据库更新失败时是否自动发送告警？ | 建议复用现有 ALERT_WEBHOOK_URL | 用户 |
| Q5 | 是否支持 IPv6 查询？ | GeoLite2 City 支持 IPv6，但 MaxMind 免费版 IPv6 覆盖有限 | 开发 |
| Q6 | MetaCubeX geoip.db 是否作为默认选项？ | 建议默认 GeoLite2，MetaCubeX 作为可选项（适配 sing-box-yg 用户） | 用户 |

---

## 附录 A：竞品参考

| 项目 | 方案 | 优缺点 |
|------|------|--------|
| sing-box-yg | MetaCubeX geoip.db（SQLite）+ ip.fm/myip.ipip.net API | 纯本地 SQLite 查询，但 ISP 信息依赖 API |
| x-ui-yg | 同 sing-box-yg | 同上 |
| Cloudflare-vless-trojan | 不做国家识别，依赖作者维护的优选 IP 列表 | 无 GeoIP 集成，不参考 |

---

*文档完成。下一步：开发团队根据此 PRD 制定技术方案和实施计划。*
