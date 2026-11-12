# 卧游 Woyou · 开发计划

| 项目 | 内容 |
|---|---|
| 文档版本 | v0.1 |
| 日期 | 2026-11-08 |
| 状态 | 设计定稿，待开工 |
| 关联文档 | [README.md](README.md) |
| 人力 | 1 人，业余时间（约 10–15 小时/周） |
| 代码许可 | MIT |

---

> **实施备注（2026-11-10）**：v0.1 已落地。实际实现与本文的差异：前端用原生 ES Module 替代 Alpine/HTMX；地理编码因 Nominatim 在当前网络不可达，改为 Open-Meteo + BigDataCloud（Photon 兜底）；新增天气卡片、雷达与云图。详见 [document.md](document.md)。

## 1. 背景

### 1.1 要解决的问题

Google Maps / Google Earth 在国内需要网络代理，探索的节奏会被网络反复打断。与此同时，开放的地理数据其实非常丰富：

- **Sentinel-2**：10 米分辨率、约 5 天重访，全球免费；
- **Landsat 8/9**：30 米，历史可追溯到 1972 年；
- **OpenStreetMap**：全球矢量底图，ODbL 许可；
- **NASA GIBS**：每日 MODIS / VIIRS 影像，可看云、火点、沙尘；
- **Mapillary**：众包街景，CC BY-SA；
- **天地图**：国内合规底图，CGCS2000。

问题是它们**散落在几十个门户里**：分辨率不同、时间粒度不同、投影不同、许可不同。用户要在浏览器标签页之间反复跳转，无法把“影像 + 街景 + 地点信息 + 时间变化”放在同一个视野里。

### 1.2 现有方案为什么不够

| 方案 | 不足 |
|---|---|
| Google Earth | 需要代理；无法离线；数据不可控 |
| QGIS | 能力极强但门槛高，交互偏“制图”而非“浏览” |
| 各类在线门户 | 单一数据源、单一时间点，缺少地点上下文 |
| 商业地图 API | 按量计费，条款限制多，不适合个人长期探索 |

### 1.3 项目机会

- 浏览器端地图引擎（MapLibre）已经能流畅渲染全球栅格/矢量/地形；
- Python 生态有成熟的 Web 框架、HTTP 客户端和地理计算库；
- 个人工具不需要多租户、SLA、计费和公网合规，可以把复杂度压到最低；
- 开源后，数据源可以由社区共同维护——这是单人项目长期存活的关键。

### 1.4 约束条件（来自前期讨论）

| 约束 | 对设计的影响 |
|---|---|
| 开发者更熟悉 Python | 后端 FastAPI；v0.1 不引入 Node 构建链 |
| 直接用浏览器打开 | 本地 Web 应用，`127.0.0.1`，不做桌面壳 |
| 不使用网络代理 | 默认数据源必须直连可达；内置健康检查与降级 |
| 部分区域没有街景可接受 | Mapillary 为主，空状态优雅降级 |
| 仅个人使用，不提供服务 | 不做账号、多用户、公网部署 |
| 界面与功能要能持续迭代 | 配置驱动数据源；API 版本化；前端可替换 |
| 计划开源到 GitHub | 默认源许可清晰；不含密钥；MIT |

---

## 2. 定位与目标

### 2.1 一句话定位

**一个本地运行、无需代理、面向个人的地理探索台：把全球开放影像、街景和地点信息收进一个浏览器界面。**

### 2.2 目标（Goals）

- **G1 开箱即用**：一条命令启动，浏览器自动打开，5 分钟内看到第一张影像。
- **G2 多源影像**：底图、卫星、地形、专题图层可叠加、可调透明度。
- **G3 地点上下文**：点一下地图，能看到街景、OSM 标签、百科/游记入口。
- **G4 时间维度**：能对比同一地点不同年份的影像。
- **G5 可离线回看**：访问过的区域缓存到本地，断网也能再看。
- **G6 易扩展**：新增一个数据源只需改 YAML，不改代码。

### 2.3 非目标（Non-goals）

- ❌ 不做公开的在线地图服务，不部署公网，不做多用户。
- ❌ 不做导航、测绘、量算等专业 GIS 功能。
- ❌ 不追求 1:1 复刻 Google Earth 的 3D 建筑与全球街景。
- ❌ 不做移动端 App。
- ❌ 不抓取 Google 瓦片，不绕过任何服务条款。

### 2.4 成功标准

| 指标 | 目标 |
|---|---|
| 安装到看到第一张影像 | ≤ 5 分钟 |
| 日常探索不打开代理的比例 | ≥ 80% |
| 已访问区域断网回看 | 可用 |
| 新增一个数据源 | ≤ 10 行 YAML，0 行代码 |
| 首屏瓦片（未缓存） | ≤ 1.5 秒 |
| 缓存命中响应 | ≤ 100 毫秒 |
| 连续使用 1 小时 | 无未处理异常、无明显内存增长 |

---

## 3. 技术路线

### 3.1 总体架构

```
┌─────────────────────────────────────────────────────┐
│ 浏览器  http://127.0.0.1:8765                        │
│  Jinja2 页面 + Alpine.js / HTMX + MapLibre GL JS     │
│   ├─ 图层抽屉 / 搜索框 / 信息面板 / 状态栏            │
│   └─ 所有静态资源本地 vendored，不依赖 CDN            │
└───────────────────────┬─────────────────────────────┘
                        │ 同源 HTTP，无 CORS
┌───────────────────────▼─────────────────────────────┐
│ FastAPI（Python 3.11+）                              │
│  ├─ /tiles/{source}/{z}/{x}/{y}  瓦片代理            │
│  ├─ /api/v1/search               Nominatim           │
│  ├─ /api/v1/streetview           Mapillary           │
│  ├─ /api/v1/wiki                 Kiwix（后期）        │
│  ├─ /api/v1/bookmarks            收藏                │
│  └─ /api/v1/health               源健康              │
│                                                      │
│  SQLite：设置 / 收藏 / 足迹 / 搜索缓存                │
│  MBTiles：瓦片缓存 / 离线包                           │
└───────────────────────┬─────────────────────────────┘
                        │ httpx（连接池、超时、重试）
              开放数据源：OSM / Esri / EOX / NASA GIBS /
              天地图 / Mapillary / Nominatim
```

### 3.2 关键决策

| 决策点 | 选择 | 理由 | 放弃的方案 |
|---|---|---|---|
| 后端语言 | Python + FastAPI | 开发者熟悉；异步；生态好 | Flask（偏同步）、Django（过重） |
| 应用形态 | 本地 Web + 浏览器 | 跨平台、零安装包、迭代快 | Tauri/Electron（增加构建复杂度） |
| 前端 | Jinja2 + Alpine + HTMX | 无 Node 构建；Python 主导；模板即 UI | React/Vue（v0.1 不必，保留升级路径） |
| 地图引擎 | MapLibre GL JS | 矢量/栅格/地形/globe 一体，BSD | Leaflet（无 3D）、Cesium（过重） |
| 存储 | SQLite + MBTiles | 零运维、单文件、可离线、可迁移 | Postgres/PostGIS（个人工具不需要） |
| 瓦片访问 | 按 `source` id 代理 | 解决 CORS、缓存、藏 key、防 SSRF | 浏览器直连（CORS/缓存不可控） |
| 数据源 | YAML 配置驱动 | 新增源不改代码；社区易贡献 | 硬编码（维护成本高） |
| 默认源 | 开放、直连、许可清晰 | 满足“无代理”和“可开源” | Google（条款/网络均不允许） |
| 前端资源 | 本地 vendored | 大陆 CDN 不稳定，且要离线可用 | 运行时 CDN |
| 数据层 | 薄 DAO + `user_version` 迁移 | 简单、可控、无 ORM 负担 | SQLAlchemy/Alembic（v0.1 过重） |

### 3.3 瓦片请求生命周期

1. 浏览器请求 `/tiles/esri/12/3345/1789`。
2. FastAPI 校验 `source` 是否在注册表、`z/x/y` 是否在合法范围。
3. 查 MBTiles 缓存：命中则直接返回，带 `Cache-Control`。
4. 未命中：`httpx` 向上游请求，带超时、重试、并发信号量。
5. 校验响应状态、`Content-Type`、大小；写入缓存。
6. 返回瓦片；失败则返回 502，并记录该源健康状态，前端提示切换备用源。
7. 缓存按 `accessed_at` 做 LRU，超过容量上限时淘汰最旧数据。

### 3.4 模块与职责

| 模块 | 职责 | 关键文件 |
|---|---|---|
| CLI | 启动服务、打开浏览器、解析参数 | `__main__.py` |
| 应用 | 路由注册、生命周期、异常处理 | `app.py` |
| 配置 | 读取设置、校验、默认值 | `config.py` |
| 源注册表 | 加载 `sources.yaml`、校验、查询 | `sources.py` |
| 瓦片代理 | 参数校验、上游请求、响应 | `tiles/proxy.py` |
| 瓦片缓存 | MBTiles 读写、LRU、统计 | `tiles/cache.py` |
| 健康检查 | 探测延迟、状态、降级 | `tiles/health.py` |
| Providers | 各数据源的 URL/鉴权/解析 | `providers/*.py` |
| 搜索 | Nominatim 调用与缓存 | `providers/nominatim.py` |
| 街景 | Mapillary 图像查询 | `providers/mapillary.py` |
| 百科 | Kiwix 查询（后期） | `providers/kiwix.py` |
| 数据层 | SQLite 连接、迁移、DAO | `db.py` |
| 前端 | 地图、面板、状态 | `static/`, `templates/` |

### 3.5 数据源配置

```yaml
# sources.yaml
- id: osm
  name: OpenStreetMap
  type: raster
  url: "https://tile.openstreetmap.org/{z}/{x}/{y}.png"
  min_zoom: 0
  max_zoom: 19
  tile_size: 256
  attribution: "© OpenStreetMap contributors"
  cache: true
  headers:
    User-Agent: "Woyou/0.1 (personal geography tool)"

- id: esri-imagery
  name: Esri World Imagery
  type: raster
  url: "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"
  max_zoom: 19
  attribution: "Esri, Maxar, Earthstar Geographics"
  cache: true
  enabled_by_default: false   # 首次启动由用户确认条款后启用

- id: eox-s2cloudless-2024
  name: Sentinel-2 cloudless 2024
  type: raster
  url: "https://tiles.maps.eox.at/wmts/1.0.0/s2cloudless-2024_3857/default/g/{z}/{y}/{x}.jpg"
  max_zoom: 14
  attribution: "Sentinel-2 cloudless by EOX (modified Copernicus data)"
  cache: true
```

字段约定：`id` 唯一且稳定；`cache` 控制是否落盘；`enabled_by_default` 控制首次启动是否勾选；`fallback` 可指定备用源 id。

### 3.6 缓存设计

**MBTiles 表结构**（标准格式 + 访问记录）：

```sql
CREATE TABLE tiles (
  zoom_level  INTEGER,
  tile_column INTEGER,
  tile_row    INTEGER,
  tile_data   BLOB,
  content_type TEXT,
  accessed_at INTEGER,
  PRIMARY KEY (zoom_level, tile_column, tile_row)
);
CREATE INDEX idx_tiles_accessed ON tiles(accessed_at);
```

- 开启 WAL；写操作串行化，避免锁冲突。
- 默认容量上限 5 GB，可在设置页调整；超限按 `accessed_at` 淘汰。
- 失败响应做短 TTL 负缓存，避免反复打上游。
- 离线导出：按 bbox + zoom 范围复制到新的 MBTiles 文件，附 `metadata` 表。

### 3.7 API 设计

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/` | 主页面 |
| GET | `/tiles/{source}/{z}/{x}/{y}` | 瓦片代理 |
| GET | `/api/v1/config` | 应用配置、默认视角、启用源 |
| GET | `/api/v1/sources` | 数据源列表与状态 |
| GET | `/api/v1/search?q=` | 地名搜索 |
| GET | `/api/v1/streetview?lat=&lon=&radius=` | 附近街景 |
| GET | `/api/v1/wiki?lat=&lon=` | 附近百科（后期） |
| GET/POST | `/api/v1/bookmarks` | 收藏列表 / 新增 |
| DELETE | `/api/v1/bookmarks/{id}` | 删除收藏 |
| GET/POST | `/api/v1/visits` | 足迹 |
| GET | `/api/v1/health` | 各源健康状态 |
| GET/PUT | `/api/v1/settings` | 读写设置 |

约定：所有 `/api/v1/*` 返回 JSON；错误统一 `{code, message, detail}`；瓦片接口返回二进制，错误时返回 JSON + 对应状态码。

### 3.8 数据模型

```sql
bookmarks(id, lat, lon, zoom, title, note, tags, created_at, updated_at)
visits(id, lat, lon, zoom, visited_at)
settings(key, value)
search_cache(query, result_json, created_at)
source_health(source_id, ok, latency_ms, checked_at)
```

- 主键用 `INTEGER PRIMARY KEY`；时间统一 UTC ISO8601。
- 迁移：`PRAGMA user_version` 递增，启动时顺序执行迁移函数。
- 经纬度统一 WGS-84 存储；GCJ-02 只在展示国内源时转换。

### 3.9 前端结构

```
templates/
  index.html            # 整体布局
  panels/
    layers.html         # 图层列表、透明度
    info.html           # 地点信息
    streetview.html     # 街景
    bookmarks.html      # 收藏
    settings.html       # 设置
    health.html         # 源健康
static/
  vendor/               # maplibre, alpine, htmx, psv, mapillary-js
  map.js                # 地图初始化、图层注册、事件
  app.js                # Alpine store、请求、面板逻辑
  style.css             # 深色主题、布局、组件
```

布局：顶部搜索栏，左侧图层抽屉，中间全屏地图，右侧信息面板，底部状态栏（坐标、缩放、源、缓存命中）。快捷键：`/` 搜索、`R` 随机传送、`1–9` 切图层、`F` 探索模式。

### 3.10 安全、合规与坐标系

- **只绑 `127.0.0.1`**；若用户改成 `0.0.0.0`，启动时打印醒目警告。
- **瓦片代理只认 source id**，不接受任意 URL；校验 `z/x/y` 范围，禁止路径穿越。
- **缓存上限**，防止磁盘被写满；日志不记录 token。
- **署名**：每个源在 UI 上显示 attribution；导出图片时也带署名。
- **不做批量下载**；离线导出限定为用户框选区域。
- **中国区域**默认天地图；不与 GCJ-02 源混用；仅供观察学习，不做导航/测绘。
- **不含 Google 瓦片**，不实现任何绕过条款的抓取。

---

## 4. 开发方案

### 4.1 里程碑

| 阶段 | 目标 | 预计周期 | 状态 |
|---|---|---|---|
| M0 | 设计、命名、README、plan | 已完成 | ✅ |
| M1 | v0.1 地图 + 多源影像 + 搜索 + 缓存 | 2 周 | 待开工 |
| M2 | v0.2 街景 + 信息面板 + 收藏 + 健康检查 | 3 周 | 规划中 |
| M3 | v0.3 时间轴 + 地形 3D + 离线导出 + Kiwix | 4 周 | 规划中 |
| M4 | v1.0 插件机制、主题、i18n、文档站 | 持续 | 远期 |

### 4.2 v0.1 任务拆解

| # | 任务 | 产出 | 验收 |
|---|---|---|---|
| 1 | 仓库脚手架 | `pyproject.toml`、包结构、LICENSE、`.gitignore`、CI 骨架 | `uv sync` 成功；`ruff` 通过 |
| 2 | CLI 与启动器 | `woyou` 命令、端口参数、自动开浏览器 | 一条命令打开页面 |
| 3 | 配置系统 | `config.py`、`sources.yaml` 加载与校验 | 配置错误有可读提示 |
| 4 | 瓦片代理 | `/tiles/{source}/{z}/{x}/{y}` | 5 个源可正常出图 |
| 5 | MBTiles 缓存 | 读写、LRU、容量统计 | 重启后命中缓存；断网可看已访问区域 |
| 6 | 前端骨架 | 布局、MapLibre、图层切换、透明度 | 切换流畅，无闪烁 |
| 7 | 搜索 | Nominatim + 缓存 + 飞行动画 | 搜“杭州”能定位 |
| 8 | 状态栏 | 坐标、缩放、当前源、缓存命中 | 实时更新 |
| 9 | 测试 | 瓦片数学、缓存、配置、接口 | `pytest` 全绿，核心覆盖 ≥ 70% |
| 10 | 文档与发布 | README 快速开始、CHANGELOG、v0.1.0 | 按文档从零装通 |

**v0.1 验收**：新机器 5 分钟内出图；5 个源可切换；缓存跨重启生效；搜索可用；连续使用 30 分钟无未处理异常。

### 4.3 v0.2 任务拆解

| # | 任务 | 产出 | 验收 |
|---|---|---|---|
| 1 | Mapillary 接入 | token 配置、附近影像查询 | 有覆盖区域能列出影像 |
| 2 | 街景查看器 | `mapillary-js` 面板、前后移动 | 可浏览、可关闭、不卡主地图 |
| 3 | 空状态 | 无街景提示 + 外链 | 空白区域不报错 |
| 4 | 信息面板 | 反向地理编码、OSM 标签、外链 | 点击任意点有内容 |
| 5 | 收藏与足迹 | CRUD、列表、跳转 | 重启后仍在 |
| 6 | 随机与快捷键 | `R`、`/`、`1–9`、`F` | 键盘可完成主要操作 |
| 7 | 健康检查页 | 延迟、状态、手动重试 | 挂掉的源有标记 |
| 8 | 设置页 | 缓存上限、默认源、主题 | 修改即时生效 |
| 9 | 测试与发布 | 新增接口测试、v0.2.0 | 回归通过 |

### 4.4 v0.3 任务拆解

| # | 任务 | 产出 | 验收 |
|---|---|---|---|
| 1 | 年度时间轴 | EOX 年度图层切换 | 同一点可看多年对比 |
| 2 | STAC 预研 | `pystac-client` + `rio-tiler` 可行性验证 | 能渲染一景 Sentinel-2 |
| 3 | 地形 | `raster-dem`、山体阴影、pitch/bearing | 山地有明显立体感 |
| 4 | 建筑 | OSM Buildings 矢量图层 | 城市可显示简单体块 |
| 5 | 离线导出 | 框选 bbox + zoom → MBTiles | 导出文件可独立加载 |
| 6 | Kiwix 集成 | 检测本地服务、图文卡片 | 断网可看百科摘要 |
| 7 | 性能优化 | 预取、并发调优、缓存预热 | 首屏与拖动明显更顺 |
| 8 | 发布 | v0.3.0 | 完整回归 |

### 4.5 v1.0 方向

- Provider 插件机制（entry points），第三方可独立发源包；
- 主题系统与中英文 i18n；
- 配置 schema v1 冻结，保证向后兼容；
- 文档站与示例源仓库；
- 可选 PyInstaller 单文件分发（Windows 优先）。

### 4.6 工程规范

| 项 | 约定 |
|---|---|
| 分支 | trunk-based，`main` + 短生命周期 `feat/*`、`fix/*` |
| 提交 | Conventional Commits（feat/fix/docs/refactor/test/chore） |
| 代码风格 | `ruff format` + `ruff check`；全量类型注解 |
| 测试 | `pytest` + `respx` 模拟上游；核心模块覆盖 ≥ 70% |
| CI | GitHub Actions：lint、test（3.11/3.12）、build wheel |
| 版本 | SemVer；`CHANGELOG.md` 记录用户可见变更 |
| 发布 | 打 tag → 构建 wheel → GitHub Release |
| 日志 | 标准 logging，带 request id；不打印 token |
| 错误处理 | 统一异常处理器；前端 toast + 降级，不出现白屏 |

### 4.7 测试策略

- **单元**：瓦片数学、URL 模板、缓存 LRU、配置校验、坐标转换。
- **集成**：用 `respx` 模拟上游，测 `/tiles`、`/api/v1/search`、`/api/v1/health`。
- **手工**：每个源的出图、缩放边界、断网行为、缓存清理。
- **端到端**（后期）：Playwright 跑“启动 → 搜索 → 切图层 → 收藏”。

### 4.8 发布与兼容

- Python 最低版本 3.11；依赖锁在 `uv.lock`。
- 数据目录用 `platformdirs`，默认 `~/.local/share/woyou`（Windows/macOS 各自规范）。
- 升级不破坏 `sources.yaml`：新增字段给默认值，旧配置可继续用。
- 数据库迁移自动执行；失败时备份原文件并给出提示。

---

## 5. 风险与应对

| 风险 | 概率 | 影响 | 应对 |
|---|---|---|---|
| 数据源 URL 变更 / 限流 | 高 | 中 | YAML 配置 + 健康检查 + 备用源；社区提 PR |
| 许可或合规问题 | 中 | 高 | 只用开放/明确授权源；保留署名；个人本地使用；不公开部署 |
| 缓存膨胀 / 磁盘占满 | 中 | 中 | 容量上限 + LRU + 设置页可见 |
| 街景覆盖稀疏 | 高 | 低 | 接受空状态；外链 Mapillary 网页 |
| 维基被墙 | 高 | 中 | Kiwix 离线；v0.2 先外链国内站点 |
| 范围蔓延 | 高 | 中 | 严格按里程碑；非目标清单；新想法进 backlog |
| 单人维护倦怠 | 中 | 中 | 小依赖、少抽象、测试护城河、文档先行 |
| 坐标系错位 | 中 | 中 | 内部统一 WGS-84；转换模块单测；国内源单独标注 |
| 上游限流封 IP | 中 | 中 | 自定义 UA、缓存、退避、并发上限 |

---

## 6. 资源与排期

- **人力**：1 人，业余 10–15 小时/周。
- **周期**：v0.1 约 2 周；v0.2 约 3 周；v0.3 约 4 周。以实际投入为准，不设硬 deadline。
- **成本**：软件全免费；仅本地磁盘（缓存建议预留 10 GB）。
- **硬件**：现有笔记本即可；无需 GPU、无需服务器。

---

## 7. 验收清单（Definition of Done）

每个版本发布前逐项确认：

- [ ] 功能按验收标准可用
- [ ] `ruff` / `pytest` 全绿
- [ ] 新增配置有文档、有示例
- [ ] `CHANGELOG.md` 已更新
- [ ] 无密钥、无个人路径、无缓存文件进入仓库
- [ ] 署名与许可信息完整
- [ ] 从零安装按 README 可复现
- [ ] 已知问题记入 release note

---

## 8. 待决问题

| # | 问题 | 备选 | 倾向 |
|---|---|---|---|
| 1 | Esri 影像是否默认启用 | 默认开 / 首次确认后开 / 仅示例 | 首次启动让用户确认条款 |
| 2 | 天地图 key 如何引导 | 文档说明 / 首次向导 | 首次向导 + 可跳过 |
| 3 | Mapillary token 如何配置 | 环境变量 / 设置页 | 设置页，存本地 |
| 4 | Kiwix 集成方式 | 外部进程 / 内置库 | 先外部 `kiwix-serve`，稳定后再内置 |
| 5 | 是否提供 Docker | 提供 / 不提供 | 暂不；优先 `pipx` |
| 6 | 界面语言 | 中文优先 / 中英双语 | 中文优先，v1.0 做 i18n |
| 7 | 是否支持 Windows 单文件 | PyInstaller / 仅 pipx | v1.0 再评估 |

---

## 9. 附录

### 9.1 目录结构

```
woyou/
  __main__.py
  app.py
  config.py
  sources.py
  tiles/
    proxy.py
    cache.py
    health.py
  providers/
    osm.py
    esri.py
    eox.py
    gibs.py
    tianditu.py
    nominatim.py
    mapillary.py
    kiwix.py
  db.py
  models.py
  static/
    vendor/
    map.js
    app.js
    style.css
  templates/
    index.html
    panels/
sources.yaml
data/
  cache.mbtiles
  woyou.db
tests/
pyproject.toml
CHANGELOG.md
README.md
plan.md
```

### 9.2 参考

- MapLibre GL JS：https://maplibre.org/
- FastAPI：https://fastapi.tiangolo.com/
- MBTiles 规范：https://github.com/mapbox/mbtiles-spec
- Nominatim 使用政策：https://operations.osmfoundation.org/policies/nominatim/
- Mapillary API：https://www.mapillary.com/developer
- Sentinel-2 cloudless（EOX）：https://s2maps.eu/
- NASA GIBS：https://earthdata.nasa.gov/gibs
- 天地图：https://www.tianditu.gov.cn/
- 《地图管理条例》：https://www.gov.cn/gongbao/content/2016/content_2979707.htm

---

> 先把 v0.1 做出来，再谈诗和远方。
