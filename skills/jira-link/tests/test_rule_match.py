"""Tests for rule-based Jira ticket scoring."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from rule_match import DEFAULT_MIN_SCORE, pick_issue, score_match  # noqa: E402


def _issue(key: str, summary: str = "", description: str = "") -> dict:
    return {
        "key": key,
        "summary": summary,
        "description": description,
        "status": "In Progress",
        "sprint_name": "",
        "ticket_url": f"https://example.atlassian.net/browse/{key}",
        "is_open": True,
    }


class TestScoreMatch(unittest.TestCase):
    def test_stopword_only_overlap_scores_zero(self) -> None:
        job = {"job_id": "2594913", "root_cause_summary": "Failed for the cluster"}
        issue = _issue("GPTEINFRA-1", summary="SSL/DNS update for the workshop")
        self.assertEqual(score_match(job, issue), 0)

    def test_role_match_meets_threshold(self) -> None:
        job = {"failing_role": "infra-openshift-cnv-resources"}
        issue = _issue("GPTEINFRA-2", summary="Fix infra-openshift-cnv-resources on ocpv01")
        self.assertGreaterEqual(score_match(job, issue), DEFAULT_MIN_SCORE)


class TestPickIssue(unittest.TestCase):
    def test_tie_breaking_preserves_issue_order(self) -> None:
        job = {"job_id": "2594913", "root_cause_summary": "unrelated failure"}
        issues = [_issue("GPTEINFRA-A"), _issue("GPTEINFRA-B")]
        best, score = pick_issue(job, issues)
        self.assertEqual(best["key"], "GPTEINFRA-A")
        self.assertEqual(score, 0)


if __name__ == "__main__":
    unittest.main()
