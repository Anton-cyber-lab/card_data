"""
Daily snapshot of Cardfight Vanguard single cards + prices from tcgcsv.com.

Source: https://tcgcsv.com (mirror of TCGplayer API, updated once a day ~20:00 UTC)
Usage rules followed (https://tcgcsv.com/docs):
  - custom User-Agent
  - pause between requests
  - check last-updated.txt and skip if nothing changed
  - far below 10 000 requests/day (~2 requests per set) + hard safety cap

extendedData (card text, grade, nation, skill, ...) is flattened into ext<Name>
columns, same naming as tcgcsv's own CSV (extNumber, extRarity, extDescription...).
The raw extendedData is also kept as JSON in case new fields appear.

Output (Hive-style partitioning, easy to load into a data lake later):
  data/vanguard/date=YYYY-MM-DD/vanguard_cards.csv
"""

import csv
import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

BASE_URL = "https://tcgcsv.com"
CATEGORY_ID = 16  # Cardfight Vanguard
USER_AGENT = "VanguardCollector/1.1 (university assignment)"

REQUEST_PAUSE_S = 0.15      # docs ask for >= 100 ms between requests
MAX_REQUESTS = 3000         # hard safety cap per run (site limit is 10 000/day)
RETRY_5XX = 3               # retries for temporary server errors
THROTTLE_WAIT_S = 610       # tcgcsv throttles an IP for 10 min -> wait it out once

ONLY_SINGLES = True  # False = also keep sealed products (boosters, boxes, decks)

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data" / "vanguard"
STATE_FILE = ROOT / "state" / "last_updated.txt"

BASE_COLUMNS = [
    "snapshot_date", "source_updated_at", "category_id",
    "group_id", "group_name", "group_abbreviation",
    "product_id", "name", "clean_name", "sub_type_name",
    "low_price", "mid_price", "high_price", "market_price", "direct_low_price",
    "currency", "product_url", "image_url", "product_modified_on",
]
TAIL_COLUMNS = ["extended_data_json"]


class TooManyRequests(Exception):
    pass


class Fetcher:
    def __init__(self) -> None:
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": USER_AGENT})
        self.count = 0
        self.throttled_once = False

    def get(self, url: str) -> requests.Response:
        attempt = 0
        while True:
            if self.count >= MAX_REQUESTS:
                raise TooManyRequests(f"Safety cap of {MAX_REQUESTS} requests reached")
            self.count += 1
            resp = self.session.get(url, timeout=30)
            time.sleep(REQUEST_PAUSE_S)

            if resp.status_code == 429:
                # IP is throttled for ~10 minutes. Wait once; if it happens again, stop
                # the run (state is not updated, so the next scheduled run retries).
                if self.throttled_once:
                    raise TooManyRequests("Throttled twice, aborting run")
                self.throttled_once = True
                print(f"  429 on {url}, waiting {THROTTLE_WAIT_S}s", file=sys.stderr)
                time.sleep(THROTTLE_WAIT_S)
                continue

            if resp.status_code >= 500 and attempt < RETRY_5XX:
                attempt += 1
                wait = 5 * attempt
                print(f"  {resp.status_code} on {url}, retry in {wait}s", file=sys.stderr)
                time.sleep(wait)
                continue

            return resp

    def results(self, url: str) -> list:
        resp = self.get(url)
        if resp.status_code != 200:
            print(f"  WARN: {resp.status_code} for {url}, skipping", file=sys.stderr)
            return []
        return resp.json().get("results", [])


def ext_column(name: str) -> str:
    """'Number' -> 'extNumber', 'Skill Icon' -> 'extSkillIcon'."""
    return "ext" + re.sub(r"[^0-9A-Za-z]", "", name)


def is_single_card(product: dict) -> bool:
    # tcgcsv docs: presence of Number or Rarity in extendedData is a good "is a card" indicator
    names = {e.get("name") for e in product.get("extendedData") or []}
    return "Number" in names or "Rarity" in names


def main() -> int:
    f = Fetcher()

    # 1) Has the source changed since our last successful run?
    source_updated = f.get(f"{BASE_URL}/last-updated.txt").text.strip()
    previous = STATE_FILE.read_text().strip() if STATE_FILE.exists() else ""
    if source_updated and source_updated == previous:
        print(f"No new data (source still at {source_updated}). Nothing to do.")
        return 0

    snapshot_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    # 2) All sets of the category
    groups = f.results(f"{BASE_URL}/tcgplayer/{CATEGORY_ID}/groups")
    print(f"Found {len(groups)} groups -> about {2 * len(groups) + 2} requests planned")

    rows: list[dict] = []
    ext_columns: dict[str, None] = {}  # ordered set of all ext* columns seen

    try:
        for i, group in enumerate(groups, 1):
            gid = group["groupId"]
            products = f.results(f"{BASE_URL}/tcgplayer/{CATEGORY_ID}/{gid}/products")
            prices = f.results(f"{BASE_URL}/tcgplayer/{CATEGORY_ID}/{gid}/prices")

            prices_by_product: dict[int, list] = {}
            for p in prices:
                prices_by_product.setdefault(p["productId"], []).append(p)

            for product in products:
                if ONLY_SINGLES and not is_single_card(product):
                    continue

                ext = product.get("extendedData") or []
                ext_flat = {}
                for item in ext:
                    col = ext_column(item.get("name", ""))
                    ext_columns.setdefault(col, None)
                    ext_flat[col] = item.get("value", "")

                base = {
                    "snapshot_date": snapshot_date,
                    "source_updated_at": source_updated,
                    "category_id": CATEGORY_ID,
                    "group_id": gid,
                    "group_name": group.get("name", ""),
                    "group_abbreviation": group.get("abbreviation", ""),
                    "product_id": product["productId"],
                    "name": product.get("name", ""),
                    "clean_name": product.get("cleanName", ""),
                    "currency": "USD",
                    "product_url": product.get("url", ""),
                    "image_url": product.get("imageUrl", ""),
                    "product_modified_on": product.get("modifiedOn", ""),
                    "extended_data_json": json.dumps(ext, ensure_ascii=False),
                    **ext_flat,
                }

                for pr in prices_by_product.get(product["productId"]) or [{}]:
                    rows.append({
                        **base,
                        "sub_type_name": pr.get("subTypeName", ""),
                        "low_price": pr.get("lowPrice"),
                        "mid_price": pr.get("midPrice"),
                        "high_price": pr.get("highPrice"),
                        "market_price": pr.get("marketPrice"),
                        "direct_low_price": pr.get("directLowPrice"),
                    })

            print(f"[{i}/{len(groups)}] {group.get('name')}: {len(products)} products")
    except TooManyRequests as e:
        print(f"ABORTED: {e}. No file written, next run will retry.", file=sys.stderr)
        return 1

    # 3) Write the snapshot (columns = base + every ext* field seen today + raw JSON)
    out_dir = DATA_DIR / f"date={snapshot_date}"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / "vanguard_cards.csv"
    columns = BASE_COLUMNS + list(ext_columns) + TAIL_COLUMNS
    with out_file.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=columns, quoting=csv.QUOTE_MINIMAL)
        writer.writeheader()
        writer.writerows(rows)

    # 4) Remember source version only after a successful full run
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(source_updated)

    print(f"Done: {len(rows)} rows, {len(ext_columns)} ext columns, "
          f"{f.count} requests -> {out_file.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
