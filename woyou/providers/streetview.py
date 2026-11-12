"""KartaView 街景照片。

KartaView（原 OpenStreetCam）的读取接口无需 key，当前网络可直连。
注意：覆盖密度因地区差异很大，中国境内通常很稀疏。
"""

from __future__ import annotations

import asyncio

import httpx

KARTAVIEW_URL = "https://api.kartaview.org/2.0/photo/"
STORAGE_BASE = "https://storage3.openstreetcam.org/files/photo/"


async def image_urls(client: httpx.AsyncClient, image_id: str) -> list[str]:
    """按优先级返回某张照片可尝试的图片地址。"""
    response = await client.get(f"https://api.kartaview.org/2.0/photo/{image_id}")
    response.raise_for_status()
    payload = response.json()
    photo = (payload.get("result") or {}).get("data") or {}
    candidates = [
        photo.get("imageProcUrl"),
        photo.get("fileurlProc"),
        photo.get("imageThUrl"),
        photo.get("imageLthUrl"),
        photo.get("fileurlTh"),
        photo.get("fileurlLth"),
    ]
    return [url for url in candidates if url]


async def _keep_available(
    client: httpx.AsyncClient, images: list[dict]
) -> list[dict]:
    """KartaView 的历史数据里混有不少已失效的图片，先用 Range 请求过滤。"""
    semaphore = asyncio.Semaphore(12)

    async def usable(image: dict) -> bool:
        async with semaphore:
            for url in (image.get("image"), image.get("image_fallback")):
                if not url:
                    continue
                try:
                    response = await client.get(
                        url,
                        headers={"Range": "bytes=0-0"},
                        timeout=5.0,
                    )
                except httpx.HTTPError:
                    continue
                if response.status_code in (200, 206) and response.content:
                    return True
        return False

    checks = await asyncio.gather(*(usable(image) for image in images))
    return [image for image, ok in zip(images, checks) if ok]


async def fetch_streetview(
    client: httpx.AsyncClient,
    lat: float,
    lon: float,
    radius: int = 500,
    limit: int = 100,
) -> dict:
    response = await client.get(
        KARTAVIEW_URL,
        params={
            "lat": round(lat, 5),
            "lng": round(lon, 5),
            "radius": radius,
            "itemsPerPage": limit,
        },
    )
    response.raise_for_status()
    payload = response.json()

    status = payload.get("status") or {}
    if status.get("httpCode") not in (None, 200):
        raise ValueError(status.get("apiMessage") or "KartaView 查询失败")
    if payload.get("code") not in (None, 200):
        raise ValueError(payload.get("message") or "KartaView 查询失败")

    photos = (payload.get("result") or {}).get("data") or []
    images: list[dict] = []
    for photo in photos:
        filepath = photo.get("filepathProc") or photo.get("filepath")
        if not filepath:
            continue
        thumb_path = photo.get("filepathTh") or filepath
        image_url = (
            photo.get("imageProcUrl")
            or photo.get("fileurlProc")
            or STORAGE_BASE + filepath
        )
        fallback_url = photo.get("fileurlProc") or STORAGE_BASE + filepath
        thumb_url = (
            photo.get("imageThUrl")
            or photo.get("imageLthUrl")
            or STORAGE_BASE + thumb_path
        )
        try:
            distance = float(photo.get("distance") or 0)
        except (TypeError, ValueError):
            distance = 0.0
        images.append(
            {
                "id": str(photo.get("id")),
                "lat": photo.get("lat"),
                "lon": photo.get("lng"),
                "image": image_url,
                "image_fallback": fallback_url,
                "thumb": thumb_url,
                "projection": photo.get("projection") or "PLANE",
                "is_pano": (photo.get("projection") or "PLANE") != "PLANE",
                "heading": photo.get("heading"),
                "captured": photo.get("dateAdded"),
                "sequence": photo.get("sequenceId"),
                "sequence_index": photo.get("sequenceIndex"),
                "distance": round(distance, 1),
            }
        )

    images.sort(key=lambda item: item["distance"])
    images = await _keep_available(client, images[:12])
    return {
        "source": "KartaView",
        "count": len(images),
        "center": {"lat": lat, "lon": lon},
        "radius": radius,
        "images": images,
    }
