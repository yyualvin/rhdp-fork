"""Job log configuration for jira-link (JOB_LOGS_DIR and remote fetch)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


@dataclass
class JobConfig:
    job_logs_dir: Path | None
    remote_host: str
    remote_log_dir: str

    @classmethod
    def from_env(cls, skill_dir: Path | None = None) -> JobConfig:
        if skill_dir is None:
            skill_dir = Path(__file__).resolve().parent.parent

        env_file = skill_dir / ".env"
        if env_file.exists():
            load_dotenv(env_file)
        load_dotenv()

        job_logs_dir_str = os.environ.get("JOB_LOGS_DIR", "").strip()
        return cls(
            job_logs_dir=Path(job_logs_dir_str) if job_logs_dir_str else None,
            remote_host=os.environ.get("REMOTE_HOST", "").strip(),
            remote_log_dir=os.environ.get("REMOTE_DIR", "").strip(),
        )

    def find_job_log(self, job_id: str) -> Path | None:
        if not self.job_logs_dir or not self.job_logs_dir.exists():
            return None

        patterns = [
            f"job_{job_id}.json",
            f"job_{job_id}.json.gz",
            f"job_{job_id}.json.gz.transform-processed",
            f"job_{job_id}.json.transform-processed",
        ]
        for pattern in patterns:
            path = self.job_logs_dir / pattern
            if path.exists():
                return path

        matches = list(self.job_logs_dir.glob(f"job_{job_id}.*"))
        return matches[0] if matches else None
