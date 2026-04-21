import json
import os
import uuid
from datetime import datetime
from typing import Callable

from apscheduler.schedulers.background import BackgroundScheduler

JOBS_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "jobs.json")


def _load_jobs() -> list[dict]:
    if not os.path.exists(JOBS_FILE):
        return []
    try:
        with open(JOBS_FILE) as f:
            return json.load(f)
    except Exception:
        return []


def _save_jobs(jobs: list[dict]):
    with open(JOBS_FILE, "w") as f:
        json.dump(jobs, f, indent=2, default=str)


class RecordingScheduler:
    def __init__(self, on_job_trigger: Callable[[str, str, str], None]):
        """on_job_trigger(job_id, url, output_dir) called when a job fires."""
        self._scheduler = BackgroundScheduler()
        self._on_trigger = on_job_trigger
        self._jobs: list[dict] = []

    def start(self):
        self._scheduler.start()
        self._reload_persisted_jobs()

    def shutdown(self):
        self._scheduler.shutdown(wait=False)

    def schedule(self, url: str, run_at: datetime, output_dir: str) -> str:
        job_id = str(uuid.uuid4())[:8]
        self._jobs.append({
            "job_id": job_id,
            "url": url,
            "run_at": run_at.isoformat(),
            "output_dir": output_dir,
            "status": "scheduled",
        })
        _save_jobs(self._jobs)
        self._register_apscheduler_job(job_id, url, run_at, output_dir)
        return job_id

    def cancel(self, job_id: str):
        try:
            self._scheduler.remove_job(job_id)
        except Exception:
            pass
        self._jobs = [j for j in self._jobs if j["job_id"] != job_id]
        _save_jobs(self._jobs)

    def mark_done(self, job_id: str):
        for job in self._jobs:
            if job["job_id"] == job_id:
                job["status"] = "done"
        _save_jobs(self._jobs)

    def get_scheduled(self) -> list[dict]:
        return [j for j in self._jobs if j["status"] == "scheduled"]

    def _register_apscheduler_job(self, job_id, url, run_at, output_dir):
        self._scheduler.add_job(
            self._fire,
            "date",
            run_date=run_at,
            id=job_id,
            args=[job_id, url, output_dir],
            misfire_grace_time=300,
        )

    def _fire(self, job_id: str, url: str, output_dir: str):
        self._on_trigger(job_id, url, output_dir)

    def _reload_persisted_jobs(self):
        saved = _load_jobs()
        now = datetime.now()
        for job in saved:
            if job.get("status") != "scheduled":
                continue
            run_at = datetime.fromisoformat(job["run_at"])
            if run_at <= now:
                # Past job — fire immediately
                run_at = now
            self._jobs.append(job)
            self._register_apscheduler_job(
                job["job_id"], job["url"], run_at, job["output_dir"]
            )
