"""Rule-based Jira ticket scoring for job summaries."""

from __future__ import annotations

import re
from typing import Any

DEFAULT_MIN_SCORE = 15
DEFAULT_SEMANTIC_MIN_CONFIDENCE = "medium"
ACCEPTED_SEMANTIC_CONFIDENCES = frozenset({"high", "medium", "low", "none"})
SEMANTIC_CONFIDENCE_RANK = {"high": 3, "medium": 2, "low": 1, "none": 0}

_STOPWORDS = frozenset({
    "for", "the", "and", "with", "from", "that", "this", "when", "not",
    "are", "was", "has", "have", "new", "progress",
})


def _tokens(text: str) -> set[str]:
    return {
        t
        for t in re.findall(r"[a-z0-9][a-z0-9_-]{2,}", text.lower())
        if t not in _STOPWORDS
    }


def _issue_text(issue: dict[str, Any]) -> str:
    parts = [
        issue.get("key", ""),
        issue.get("summary", ""),
        issue.get("description", ""),
        issue.get("status", ""),
        issue.get("sprint_name", ""),
    ]
    return " ".join(str(p) for p in parts if p)


def _job_text(job: dict[str, Any]) -> str:
    parts = [
        job.get("job_id", ""),
        job.get("root_cause_summary", ""),
        job.get("root_cause_category", ""),
        job.get("catalog_item", ""),
        job.get("cluster", ""),
        job.get("platform", ""),
        job.get("guid", ""),
        job.get("failing_role", ""),
        job.get("failing_github_path", ""),
    ]
    return " ".join(str(p) for p in parts if p)


def score_match(job: dict[str, Any], issue: dict[str, Any]) -> int:
    job_blob = _job_text(job).lower()
    issue_blob = _issue_text(issue).lower()
    score = 0

    guid = str(job.get("guid", "")).lower()
    if guid and guid in issue_blob:
        score += 50

    job_id = str(job.get("job_id", ""))
    if job_id and job_id in issue_blob:
        score += 40

    catalog = str(job.get("catalog_item", "")).lower()
    if catalog and catalog in issue_blob:
        score += 25

    platform = str(job.get("platform", "")).lower()
    if platform and platform in issue_blob:
        score += 10

    role = str(job.get("failing_role", "")).lower()
    if role and role in issue_blob:
        score += 15

    path = str(job.get("failing_github_path", "")).lower()
    if path:
        filename = path.rsplit(":", 1)[0].rsplit("/", 1)[-1]
        if filename and filename in issue_blob:
            score += 12

    job_tokens = _tokens(job_blob)
    issue_tokens = _tokens(issue_blob)
    score += len(job_tokens & issue_tokens)

    return score


def pick_issue(
    job: dict[str, Any], issues: list[dict[str, Any]]
) -> tuple[dict[str, Any], int]:
    if not issues:
        raise ValueError("No Jira issues available for ticket matching")

    ranked = sorted(issues, key=lambda issue: score_match(job, issue), reverse=True)
    best = ranked[0]
    return best, score_match(job, best)


def issue_by_key(issues: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {str(issue.get("key", "")): issue for issue in issues if issue.get("key")}


def confidence_meets_minimum(confidence: str, minimum: str) -> bool:
    return SEMANTIC_CONFIDENCE_RANK.get(confidence, 0) >= SEMANTIC_CONFIDENCE_RANK.get(
        minimum, 0
    )
