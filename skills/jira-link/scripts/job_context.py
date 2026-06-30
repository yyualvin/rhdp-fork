"""Build job matching context from a job ID and local job log."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from config import JobConfig


def skill_dir() -> Path:
    return Path(__file__).resolve().parent.parent


def working_dir(job_id: str) -> Path:
    return skill_dir() / ".working" / job_id


def rca_analysis_dir(job_id: str) -> Path:
    return skill_dir().parent / "root-cause-analysis" / ".analysis" / job_id


def _rca_root() -> Path:
    return skill_dir().parent / "root-cause-analysis"


def _import_rca_parser():
    rca_root = str(_rca_root())
    if rca_root not in sys.path:
        sys.path.insert(0, rca_root)
    from scripts.job_parser import parse_job_log  # noqa: WPS433

    return parse_job_log


def _import_rca_fetcher():
    rca_root = str(_rca_root())
    if rca_root not in sys.path:
        sys.path.insert(0, rca_root)
    from scripts.log_fetcher import fetch_job_log  # noqa: WPS433

    return fetch_job_log


def _parse_job_name(job_name: str, guid: str) -> dict[str, str]:
    """Parse platform/catalog/env from RHPDS job name."""
    name = job_name.removeprefix("RHPDS ").strip()
    if " " in name:
        name, _ = name.split(maxsplit=1)

    guid_pattern = f"-{guid}-"
    if guid_pattern not in name:
        return {"platform": "", "catalog_item": "", "env": ""}

    before_guid, _ = name.split(guid_pattern, 1)
    parts = before_guid.split(".")
    if len(parts) >= 3:
        return {
            "platform": parts[0],
            "catalog_item": ".".join(parts[1:-1]),
            "env": parts[-1],
        }
    if len(parts) == 2:
        return {"platform": parts[0], "catalog_item": parts[1], "env": ""}
    return {"platform": parts[0] if parts else "", "catalog_item": "", "env": ""}


def _failing_fields(failed_tasks: list[dict[str, Any]]) -> dict[str, Any]:
    if not failed_tasks:
        return {}
    first = failed_tasks[0]
    fields: dict[str, Any] = {}
    role = first.get("role")
    if role:
        fields["failing_role"] = str(role)
    task_path = first.get("task_path")
    if task_path:
        fields["failing_github_path"] = str(task_path)
    error = first.get("error_message")
    if error:
        fields["root_cause_summary"] = str(error)
        fields["root_cause_category"] = "unknown"
    return fields


def _enrich_from_step5(job_id: str) -> dict[str, Any]:
    """Optional enrichment when root-cause-analysis step5 exists for this job."""
    step5_path = rca_analysis_dir(job_id) / "step5_analysis_summary.json"
    if not step5_path.is_file():
        return {}

    with step5_path.open() as f:
        step5 = json.load(f)

    fields: dict[str, Any] = {}
    root_cause = step5.get("root_cause") or {}
    if root_cause.get("summary"):
        fields["root_cause_summary"] = root_cause["summary"]
    if root_cause.get("category"):
        fields["root_cause_category"] = root_cause["category"]

    for item in step5.get("evidence") or []:
        github_path = item.get("github_path")
        if github_path:
            fields["failing_github_path"] = str(github_path)
            return fields

    for rec in step5.get("recommendations") or []:
        github_path = rec.get("github_path")
        if github_path:
            fields["failing_github_path"] = str(github_path)
            break

    return fields


def resolve_job_log(job_id: str, *, fetch: bool = False) -> Path:
    """Locate job log file by job ID; optionally fetch from remote."""
    config = JobConfig.from_env(skill_dir())
    path = config.find_job_log(job_id)
    if path:
        return path

    if fetch:
        if not config.remote_host or not config.remote_log_dir:
            raise FileNotFoundError(
                f"No log for job {job_id} in {config.job_logs_dir}. "
                "--fetch requires REMOTE_HOST and REMOTE_DIR in settings."
            )
        if not config.job_logs_dir:
            raise FileNotFoundError(
                f"No log for job {job_id}. JOB_LOGS_DIR is not configured."
            )
        fetch_job_log = _import_rca_fetcher()
        try:
            fetch_job_log(
                job_id,
                config.job_logs_dir,
                config.remote_host,
                config.remote_log_dir,
            )
        except (
            FileNotFoundError,
            subprocess.CalledProcessError,
            subprocess.TimeoutExpired,
        ) as e:
            raise FileNotFoundError(f"Failed to fetch log for job {job_id}: {e}") from e

        path = config.find_job_log(job_id)
        if path:
            return path

    if config.job_logs_dir:
        raise FileNotFoundError(
            f"No log file for job {job_id} in {config.job_logs_dir}. "
            "Place job_<id>.json in JOB_LOGS_DIR or run prepare with --fetch."
        )
    raise FileNotFoundError(
        f"No log file for job {job_id}. Set JOB_LOGS_DIR in .claude/settings.json "
        "or run prepare with --fetch."
    )


def build_job_summary(job_id: str, *, fetch: bool = False) -> dict[str, Any]:
    """Build matching context by parsing the job log for job_id."""
    log_path = resolve_job_log(job_id, fetch=fetch)
    parse_job_log = _import_rca_parser()
    context = parse_job_log(log_path)

    guid = str(context.get("guid") or "")
    parsed = _parse_job_name(str(context.get("job_name") or ""), guid)

    job: dict[str, Any] = {
        "job_id": str(context.get("job_id") or job_id),
        "status": context.get("status") or "failed",
        "guid": guid or None,
        "catalog_item": parsed.get("catalog_item") or None,
        "cluster": context.get("cluster") or None,
        "platform": parsed.get("platform") or None,
    }

    job.update(_failing_fields(context.get("failed_tasks") or []))
    job.update(_enrich_from_step5(job_id))

    return {k: v for k, v in job.items() if v is not None}
