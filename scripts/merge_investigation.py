#!/usr/bin/env python3
"""Merge multiple SpiderFoot scans into one investigation report."""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from spiderfoot import SpiderFootDb
from spiderfoot.investigation import build_report_from_db


DB_PATH = Path.home() / ".spiderfoot" / "spiderfoot.db"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ids", help="Comma-separated scan IDs")
    parser.add_argument("--title", default="Investigation merge report")
    parser.add_argument("--out", required=True, help="Output file (.json)")
    parser.add_argument("--db", default=str(DB_PATH))
    args = parser.parse_args()

    if not args.ids:
        raise SystemExit("Provide --ids")

    scan_ids = [x.strip() for x in args.ids.split(",") if x.strip()]
    conn = SpiderFootDb({"__database": args.db})
    report = build_report_from_db(conn, scan_ids)

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Wrote {out}")
    print(
        f"Scans: {report['summary']['scan_count']} | "
        f"Events: {report['summary']['event_count']} | "
        f"Correlations: {report['summary']['correlation_count']}"
    )


if __name__ == "__main__":
    main()