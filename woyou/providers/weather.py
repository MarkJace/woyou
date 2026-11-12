"""Open-Meteo 天气数据。"""

from __future__ import annotations

import httpx

OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"

# WMO 天气代码 -> (中文描述, 图标键)
WMO: dict[int, tuple[str, str]] = {
    0: ("晴", "clear"),
    1: ("晴间多云", "mostly-clear"),
    2: ("多云", "partly"),
    3: ("阴", "cloudy"),
    45: ("雾", "fog"),
    48: ("雾凇", "fog"),
    51: ("小毛毛雨", "drizzle"),
    53: ("毛毛雨", "drizzle"),
    55: ("大毛毛雨", "drizzle"),
    56: ("冻毛毛雨", "drizzle"),
    57: ("强冻毛毛雨", "drizzle"),
    61: ("小雨", "rain"),
    63: ("中雨", "rain"),
    65: ("大雨", "rain"),
    66: ("冻雨", "rain"),
    67: ("强冻雨", "rain"),
    71: ("小雪", "snow"),
    73: ("中雪", "snow"),
    75: ("大雪", "snow"),
    77: ("米雪", "snow"),
    80: ("阵雨", "showers"),
    81: ("强阵雨", "showers"),
    82: ("暴雨", "showers"),
    85: ("阵雪", "snow"),
    86: ("强阵雪", "snow"),
    95: ("雷暴", "thunder"),
    96: ("雷暴伴冰雹", "thunder"),
    99: ("强雷暴伴冰雹", "thunder"),
}

_WIND_DIRS = ["北", "东北", "东", "东南", "南", "西南", "西", "西北"]


def describe(code: int | None) -> dict[str, str]:
    label, icon = WMO.get(int(code or 0), ("未知", "cloudy"))
    return {"label": label, "icon": icon}


def wind_direction(degrees: float | None) -> str:
    if degrees is None:
        return "—"
    index = int((float(degrees) + 22.5) // 45) % 8
    return f"{_WIND_DIRS[index]}风"


def _num(value: float | None) -> float | None:
    return None if value is None else round(float(value), 1)


def _hourly_window(hourly: dict, current_time: str, size: int = 24) -> list[dict]:
    times: list[str] = hourly.get("time", [])
    start = 0
    for index, value in enumerate(times):
        if value[:13] >= current_time[:13]:
            start = index
            break
    result: list[dict] = []
    for index in range(start, min(start + size, len(times))):
        code = hourly.get("weather_code", [None] * len(times))[index]
        result.append(
            {
                "time": times[index],
                "temp": _num(hourly.get("temperature_2m", [None] * len(times))[index]),
                "precip_prob": hourly.get("precipitation_probability", [None] * len(times))[index],
                "precip": _num(hourly.get("precipitation", [None] * len(times))[index]),
                "wind": _num(hourly.get("wind_speed_10m", [None] * len(times))[index]),
                **describe(code),
            }
        )
    return result


def _daily_window(daily: dict, size: int = 7) -> list[dict]:
    times: list[str] = daily.get("time", [])[:size]
    result: list[dict] = []
    for index, day in enumerate(times):
        code = daily.get("weather_code", [None] * len(times))[index]
        result.append(
            {
                "date": day,
                "temp_max": _num(daily.get("temperature_2m_max", [None] * len(times))[index]),
                "temp_min": _num(daily.get("temperature_2m_min", [None] * len(times))[index]),
                "precip_prob": daily.get(
                    "precipitation_probability_max", [None] * len(times)
                )[index],
                "wind_max": _num(daily.get("wind_speed_10m_max", [None] * len(times))[index]),
                "sunrise": daily.get("sunrise", [None] * len(times))[index],
                "sunset": daily.get("sunset", [None] * len(times))[index],
                **describe(code),
            }
        )
    return result


async def fetch_weather(
    client: httpx.AsyncClient, lat: float, lon: float, units: str = "metric"
) -> dict:
    imperial = units == "imperial"
    params = {
        "latitude": round(lat, 4),
        "longitude": round(lon, 4),
        "current": (
            "temperature_2m,relative_humidity_2m,apparent_temperature,is_day,"
            "precipitation,weather_code,cloud_cover,pressure_msl,"
            "wind_speed_10m,wind_direction_10m,wind_gusts_10m"
        ),
        "hourly": (
            "temperature_2m,precipitation_probability,precipitation,"
            "weather_code,wind_speed_10m"
        ),
        "daily": (
            "weather_code,temperature_2m_max,temperature_2m_min,sunrise,sunset,"
            "precipitation_probability_max,wind_speed_10m_max"
        ),
        "timezone": "auto",
        "forecast_days": 7,
        "temperature_unit": "fahrenheit" if imperial else "celsius",
        "wind_speed_unit": "mph" if imperial else "kmh",
        "precipitation_unit": "inch" if imperial else "mm",
    }
    response = await client.get(OPEN_METEO_URL, params=params)
    response.raise_for_status()
    data = response.json()

    current = data.get("current", {})
    current_units = data.get("current_units", {})
    code = current.get("weather_code")
    description = describe(code)
    wind_unit = current_units.get("wind_speed_10m", "mph" if imperial else "km/h")
    if wind_unit in {"mp/h", "m/h"}:
        wind_unit = "mph"

    return {
        "provider": "Open-Meteo",
        "location": {
            "lat": data.get("latitude", lat),
            "lon": data.get("longitude", lon),
            "timezone": data.get("timezone"),
            "timezone_abbreviation": data.get("timezone_abbreviation"),
            "elevation": data.get("elevation"),
        },
        "units": {
            "temperature": current_units.get("temperature_2m", "°F" if imperial else "°C"),
            "wind": wind_unit,
            "precipitation": current_units.get("precipitation", "inch" if imperial else "mm"),
            "pressure": current_units.get("pressure_msl", "hPa"),
        },
        "current": {
            "time": current.get("time"),
            "temp": _num(current.get("temperature_2m")),
            "feels": _num(current.get("apparent_temperature")),
            "humidity": current.get("relative_humidity_2m"),
            "precip": _num(current.get("precipitation")),
            "code": code,
            "is_day": bool(current.get("is_day", 1)),
            "cloud": current.get("cloud_cover"),
            "pressure": _num(current.get("pressure_msl")),
            "wind": _num(current.get("wind_speed_10m")),
            "wind_dir": wind_direction(current.get("wind_direction_10m")),
            "gust": _num(current.get("wind_gusts_10m")),
            **description,
        },
        "hourly": _hourly_window(data.get("hourly", {}), current.get("time", "")),
        "daily": _daily_window(data.get("daily", {})),
    }
