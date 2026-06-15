# -*- coding: utf-8 -*-
"""Merge SpiderFoot scans and analyze them with a local Ollama model."""

import json
import os
import re
import urllib.error
import urllib.request
from collections import defaultdict
from datetime import datetime
from urllib.parse import urlparse


HIGH_SIGNAL_PLATFORMS = {
    "instagram", "tiktok", "twitter", "x.com", "youtube", "snapchat",
    "allmylinks", "linktr.ee", "beacons.ai", "carrd.co", "github",
    "reddit", "facebook", "threads.net", "bsky.app", "discord",
}

LINK_HUB_KEYWORDS = ("allmylinks", "linktr.ee", "beacons", "carrd.co", "bio.link", "hoo.be")

DEFAULT_OLLAMA_HOST = os.environ.get("SPIDERFOOT_OLLAMA_HOST", "http://127.0.0.1:11434")
DEFAULT_OLLAMA_MODEL = os.environ.get("SPIDERFOOT_OLLAMA_MODEL", "cogito:32b")


def extract_url(data: str) -> str:
    data = data.replace("<SFURL>", "").replace("</SFURL>", "")
    match = re.search(r"https?://[^\s<>]+", data)
    return match.group(0).rstrip("/") if match else ""


def platform_from_account(data: str) -> str:
    first_line = data.split("\n", 1)[0]
    return first_line.split(" (Category:", 1)[0].strip()


def normalize_platform(url: str) -> str:
    if not url:
        return "unknown"
    host = urlparse(url).netloc.lower().replace("www.", "")
    return host.split(":")[0]


def is_high_signal(url: str, platform: str) -> bool:
    blob = f"{url} {platform}".lower()
    return any(k in blob for k in HIGH_SIGNAL_PLATFORMS)


def is_link_hub(url: str) -> bool:
    blob = url.lower()
    return any(k in blob for k in LINK_HUB_KEYWORDS)


def build_report_from_db(dbh, scan_ids: list) -> dict:
    scans = []
    events = []

    for scan_id in scan_ids:
        scan_id = scan_id.strip()
        if not scan_id:
            continue

        scan = dbh.scanInstanceGet(scan_id)
        if scan is None:
            continue

        scans.append({
            "id": scan_id,
            "name": scan[0],
            "target": scan[1],
            "status": scan[5],
        })

        for row in dbh.scanResultEvent(scan_id):
            event_type = row[4]
            if event_type == "ROOT":
                continue

            data = str(row[1])
            events.append({
                "scan_id": scan_id,
                "scan_name": scan[0],
                "scan_target": scan[1],
                "type": event_type,
                "data": data,
                "module": str(row[3]),
                "source_data": str(row[2]),
                "url": extract_url(data),
                "platform": platform_from_account(data) if event_type == "ACCOUNT_EXTERNAL_OWNED" else "",
            })

    return _build_report(scans, events)


def _build_report(scans: list, events: list) -> dict:
    grouped = defaultdict(list)
    for item in events:
        grouped[item["type"]].append(item)

    human_names = defaultdict(set)
    emails = defaultdict(set)
    platform_hits = defaultdict(lambda: defaultdict(set))
    correlations = []

    for item in grouped.get("HUMAN_NAME", []):
        human_names[item["data"].strip().lower()].add(item["scan_name"])

    for item in grouped.get("EMAILADDR", []):
        emails[item["data"].strip().lower()].add(item["scan_name"])

    for item in grouped.get("ACCOUNT_EXTERNAL_OWNED", []):
        url = item.get("url") or extract_url(item.get("data", ""))
        if url:
            platform_hits[normalize_platform(url)][url].add(item["scan_name"])

    for name, scan_set in human_names.items():
        if len(scan_set) > 1:
            correlations.append({
                "kind": "shared_human_name",
                "value": name,
                "scans": sorted(scan_set),
                "confidence": "medium",
            })

    for email, scan_set in emails.items():
        if len(scan_set) > 1:
            correlations.append({
                "kind": "shared_email",
                "value": email,
                "scans": sorted(scan_set),
                "confidence": "high",
            })

    for platform, urls in platform_hits.items():
        for url, scan_set in urls.items():
            if len(scan_set) > 1:
                correlations.append({
                    "kind": "same_profile_url",
                    "value": url,
                    "platform": platform,
                    "scans": sorted(scan_set),
                    "confidence": "high",
                })

    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "scans": scans,
        "summary": {
            "scan_count": len(scans),
            "event_count": len(events),
            "event_types": {k: len(v) for k, v in grouped.items()},
            "correlation_count": len(correlations),
        },
        "correlations": correlations,
        "events_by_type": grouped,
    }


def condense_report(report: dict, max_accounts_per_scan: int = 40) -> dict:
    events = report.get("events_by_type", {})
    brief = {
        "investigation": report.get("scans", []),
        "summary": report.get("summary", {}),
        "correlations": report.get("correlations", []),
        "scans": [],
    }

    accounts = events.get("ACCOUNT_EXTERNAL_OWNED", [])
    by_scan = defaultdict(list)
    for item in accounts:
        by_scan[item["scan_name"]].append(item)

    for scan in report.get("scans", []):
        scan_name = scan["name"]
        scan_accounts = by_scan.get(scan_name, [])

        link_hubs = []
        high_signal = []
        other_samples = []

        for item in scan_accounts:
            url = item.get("url") or extract_url(item.get("data", ""))
            platform = item.get("platform") or normalize_platform(url)
            entry = {"platform": platform, "url": url, "module": item.get("module")}

            if is_link_hub(url):
                link_hubs.append(entry)
            elif is_high_signal(url, platform):
                high_signal.append(entry)
            else:
                other_samples.append(entry)

        condensed_accounts = link_hubs + high_signal
        remaining = max_accounts_per_scan - len(condensed_accounts)
        if remaining > 0:
            condensed_accounts.extend(other_samples[:remaining])

        brief["scans"].append({
            "scan_name": scan_name,
            "target": scan["target"],
            "account_hits_total": len(scan_accounts),
            "accounts_in_brief": condensed_accounts,
            "human_names": [
                x["data"] for x in events.get("HUMAN_NAME", [])
                if x["scan_name"] == scan_name
            ],
            "social_media": [
                {
                    "data": x["data"],
                    "url": x.get("url") or extract_url(x.get("data", "")),
                    "module": x.get("module"),
                }
                for x in events.get("SOCIAL_MEDIA", [])
                if x["scan_name"] == scan_name
            ],
            "raw_profile_data": [
                x["data"][:500] for x in events.get("RAW_RIR_DATA", [])
                if x["scan_name"] == scan_name
            ],
            "emails": [
                x["data"] for x in events.get("EMAILADDR", [])
                if x["scan_name"] == scan_name
            ],
        })

    return brief


def build_analysis_prompt(brief: dict, context: str = "") -> str:
    payload = json.dumps(brief, indent=2, ensure_ascii=False)
    return f"""You are assisting with defensive/educational OSINT review on a private offline system.

An investigator selected multiple SpiderFoot scans that may relate to the same individual using
different aliases. Many hits from generic usernames are false positives from a module that only
checks whether a URL exists, not whether it belongs to the target person.

Your job:
1. Identify which aliases likely belong to the SAME individual vs unrelated coincidences.
2. Rank the strongest identity anchors (most unique usernames, link hubs, cross-platform bridges).
3. Propose a short list of highest-confidence accounts worth manual verification.
4. Flag weak/noisy results that should be deprioritized.
5. Suggest the next 3 OSINT steps.

Rules:
- Do NOT invent facts not present in the data.
- Mark confidence as high/medium/low for each conclusion.
- Be explicit about uncertainty and false-positive risk.
- Output markdown with sections: Executive Summary, Alias Assessment, High-Confidence Leads,
  Likely False Positives, Recommended Next Steps, Open Questions.

{f"Investigator notes: {context}" if context else ""}

Investigation data (condensed JSON):
{payload}
"""


def check_ollama(host: str = DEFAULT_OLLAMA_HOST, timeout: int = 5) -> None:
    """Verify that Ollama is reachable before starting analysis."""
    req = urllib.request.Request(f"{host.rstrip('/')}/api/tags", method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            if resp.status != 200:
                raise RuntimeError(f"Ollama returned HTTP {resp.status}")
    except urllib.error.URLError as e:
        raise RuntimeError(
            f"Ollama is not reachable at {host}. Start it with: ollama serve"
        ) from e


def call_ollama(
    prompt: str,
    model: str = DEFAULT_OLLAMA_MODEL,
    host: str = DEFAULT_OLLAMA_HOST,
    timeout: int = 1800,
) -> str:
    system = (
        "You are an OSINT analyst assistant. Work only from supplied data. "
        "Never invent accounts, links, or biographical facts. "
        "Treat generic username hits as probable false positives unless bridged "
        "by link hubs, matching bios, or unique handles. "
        "Respond in markdown with the exact sections requested."
    )
    body = json.dumps({
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ],
        "stream": False,
        "options": {
            "temperature": 0.1,
            "num_predict": 4096,
        },
    }).encode("utf-8")

    req = urllib.request.Request(
        f"{host.rstrip('/')}/api/chat",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.URLError as e:
        raise RuntimeError(f"Could not reach Ollama at {host}: {e}") from e

    content = data.get("message", {}).get("content", "").strip()
    if not content:
        raise RuntimeError(f"Ollama model '{model}' returned an empty response.")
    return content


def render_analysis_markdown(
    analysis: str,
    report: dict,
    model: str,
    context: str = "",
) -> str:
    scan_names = ", ".join(s["name"] for s in report.get("scans", []))
    return f"""# SpiderFoot LLM Investigation Analysis

- Model: `{model}`
- Generated: {datetime.now().isoformat(timespec="seconds")}
- Scans merged: {scan_names}
- Total events: {report.get("summary", {}).get("event_count", 0)}
- Cross-scan correlations: {report.get("summary", {}).get("correlation_count", 0)}
{f"- Investigator notes: {context}" if context else ""}

---

{analysis}
"""


def analyze_scans(
    dbh,
    scan_ids: list,
    context: str = "",
    model: str = DEFAULT_OLLAMA_MODEL,
    host: str = DEFAULT_OLLAMA_HOST,
    timeout: int = 1800,
    on_stage=None,
) -> str:
    def stage(name: str, message: str) -> None:
        if on_stage:
            on_stage(name, message)

    stage("loading_scans", f"Loading {len(scan_ids)} scan(s) from database...")
    report = build_report_from_db(dbh, scan_ids)
    if not report["scans"]:
        raise ValueError("No matching scans found.")

    stage(
        "merging_scans",
        f"Merged {report['summary']['event_count']} events from {report['summary']['scan_count']} scan(s)...",
    )
    brief = condense_report(report)
    stage("condensing_data", "Condensing account hits for LLM prompt...")
    prompt = build_analysis_prompt(brief, context)
    stage("calling_ollama", f"Calling Ollama model '{model}' (watch CPU/GPU sensors)...")
    analysis = call_ollama(prompt, model=model, host=host, timeout=timeout)
    stage("rendering_report", "Formatting analysis report...")
    return render_analysis_markdown(analysis, report, model, context)