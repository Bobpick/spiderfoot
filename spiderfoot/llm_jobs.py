# -*- coding: utf-8 -*-
"""Background job manager for SpiderFoot LLM analysis."""

import re
import threading
import time
import uuid
from datetime import datetime
from pathlib import Path

from spiderfoot import SpiderFootDb
from spiderfoot.investigation import (
    DEFAULT_OLLAMA_HOST,
    DEFAULT_OLLAMA_MODEL,
    analyze_scans,
    check_ollama,
)


REPORTS_DIR = Path(__file__).resolve().parents[1] / "reports"


class LLMJobManager:
    """Run LLM analysis jobs in background threads."""

    def __init__(self) -> None:
        self._jobs = {}
        self._lock = threading.Lock()
        REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    def start(self, db_config: dict, scan_ids: list, context: str = "", model: str = "") -> str:
        job_id = uuid.uuid4().hex[:12]
        ollama_model = model.strip() if model else DEFAULT_OLLAMA_MODEL

        with self._lock:
            self._jobs[job_id] = {
                "status": "queued",
                "stage": "queued",
                "message": "Queued for analysis",
                "started": time.time(),
                "updated": time.time(),
                "scan_ids": scan_ids,
                "scan_count": len(scan_ids),
                "context": context,
                "model": ollama_model,
                "error": None,
                "filename": None,
                "filepath": None,
                "result": None,
            }

        thread = threading.Thread(
            target=self._run,
            args=(job_id, db_config, scan_ids, context, ollama_model),
            daemon=True,
            name=f"llm-job-{job_id}",
        )
        thread.start()
        return job_id

    def get(self, job_id: str) -> dict:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return None
            return self._public_view(job)

    def get_result(self, job_id: str) -> tuple:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None or job["status"] != "finished":
                return None, None
            return job.get("filename"), job.get("result")

    def _update(self, job_id: str, **fields) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return
            job.update(fields)
            job["updated"] = time.time()

    def _public_view(self, job: dict) -> dict:
        elapsed = int(time.time() - job["started"])
        return {
            "status": job["status"],
            "stage": job["stage"],
            "message": job.get("message", ""),
            "elapsed": elapsed,
            "scan_count": job.get("scan_count", 0),
            "model": job.get("model", DEFAULT_OLLAMA_MODEL),
            "error": job.get("error"),
            "filename": job.get("filename"),
            "filepath": job.get("filepath"),
        }

    def _run(self, job_id: str, db_config: dict, scan_ids: list, context: str, model: str) -> None:
        self._update(
            job_id,
            status="running",
            stage="checking_ollama",
            message="Checking Ollama connection...",
        )

        try:
            check_ollama(DEFAULT_OLLAMA_HOST)
        except Exception as e:
            self._update(
                job_id,
                status="error",
                stage="failed",
                message="Ollama is not reachable",
                error=str(e),
            )
            return

        def on_stage(stage: str, message: str) -> None:
            self._update(job_id, stage=stage, message=message)

        try:
            dbh = SpiderFootDb(db_config)
            markdown = analyze_scans(
                dbh,
                scan_ids,
                context=context,
                model=model,
                on_stage=on_stage,
            )
        except Exception as e:
            self._update(
                job_id,
                status="error",
                stage="failed",
                message="Analysis failed",
                error=str(e),
            )
            return

        on_stage("saving_report", "Saving report to disk...")
        filename, filepath = _save_report(markdown, scan_ids, dbh)

        self._update(
            job_id,
            status="finished",
            stage="complete",
            message="Analysis complete",
            result=markdown,
            filename=filename,
            filepath=str(filepath),
        )

    def cleanup_old_jobs(self, max_age_seconds: int = 3600) -> None:
        cutoff = time.time() - max_age_seconds
        with self._lock:
            stale = [job_id for job_id, job in self._jobs.items() if job["started"] < cutoff]
            for job_id in stale:
                del self._jobs[job_id]


def _safe_name(value: str) -> str:
    value = re.sub(r"[^\w.\-]+", "_", value.strip())
    return value[:80] or "investigation"


def _save_report(markdown: str, scan_ids: list, dbh) -> tuple:
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    if len(scan_ids) == 1:
        scan = dbh.scanInstanceGet(scan_ids[0])
        base = _safe_name(scan[0]) if scan else "investigation"
    else:
        base = "multi-scan"
    filename = f"{base}-LLM-Analysis-{timestamp}.md"
    filepath = REPORTS_DIR / filename
    filepath.write_text(markdown, encoding="utf-8")
    return filename, filepath


llm_job_manager = LLMJobManager()