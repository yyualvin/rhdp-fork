#!/usr/bin/env python3
"""CLI for the jira-link skill (interactive workflow)."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from job_context import build_job_summary, working_dir  # noqa: E402
from rule_match import (  # noqa: E402
    DEFAULT_MIN_SCORE,
    DEFAULT_SEMANTIC_MIN_CONFIDENCE,
    ACCEPTED_SEMANTIC_CONFIDENCES,
    confidence_meets_minimum,
    issue_by_key,
    pick_issue,
)
from semantic_validate import validate_single_match  # noqa: E402


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as f:
        json.dump(data, f, indent=2)
        f.write("\n")


def _read_json(path: Path) -> dict[str, Any]:
    with path.open() as f:
        return json.load(f)


def _fetch_jira_issues(output_path: Path) -> None:
    board_url = os.environ.get("JIRA_BOARD_URL", "").strip()
    if not board_url:
        raise ValueError(
            "JIRA_BOARD_URL is not set. Add it to .claude/settings.json env section."
        )

    jira_script = _SCRIPT_DIR / "jira.py"
    result = subprocess.run(
        [
            sys.executable,
            str(jira_script),
            "--board-url",
            board_url,
            "--active-sprint",
            "--output",
            str(output_path),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        stderr = result.stderr.strip() or result.stdout.strip() or "unknown error"
        raise RuntimeError(f"Jira fetch failed: {stderr}")


def cmd_prepare(job_id: str, fetch: bool = False) -> int:
    try:
        job = build_job_summary(job_id, fetch=fetch)
    except FileNotFoundError as e:
        print(f"[ERROR] {e}", file=sys.stderr)
        return 1

    work = working_dir(job_id)
    job_path = work / "job.json"
    jira_path = work / "jira_issues.json"

    _write_json(job_path, job)

    try:
        _fetch_jira_issues(jira_path)
    except (ValueError, RuntimeError) as e:
        print(f"[ERROR] {e}", file=sys.stderr)
        return 1

    issue_count = len(_read_json(jira_path).get("issues", []))
    print(f"[OK] Prepared job {job_id} at {work}")
    print(f"     job.json written ({len(job)} field(s))")
    print(f"     jira_issues.json written ({issue_count} issue(s))")
    return 0


def cmd_rule_match(job_id: str, min_score: int) -> int:
    work = working_dir(job_id)
    job_path = work / "job.json"
    jira_path = work / "jira_issues.json"

    for path in (job_path, jira_path):
        if not path.is_file():
            print(
                f"[ERROR] {path} not found. Run: python scripts/cli.py prepare --job-id {job_id}",
                file=sys.stderr,
            )
            return 1

    job = _read_json(job_path)
    jira_data = _read_json(jira_path)
    issues = jira_data.get("issues", [])
    if not issues:
        print("[ERROR] Jira issue list is empty", file=sys.stderr)
        return 1

    best, score = pick_issue(job, issues)
    job["ticket_match_score"] = score
    _write_json(job_path, job)

    result: dict[str, Any] = {
        "job_id": job_id,
        "ticket_match_score": score,
        "min_score": min_score,
        "meets_threshold": score >= min_score,
    }

    if score >= min_score:
        result.update(
            {
                "method": "rule",
                "ticket_key": best.get("key"),
                "ticket_link": best.get("ticket_url"),
                "is_open": best.get("is_open", True),
                "ticket_match_confidence": None,
                "ticket_match_rationale": None,
            }
        )
        print(f"[OK] Rule match for job {job_id}: {best.get('key')} (score={score})")
        print("     Semantic matching not needed.")
    else:
        result.update(
            {
                "method": None,
                "ticket_key": None,
                "ticket_link": None,
                "needs_semantic_match": True,
            }
        )
        print(f"[OK] Rule score {score} below threshold {min_score} for job {job_id}")
        print("     Semantic matching required — follow SKILL.md step 5.")

    rule_result_path = work / "rule_result.json"
    _write_json(rule_result_path, result)
    print(f"     rule_result.json written to {rule_result_path}")
    return 0


def cmd_finalize(job_id: str, semantic_min_confidence: str) -> int:
    work = working_dir(job_id)
    rule_result_path = work / "rule_result.json"
    jira_path = work / "jira_issues.json"
    semantic_path = work / "semantic_match.json"
    final_path = work / "final_result.json"

    if not rule_result_path.is_file():
        print(
            f"[ERROR] {rule_result_path} not found. Run rule-match first.",
            file=sys.stderr,
        )
        return 1

    rule_result = _read_json(rule_result_path)
    jira_data = _read_json(jira_path) if jira_path.is_file() else {"issues": []}
    issues = jira_data.get("issues", [])
    issue_map = issue_by_key(issues)
    valid_keys = set(issue_map.keys())

    final: dict[str, Any] = {
        "job_id": job_id,
        "ticket_link": None,
        "is_open": None,
        "ticket_match_method": None,
        "ticket_match_score": rule_result.get("ticket_match_score"),
        "ticket_match_confidence": None,
        "ticket_match_rationale": None,
    }

    if rule_result.get("meets_threshold"):
        final.update(
            {
                "ticket_link": rule_result.get("ticket_link"),
                "is_open": rule_result.get("is_open"),
                "ticket_match_method": "rule",
            }
        )
    elif semantic_path.is_file():
        semantic_data = _read_json(semantic_path)
        entry = validate_single_match(semantic_data, job_id, valid_keys)
        if entry:
            confidence = str(entry.get("confidence", "none")).lower()
            if confidence not in ACCEPTED_SEMANTIC_CONFIDENCES:
                confidence = "none"
            ticket_key = entry.get("ticket_key")
            if (
                ticket_key
                and confidence_meets_minimum(confidence, semantic_min_confidence)
            ):
                issue = issue_map.get(str(ticket_key))
                if issue:
                    final.update(
                        {
                            "ticket_link": issue.get("ticket_url"),
                            "is_open": issue.get("is_open", True),
                            "ticket_match_method": "semantic",
                            "ticket_match_confidence": confidence,
                            "ticket_match_rationale": entry.get("rationale"),
                        }
                    )
            elif ticket_key and confidence == "none":
                final["ticket_match_rationale"] = entry.get("rationale")
    elif rule_result.get("needs_semantic_match"):
        print(
            f"[ERROR] semantic_match.json not found at {semantic_path}. "
            "Complete semantic matching (SKILL.md step 5) before finalize.",
            file=sys.stderr,
        )
        return 1

    _write_json(final_path, final)

    method = final.get("ticket_match_method") or "none"
    print(f"[OK] Final result for job {job_id} (method={method})")
    print(f"     ticket_link: {final.get('ticket_link')}")
    if final.get("ticket_match_confidence"):
        print(f"     confidence: {final.get('ticket_match_confidence')}")
    if final.get("ticket_match_rationale"):
        print(f"     rationale: {final.get('ticket_match_rationale')}")
    print(f"     written to {final_path}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Jira-link skill CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    prepare_parser = subparsers.add_parser("prepare", help="Build job.json and fetch Jira issues")
    prepare_parser.add_argument("--job-id", required=True)
    prepare_parser.add_argument(
        "--fetch",
        action="store_true",
        help="Fetch job log from remote when not found in JOB_LOGS_DIR",
    )

    rule_parser = subparsers.add_parser("rule-match", help="Run rule-based ticket matching")
    rule_parser.add_argument("--job-id", required=True)
    rule_parser.add_argument(
        "--min-score",
        type=int,
        default=int(os.environ.get("JIRA_MATCH_MIN_SCORE", DEFAULT_MIN_SCORE)),
    )

    finalize_parser = subparsers.add_parser(
        "finalize", help="Apply semantic match and print final ticket link"
    )
    finalize_parser.add_argument("--job-id", required=True)
    finalize_parser.add_argument(
        "--semantic-min-confidence",
        default=os.environ.get("JIRA_SEMANTIC_MIN_CONFIDENCE", DEFAULT_SEMANTIC_MIN_CONFIDENCE),
        choices=sorted(ACCEPTED_SEMANTIC_CONFIDENCES - {"none"}),
    )

    args = parser.parse_args(argv)

    if args.command == "prepare":
        return cmd_prepare(args.job_id, fetch=args.fetch)
    if args.command == "rule-match":
        return cmd_rule_match(args.job_id, args.min_score)
    if args.command == "finalize":
        return cmd_finalize(args.job_id, args.semantic_min_confidence)

    return 1


if __name__ == "__main__":
    sys.exit(main())
