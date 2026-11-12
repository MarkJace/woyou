"""Open-Meteo 网格采样：气温、风场、空气质量。

把当前视野切成 nx × ny 的经纬网格，一次请求多个坐标，返回矩阵。
前端用这些矩阵绘制热力图和风场流线。
"""

from __future__ import annotations

import math
from typing import Any

import httpx

FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
AIR_QUALITY_URL = "https://air-quality-api.open-meteo.com/v1/air-quality"


def _axes(south: float, west: float, north: float, east: float, nx: int, ny: int):
    lats = [south + (north - south) * j / (ny - 1) for j in range(ny)]
    lons = [west + (east - west) * i / (nx - 1) for i in range(nx)]
    return lats, lons


def _matrix(values: list[Any], nx: int, ny: int) -> list[list[Any]]:
    return [values[j * nx : (j + 1) * nx] for j in range(ny)]


def _minmax(values: list[list[Any]]) -> tuple[float | None, float | None]:
    flat = [float(v) for row in values for v in row if v is not None]
    if not flat:
        return None, None
    return round(min(flat), 1), round(max(flat), 1)


async def _fetch(client: httpx.AsyncClient, url: str, params: dict) -> list[dict]:
    response = await client.get(url, params=params)
    response.raise_for_status()
    payload = response.json()
    if isinstance(payload, dict):
        payload = [payload]
    return payload


def _base_payload(
    kind: str,
    south: float,
    west: float,
    north: float,
    east: float,
    nx: int,
    ny: int,
    unit: str,
) -> dict:
    return {
        "kind": kind,
        "unit": unit,
        "bounds": {
            "south": round(south, 4),
            "west": round(west, 4),
            "north": round(north, 4),
            "east": round(east, 4),
        },
        "nx": nx,
        "ny": ny,
        "source": "Open-Meteo",
    }


async def fetch_temperature(
    client: httpx.AsyncClient,
    south: float,
    west: float,
    north: float,
    east: float,
    nx: int = 12,
    ny: int = 9,
) -> dict:
    lats, lons = _axes(south, west, north, east, nx, ny)
    params = {
        "latitude": ",".join(f"{lat:.4f}" for lat in lats for _ in lons),
        "longitude": ",".join(f"{lon:.4f}" for _ in lats for lon in lons),
        "current": "temperature_2m",
        "temperature_unit": "celsius",
    }
    data = await _fetch(client, FORECAST_URL, params)
    values = [
        (item.get("current") or {}).get("temperature_2m")
        for item in data
    ]
    matrix = _matrix(values, nx, ny)
    low, high = _minmax(matrix)
    return {
        **_base_payload("temperature", south, west, north, east, nx, ny, "°C"),
        "values": matrix,
        "min": low,
        "max": high,
    }


async def fetch_wind(
    client: httpx.AsyncClient,
    south: float,
    west: float,
    north: float,
    east: float,
    nx: int = 12,
    ny: int = 9,
) -> dict:
    lats, lons = _axes(south, west, north, east, nx, ny)
    params = {
        "latitude": ",".join(f"{lat:.4f}" for lat in lats for _ in lons),
        "longitude": ",".join(f"{lon:.4f}" for _ in lats for lon in lons),
        "current": "wind_speed_10m,wind_direction_10m",
        "wind_speed_unit": "ms",
    }
    data = await _fetch(client, FORECAST_URL, params)
    u_values: list[float | None] = []
    v_values: list[float | None] = []
    speed_values: list[float | None] = []
    for item in data:
        current = item.get("current") or {}
        speed = current.get("wind_speed_10m")
        direction = current.get("wind_direction_10m")
        if speed is None or direction is None:
            u_values.append(None)
            v_values.append(None)
            speed_values.append(None)
            continue
        radians = math.radians(direction)
        # 气象风向是“风从哪来”，所以 u/v 取反。
        u_values.append(round(-speed * math.sin(radians), 2))
        v_values.append(round(-speed * math.cos(radians), 2))
        speed_values.append(round(speed, 2))

    u_matrix = _matrix(u_values, nx, ny)
    v_matrix = _matrix(v_values, nx, ny)
    speed_matrix = _matrix(speed_values, nx, ny)
    low, high = _minmax(speed_matrix)
    return {
        **_base_payload("wind", south, west, north, east, nx, ny, "m/s"),
        "u": u_matrix,
        "v": v_matrix,
        "speed": speed_matrix,
        "min": low,
        "max": high,
    }


async def fetch_air(
    client: httpx.AsyncClient,
    south: float,
    west: float,
    north: float,
    east: float,
    nx: int = 12,
    ny: int = 9,
) -> dict:
    lats, lons = _axes(south, west, north, east, nx, ny)
    params = {
        "latitude": ",".join(f"{lat:.4f}" for lat in lats for _ in lons),
        "longitude": ",".join(f"{lon:.4f}" for _ in lats for lon in lons),
        "current": "us_aqi,pm2_5",
    }
    data = await _fetch(client, AIR_QUALITY_URL, params)
    aqi_values = [(item.get("current") or {}).get("us_aqi") for item in data]
    pm_values = [(item.get("current") or {}).get("pm2_5") for item in data]
    matrix = _matrix(aqi_values, nx, ny)
    low, high = _minmax(matrix)
    return {
        **_base_payload("air", south, west, north, east, nx, ny, "US AQI"),
        "values": matrix,
        "pm25": _matrix(pm_values, nx, ny),
        "min": low,
        "max": high,
    }


async def fetch_grid(
    client: httpx.AsyncClient,
    kind: str,
    south: float,
    west: float,
    north: float,
    east: float,
    nx: int = 12,
    ny: int = 9,
) -> dict:
    if kind == "temperature":
        return await fetch_temperature(client, south, west, north, east, nx, ny)
    if kind == "wind":
        return await fetch_wind(client, south, west, north, east, nx, ny)
    if kind == "air":
        return await fetch_air(client, south, west, north, east, nx, ny)
    raise ValueError(f"unknown grid kind: {kind}")
