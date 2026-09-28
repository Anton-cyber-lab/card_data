"""Orchestrates one ingestion run: groups -> products/prices per group -> manifest."""

from __future__ import annotations

import logging
from datetime import date
from pathlib import Path

from lorcana_ingest.config import Config
from lorcana_ingest.http_client import Fetcher, TooManyRequestsError
from lorcana_ingest.manifest import RunManifest, new_manifest, write_manifest
from lorcana_ingest.paths import BronzeKind, bronze_file_path, write_json_atomic

logger = logging.getLogger(__name__)


def fetch_or_load_bronze(
    fetcher: Fetcher,
    config: Config,
    kind: BronzeKind,
    run_date: date,
    file_id: int | str,
    url_path: str,
    force: bool,
) -> tuple[dict, bool]:
    """Returns (payload, was_skipped). Skips the HTTP call if the file already
    exists for this run_date and force is False."""
    path = bronze_file_path(config, kind, run_date, file_id)
    if path.exists() and not force:
        logger.info("SKIP %s (already present at %s)", url_path, path)
        payload = _read_json(path)
        return payload, True

    payload = fetcher.get_json(url_path)
    write_json_atomic(path, payload)
    logger.info("WROTE %s -> %s", url_path, path)
    return payload, False


def _read_json(path: Path) -> dict:
    import json

    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def run_ingestion(
    config: Config,
    run_date: date,
    force: bool = False,
    limit_groups: int | None = None,
) -> RunManifest:
    fetcher = Fetcher(config)
    manifest = new_manifest(config, run_date, force, limit_groups)

    try:
        groups_payload, skipped = fetch_or_load_bronze(
            fetcher, config, "groups", run_date, config.category_id,
            f"/tcgplayer/{config.category_id}/groups", force,
        )
        _record(manifest, skipped)
    except Exception as exc:  # noqa: BLE001 - a failed groups fetch aborts the run
        logger.error("Failed to fetch groups: %s", exc)
        manifest.errors.append(f"groups: {exc}")
        write_manifest(config, manifest)
        return manifest

    groups = groups_payload.get("results", [])
    manifest.groups_count = len(groups)
    if limit_groups is not None:
        groups = groups[:limit_groups]

    for group in groups:
        group_id = group["groupId"]
        for kind, suffix in (("products", "products"), ("prices", "prices")):
            url_path = f"/tcgplayer/{config.category_id}/{group_id}/{suffix}"
            try:
                _, skipped = fetch_or_load_bronze(
                    fetcher, config, kind, run_date, group_id, url_path, force,
                )
                _record(manifest, skipped)
            except TooManyRequestsError as exc:
                logger.error("Aborting run: %s", exc)
                manifest.errors.append(str(exc))
                write_manifest(config, manifest)
                return manifest
            except Exception as exc:  # noqa: BLE001 - keep going with other groups
                logger.error("Failed %s for group %s: %s", kind, group_id, exc)
                manifest.errors.append(f"{kind} group={group_id}: {exc}")

    write_manifest(config, manifest)
    logger.info(
        "Done: %d groups, %d files written, %d skipped, %d errors",
        manifest.groups_count, manifest.files_written, manifest.files_skipped, len(manifest.errors),
    )
    return manifest


def _record(manifest: RunManifest, skipped: bool) -> None:
    if skipped:
        manifest.files_skipped += 1
    else:
        manifest.files_written += 1
