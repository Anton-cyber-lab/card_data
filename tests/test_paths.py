from __future__ import annotations

from datetime import date

from lorcana_ingest.config import Config, slugify
from lorcana_ingest.paths import bronze_file_path, manifests_dir


def test_slugify() -> None:
    assert slugify("Lorcana") == "lorcana"
    assert slugify("Disney Lorcana") == "disney-lorcana"
    assert slugify("  Weird   Name!! ") == "weird-name"


def test_bronze_file_path_groups(config: Config) -> None:
    path = bronze_file_path(config, "groups", date(2026, 9, 28), 71)
    expected = config.data_lake_path / "bronze" / "tcgcsv" / "lorcana" / "groups" / "date=2026-09-28" / "71.json"
    assert path == expected


def test_bronze_file_path_products(config: Config) -> None:
    path = bronze_file_path(config, "products", date(2026, 9, 28), 24890)
    expected = (
        config.data_lake_path / "bronze" / "tcgcsv" / "lorcana" / "products"
        / "date=2026-09-28" / "24890.json"
    )
    assert path == expected


def test_manifests_dir(config: Config) -> None:
    path = manifests_dir(config)
    expected = config.data_lake_path / "bronze" / "tcgcsv" / "lorcana" / "_manifests"
    assert path == expected
