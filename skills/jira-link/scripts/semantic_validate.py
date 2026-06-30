"""Validate and compact semantic Jira match payloads."""

from __future__ import annotations

import json
import re
import sys
from typing import Any


def compact_job(job: dict[str, Any]) -> dict[str, Any]:
    fields = (
        "job_id",
        "status",
        "root_cause_category",
        "root_cause_summary",
        "guid",
        "catalog_item",
        "cluster",
        "platform",
        "failing_role",
        "failing_github_path",
        "ticket_match_score",
    )
    return {field: job.get(field) for field in fields if job.get(field) is not None}


def compact_issue(issue: dict[str, Any]) -> dict[str, Any]:
    fields = ("key", "summary", "description", "status", "ticket_url", "is_open")
    compact = {field: issue.get(field) for field in fields if issue.get(field) is not None}
    if compact.get("description"):
        compact["description"] = str(compact["description"])[:500]
    return compact


def extract_json(text: str) -> dict[str, Any]:
    text = text.strip()
    if not text:
        raise ValueError("Claude returned empty output")

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    fence_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fence_match:
        return json.loads(fence_match.group(1))

    brace_match = re.search(r"(\{.*\})", text, re.DOTALL)
    if brace_match:
        return json.loads(brace_match.group(1))

    raise ValueError("Could not parse JSON from Claude output")


def validate_matches(
    data: dict[str, Any],
    expected_job_ids: set[str],
    valid_ticket_keys: set[str],
) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise ValueError("Semantic match output must be a JSON object")

    raw_matches = data.get("matches", [])
    if not isinstance(raw_matches, list):
        raise ValueError("Semantic match output must include a matches array")

    validated: list[dict[str, Any]] = []
    for entry in raw_matches:
        if not isinstance(entry, dict):
            continue
        job_id = str(entry.get("job_id", "")).strip()
        if job_id not in expected_job_ids:
            print(f"[WARN] Ignoring semantic match for unexpected job_id {job_id}", file=sys.stderr)
            continue

        ticket_key = entry.get("ticket_key")
        confidence = str(entry.get("confidence", "none")).lower()
        rationale = str(entry.get("rationale") or "").strip()

        if ticket_key is None or str(ticket_key).lower() == "null" or confidence == "none":
            validated.append(
                {
                    "job_id": job_id,
                    "ticket_key": None,
                    "confidence": "none",
                    "rationale": rationale or "No suitable Jira ticket found",
                }
            )
            continue

        ticket_key = str(ticket_key).strip()
        if ticket_key not in valid_ticket_keys:
            print(
                f"[WARN] Ignoring semantic match for job {job_id}: unknown ticket {ticket_key}",
                file=sys.stderr,
            )
            continue

        validated.append(
            {
                "job_id": job_id,
                "ticket_key": ticket_key,
                "confidence": confidence,
                "rationale": rationale,
            }
        )

    return {"matches": validated}


def validate_single_match(
    data: dict[str, Any],
    job_id: str,
    valid_ticket_keys: set[str],
) -> dict[str, Any] | None:
    """Return the validated match entry for a single job, or None if rejected."""
    result = validate_matches(data, {job_id}, valid_ticket_keys)
    matches = result.get("matches", [])
    return matches[0] if matches else None
