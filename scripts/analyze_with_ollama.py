#!/usr/bin/env python3
"""Summarize SpiderFoot investigation data and analyze it with a local Ollama model."""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from spiderfoot import SpiderFootDb
from spiderfoot.investigation import (
    DEFAULT_OLLAMA_HOST,
    DEFAULT_OLLAMA_MODEL,
    analyze_scans,
    build_report_from_db,
    build_analysis_prompt,
    call_ollama,
    condense_report,
    render_analysis_markdown,
)


DB_PATH = Path.home() / ".spiderfoot" / "spiderfoot.db"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", help="Merged investigation JSON")
    parser.add_argument("--ids", help="Comma-separated scan IDs (alternative to --input)")
    parser.add_argument("--out", required=True, help="Output markdown analysis path")
    parser.add_argument("--model", default=DEFAULT_OLLAMA_MODEL)
    parser.add_argument("--host", default=DEFAULT_OLLAMA_HOST)
    parser.add_argument("--context", default="", help="Optional investigator notes")
    parser.add_argument("--db", default=str(DB_PATH))
    parser.add_argument("--timeout", type=int, default=1800)
    parser.add_argument("--dry-run", action="store_true", help="Write prompt only, skip LLM call")
    args = parser.parse_args()

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)

    if args.ids:
        dbh = SpiderFootDb({"__database": args.db})
        if args.dry_run:
            report = build_report_from_db(dbh, [x.strip() for x in args.ids.split(",") if x.strip()])
            brief = condense_report(report)
            prompt = build_analysis_prompt(brief, args.context)
            prompt_path = out.with_suffix(".prompt.txt")
            prompt_path.write_text(prompt, encoding="utf-8")
            print(f"Wrote prompt to {prompt_path}")
            return

        markdown = analyze_scans(
            dbh,
            [x.strip() for x in args.ids.split(",") if x.strip()],
            context=args.context,
            model=args.model,
            host=args.host,
            timeout=args.timeout,
        )
        out.write_text(markdown, encoding="utf-8")
        print(f"Wrote {out}")
        return

    if not args.input:
        raise SystemExit("Provide --input or --ids")

    report = json.loads(Path(args.input).read_text(encoding="utf-8"))
    brief = condense_report(report)
    prompt = build_analysis_prompt(brief, args.context)

    if args.dry_run:
        prompt_path = out.with_suffix(".prompt.txt")
        prompt_path.write_text(prompt, encoding="utf-8")
        print(f"Wrote prompt to {prompt_path}")
        return

    print(f"Calling {args.model} via Ollama...")
    analysis = call_ollama(prompt, model=args.model, host=args.host, timeout=args.timeout)
    out.write_text(render_analysis_markdown(analysis, report, args.model, args.context), encoding="utf-8")
    print(f"Wrote {out}")


if __name__ == "__main__":
    main()