# Lorcana TCGCSV bronze ingestion

Downloads raw group/product/price data for **Disney Lorcana** (`categoryId = 71`) from
[tcgcsv.com](https://tcgcsv.com) — a public mirror of the TCGplayer API — and stores it
unmodified as the bronze layer of a local data lake.

This project is adapted from an original single-game (Cardfight Vanguard) collector by
[Ivan Pavlenko](https://github.com/Anton-cyber-lab/card_data), repurposed here for Disney
Lorcana and restructured into a configurable, idempotent bronze-layer ingestion pipeline
as part of a university data lake assignment. It only handles ingestion into bronze — no
silver/gold transformation layers or database are part of this repository.

## What it does

For a given run date (UTC), it calls:

- `GET /tcgplayer/{categoryId}/groups` — once per run, the list of Lorcana sets
- `GET /tcgplayer/{categoryId}/{groupId}/products` — once per set
- `GET /tcgplayer/{categoryId}/{groupId}/prices` — once per set (products and prices are
  stored separately and only joined later, via `productId`, outside this repo)

Each response is written **unmodified** (raw JSON) to:

```
lake/bronze/tcgcsv/lorcana/groups/date=YYYY-MM-DD/{categoryId}.json
lake/bronze/tcgcsv/lorcana/products/date=YYYY-MM-DD/{groupId}.json
lake/bronze/tcgcsv/lorcana/prices/date=YYYY-MM-DD/{groupId}.json
```

Every run also writes a manifest to `lake/bronze/tcgcsv/lorcana/_manifests/` recording the
UTC collection time, `categoryId`, number of sets found, number of files written/skipped,
and any errors.

**Idempotency:** if a file for the run date already exists, it is not re-downloaded or
overwritten. Re-running the same day is a no-op unless `--force` is passed.

## Installation

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

For running tests, install the dev requirements instead:

```bash
pip install -r requirements-dev.txt
```

## Configuration

Copy the example config and adjust if needed (defaults already target Lorcana):

```bash
cp config.example.yaml config.yaml
```

| Key | Meaning |
|---|---|
| `category_id` | TCGplayer categoryId, verified against `https://tcgcsv.com/tcgplayer/categories` — do not guess it |
| `game_name` | Human-readable name; slugified into the bronze folder name (`Lorcana` -> `lorcana`) |
| `data_lake_path` | Root folder of the data lake (default `lake`, not committed to git) |
| `request_pause_seconds` | Pause between HTTP requests (default `0.5`) |
| `retry_count` | Retries with exponential backoff on 5xx/network errors |
| `request_timeout_seconds` | Per-request timeout |
| `max_requests_per_run` | Hard safety cap on total requests per run |
| `user_agent` | Custom User-Agent sent with every request |

## Running

```bash
python -m lorcana_ingest                      # today, UTC
python -m lorcana_ingest --date 2026-09-27     # re-run a specific day
python -m lorcana_ingest --force               # overwrite already-downloaded files
python -m lorcana_ingest --config other.yaml   # use a different config file
python -m lorcana_ingest --limit-groups 1      # only process the first set (testing)
```

Logs go to both the console and `logs/ingest.log`.

## Scheduling with cron (macOS/Linux)

tcgcsv.com's own data refreshes once a day around **20:00 UTC**. Schedule the run with a
safety margin after that, e.g. 21:00 UTC:

```cron
# crontab -e
0 21 * * * cd /path/to/card_data && .venv/bin/python -m lorcana_ingest >> logs/cron.log 2>&1
```

Adjust `0 21` for your server's local timezone if it does not run in UTC (e.g. `crontab`
on macOS uses the system's local time by default — check with `date` and `TZ`).

## Tests

```bash
pip install -r requirements-dev.txt
pytest
```

Tests mock all HTTP responses (`lorcana_ingest.pipeline.Fetcher` is monkeypatched) — no
real requests are made against tcgcsv.com. They cover bronze path generation and the
idempotency/`--force`/`--limit-groups` behavior of a run.
