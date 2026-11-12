# 卧游 Woyou · 开发记录

> 本文档随开发同步更新。当前版本 **v0.4.0**（2026-11-11）。
> 产品概述见 [README.md](README.md)，执行计划见 [plan.md](plan.md)。

---

## 1. 本轮目标

按 `plan.md` 的 v0.1 范围，并加入“浏览天气”的需求，做出第一个可运行版本：

- 本地 FastAPI 服务，浏览器直接打开，无需网络代理；
- 多源底图 / 卫星影像切换，带本地瓦片缓存；
- 地名搜索、点击地图查看地点天气；
- MSN 天气地图风格的界面：全屏地图 + 左侧图层面板 + 右侧天气卡片 + 底部时间轴；
- 雷达回波与卫星云图两个天气叠加层；
- 可开源的工程骨架与基础测试。

---

## 2. 开发环境

| 项 | 值 |
|---|---|
| 日期 | 2026-11-10 |
| Python | 3.12.3 |
| 虚拟环境 | `~/repositories/woyou/proj_env` |
| Web 框架 | FastAPI 0.162.2 / Starlette 1.10.0 |
| ASGI | Uvicorn 0.54.0 |
| HTTP 客户端 | httpx 0.28.1 |
| 模板 | Jinja2 3.1.6 |
| 配置 | pydantic-settings 2.16.2 / PyYAML 6.0.3 |
| 测试 | pytest 9.2.0 |
| 地图 | MapLibre GL JS 4.7.1（本地 vendored） |
| 前端构建 | 无（原生 ES Module + 本地静态资源） |

---

## 3. 已实现内容

### 3.1 服务端

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/` | 主页面 |
| GET | `/healthz` | 存活检查 |
| GET | `/tiles/{source}/{z}/{x}/{y}` | 瓦片代理 + 缓存 |
| GET | `/api/v1/config` | 应用配置、默认视角、数据源 |
| GET | `/api/v1/sources` | 数据源列表 |
| GET | `/api/v1/weather` | 当前 / 24 小时 / 7 天天气 |
| GET | `/api/v1/radar` | RainViewer 雷达帧 |
| GET | `/api/v1/grid` | 气温 / 风场 / 空气质量网格 |
| GET | `/api/v1/streetview` | KartaView 街景照片 |
| GET | `/api/v1/search` | 中文地名搜索 |
| GET | `/api/v1/reverse` | 逆地理编码 |
| GET | `/api/v1/health` | 数据源健康检查 |
| GET | `/api/v1/stats` | 瓦片缓存统计 |

设计约束：瓦片接口只接受配置中的 `source` id，不接受任意 URL；服务只监听 `127.0.0.1`。

### 3.2 数据源

| id | 内容 | 说明 |
|---|---|---|
| `osm` | OpenStreetMap 街道图 | 使用 `tile.openstreetmap.de` |
| `esri-street` | Esri 全球街道图 | 补充底图 |
| `carto-voyager` | Carto Voyager 街道图 | OSM 数据，配色柔和 |
| `carto-light` | Carto Light 街道图 | 浅色极简，适合叠加 |
| `osm-hot` | OSM HOT 街道图 | 人道主义风格 |
| `carto-labels` | Carto 透明标注层 | 仅路名/地名，可叠加影像 |
| `esri-imagery` | Esri 高分辨率卫星影像 | 默认底图 |
| `esri-topo` | Esri 地形图 | 带等高线与地名 |
| `eox-s2cloudless-2024` | Sentinel-2 年度无云影像 | 最大 zoom 14 |
| `gibs-clouds` | NASA GIBS MODIS 真彩云图 | 按天更新，最大 zoom 9 |
| Open-Meteo | 天气、地理编码 | 免费、无 key |
| RainViewer | 雷达回波 | 免费、瓦片支持 CORS |
| BigDataCloud | 中文逆地理编码 | 免费、无 key |
| Photon | 地理编码兜底 | OSM 数据 |
| KartaView | 街景照片 | 免费读取 API，无需 key；覆盖稀疏，历史图片可能失效 |

**实际取舍**：`tile.openstreetmap.org` 在本机网络下连接被重置（HTTP 000），因此改用 `tile.openstreetmap.de`（同为 OSM 官方允许的瓦片服务），并新增 Esri 街道图作为备选。这是“无代理可用”约束下的真实调整，后续可在 `sources.yaml` 中替换为天地图或其他可直连源。街景同理：Mapillary 域名不可达，改用可直连的 KartaView；但 KartaView 覆盖稀疏，且部分历史照片已失效，服务端会先做可用性过滤。

### 3.2.1 多源底图合成（v0.4.0）

- 底图从单选扩展为“单选 / 多源合成”两种模式；
- 打开面板顶部“多源合成”后，每张底图变成开关，可同时勾选多个；
- 第一张为主底图（100%），其余按“叠加透明度”混合；
- 常用组合：Esri 影像 + Carto 透明标注、OSM + Esri 街道、Carto Light + OSM HOT；
- 状态栏与署名会显示当前主底图和叠加数量；
- Google 街道瓦片不接入：域名不可达，且条款禁止抓取/缓存/再分发。

### 3.3 瓦片缓存

- 每个数据源一个 MBTiles 文件，存放在 `data/tiles/{source}.mbtiles`；
- 使用 TMS 行号存储（`y` 翻转），兼容标准 MBTiles 工具；
- SQLite WAL 模式，`accessed_at` 记录访问时间，按 LRU 淘汰；
- 单源上限约 1.25 GB（总预算 5 GB 按 4 个源分摊），可在设置中调整；
- 命中时返回 `X-Woyou-Cache: hit`，便于调试；
- 按天变化的源（GIBS）缓存键带日期，避免跨天脏读。

### 3.4 天气

- Open-Meteo `forecast` 接口：当前温度、体感、湿度、降水、云量、气压、风速/风向/阵风；
- 未来 24 小时逐小时温度、降水概率、天气代码；
- 未来 7 天最高/最低温、降水概率、日出日落；
- WMO 天气代码映射为中文描述与图标键；
- 支持 °C / °F、km/h / mph、mm / inch；
- 服务端内存缓存 10 分钟，按经纬度（3 位小数）+ 单位索引；
- 地图点击、搜索、随机传送都会更新天气卡片。

### 3.5 雷达与云图

- RainViewer `weather-maps.json` 获取历史帧与短临预报帧；当前时段返回 8 个历史帧，nowcast 可能为空；
- 雷达瓦片直接由浏览器访问 `tilecache.rainviewer.com`，已确认返回 `Access-Control-Allow-Origin: *`；
- 时间轴支持播放/暂停、拖动、帧时间与“历史回波 / 短临预报”标识；
- 卫星云图走本地代理，按 UTC 昨天取 GIBS 真彩影像；
- 两个图层共用透明度滑块。

### 3.6 环境图层（v0.2.0）

- 气温热力图：Open-Meteo 2 米气温，当前视野 12×9 采样，径向渐变 + 模糊绘制；
- 风场流线：10 米风速/风向转 u/v，Canvas 粒子轨迹，流线长度随风速变化，带渐隐拖尾；
- 空气质量：Open-Meteo Air Quality 的 US AQI 与 PM2.5，同样 12×9 采样；
- 气温与空气质量互斥，共用一张热力图；风场可与任一层叠加；
- 图例、透明度、单位切换与天气卡片共享；
- 服务端缓存 5 分钟、前端缓存 5 分钟，拖动地图不会频繁请求；
- 数据是模型/再分析网格，不是高分辨率瓦片，适合看大范围趋势。

### 3.6.1 街景（v0.3.0）

- Mapillary 的 Graph API / 瓦片域名在当前网络不可达，改用可直连的 **KartaView**；
- KartaView 读取 API 无需 key，服务端按地图中心 500 米查询，按距离排序；
- 取最近 12 张，用 `Range: bytes=0-0` 验证图片真实可访问，过滤失效记录；
- 前端以蓝色点位显示覆盖，点击打开照片查看器，支持上一张 / 下一张；
- 支持 `?layer=streetview&lat=...&lon=...&zoom=...&sv=1` 直达并自动打开首张；
- 图片经本地 `/api/v1/streetview/image/{id}` 代理，依次尝试 CDN 原图、存储回退、缩略图；单张失败会自动切到下一张；
- 照片为 KartaView 的街道级影像（多为 PLANE），不是可自由环视的 360 全景；
- 覆盖稀疏，中国境内尤其少；部分历史照片已从 CDN 移除，因此需要服务端过滤。

### 3.7 界面

参考 MSN 天气地图的布局逻辑：

- **全屏地图**：MapLibre GL JS，栅格图层，底图切换无刷新；
- **顶部**：品牌、搜索框、单位切换、主题切换、设置；
- **左侧**：图层抽屉，底图单选、天气图层开关、透明度、雷达状态、更多图层占位；
- **右侧**：天气卡片，当前温度大字号、天气图标、体感/湿度/风/降水、24 小时横向滚动、7 天列表；
- **底部**：雷达时间轴、状态栏（坐标、缩放、底图、数据源健康）；
- **设置弹窗**：单位、主题、跟随地图中心、雷达速度、缓存统计；
- **快捷键**：`/` 搜索、`R` 随机传送、`Esc` 关闭浮层；
- **响应式**：窄屏下图层面板变为底部抽屉，天气卡片全宽，隐藏次要指标。

天气图标为内联 SVG，按 WMO 代码与昼夜切换，不依赖图标字体或外部资源。

### 3.8 安全与边界

- 只绑定 `127.0.0.1`，不做账号、多用户或公网服务；
- 瓦片代理按 source id 查表，杜绝任意 URL 与 SSRF；
- 校验 `z/x/y` 范围，单瓦片大小上限 8 MB；
- 缓存设容量上限，避免磁盘写满；
- 不包含 Google 瓦片，不实现绕过服务条款的抓取；
- UI 显示各数据源 attribution。

### 3.9 启动体验（v0.1.1）

- 启动面板在服务真正 ready 后才打印，URL 不会被日志淹没；
- uvicorn / httpx 日志压到 WARNING，且不使用 ANSI 颜色；
- uvicorn 在主线程运行，Ctrl+C 由它自己处理，退出后打印“已停止”，终端不留残余输出；
- 数据目录启动前做写权限探测，失败时给出可读提示，不抛 traceback；
- 浏览器打开只尝试 GUI 通道：WSL 下依次尝试 `wslview` / PowerShell / `cmd`；Linux 下只在系统注册了默认浏览器时用 `xdg-open`，并直接尝试常见 GUI 浏览器；绝不回退到 `lynx` / `w3m` 等文本浏览器；
- 启动面板始终打印 URL，并提示“若未自动打开，按住 Ctrl 点击或复制”。

---

## 4. 文件结构

```
woyou/
  __main__.py            # CLI：起服务 + 打开浏览器
  app.py                 # FastAPI 路由与生命周期
  config.py              # 配置
  sources.py             # 数据源定义、YAML 加载、URL 拼装
  db.py                  # SQLite：设置/搜索缓存/健康/书签表
  tiles/
    cache.py             # MBTiles 缓存 + LRU
    proxy.py             # 瓦片代理 + 健康探测
  providers/
    weather.py           # Open-Meteo
    radar.py             # RainViewer
    geocode.py           # Open-Meteo / BigDataCloud / Photon
  static/
    css/style.css
    js/map.js            # 地图、图层、雷达源
    js/app.js            # UI、天气、搜索、设置
    vendor/              # maplibre-gl.js / .css
  templates/index.html
sources.yaml
tests/test_basic.py
pyproject.toml
data/                    # 运行时生成，gitignore
```

---

## 5. 运行方式

```bash
cd ~/repositories/woyou
source proj_env/bin/activate
pip install -e .
woyou
```

浏览器会自动打开 `http://127.0.0.1:8765`。

也可以不安装，直接运行：

```bash
proj_env/bin/python -m woyou
```

常用参数：

```bash
woyou --port 8766          # 指定起始端口（被占用会自动顺延）
woyou --no-browser         # 不自动开浏览器
woyou --data-dir ./data    # 指定缓存与数据库目录
woyou --reload             # 开发模式，改代码自动重载
```

---

## 6. 验证记录

| 项 | 结果 |
|---|---|
| `pytest` | 4 passed |
| `/healthz` | 200，返回版本 0.1.0 |
| `/` | 200，模板正常渲染 |
| `/api/v1/config` | 200，6 个底图/天气源 |
| `/api/v1/weather` | 200，24 小时 + 7 天完整 |
| `/api/v1/search?q=杭州` | 200，返回“杭州 · 浙江 · 中国” |
| `/api/v1/reverse` | 200，返回“上海市 · 中华人民共和国” |
| `/api/v1/radar` | 200，8 个历史帧 |
| `/api/v1/grid` 温度/风/空气 | 200，12×9 矩阵 |
| `/api/v1/streetview` | 柏林 12 张、巴黎 3 张、上海 1 张可用照片 |
| Carto / OSM HOT 瓦片 | 200 |
| 多源合成截图 | 影像 + Carto 标注正常，状态栏显示 `+1` |
| 瓦片首次请求 | 200，`X-Woyou-Cache: miss` |
| 瓦片二次请求 | 200，`X-Woyou-Cache: hit` |
| GIBS / EOX / OSM 瓦片 | 均 200 |
| 雷达瓦片 CORS | `Access-Control-Allow-Origin: *` |
| `python -m woyou` | 8899 端口启动成功，`/healthz` 200 |
| 前端冒烟（jsdom + Mock MapLibre） | 通过：5 个底图、2 个天气层、24 小时、7 天、雷达时间轴、搜索联动 |
| 前端冒烟（环境图层） | 气温图例、风场图例与 Canvas 绘制路径通过 |
| 街景查看器 | Edge 截图：弹窗、元数据、上一张/下一张布局正常；首图受 CDN 速度影响 |
| Edge headless 截图 | 底图、气温、风场、空气质量、街景弹窗布局正常 |
| 启动 + Ctrl+C | 退出码 0，stderr 为空，打印“已停止” |
| 不可写数据目录 | 退出码 1，给出可读提示，无 traceback |
| 浏览器失败降级 | 启动面板始终显示 URL 与手动打开提示 |

**截图验证**：用 Windows Edge headless 对底图、气温、风场、空气质量、街景弹窗截图检查，图例、面板、Canvas 叠加和照片查看器布局均正常。尚未建立视觉基线做自动像素对比；后续可用 Playwright + Edge 补上。

---

## 7. 已知问题与限制

1. **环境图层是采样网格，不是高分辨率瓦片**：12×9，适合看大范围趋势；气温/AQI 为模型/再分析数据，不能替代站点观测。
2. **RainViewer 短临预报帧可能为空**：取决于当前时段，界面会显示“预报 0 帧”，不影响历史回波。
3. **OSM 官方瓦片不可达**：使用 `tile.openstreetmap.de`；高流量或商用需自建瓦片或换用天地图。
4. **搜索缓存会残留**：`search_cache` 表持久化；更换地理编码策略后，旧查询可能命中旧结果，需要清表或换查询词。
5. **逆地理编码中文地名**：来自 BigDataCloud，部分地名可能为繁体或与本地叫法不同。
6. **收藏/足迹只有表结构**：环境图层已完成，收藏/足迹 UI 仍在 v0.2 backlog。
7. **首次健康检查较慢**：GIBS 探测约 3 秒，整体 3–5 秒；页面不阻塞，状态栏随后更新。
8. **缓存预算**：按 4 个源分摊，实际总容量可能低于 5 GB；源数量增加后需要调整分配。
9. **没有地形、3D、年度时间轴**：属于 v0.3 范围。
10. **瓦片源稳定性**：第三方源可能改 URL 或限流；`sources.yaml` 与健康检查用于快速修复。
11. **自动打开浏览器依赖系统关联**：WSL/Linux 若未注册默认浏览器，工具会尝试已知 GUI 浏览器；仍失败时请手动打开启动面板中的 URL（已保证不被日志淹没）。
12. **风场动画是屏幕空间近似**：地图旋转或大范围缩放时，流线方向与速度仅作视觉参考，不用于精确风场分析。
13. **KartaView 覆盖稀疏**：中国境内点位很少，且部分历史图片已失效；查看器只展示经过服务端验证的最近 12 张。
14. **街景多为平面照片**：KartaView 返回的大多是 PLANE 投影，不能像 Google 街景那样自由环视；如需 360 全景或国内高覆盖，需另接高德/百度（需 key）或 Mapillary（需代理）。

---

## 8. 下一版计划（v0.2）

- 收藏与足迹 UI（保存视角、备注、跳转）；
- 地点信息面板：OSM 标签、外链百科/游记；
- 天气图层扩展：尝试 Open-Meteo 网格或其他可直连的温度/风场栅格；
- 数据源健康状态进入图层面板，失败自动降级；
- 年度影像时间轴（EOX 多年份）；
- 引入 Playwright 截图回归，覆盖桌面与窄屏；
- 把 README 的“规划”表述更新为“已实现/进行中”。

---

## 9. 变更日志

| 日期 | 版本 | 内容 |
|---|---|---|
| 2026-11-10 | v0.1.0 | 首个可运行版本：多源底图、瓦片缓存、中文搜索、天气卡片、雷达/云图、MSN 风格界面、基础测试 |
| 2026-11-11 | v0.1.1 | 修复启动体验：压缩 uvicorn/httpx 日志、主线程运行以干净响应 Ctrl+C、仅尝试 GUI 浏览器、数据目录预检与可读错误 |
| 2026-11-11 | v0.2.0 | 新增气温热力图、风场流线、空气质量图层；新增 `/api/v1/grid`；Canvas 叠加与图例 |
| 2026-11-11 | v0.3.0 | 新增 KartaView 街景图层与照片查看器；服务端过滤失效图片；支持街景深链接 |
| 2026-11-11 | v0.3.1 | 街景图片改走本地代理（原图→回退→缩略图），失败自动切下一张，避免 CDN 直连导致“KartaView 不可用” |
| 2026-11-12 | v0.4.0 | 新增 Carto Voyager/Light、OSM HOT、透明标注；底图支持多源合成与叠加透明度 |

---

## 10. 决策记录

- **不做 Node 构建链**：Jinja2 + 原生 ES Module 足够支撑当前 UI，降低环境门槛；后续 UI 复杂化再评估 Vue。
- **天气卡片放右侧**：左侧留给图层，底部留给时间轴，右侧卡片不遮挡地图中心，接近 MSN 天气地图的信息层级。
- **天气数据选 Open-Meteo**：免费、无 key、支持中文、字段完整；雷达选 RainViewer 因为瓦片直接支持 CORS。
- **地理编码选 Open-Meteo + BigDataCloud**：Nominatim 在本机网络不可达，Photon 中文返回不稳定；Open-Meteo 搜索与 BigDataCloud 逆编码都返回中文。
- **MBTiles 按源拆分**：避免单文件锁竞争，便于单独清理和导出；代价是缓存统计需要聚合。
- **只绑 127.0.0.1**：把项目稳定地留在“个人工具”一侧，规避互联网地图服务的资质与审核问题。
- **不用 `webbrowser` 模块**：它在 Linux/WSL 上可能退回 `lynx`/`w3m` 等文本浏览器，正是终端“跳出一个网址”的来源；改为只尝试 GUI 通道，失败就保留清晰的手动地址。

---

## 11. 部署状态

- 代码已部署到 `~/repositories/woyou`，虚拟环境为 `proj_env`；
- 已执行 `proj_env/bin/pip install -e .`，`proj_env/bin/woyou` 可直接启动；
- 部署后回归：`/healthz` 200、首页 200、OSM 瓦片 200、`pytest` 4 passed；
- v0.1.1 启动验证：8914 端口，Ctrl+C 退出码 0、stderr 为空；不可写数据目录退出码 1、提示可读；启动面板始终包含 URL；
- v0.2.0 环境图层验证：`/api/v1/grid` 三类图层 12×9 均 200；前端冒烟覆盖气温/风场图例与 Canvas 绘制路径；
- Edge headless 截图检查：底图、气温、风场、空气质量、街景弹窗布局正常；
- v0.3.0 街景验证：`/api/v1/streetview` 柏林 12 张、上海 1 张可用；Ctrl+C 退出码 0、stderr 为空；
- v0.4.0 底图验证：10 个源加载正常，Carto/OSM HOT 瓦片 200，多源合成（影像 + Carto 标注）Edge 截图正常；
- 验证后已停止，未常驻后台；
- 首次使用：

```bash
cd ~/repositories/woyou
source proj_env/bin/activate
woyou
```

如端口被占用，`woyou` 会自动顺延；可用 `--port` 指定起始端口。
