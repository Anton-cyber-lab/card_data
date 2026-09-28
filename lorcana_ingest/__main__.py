"""CLI entry point: python -m lorcana_ingest [--date YYYY-MM-DD] [--force] [--config PATH] [--limit-groups N]"""

from __future__ import annotations

import argparse
import sys
from datetime import date, datetime, timezone
from pathlib import Path

from lorcana_ingest.config import REPO_ROOT, load_config
from lorcana_ingest.logging_setup import configure_logging
from lorcana_ingest.pipeline import run_ingestion


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Ingest TCGCSV data into the bronze data lake layer.")
    parser.add_argument(
        "--date", type=parse_date, default=None,
        help="UTC date to (re)run as YYYY-MM-DD (default: today UTC)",
    )
    parser.add_argument(
        "--force", action="store_true",
        help="Re-download and overwrite files even if already present for the run date",
    )
    parser.add_argument(
        "--config", type=Path, default=REPO_ROOT / "config.yaml",
        help="Path to config.yaml (default: ./config.yaml)",
    )
    parser.add_argument(
        "--limit-groups", type=int, default=None,
        help="Only process the first N groups (useful for testing)",
    )
    return parser.parse_args(argv)


def parse_date(value: str) -> date:
    return datetime.strptime(value, "%Y-%m-%d").date()


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    config = load_config(args.config)
    configure_logging(REPO_ROOT / "logs")

    run_date = args.date or datetime.now(timezone.utc).date()
    manifest = run_ingestion(config, run_date, force=args.force, limit_groups=args.limit_groups)

    return 1 if manifest.errors else 0


if __name__ == "__main__":
    sys.exit(main())
