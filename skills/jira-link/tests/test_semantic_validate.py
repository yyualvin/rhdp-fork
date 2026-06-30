"""Tests for semantic match validation and finalize confidence gating."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from cli import cmd_finalize  # noqa: E402
from job_context import working_dir  # noqa: E402
from semantic_validate import validate_matches  # noqa: E402


def _issue(key: str, summary: str = "") -> dict:
    return {
        "key": key,
        "summary": summary,
        "status": "In Progress",
        "ticket_url": f"https://example.atlassian.net/browse/{key}",
        "is_open": True,
    }


class TestValidateMatches(unittest.TestCase):
    def test_rejects_unknown_ticket(self) -> None:
        data = {
            "matches": [
                {
                    "job_id": "2594913",
                    "ticket_key": "GPTEINFRA-99999",
                    "confidence": "high",
                    "rationale": "bad key",
                }
            ]
        }
        result = validate_matches(data, {"2594913"}, {"GPTEINFRA-16879"})
        self.assertEqual(result["matches"], [])

    def test_accepts_valid_match(self) -> None:
        data = {
            "matches": [
                {
                    "job_id": "2594913",
                    "ticket_key": "GPTEINFRA-16879",
                    "confidence": "high",
                    "rationale": "CNV workshop",
                }
            ]
        }
        result = validate_matches(data, {"2594913"}, {"GPTEINFRA-16879"})
        self.assertEqual(len(result["matches"]), 1)
        self.assertEqual(result["matches"][0]["ticket_key"], "GPTEINFRA-16879")

    def test_none_confidence_when_no_ticket(self) -> None:
        data = {
            "matches": [
                {
                    "job_id": "2594913",
                    "ticket_key": None,
                    "confidence": "none",
                    "rationale": "No sprint ticket",
                }
            ]
        }
        result = validate_matches(data, {"2594913"}, {"GPTEINFRA-16879"})
        self.assertEqual(result["matches"][0]["confidence"], "none")
        self.assertIsNone(result["matches"][0]["ticket_key"])


class TestFinalizeConfidenceGating(unittest.TestCase):
    def test_low_semantic_confidence_rejected(self) -> None:
        job_id = "2594913"
        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp)
            with patch("cli.working_dir", return_value=work):
                (work / "rule_result.json").write_text(
                    json.dumps(
                        {
                            "job_id": job_id,
                            "ticket_match_score": 0,
                            "min_score": 15,
                            "meets_threshold": False,
                            "needs_semantic_match": True,
                        }
                    )
                )
                (work / "jira_issues.json").write_text(
                    json.dumps({"issues": [_issue("GPTEINFRA-16879", "CNV workshop")]})
                )
                (work / "semantic_match.json").write_text(
                    json.dumps(
                        {
                            "matches": [
                                {
                                    "job_id": job_id,
                                    "ticket_key": "GPTEINFRA-16879",
                                    "confidence": "low",
                                    "rationale": "Weak match",
                                }
                            ]
                        }
                    )
                )
                rc = cmd_finalize(job_id, semantic_min_confidence="medium")
                self.assertEqual(rc, 0)
                final = json.loads((work / "final_result.json").read_text())
                self.assertIsNone(final["ticket_link"])
                self.assertIsNone(final["ticket_match_method"])


if __name__ == "__main__":
    unittest.main()
