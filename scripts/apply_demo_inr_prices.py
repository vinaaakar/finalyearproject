#!/usr/bin/env python3
"""Apply the ACADEMIC DEMONSTRATION INR price list (config/pricing/demo-inr-prices.json) to product_prices.

  backend/.venv/bin/python scripts/apply_demo_inr_prices.py --dry-run          # development databases: show changes
  backend/.venv/bin/python scripts/apply_demo_inr_prices.py                    # development databases: apply
  backend/.venv/bin/python scripts/apply_demo_inr_prices.py --target test      # the *_test databases (browser tests)
  ... --target test --remove                       # TEST ONLY: delete the demonstration rows again
  ... --target test --unset store-a:granite-hiking-boots   # TEST ONLY: leave that product without an INR price

Only product_prices is written (insert or update of the listed products' INR price); no product, order, cart or
customer row is touched, and no amount is converted from USD. Back up first (scripts/backup_db.sh).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from urllib.parse import urlparse, urlunparse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", choices=("dev", "test"), default="dev")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--list", type=Path, default=None)
    ap.add_argument("--remove", action="store_true", help="test databases only: delete the demonstration rows")
    ap.add_argument("--unset", action="append", default=[], metavar="STORE:SLUG", help="test databases only")
    args = ap.parse_args()
    if (args.remove or args.unset) and args.target != "test":
        print("refusing: --remove / --unset are for the *_test databases only", file=sys.stderr)
        return 2

    from app import demo_prices
    from app.config import load_settings

    urls = dict(load_settings().store_database_urls)
    if args.target == "test":
        urls = {k: urlunparse(urlparse(v)._replace(path=urlparse(v).path.rstrip("/") + "_test")) for k, v in urls.items()}
        if not all(urlparse(u).path.endswith("_test") for u in urls.values()):
            print("refusing: not *_test databases", file=sys.stderr)
            return 2
    data = demo_prices.load_list(args.list or demo_prices.DEFAULT_LIST)
    if args.remove:
        import psycopg
        for url in urls.values():
            with psycopg.connect(url) as conn:
                conn.execute("DELETE FROM product_prices WHERE approved_by = %s", [data["approved_by"]])
        print(json.dumps({"target": "test", "removed": True}))
        return 0
    report = demo_prices.apply(urls, data, dry_run=args.dry_run)
    if args.unset:
        import psycopg
        for item in args.unset:
            store, slug = item.split(":", 1)
            with psycopg.connect(urls[store]) as conn:
                conn.execute("DELETE FROM product_prices WHERE currency = 'INR' AND product_id = (SELECT id FROM products WHERE slug = %s)", [slug])
    print(json.dumps({"target": args.target, "dry_run": args.dry_run, "stores": report}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
