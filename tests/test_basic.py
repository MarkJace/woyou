from fastapi.testclient import TestClient

from woyou.app import create_app
from woyou.config import Settings
from woyou.providers.weather import describe, wind_direction
from woyou.sources import Source
from woyou.tiles.cache import TileCache


def test_source_tile_url() -> None:
    source = Source(id="demo", name="Demo", url="https://example.com/{z}/{x}/{y}.png")
    assert source.tile_url(3, 6, 2) == "https://example.com/3/6/2.png"
    assert source.cache_key() == "demo"


def test_weather_describe() -> None:
    assert describe(0) == {"label": "晴", "icon": "clear"}
    assert describe(95)["icon"] == "thunder"
    assert describe(999)["label"] == "未知"
    assert wind_direction(0) == "北风"
    assert wind_direction(180) == "南风"


def test_tile_cache_roundtrip(tmp_path) -> None:
    cache = TileCache(tmp_path / "cache.mbtiles", 64 * 1024 * 1024)
    cache.put(2, 1, 3, b"tile-bytes", "image/png")
    result = cache.get(2, 1, 3)
    assert result == (b"tile-bytes", "image/png")
    assert cache.get(2, 0, 0) is None
    assert cache.stats()["tiles"] == 1


def test_app_shell(tmp_path) -> None:
    app = create_app(Settings(data_dir=tmp_path / "data", cache_max_mb=64))
    with TestClient(app) as client:
        assert client.get("/healthz").json()["ok"] is True

        page = client.get("/")
        assert page.status_code == 200
        assert "卧游" in page.text

        config = client.get("/api/v1/config").json()
        ids = {source["id"] for source in config["sources"]}
        assert {"osm", "esri-imagery", "esri-street", "gibs-clouds"} <= ids

        assert client.get("/tiles/unknown/0/0/0").status_code == 404
        assert client.get("/api/v1/weather?lat=91&lon=0").status_code == 422
        assert client.get("/api/v1/streetview?lat=91&lon=0").status_code == 422
        assert (
            client.get(
                "/api/v1/grid?kind=air&west=122&south=30&east=119&north=32"
            ).status_code
            == 400
        )
        assert (
            client.get(
                "/api/v1/grid?kind=nope&west=119&south=30&east=122&north=32"
            ).status_code
            == 422
        )
