from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from lorcana_ingest.config import Config
from lorcana_ingest.paths import bronze_file_path
from lorcana_ingest import pipeline

RUN_DATE = date(2026, 9, 28)

GROUPS_RESPONSE = {"results": [{"groupId": 1, "name": "Set One"}, {"groupId": 2, "name": "Set Two"}]}
PRODUCTS_RESPONSE = {"results": [{"productId": 100, "name": "Card A"}]}
PRICES_RESPONSE = {"results": [{"productId": 100, "marketPrice": 1.23}]}


class FakeFetcher:
    """Stands in for http_client.Fetcher: no real HTTP calls, just call tracking."""

    def __init__(self, config: Config) -> None:
        self.calls: list[str] = []

    def get_json(self, path: str) -> dict:
        self.calls.append(path)
        if path.endswith("/groups"):
            return GROUPS_RESPONSE
        if path.endswith("/products"):
            return PRODUCTS_RESPONSE
        if path.endswith("/prices"):
            return PRICES_RESPONSE
        raise AssertionError(f"unexpected path {path}")


@pytest.fixture(autouse=True)
def patch_fetcher(monkeypatch: pytest.MonkeyPatch) -> list[FakeFetcher]:
    instances: list[FakeFetcher] = []

    def factory(config: Config) -> FakeFetcher:
        fetcher = FakeFetcher(config)
        instances.append(fetcher)
        return fetcher

    monkeypatch.setattr(pipeline, "Fetcher", factory)
    return instances


def test_first_run_writes_all_files(config: Config, patch_fetcher: list[FakeFetcher]) -> None:
    manifest = pipeline.run_ingestion(config, RUN_DATE)

    assert manifest.groups_count == 2
    assert manifest.files_written == 1 + 2 * 2  # groups + (products+prices) per group
    assert manifest.files_skipped == 0
    assert manifest.errors == []

    groups_path = bronze_file_path(config, "groups", RUN_DATE, config.category_id)
    assert groups_path.exists()
    assert json.loads(groups_path.read_text()) == GROUPS_RESPONSE


def test_second_run_same_day_skips_existing_files_without_http_calls(
    config: Config, patch_fetcher: list[FakeFetcher]
) -> None:
    pipeline.run_ingestion(config, RUN_DATE)
    first_run_call_count = len(patch_fetcher[0].calls)

    manifest = pipeline.run_ingestion(config, RUN_DATE)

    assert first_run_call_count > 0
    assert patch_fetcher[1].calls == []  # no HTTP calls made on the second run
    assert manifest.files_written == 0
    assert manifest.files_skipped == 1 + 2 * 2


def test_force_redownloads_and_overwrites(config: Config, patch_fetcher: list[FakeFetcher]) -> None:
    pipeline.run_ingestion(config, RUN_DATE)

    manifest = pipeline.run_ingestion(config, RUN_DATE, force=True)

    assert len(patch_fetcher[1].calls) == 1 + 2 * 2  # groups + products/prices per group
    assert manifest.files_written == 1 + 2 * 2
    assert manifest.files_skipped == 0


def test_limit_groups_restricts_processing(config: Config, patch_fetcher: list[FakeFetcher]) -> None:
    manifest = pipeline.run_ingestion(config, RUN_DATE, limit_groups=1)

    assert manifest.groups_count == 2  # full group count is still reported
    assert manifest.files_written == 1 + 1 * 2  # groups + one group's products/prices


def test_manifest_file_is_written(config: Config, patch_fetcher: list[FakeFetcher]) -> None:
    from lorcana_ingest.paths import manifests_dir

    pipeline.run_ingestion(config, RUN_DATE)

    manifest_files = list(manifests_dir(config).glob("manifest_*.json"))
    assert len(manifest_files) == 1
    payload = json.loads(manifest_files[0].read_text())
    assert payload["category_id"] == config.category_id
    assert payload["groups_count"] == 2
