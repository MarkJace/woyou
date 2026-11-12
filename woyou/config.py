"""应用配置。"""

from __future__ import annotations

import os
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

PACKAGE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = PACKAGE_DIR.parent


def _default_data_dir() -> Path:
    env = os.getenv("WOYOU_DATA_DIR")
    if env:
        return Path(env).expanduser().resolve()
    if (PROJECT_ROOT / "pyproject.toml").exists():
        return PROJECT_ROOT / "data"
    return Path.home() / ".local" / "share" / "woyou"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="WOYOU_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    host: str = "127.0.0.1"
    port: int = 8765
    data_dir: Path = Field(default_factory=_default_data_dir)

    default_lat: float = 31.2304
    default_lon: float = 121.4737
    default_zoom: float = 3.2

    cache_max_mb: int = 5120
    request_timeout: float = 12.0
    user_agent: str = "Woyou/0.1 (personal geography tool)"

    open_browser: bool = True
    debug: bool = False

    @property
    def tile_dir(self) -> Path:
        return self.data_dir / "tiles"

    @property
    def db_path(self) -> Path:
        return self.data_dir / "woyou.db"


def get_settings() -> Settings:
    return Settings()
