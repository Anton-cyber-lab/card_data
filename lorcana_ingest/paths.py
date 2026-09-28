"""Bronze-layer path generation and atomic file writes."""

from __future__ import annotations

import json
import os
from datetime import date
from pathlib import Path
from typing import Literal

from lorcana_ingest.config import Config

BronzeKind = Literal["groups", "products", "prices"]


def bronze_root(config: Config) -> Path:
    return config.data_lake_path / "bronze" / "tcgcsv" / config.game_slug


def bronze_file_path(config: Config, kind: BronzeKind, run_date: date, file_id: int | str) -> Path:
    return bronze_root(config) / kind / f"date={run_date.isoformat()}" / f"{file_id}.json"


def manifests_dir(config: Config) -> Path:
    return bronze_root(config) / "_manifests"


def write_json_atomic(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    with tmp_path.open("w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)
    os.replace(tmp_path, path)
