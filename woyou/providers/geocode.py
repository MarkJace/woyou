"""地理编码：Open-Meteo（中文搜索）+ BigDataCloud（中文逆编码）+ Photon 兜底。"""

from __future__ import annotations

import httpx

OPEN_METEO_GEOCODE = "https://geocoding-api.open-meteo.com/v1/search"
BIGDATA_REVERSE = "https://api.bigdatacloud.net/data/reverse-geocode-client"
PHOTON_BASE = "https://photon.komoot.io"

_FEATURE_LABELS = {
    "PPL": "城市",
    "PPLA": "城市",
    "PPLA2": "城市",
    "PPLA3": "城市",
    "PPLA4": "城镇",
    "PPLC": "首都",
    "PPLX": "城区",
    "ADM1": "省",
    "ADM2": "市",
    "ADM3": "区县",
    "ISL": "岛屿",
    "MT": "山峰",
    "PK": "山峰",
    "LK": "湖泊",
    "STM": "河流",
    "AIRP": "机场",
    "AIRF": "机场",
}


def _unique(parts: list[str | None]) -> list[str]:
    result: list[str] = []
    for part in parts:
        if part and part not in result:
            result.append(str(part))
    return result


def _photon_feature(feature: dict) -> dict:
    props = feature.get("properties", {})
    coords = (feature.get("geometry") or {}).get("coordinates") or [None, None]
    lon, lat = (coords + [None, None])[:2]
    name = (
        props.get("name")
        or props.get("street")
        or props.get("city")
        or props.get("district")
        or "未命名地点"
    )
    city = props.get("city") or props.get("district") or props.get("county")
    state = props.get("state")
    country = props.get("country")
    parts = _unique([name, city if city and city != name else None, state, country])
    return {
        "name": name,
        "label": " · ".join(parts),
        "city": city,
        "state": state,
        "country": country,
        "type": props.get("osm_value") or props.get("type"),
        "lat": lat,
        "lon": lon,
    }


async def _open_meteo_search(client: httpx.AsyncClient, query: str, limit: int) -> list[dict]:
    response = await client.get(
        OPEN_METEO_GEOCODE,
        params={"name": query, "count": limit, "language": "zh", "format": "json"},
    )
    response.raise_for_status()
    results = response.json().get("results", [])
    output: list[dict] = []
    for item in results:
        name = item.get("name") or "未命名地点"
        state = item.get("admin1")
        country = item.get("country")
        parts = _unique([name, state if state and state != name else None, country])
        feature_code = item.get("feature_code") or ""
        output.append(
            {
                "name": name,
                "label": " · ".join(parts),
                "city": name,
                "state": state,
                "country": country,
                "type": _FEATURE_LABELS.get(feature_code, "地点"),
                "lat": item.get("latitude"),
                "lon": item.get("longitude"),
            }
        )
    return [item for item in output if item["lat"] is not None and item["lon"] is not None]


async def _photon_search(client: httpx.AsyncClient, query: str, limit: int) -> list[dict]:
    response = await client.get(f"{PHOTON_BASE}/api/", params={"q": query, "limit": limit})
    response.raise_for_status()
    features = response.json().get("features", [])
    return [
        result
        for item in features
        if (result := _photon_feature(item))["lat"] is not None
    ]


async def search(client: httpx.AsyncClient, query: str, limit: int = 6) -> list[dict]:
    try:
        results = await _open_meteo_search(client, query, limit)
        if results:
            return results
    except httpx.HTTPError:
        pass
    return await _photon_search(client, query, limit)


async def _bigdata_reverse(client: httpx.AsyncClient, lat: float, lon: float) -> dict:
    response = await client.get(
        BIGDATA_REVERSE,
        params={"latitude": lat, "longitude": lon, "localityLanguage": "zh"},
    )
    response.raise_for_status()
    data = response.json()
    city = data.get("city") or data.get("locality")
    state = data.get("principalSubdivision")
    country = data.get("countryName")
    parts = _unique([city, state if state and state != city else None, country])
    return {
        "name": city or state or f"{lat:.4f}, {lon:.4f}",
        "label": " · ".join(parts) or f"{lat:.4f}, {lon:.4f}",
        "city": city,
        "state": state,
        "country": country,
        "type": "行政区域",
        "lat": lat,
        "lon": lon,
    }


async def _photon_reverse(client: httpx.AsyncClient, lat: float, lon: float) -> dict:
    response = await client.get(
        f"{PHOTON_BASE}/reverse", params={"lat": lat, "lon": lon, "limit": 1}
    )
    response.raise_for_status()
    features = response.json().get("features", [])
    if not features:
        raise ValueError("no reverse result")
    result = _photon_feature(features[0])
    admin = _unique([result.get("city"), result.get("state"), result.get("country")])
    result["label"] = " · ".join(admin) or result["label"]
    result["name"] = result.get("city") or result.get("name")
    result["lat"] = lat
    result["lon"] = lon
    return result


async def reverse(client: httpx.AsyncClient, lat: float, lon: float) -> dict:
    try:
        return await _bigdata_reverse(client, lat, lon)
    except (httpx.HTTPError, ValueError):
        try:
            return await _photon_reverse(client, lat, lon)
        except (httpx.HTTPError, ValueError):
            return {
                "name": f"{lat:.4f}, {lon:.4f}",
                "label": f"{lat:.4f}, {lon:.4f}",
                "lat": lat,
                "lon": lon,
                "city": None,
                "state": None,
                "country": None,
            }
