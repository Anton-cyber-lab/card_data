from __future__ import annotations

from pathlib import Path

import pytest

from lorcana_ingest.config import Config


@pytest.fixture
def config(tmp_path: Path) -> Config:
    return Config(
        category_id=71,
        game_name="Lorcana",
        data_lake_path=tmp_path / "lake",
        request_pause_seconds=0.0,
        retry_count=1,
        request_timeout_seconds=5,
        max_requests_per_run=1000,
        user_agent="test-agent",
    )
