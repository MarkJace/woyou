"""数据源定义、加载与 URL 拼装。"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field, fields
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import yaml

from .config import PACKAGE_DIR, PROJECT_ROOT

log = logging.getLogger(__name__)


@dataclass
class Source:
    id: str
    name: str
    url: str
    type: str = "raster"
    category: str = "base"  # base | weather
    min_zoom: int = 0
    max_zoom: int = 19
    tile_size: int = 256
    attribution: str = ""
    cache: bool = True
    enabled: bool = True
    opacity: float = 0.6
    date_offset: int | None = None
    headers: dict[str, str] = field(default_factory=dict)
    icon: str = ""
    description: str = ""

    def _date(self) -> str:
        offset = self.date_offset or 0
        return (datetime.now(timezone.utc) + timedelta(days=offset)).strftime("%Y-%m-%d")

    def tile_url(self, z: int, x: int, y: int) -> str:
        return self.url.format(
            z=z,
            x=x,
            y=y,
            date=self._date(),
            s="abc"[(x + y) % 3],
        )

    def cache_key(self) -> str:
        if self.date_offset is not None:
            return f"{self.id}@{self._date()}"
        return self.id

    def public(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "type": self.type,
            "category": self.category,
            "max_zoom": self.max_zoom,
            "attribution": self.attribution,
            "enabled": self.enabled,
            "opacity": self.opacity,
            "icon": self.icon,
            "description": self.description,
        }


DEFAULT_SOURCES: list[dict[str, Any]] = [
    {
        "id": "osm",
        "name": "街道地图",
        "url": "https://tile.openstreetmap.de/{z}/{x}/{y}.png",
        "category": "base",
        "max_zoom": 19,
        "attribution": "© OpenStreetMap contributors",
        "icon": "streets",
        "description": "开放街道底图，适合看道路、地名与城市结构",
        "headers": {"User-Agent": "Woyou/0.1 (personal geography tool)"},
    },
    {
        "id": "esri-street",
        "name": "街道地图 · Esri",
        "url": (
            "https://server.arcgisonline.com/ArcGIS/rest/services/"
            "World_Street_Map/MapServer/tile/{z}/{y}/{x}"
        ),
        "category": "base",
        "max_zoom": 19,
        "attribution": "Esri, HERE, Garmin, © OpenStreetMap contributors",
        "icon": "streets",
        "description": "带完整道路与地名标注的全球街道图",
    },
    {
        "id": "carto-voyager",
        "name": "街道地图 · Carto Voyager",
        "url": "https://basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}.png",
        "category": "base",
        "max_zoom": 19,
        "attribution": "© OpenStreetMap contributors © CARTO",
        "icon": "streets",
        "description": "配色柔和的全球街道图，适合日常浏览",
    },
    {
        "id": "carto-light",
        "name": "街道地图 · Carto Light",
        "url": "https://basemaps.cartocdn.com/light_all/{z}/{x}/{y}.png",
        "category": "base",
        "max_zoom": 19,
        "attribution": "© OpenStreetMap contributors © CARTO",
        "icon": "streets",
        "description": "浅色极简街道图，适合叠加专题图层",
    },
    {
        "id": "osm-hot",
        "name": "街道地图 · OSM HOT",
        "url": "https://a.tile.openstreetmap.fr/hot/{z}/{x}/{y}.png",
        "category": "base",
        "max_zoom": 19,
        "attribution": "© OpenStreetMap contributors, HOT",
        "icon": "streets",
        "description": "人道主义风格的 OSM 街道图，道路更醒目",
    },
    {
        "id": "carto-labels",
        "name": "街道标注（透明）",
        "url": "https://basemaps.cartocdn.com/light_only_labels/{z}/{x}/{y}.png",
        "category": "base",
        "max_zoom": 19,
        "attribution": "© OpenStreetMap contributors © CARTO",
        "icon": "streets",
        "description": "透明路名/地名层，可叠加在影像或其他街道图上",
    },
    {
        "id": "esri-imagery",
        "name": "卫星影像",
        "url": (
            "https://server.arcgisonline.com/ArcGIS/rest/services/"
            "World_Imagery/MapServer/tile/{z}/{y}/{x}"
        ),
        "category": "base",
        "max_zoom": 19,
        "attribution": "Esri, Maxar, Earthstar Geographics",
        "icon": "satellite",
        "description": "高分辨率卫星影像，城市区域可达亚米级",
    },
    {
        "id": "esri-topo",
        "name": "地形图",
        "url": (
            "https://server.arcgisonline.com/ArcGIS/rest/services/"
            "World_Topo_Map/MapServer/tile/{z}/{y}/{x}"
        ),
        "category": "base",
        "max_zoom": 19,
        "attribution": "Esri, HERE, Garmin, USGS",
        "icon": "terrain",
        "description": "带等高线与地名标注的地形底图",
    },
    {
        "id": "eox-s2cloudless-2024",
        "name": "无云影像 2024",
        "url": (
            "https://tiles.maps.eox.at/wmts/1.0.0/"
            "s2cloudless-2024_3857/default/g/{z}/{y}/{x}.jpg"
        ),
        "category": "base",
        "max_zoom": 14,
        "attribution": "Sentinel-2 cloudless by EOX (modified Copernicus data)",
        "icon": "cloudless",
        "description": "Sentinel-2 年度无云合成，适合看地表与大尺度变化",
    },
    {
        "id": "gibs-clouds",
        "name": "卫星云图",
        "url": (
            "https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/"
            "MODIS_Terra_CorrectedReflectance_TrueColor/default/{date}/"
            "GoogleMapsCompatible_Level9/{z}/{y}/{x}.jpg"
        ),
        "category": "weather",
        "max_zoom": 9,
        "date_offset": -1,
        "opacity": 0.55,
        "attribution": "NASA GIBS / MODIS Terra",
        "icon": "clouds",
        "description": "NASA 每日真彩云图，可看云系、台风与沙尘",
    },
]


def _candidate_paths() -> list[Path]:
    paths: list[Path] = []
    env = os.getenv("WOYOU_SOURCES")
    if env:
        paths.append(Path(env).expanduser())
    paths.extend(
        [
            Path.cwd() / "sources.yaml",
            PROJECT_ROOT / "sources.yaml",
            PACKAGE_DIR / "sources.yaml",
        ]
    )
    return paths


def load_sources(path: str | Path | None = None) -> dict[str, Source]:
    """加载数据源；YAML 中的同 id 项覆盖内置默认值。"""
    merged: dict[str, dict[str, Any]] = {item["id"]: dict(item) for item in DEFAULT_SOURCES}

    source_path: Path | None = Path(path).expanduser() if path else None
    if source_path is None:
        for candidate in _candidate_paths():
            if candidate.is_file():
                source_path = candidate
                break

    if source_path is not None and source_path.is_file():
        try:
            raw = yaml.safe_load(source_path.read_text(encoding="utf-8")) or []
        except Exception as exc:  # noqa: BLE001
            log.warning("读取 %s 失败：%s", source_path, exc)
        else:
            if isinstance(raw, list):
                for item in raw:
                    if not isinstance(item, dict) or not item.get("id"):
                        continue
                    merged[item["id"]] = {**merged.get(item["id"], {}), **item}
            else:
                log.warning("%s 应为列表，已忽略", source_path)

    allowed = {f.name for f in fields(Source)}
    result: dict[str, Source] = {}
    for source_id, item in merged.items():
        clean = {k: v for k, v in item.items() if k in allowed}
        try:
            result[source_id] = Source(**clean)
        except Exception as exc:  # noqa: BLE001
            log.warning("数据源 %s 配置无效：%s", source_id, exc)
    return result
