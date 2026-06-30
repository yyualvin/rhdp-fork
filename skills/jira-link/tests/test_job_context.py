"""Tests for building job summaries from job logs by job ID."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from config import JobConfig  # noqa: E402
from job_context import build_job_summary, resolve_job_log  # noqa: E402


SAMPLE_JOB = {
    "metadata": {
        "job_metadata": {
            "job_id": "1234567",
            "job_name": "RHPDS openshift_cnv.zt-rhel-bu-lab-developer-cnv.prod-x1234-provision",
            "guid": "x1234",
            "status": "failed",
            "sandbox_openshift_cluster": "ocpv01",
        }
    },
    "events": [
        {
            "event": "runner_on_failed",
            "failed": True,
            "task": "Create PVC",
            "role": "infra-openshift-cnv-resources",
            "event_data": {
                "res": {"msg": "Missing PVC in cnv-images namespace"},
                "task_path": "/roles/infra-openshift-cnv-resources/tasks/main.yml",
            },
        }
    ],
}


class TestBuildJobSummary(unittest.TestCase):
    def test_builds_from_job_log(self) -> None:
        job_id = "1234567"
        with tempfile.TemporaryDirectory() as tmp:
            logs_dir = Path(tmp) / "logs"
            logs_dir.mkdir()
            log_path = logs_dir / f"job_{job_id}.json"
            log_path.write_text(json.dumps(SAMPLE_JOB))

            config = JobConfig(job_logs_dir=logs_dir, remote_host="", remote_log_dir="")
            with patch("job_context.JobConfig.from_env", return_value=config):
                job = build_job_summary(job_id)

            self.assertEqual(job["job_id"], job_id)
            self.assertEqual(job["guid"], "x1234")
            self.assertEqual(job["failing_role"], "infra-openshift-cnv-resources")
            self.assertIn("openshift_cnv", job.get("platform", ""))
            self.assertIn("Missing PVC", job.get("root_cause_summary", ""))

    def test_enriches_from_optional_step5(self) -> None:
        job_id = "1234567"
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            logs_dir = tmp_path / "logs"
            logs_dir.mkdir()
            (logs_dir / f"job_{job_id}.json").write_text(json.dumps(SAMPLE_JOB))

            analysis_dir = tmp_path / "analysis" / job_id
            analysis_dir.mkdir(parents=True)
            (analysis_dir / "step5_analysis_summary.json").write_text(
                json.dumps(
                    {
                        "job_id": job_id,
                        "root_cause": {
                            "summary": "PVC quota exceeded in cnv-images",
                            "category": "resource",
                        },
                    }
                )
            )

            config = JobConfig(job_logs_dir=logs_dir, remote_host="", remote_log_dir="")
            with (
                patch("job_context.JobConfig.from_env", return_value=config),
                patch("job_context.rca_analysis_dir", return_value=analysis_dir),
            ):
                job = build_job_summary(job_id)

            self.assertEqual(job["root_cause_category"], "resource")
            self.assertEqual(job["root_cause_summary"], "PVC quota exceeded in cnv-images")

    def test_resolve_job_log_raises_when_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            logs_dir = Path(tmp) / "logs"
            logs_dir.mkdir()
            config = JobConfig(job_logs_dir=logs_dir, remote_host="", remote_log_dir="")
            with patch("job_context.JobConfig.from_env", return_value=config):
                with self.assertRaises(FileNotFoundError):
                    resolve_job_log("9999999")


if __name__ == "__main__":
    unittest.main()
