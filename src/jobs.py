import uuid
import time
import threading
from typing import Dict, Any
import traceback

class JobManager:
    """
    Simple in-memory job manager for async tasks.
    """
    _jobs: Dict[str, Dict[str, Any]] = {}
    _lock = threading.Lock()

    @classmethod
    def create_job(cls, job_type: str = "backtest") -> str:
        job_id = str(uuid.uuid4())
        with cls._lock:
            cls._jobs[job_id] = {
                "id": job_id,
                "type": job_type,
                "status": "pending", # pending, running, completed, failed
                "result": None,
                "error": None,
                "created_at": time.time(),
                "progress": 0
            }
        return job_id

    @classmethod
    def get_job(cls, job_id: str):
        with cls._lock:
            return cls._jobs.get(job_id)

    @classmethod
    def update_job(cls, job_id: str, status: str = None, result: Any = None, error: str = None, progress: int = None):
        with cls._lock:
            if job_id in cls._jobs:
                if status:
                    cls._jobs[job_id]["status"] = status
                if result:
                    cls._jobs[job_id]["result"] = result
                if error:
                    cls._jobs[job_id]["error"] = error
                    cls._jobs[job_id]["status"] = "failed"
                if progress is not None:
                    cls._jobs[job_id]["progress"] = progress

    @classmethod
    def cleanup_old_jobs(cls, max_age_seconds=3600):
        with cls._lock:
            now = time.time()
            to_delete = [
                jid for jid, job in cls._jobs.items()
                if now - job['created_at'] > max_age_seconds and job['status'] in ['completed', 'failed']
            ]
            for jid in to_delete:
                del cls._jobs[jid]
