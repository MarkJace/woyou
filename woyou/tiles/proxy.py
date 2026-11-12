"""瓦片代理路由。"""

from __future__ import annotations

import logging
import time

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response

from ..sources import Source

log = logging.getLogger(__name__)
router = APIRouter()

MAX_TILE_BYTES = 8 * 1024 * 1024
MAX_ZOOM = 22


def _bad(message: str, status: int = 400) -> JSONResponse:
    return JSONResponse({"code": status, "message": message}, status_code=status)


@router.get("/tiles/{source_id}/{z}/{x}/{y}")
async def get_tile(source_id: str, z: int, x: int, y: int, request: Request) -> Response:
    registry: dict[str, Source] = request.app.state.registry
    source = registry.get(source_id)
    if source is None:
        return _bad("未知数据源", 404)
    if z < 0 or z > MAX_ZOOM:
        return _bad("缩放级别超出范围", 400)
    if not (0 <= x < (1 << z)) or not (0 <= y < (1 << z)):
        return _bad("瓦片坐标超出范围", 400)
    if z > source.max_zoom:
        return Response(status_code=204)

    cache = request.app.state.caches.get(source.cache_key())
    cached = cache.get(z, x, y)
    if cached is not None:
        data, content_type = cached
        return Response(
            content=data,
            media_type=content_type,
            headers={"Cache-Control": "public, max-age=86400", "X-Woyou-Cache": "hit"},
        )

    try:
        url = source.tile_url(z, x, y)
    except (KeyError, ValueError) as exc:
        log.warning("数据源 %s 的 URL 模板无效：%s", source_id, exc)
        return _bad("数据源 URL 模板无效", 500)

    headers = {"User-Agent": request.app.state.settings.user_agent, **source.headers}
    client: httpx.AsyncClient = request.app.state.http
    started = time.perf_counter()
    try:
        upstream = await client.get(url, headers=headers)
    except httpx.HTTPError as exc:
        request.app.state.health[source_id] = {
            "ok": False,
            "latency_ms": None,
            "error": str(exc),
            "checked_at": time.time(),
        }
        log.info("瓦片请求失败 %s：%s", source_id, exc)
        return _bad("上游数据源暂时不可用", 502)

    latency = (time.perf_counter() - started) * 1000
    if upstream.status_code != 200 or not upstream.content:
        request.app.state.health[source_id] = {
            "ok": False,
            "latency_ms": round(latency, 1),
            "error": f"HTTP {upstream.status_code}",
            "checked_at": time.time(),
        }
        return _bad(f"上游返回 {upstream.status_code}", 502)

    content_type = upstream.headers.get("content-type", "image/png").split(";")[0].strip()
    if not content_type.startswith("image/"):
        content_type = "image/png"

    if source.cache and len(upstream.content) <= MAX_TILE_BYTES:
        try:
            cache.put(z, x, y, upstream.content, content_type)
        except Exception as exc:  # noqa: BLE001
            log.warning("写入缓存失败 %s：%s", source_id, exc)

    request.app.state.health[source_id] = {
        "ok": True,
        "latency_ms": round(latency, 1),
        "error": None,
        "checked_at": time.time(),
    }
    return Response(
        content=upstream.content,
        media_type=content_type,
        headers={"Cache-Control": "public, max-age=86400", "X-Woyou-Cache": "miss"},
    )


async def probe_source(client: httpx.AsyncClient, source: Source, timeout: float = 5.0) -> dict:
    started = time.perf_counter()
    try:
        response = await client.get(
            source.tile_url(0, 0, 0),
            headers={"User-Agent": "Woyou/0.1 (personal geography tool)"},
            timeout=timeout,
        )
        latency = (time.perf_counter() - started) * 1000
        ok = response.status_code == 200 and len(response.content) > 0
        return {
            "id": source.id,
            "ok": ok,
            "latency_ms": round(latency, 1),
            "error": None if ok else f"HTTP {response.status_code}",
        }
    except httpx.HTTPError as exc:
        return {
            "id": source.id,
            "ok": False,
            "latency_ms": None,
            "error": f"{type(exc).__name__}: {exc}".strip(": "),
        }
