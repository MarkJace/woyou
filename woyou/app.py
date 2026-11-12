"""FastAPI 应用。"""

from __future__ import annotations

import asyncio
import logging
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import httpx
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from . import __app_name__, __version__
from .config import PACKAGE_DIR, Settings, get_settings
from .db import Database
from .providers import geocode, grid, radar, streetview, weather
from .sources import Source, load_sources
from .tiles.cache import CacheManager
from .tiles.proxy import probe_source
from .tiles.proxy import router as tiles_router

log = logging.getLogger(__name__)

STREETVIEW_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36 Edg/142.0.0.0"
    ),
    "Referer": "https://kartaview.org/",
    "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
}


class TTLCache:
    """极简内存缓存，够本地工具使用。"""

    def __init__(self, ttl: float, maxsize: int = 128):
        self.ttl = ttl
        self.maxsize = maxsize
        self._data: dict[Any, tuple[float, Any]] = {}

    def get(self, key: Any) -> Any | None:
        item = self._data.get(key)
        if item is None:
            return None
        expires, value = item
        if time.monotonic() > expires:
            self._data.pop(key, None)
            return None
        return value

    def set(self, key: Any, value: Any) -> None:
        if len(self._data) >= self.maxsize:
            oldest = min(self._data, key=lambda k: self._data[k][0])
            self._data.pop(oldest, None)
        self._data[key] = (time.monotonic() + self.ttl, value)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings: Settings = app.state.settings
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    settings.tile_dir.mkdir(parents=True, exist_ok=True)

    app.state.db = Database(settings.db_path)
    app.state.registry = load_sources()
    app.state.caches = CacheManager(settings.tile_dir, settings.cache_max_mb * 1024 * 1024)
    app.state.http = httpx.AsyncClient(
        timeout=httpx.Timeout(settings.request_timeout, connect=6.0),
        limits=httpx.Limits(max_connections=32, max_keepalive_connections=16),
        headers={
            "User-Agent": settings.user_agent,
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        },
        follow_redirects=True,
    )
    app.state.weather_cache = TTLCache(ttl=600, maxsize=128)
    app.state.radar_cache = TTLCache(ttl=120, maxsize=4)
    app.state.grid_cache = TTLCache(ttl=300, maxsize=64)
    app.state.streetview_cache = TTLCache(ttl=60, maxsize=64)
    app.state.streetview_images = {}
    app.state.streetview_image_cache = {}
    app.state.health = {}
    app.state.health_checked_at = 0.0
    log.info("卧游 v%s 数据目录：%s", __version__, settings.data_dir)
    try:
        yield
    finally:
        await app.state.http.aclose()


def create_app(settings: Settings | None = None) -> FastAPI:
    application = FastAPI(
        title="卧游 Woyou",
        version=__version__,
        lifespan=lifespan,
        docs_url="/api/docs",
        redoc_url=None,
    )
    application.state.settings = settings or get_settings()
    application.mount(
        "/static",
        StaticFiles(directory=str(PACKAGE_DIR / "static")),
        name="static",
    )
    application.state.templates = Jinja2Templates(directory=str(PACKAGE_DIR / "templates"))
    application.include_router(tiles_router)

    @application.get("/", response_class=HTMLResponse)
    async def index(request: Request) -> HTMLResponse:
        return request.app.state.templates.TemplateResponse(
            request=request,
            name="index.html",
            context={"app_name": __app_name__, "version": __version__},
        )

    @application.get("/healthz")
    async def healthz() -> dict:
        return {"ok": True, "version": __version__}

    @application.get("/api/v1/config")
    async def config(request: Request) -> dict:
        settings: Settings = request.app.state.settings
        registry: dict[str, Source] = request.app.state.registry
        return {
            "app": {"name": __app_name__, "version": __version__},
            "default_view": {
                "lat": settings.default_lat,
                "lon": settings.default_lon,
                "zoom": settings.default_zoom,
            },
            "units": "metric",
            "sources": [source.public() for source in registry.values() if source.enabled],
            "weather": {"provider": "Open-Meteo", "radar": "RainViewer"},
            "cache": {"max_mb": settings.cache_max_mb},
        }

    @application.get("/api/v1/sources")
    async def sources(request: Request) -> dict:
        registry: dict[str, Source] = request.app.state.registry
        return {"sources": [source.public() for source in registry.values()]}

    @application.get("/api/v1/weather")
    async def api_weather(
        request: Request,
        lat: float = Query(..., ge=-90, le=90),
        lon: float = Query(..., ge=-180, le=180),
        units: str = Query("metric", pattern="^(metric|imperial)$"),
    ) -> dict:
        key = (round(lat, 3), round(lon, 3), units)
        cached = request.app.state.weather_cache.get(key)
        if cached is not None:
            return cached
        try:
            data = await weather.fetch_weather(request.app.state.http, lat, lon, units)
        except httpx.HTTPError as exc:
            log.warning("天气请求失败：%s", exc)
            raise HTTPException(status_code=502, detail="天气服务暂时不可用") from exc
        request.app.state.weather_cache.set(key, data)
        return data

    @application.get("/api/v1/radar")
    async def api_radar(request: Request) -> dict:
        cached = request.app.state.radar_cache.get("radar")
        if cached is not None:
            return cached
        try:
            data = await radar.fetch_radar(request.app.state.http)
        except httpx.HTTPError as exc:
            log.warning("雷达请求失败：%s", exc)
            raise HTTPException(status_code=502, detail="雷达服务暂时不可用") from exc
        request.app.state.radar_cache.set("radar", data)
        return data

    @application.get("/api/v1/grid")
    async def api_grid(
        request: Request,
        kind: str = Query(..., pattern="^(temperature|wind|air)$"),
        west: float = Query(..., ge=-180, le=180),
        south: float = Query(..., ge=-85, le=85),
        east: float = Query(..., ge=-180, le=180),
        north: float = Query(..., ge=-85, le=85),
        nx: int = Query(12, ge=4, le=16),
        ny: int = Query(9, ge=4, le=12),
    ) -> dict:
        if south >= north or west >= east:
            raise HTTPException(status_code=400, detail="无效的视野范围")
        if nx * ny > 192:
            raise HTTPException(status_code=400, detail="网格过大")
        key = (
            kind,
            round(west, 2),
            round(south, 2),
            round(east, 2),
            round(north, 2),
            nx,
            ny,
        )
        cached = request.app.state.grid_cache.get(key)
        if cached is not None:
            return cached
        try:
            data = await grid.fetch_grid(
                request.app.state.http,
                kind,
                south,
                west,
                north,
                east,
                nx,
                ny,
            )
        except httpx.HTTPError as exc:
            log.warning("网格请求失败（%s）：%s", kind, exc)
            raise HTTPException(status_code=502, detail="环境图层服务暂时不可用") from exc
        request.app.state.grid_cache.set(key, data)
        return data

    @application.get("/api/v1/streetview")
    async def api_streetview(
        request: Request,
        lat: float = Query(..., ge=-85, le=85),
        lon: float = Query(..., ge=-180, le=180),
        radius: int = Query(500, ge=50, le=500),
        limit: int = Query(100, ge=1, le=200),
    ) -> dict:
        key = (round(lat, 3), round(lon, 3), radius, limit)
        cached = request.app.state.streetview_cache.get(key)
        if cached is not None:
            return cached
        try:
            data = await streetview.fetch_streetview(
                request.app.state.http, lat, lon, radius, limit
            )
        except (httpx.HTTPError, ValueError) as exc:
            log.warning("街景请求失败：%s", exc)
            raise HTTPException(status_code=502, detail="街景服务暂时不可用") from exc
        for image in data.get("images", []):
            request.app.state.streetview_images[image["id"]] = image
        while len(request.app.state.streetview_images) > 500:
            request.app.state.streetview_images.pop(
                next(iter(request.app.state.streetview_images))
            )
        request.app.state.streetview_cache.set(key, data)
        return data

    @application.get("/api/v1/streetview/image/{image_id}")
    async def api_streetview_image(request: Request, image_id: str) -> Response:
        if not image_id.isdigit():
            raise HTTPException(status_code=400, detail="无效的街景 ID")
        cache = request.app.state.streetview_image_cache
        cached = cache.get(image_id)
        if cached is not None:
            content, content_type = cached
            return Response(
                content=content,
                media_type=content_type,
                headers={"Cache-Control": "public, max-age=86400"},
            )

        image = request.app.state.streetview_images.get(image_id)
        urls = []
        if image:
            urls = [image.get("image"), image.get("image_fallback"), image.get("thumb")]
        if not urls:
            try:
                urls = await streetview.image_urls(request.app.state.http, image_id)
            except (httpx.HTTPError, ValueError):
                urls = []

        for url in urls:
            if not url:
                continue
            try:
                response = await request.app.state.http.get(
                    url,
                    headers=STREETVIEW_HEADERS,
                    timeout=15.0,
                )
            except httpx.HTTPError:
                continue
            content_type = (response.headers.get("content-type") or "").split(";")[0]
            if (
                response.status_code == 200
                and content_type.startswith("image/")
                and response.content
            ):
                if len(cache) >= 24:
                    cache.pop(next(iter(cache)))
                cache[image_id] = (response.content, content_type)
                return Response(
                    content=response.content,
                    media_type=content_type,
                    headers={"Cache-Control": "public, max-age=86400"},
                )
        raise HTTPException(status_code=404, detail="街景图片不可用")

    @application.get("/api/v1/search")
    async def api_search(
        request: Request,
        q: str = Query(..., min_length=1, max_length=80),
    ) -> dict:
        query = q.strip()
        if not query:
            raise HTTPException(status_code=400, detail="搜索词不能为空")
        db: Database = request.app.state.db
        cached = db.get_cached_search(query.lower())
        if cached is not None:
            return {"query": query, "results": cached, "cached": True}
        try:
            results = await geocode.search(request.app.state.http, query)
        except httpx.HTTPError as exc:
            log.warning("地理编码失败：%s", exc)
            raise HTTPException(status_code=502, detail="搜索服务暂时不可用") from exc
        db.cache_search(query.lower(), results)
        return {"query": query, "results": results, "cached": False}

    @application.get("/api/v1/reverse")
    async def api_reverse(
        request: Request,
        lat: float = Query(..., ge=-90, le=90),
        lon: float = Query(..., ge=-180, le=180),
    ) -> dict:
        try:
            return await geocode.reverse(request.app.state.http, lat, lon)
        except httpx.HTTPError as exc:
            log.warning("逆地理编码失败：%s", exc)
            return {
                "name": f"{lat:.4f}, {lon:.4f}",
                "label": f"{lat:.4f}, {lon:.4f}",
                "lat": lat,
                "lon": lon,
            }

    @application.get("/api/v1/health")
    async def api_health(request: Request) -> dict:
        now = time.time()
        if now - request.app.state.health_checked_at < 60 and request.app.state.health:
            return {"sources": list(request.app.state.health.values())}
        registry: dict[str, Source] = request.app.state.registry
        client: httpx.AsyncClient = request.app.state.http
        results = await asyncio.gather(
            *(probe_source(client, source) for source in registry.values())
        )
        db: Database = request.app.state.db
        for item in results:
            request.app.state.health[item["id"]] = item
            db.upsert_health(item["id"], item["ok"], item.get("latency_ms"), item.get("error"))
        request.app.state.health_checked_at = now
        return {"sources": results}

    @application.get("/api/v1/stats")
    async def api_stats(request: Request) -> dict:
        caches: CacheManager = request.app.state.caches
        stats = caches.stats()
        stats["database_bytes"] = (
            request.app.state.settings.db_path.stat().st_size
            if request.app.state.settings.db_path.exists()
            else 0
        )
        return stats

    @application.exception_handler(Exception)
    async def unhandled_exception(request: Request, exc: Exception) -> JSONResponse:
        log.exception("未处理异常：%s", exc)
        return JSONResponse(
            {"code": 500, "message": "服务器内部错误"},
            status_code=500,
        )

    return application


app = create_app()
