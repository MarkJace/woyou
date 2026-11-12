# 卧游 · Woyou

> 不出户，游天下。
>
> 一个跑在浏览器里的个人地理探索台。

---

## 这是什么

**卧游**是一个本地运行的个人地理探索工具。它把全球的卫星影像、街道地图、天气、雷达和地点信息，聚合到一个浏览器界面里，让你在不依赖网络代理的情况下看世界。

它不是一个地图服务：不面向公众提供访问，不需要账号，不上传你的数据。它是一个装在自己电脑上、一条命令启动、浏览器自动打开的工具。

当前版本 **v0.4.0**，已经可以：

- 切换 10 个底图 / 影像 / 云图源，支持多源街道底图合成；
- 搜索中文地名，点击地图查看该地点天气；
- 查看当前天气、未来 24 小时与 7 天预报；
- 叠加雷达回波并播放时间轴；
- 叠加气温热力图、风场流线与空气质量图层；
- 查看 KartaView 街景照片（无需 key）；
- 把浏览过的瓦片缓存到本地。

---

## 名字的由来

「卧游」出自《宋书·宗炳传》。南朝画家宗炳年老多病，感叹名山难以遍游，于是把游历过的山水画满四壁，说：

> 老疾俱至，名山恐难遍睹，唯当澄怀观道，卧以游之。

躺着看画，神游万里。后来「卧游」成了中国山水画里的一个母题——不出门，也能游遍天下。

英文名 **Woyou**，*Armchair atlas — explore the world from your desk.*

---

## 为什么做它

- **访问被中断**：Google Earth / Google Maps 在国内需要代理，探索的节奏总被网络打断。
- **数据很分散**：Sentinel、Landsat、OSM、NASA GIBS、天气与雷达，散在几十个站点，分辨率、时间、覆盖各不相同。
- **现成工具不顺手**：QGIS 太重，单一数据源网站太专，在线服务又把数据放在别人服务器上。

卧游想做的，是把这些源收进一个本地界面：**一个搜索框、一层层影像、一条时间轴、一张天气卡片。**

---

## 快速开始

项目目录下已经准备好虚拟环境 `proj_env`（Python 3.12）：

```bash
cd ~/repositories/woyou
source proj_env/bin/activate
pip install -e .
woyou
```

终端会显示一个简洁的启动面板，并尝试打开系统浏览器。若没有自动打开，按住 Ctrl 点击面板里的地址，或复制到浏览器即可。

如果只想复现依赖、不安装项目本身：

```bash
pip install -r requirements.txt
python -m woyou
```

不安装也可以直接运行：

```bash
proj_env/bin/python -m woyou
```

常用参数：

```bash
woyou --port 8766          # 起始端口，被占用会自动顺延
woyou --no-browser         # 不自动打开浏览器
woyou --data-dir ./data    # 缓存与数据库目录
woyou --reload             # 开发模式
```

数据默认写入项目下的 `data/`：`tiles/*.mbtiles` 是瓦片缓存，`woyou.db` 保存设置与搜索缓存。

---

## 现在能做什么

### 地图

- **OpenStreetMap** 街道图（`tile.openstreetmap.de`）
- **Esri World Street Map** 全球街道图
- **Carto Voyager / Carto Light** 两种 OSM 风格街道图
- **OSM HOT** 人道主义风格街道图
- **Carto 透明标注层** 可叠加在影像或其他街道图上
- **Esri World Imagery** 高分辨率卫星影像（默认）
- **Esri World Topo Map** 地形图
- **EOX Sentinel-2 cloudless 2024** 年度无云影像
- **NASA GIBS MODIS** 每日真彩云图

**多源合成**：勾选“多源合成”后，底图从单选变为多选。第一张为主底图（100%），其余按“叠加透明度”混合。常用组合：

- 卫星影像 + Carto 透明标注 → 高清影像带路名；
- OSM + Esri 街道 → 对比两套道路数据；
- Carto Light + OSM HOT → 叠加不同风格的道路与地名。

图层可切换、可调透明度；底图请求经过本地代理并写入 MBTiles 缓存。

> Google 街道瓦片不在此列：`google.com` 相关域名在当前网络不可达，且 Google 条款禁止抓取、缓存或再分发瓦片，不能作为本地数据源接入。

### 搜索与地点

- Open-Meteo 地理编码，中文地名优先；
- 搜索“杭州”“上海”直接定位；
- 点击地图任意位置，显示坐标并反查行政区；
- 逆地理编码优先 BigDataCloud（中文），Photon 兜底。

### 天气

- 当前温度、体感、湿度、风、降水、云量、气压；
- 未来 24 小时逐小时预报；
- 未来 7 天最高 / 最低温；
- °C / °F 切换，km/h / mph、mm / inch 随单位变化；
- 支持“跟随地图中心”自动更新。

### 雷达与云图

- RainViewer 雷达回波，支持播放、暂停、拖动时间轴；
- 历史回波与短临预报分开展示；
- NASA GIBS 卫星云图叠加；
- 雷达瓦片直接由浏览器访问，支持 CORS。

### 环境图层

- **气温热力图**：Open-Meteo 2 米气温，按当前视野采样 12×9 网格绘制；
- **风场流线**：10 米风速/风向转成 u/v，Canvas 粒子动画；
- **空气质量**：CAMS 的 US AQI 与 PM2.5，同样按网格采样；
- 气温与空气质量共用一张热力图（互斥），风场可与任一层叠加；
- 每个图层都有图例、透明度与单位联动；
- 可用 `?layer=temperature` / `?layer=wind` / `?layer=airquality` 直接打开对应图层；
- 网格数据服务端缓存 5 分钟，前端也缓存 5 分钟，拖动地图不会疯狂请求。

### 街景

- 使用 KartaView 读取 API，无需 key，也无需代理；
- 打开左侧“街景”开关或顶部相机按钮，放大到街道级别（z ≥ 13）；
- 当前 500 米内的可用照片会显示为蓝色点位，点击打开查看器；
- 查看器支持上一张 / 下一张，显示拍摄日期、朝向与距离；
- 只保留最近 12 张且图片实际可访问的记录，避免点到失效图片；
- KartaView 覆盖稀疏，中国境内尤其少；可试试柏林、巴黎等覆盖较多的城市；
- 示例：`?layer=streetview&lat=52.5&lon=13.4&zoom=16&sv=1`。

### 界面

参考 MSN 天气地图的信息层级：

- 全屏地图；
- 顶部搜索与单位/主题/设置；
- 左侧图层面板（底图、天气、环境图层、图例）；
- 右侧天气卡片（当前 + 24 小时 + 7 天）；
- 底部雷达时间轴与状态栏；
- 窄屏下图层面板变为底部抽屉；
- 快捷键：`/` 搜索、`R` 随机传送、`Esc` 关闭浮层。

---

## 数据源与许可

| 数据源 | 用途 | 许可 / 备注 |
|---|---|---|
| OpenStreetMap | 街道底图 | ODbL，需署名；遵守 tile usage policy |
| Esri World Imagery / Street / Topo | 影像、街道、地形 | Esri 条款；个人非商业、署名，禁止批量下载与再分发 |
| EOX Sentinel-2 cloudless | 年度无云影像 | CC 授权，需署名；使用前确认对应年份条款 |
| NASA GIBS | 每日真彩云图 | 免费开放，NASA 署名 |
| Open-Meteo | 天气、地理编码 | 免费、无 key；天气数据 CC BY 4.0 |
| Open-Meteo Air Quality | 空气质量（US AQI / PM2.5） | 免费、无 key；CAMS 数据 |
| BigDataCloud | 逆地理编码 | 免费客户端接口，无需 key |
| Photon | 地理编码兜底 | OSM 数据，需遵守使用政策 |
| RainViewer | 雷达回波 | 免费公共 API，瓦片支持 CORS |
| KartaView | 街景照片 | 免费读取 API，无需 key；覆盖稀疏，部分历史图片可能失效 |
| Carto / OSM HOT | 街道底图、透明标注 | © OpenStreetMap contributors © CARTO；HOT 风格 |

新增数据源时，在 `sources.yaml` 中声明 `attribution`、`max_zoom`、是否允许缓存，前端会自动拼接署名条。

> 说明：`tile.openstreetmap.org` 在部分网络下不可达，默认改用 `tile.openstreetmap.de`。如果你有天地图 key 或其他可直连源，可以在 `sources.yaml` 中替换。

---

## 技术方案

**Python 后端 + 原生浏览器前端，全部跑在本机。**

```
浏览器（http://127.0.0.1:8765）
  Jinja2 页面 + 原生 ES Module + MapLibre GL JS
        │  同源请求，无 CORS
FastAPI（Python）
  ├─ /tiles/{source}/{z}/{x}/{y}   瓦片代理 + MBTiles 缓存
  ├─ /api/v1/weather               Open-Meteo
  ├─ /api/v1/radar                 RainViewer
  ├─ /api/v1/grid                  气温/风场/空气质量网格
  ├─ /api/v1/search                地理编码
  ├─ /api/v1/reverse               逆地理编码
  └─ SQLite：设置 / 搜索缓存 / 源健康 / 书签表
```

| 层 | 选型 |
|---|---|
| Web 框架 | FastAPI + Uvicorn |
| 页面 | Jinja2 + 原生 ES Module（无 Node 构建） |
| 地图 | MapLibre GL JS 4.7.1（本地 vendored） |
| 叠加绘制 | Canvas 2D（热力图、风场粒子） |
| HTTP | httpx（连接池、超时、重试） |
| 缓存 | MBTiles（SQLite，WAL，LRU） |
| 数据库 | sqlite3 标准库 |
| 配置 | pydantic-settings + PyYAML |
| 测试 | pytest |

瓦片接口只接受配置里的 `source` id，不接受任意 URL；服务默认只监听 `127.0.0.1`。

---

## 项目结构

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
    grid.py              # 气温 / 风场 / 空气质量网格
    geocode.py           # Open-Meteo / BigDataCloud / Photon
  static/
    css/style.css
    js/map.js
    js/overlays.js       # 热力图 + 风场流线
    js/app.js
    vendor/              # maplibre-gl.js / .css
  templates/index.html
sources.yaml
tests/test_basic.py
pyproject.toml
data/                    # 运行时生成，gitignore
```

---

## 路线图

| 版本 | 目标 | 状态 |
|---|---|---|
| v0.1 | 多源影像 + 搜索 + 天气 + 雷达/云图 + 缓存 | ✅ 已完成 |
| v0.2 | 环境图层（气温/风场/空气质量）✅；收藏/足迹、信息面板进行中 | 进行中 |
| v0.3 | 街景（KartaView）✅；年度时间轴、地形 3D、离线导出进行中 | 进行中 |
| v0.4 | 多源街道底图 + 合成模式 ✅ | 已完成 |
| v1.0 | 源插件机制、主题、i18n、稳定配置 schema | 远期 |

---

## 边界与合规

- **个人使用**：只监听 `127.0.0.1`，不部署公网，不做多用户，不提供托管服务。
- **尊重数据条款**：保留完整署名，不批量下载、不再分发瓦片；禁止缓存的源只做透传。
- **中国区域**：如需合规底图，建议接入天地图；WGS-84 与 GCJ-02 不混用。
- **用途限制**：仅供地理观察与学习，不作为测绘、导航或决策依据。

如果未来要公开部署给他人使用，请先了解《地图管理条例》对互联网地图服务、测绘资质与地图审核的要求——那已经是另一个项目了。

---

## 文档

- [plan.md](plan.md) — 背景、技术路线、开发计划
- [document.md](document.md) — 开发记录、验证结果、已知问题

---

## 许可

代码 MIT。数据与图片遵循各自许可，详见上表。

## 致谢

OpenStreetMap 贡献者、Copernicus / ESA、NASA GIBS、Esri、EOX、Open-Meteo、RainViewer、Mapillary，以及所有把地理数据开放出来的人。

> 山川之美，古来共谈。今以寸屏，卧而游之。
