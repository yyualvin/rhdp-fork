#!/usr/bin/env python3
"""List job log files on the remote bastion (read-only, no download)."""

from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import subprocess
import sys

REMOTE_HOST = os.environ.get("REMOTE_HOST", "")
REMOTE_DIR = os.environ.get("REMOTE_DIR", "")

JOB_ID_RE = re.compile(r"^job_(\d+)")


def build_remote_list_command(mode: str, order: str, limit: int | None) -> str:
    if mode == "processed":
        pattern = "job_*.transform-processed"
    elif mode == "ignored":
        pattern = "job_*.transform-ignored"
    elif mode == "all":
        pattern = "job_*"
    else:
        raise ValueError(f"Unknown mode: {mode}")

    # ls -1t: newest first; ls -1tr: oldest first
    sort_flag = "-1t" if order == "desc" else "-1tr"
    list_cmd = f"ls {sort_flag} {pattern} 2>/dev/null"
    if limit is not None:
        list_cmd += f" | head -n {int(limit)}"
    return f"cd {shlex.quote(REMOTE_DIR)} && {list_cmd}"


def extract_job_id(filename: str) -> str | None:
    match = JOB_ID_RE.match(filename.strip())
    return match.group(1) if match else None


def list_remote_files(mode: str, order: str, limit: int | None) -> list[str]:
    remote_cmd = build_remote_list_command(mode, order, limit)
    result = subprocess.run(
        ["ssh", REMOTE_HOST, remote_cmd],
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    if result.returncode != 0:
        stderr = result.stderr.strip() or result.stdout.strip() or "ssh failed"
        raise RuntimeError(stderr)
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="List job log files on the remote bastion (read-only)"
    )
    parser.add_argument(
        "--mode",
        choices=["processed", "ignored", "all"],
        default="processed",
        help="Which log files to list (default: processed)",
    )
    parser.add_argument(
        "--order",
        choices=["desc", "asc"],
        default="desc",
        help="Sort by mtime: desc=newest first (default), asc=oldest first",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=20,
        help="Max files to list (default: 20, use 0 for no limit)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output JSON with filenames and extracted job_ids",
    )
    args = parser.parse_args(argv)

    if not REMOTE_HOST or not REMOTE_DIR:
        print(
            "REMOTE_HOST and REMOTE_DIR must be set (e.g. in .claude/settings.json env)",
            file=sys.stderr,
        )
        return 1

    limit = None if args.limit == 0 else args.limit

    try:
        files = list_remote_files(args.mode, args.order, limit)
    except (RuntimeError, subprocess.TimeoutExpired) as e:
        print(f"[ERROR] {e}", file=sys.stderr)
        return 1

    entries = []
    for name in files:
        job_id = extract_job_id(name)
        entries.append({"filename": name, "job_id": job_id})

    if args.json:
        print(
            json.dumps(
                {
                    "remote_host": REMOTE_HOST,
                    "remote_dir": REMOTE_DIR,
                    "mode": args.mode,
                    "count": len(entries),
                    "jobs": entries,
                },
                indent=2,
            )
        )
        return 0

    print(f"[INFO] Remote: {REMOTE_HOST}:{REMOTE_DIR}")
    print(f"[INFO] Mode: {args.mode}, order: {args.order}, found: {len(entries)}")
    if not entries:
        print("[INFO] No matching job log files on remote.")
        return 0

    print(f"{'JOB_ID':<12} FILENAME")
    print("-" * 60)
    for entry in entries:
        job_id = entry["job_id"] or "?"
        print(f"{job_id:<12} {entry['filename']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
