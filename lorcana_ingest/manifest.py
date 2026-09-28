"""Per-run manifest describing what an ingestion run did."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timezone

from lorcana_ingest.config import Config
from lorcana_ingest.paths import manifests_dir, write_json_atomic


@dataclass
class RunManifest:
    run_started_at: str
    category_id: int
    run_date: str
    groups_count: int = 0
    files_written: int = 0
    files_skipped: int = 0
    errors: list[str] = field(default_factory=list)
    forced: bool = False
    limit_groups: int | None = None
    run_finished_at: str | None = None

    def finish(self) -> None:
        self.run_finished_at = datetime.now(timezone.utc).isoformat()


def new_manifest(config: Config, run_date: date, force: bool, limit_groups: int | None) -> RunManifest:
    return RunManifest(
        run_started_at=datetime.now(timezone.utc).isoformat(),
        category_id=config.category_id,
        run_date=run_date.isoformat(),
        forced=force,
        limit_groups=limit_groups,
    )


def write_manifest(config: Config, manifest: RunManifest) -> None:
    manifest.finish()
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = manifests_dir(config) / f"manifest_{manifest.run_date}_{timestamp}.json"
    write_json_atomic(path, asdict(manifest))
