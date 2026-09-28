"""Loading and validating config.yaml."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class Config:
    category_id: int
    game_name: str
    data_lake_path: Path
    request_pause_seconds: float
    retry_count: int
    request_timeout_seconds: float
    max_requests_per_run: int
    user_agent: str

    @property
    def game_slug(self) -> str:
        return slugify(self.game_name)


def slugify(name: str) -> str:
    slug = re.sub(r"[^0-9a-z]+", "-", name.strip().lower())
    return slug.strip("-")


def load_config(config_path: Path) -> Config:
    with config_path.open("r", encoding="utf-8") as fh:
        raw = yaml.safe_load(fh) or {}

    missing = [key for key in REQUIRED_KEYS if key not in raw]
    if missing:
        raise ValueError(f"config {config_path} is missing required keys: {missing}")

    data_lake_path = Path(raw["data_lake_path"])
    if not data_lake_path.is_absolute():
        data_lake_path = REPO_ROOT / data_lake_path

    return Config(
        category_id=int(raw["category_id"]),
        game_name=str(raw["game_name"]),
        data_lake_path=data_lake_path,
        request_pause_seconds=float(raw["request_pause_seconds"]),
        retry_count=int(raw["retry_count"]),
        request_timeout_seconds=float(raw["request_timeout_seconds"]),
        max_requests_per_run=int(raw["max_requests_per_run"]),
        user_agent=str(raw["user_agent"]),
    )


REQUIRED_KEYS = (
    "category_id",
    "game_name",
    "data_lake_path",
    "request_pause_seconds",
    "retry_count",
    "request_timeout_seconds",
    "max_requests_per_run",
    "user_agent",
)
