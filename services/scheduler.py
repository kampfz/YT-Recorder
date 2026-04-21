import json
import os
import uuid
from datetime import datetime
from typing import Callable, Optional
from zoneinfo import ZoneInfo

from apscheduler.schedulers.background import BackgroundScheduler

JOBS_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "jobs.json")

COMMON_TIMEZONES = [
    "Local",
    "UTC",
    "US/Eastern",
    "US/Central",
    "US/Mountain",
    "US/Pacific",
    "Europe/London",
    "Europe/Paris",
    "Europe/Berlin",
    "Asia/Tokyo",
    "Asia/Shanghai",
    "Australia/Sydney",
]

DEFAULT_GRACE_MINUTES = 5


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
    def __init__(self, on_job_trigger: Callable[[str, str, str, dict], None]):
        """on_job_trigger(job_id, url, output_dir, options) called when a job fires."""
        self._scheduler = BackgroundScheduler()
        self._on_trigger = on_job_trigger
        self._jobs: list[dict] = []
        self._grace_minutes = DEFAULT_GRACE_MINUTES

    def start(self):
        self._scheduler.start()
        self._reload_persisted_jobs()

    def shutdown(self):
        self._scheduler.shutdown(wait=False)

    def set_grace_minutes(self, minutes: int):
        self._grace_minutes = max(1, min(60, minutes))

    def get_grace_minutes(self) -> int:
        return self._grace_minutes

    def schedule(
        self,
        url: str,
        run_at: datetime,
        output_dir: str,
        format_key: str = "mp4 1080p",
        end_time: Optional[datetime] = None,
        duration_minutes: Optional[int] = None,
        auto_stop: bool = True,
        timezone: str = "Local",
    ) -> str:
        job_id = str(uuid.uuid4())[:8]
        job_data = {
            "job_id": job_id,
            "url": url,
            "run_at": run_at.isoformat(),
            "output_dir": output_dir,
            "format_key": format_key,
            "end_time": end_time.isoformat() if end_time else None,
            "duration_minutes": duration_minutes,
            "auto_stop": auto_stop,
            "timezone": timezone,
            "status": "scheduled",
        }
        self._jobs.append(job_data)
        _save_jobs(self._jobs)
        self._register_apscheduler_job(job_data, run_at)
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

    def _register_apscheduler_job(self, job_data: dict, run_at: datetime):
        self._scheduler.add_job(
            self._fire,
            "date",
            run_date=run_at,
            id=job_data["job_id"],
            args=[job_data],
            misfire_grace_time=self._grace_minutes * 60,
        )

    def _fire(self, job_data: dict):
        options = {
            "format_key": job_data.get("format_key", "mp4 1080p"),
            "end_time": job_data.get("end_time"),
            "duration_minutes": job_data.get("duration_minutes"),
            "auto_stop": job_data.get("auto_stop", True),
        }
        self._on_trigger(
            job_data["job_id"],
            job_data["url"],
            job_data["output_dir"],
            options,
        )

    def _reload_persisted_jobs(self):
        saved = _load_jobs()
        now = datetime.now()
        for job in saved:
            if job.get("status") != "scheduled":
                continue
            run_at = datetime.fromisoformat(job["run_at"])
            if run_at <= now:
                run_at = now
            self._jobs.append(job)
            self._register_apscheduler_job(job, run_at)
