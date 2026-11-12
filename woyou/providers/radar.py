"""RainViewer 雷达回波。"""

from __future__ import annotations

import httpx

RAINVIEWER_URL = "https://api.rainviewer.com/public/weather-maps.json"


async def fetch_radar(client: httpx.AsyncClient) -> dict:
    response = await client.get(RAINVIEWER_URL)
    response.raise_for_status()
    data = response.json()
    radar = data.get("radar", {})
    frames: list[dict] = []

    past = radar.get("past", [])
    for frame in past[-8:]:
        frames.append({"time": frame.get("time"), "path": frame.get("path"), "kind": "past"})
    for frame in radar.get("nowcast", []):
        frames.append(
            {"time": frame.get("time"), "path": frame.get("path"), "kind": "nowcast"}
        )

    return {
        "host": data.get("host", "https://tilecache.rainviewer.com"),
        "generated": data.get("generated"),
        "frames": frames,
    }
