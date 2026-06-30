---
name: jira-link
description: Match failed RHDP/AAP jobs to open Jira sprint tickets using rule-based scoring with Claude semantic fallback. Use when linking a job to a Jira ticket or testing ticket matching interactively.
disable-model-invocation: true
argument-hint: [job-id]
arguments: [job-id]
allowed-tools:
  - Bash
  - Read
  - Write
---

# Jira Link

Match a failed job to an open Jira sprint ticket by **job ID**. Parses the job log from `JOB_LOGS_DIR` (same as root-cause-analysis). Uses rule scoring first; semantic fallback when the score is below threshold.

**Job ID:** $0

## Prerequisites

**Required env vars** (from `.claude/settings.json`):
- `JOB_LOGS_DIR` — local directory containing `job_<id>.json` logs
- `JIRA_EMAIL`, `JIRA_API_TOKEN`, `JIRA_BOARD_URL`

**Optional env vars:**
- `REMOTE_HOST`, `REMOTE_DIR` — required only when using `--fetch` to download a missing log
- `JIRA_MATCH_MIN_SCORE` (default: 15)
- `JIRA_SEMANTIC_MIN_CONFIDENCE` (default: medium)

If `skills/root-cause-analysis/.analysis/$0/step5_analysis_summary.json` exists, its root cause summary is used to improve semantic matching. RCA is **not** required.

Install dependencies once:

```bash
cd skills/jira-link
python3 -m venv .venv && .venv/bin/pip install -q -r requirements.txt
```

Use `.venv/bin/python` for commands below if the venv exists.

---

## Workflow

```
- [ ] Step 1: Prepare inputs
- [ ] Step 2: Rule match
- [ ] Step 3: Semantic fallback (if needed)
- [ ] Step 4: Finalize and present
```

### Step 1: Prepare inputs

Parse job `$0` from `JOB_LOGS_DIR` and fetch open Jira sprint tickets:

```bash
cd skills/jira-link
python scripts/cli.py prepare --job-id $0
```

If the log is not local, fetch from the remote log server:

```bash
python scripts/cli.py prepare --job-id $0 --fetch
```

Writes `.working/$0/job.json` and `.working/$0/jira_issues.json`.

### Step 2: Rule match

```bash
python scripts/cli.py rule-match --job-id $0
```

Read `.working/$0/rule_result.json`:
- If `"meets_threshold": true` → skip to Step 4
- If `"needs_semantic_match": true` → continue to Step 3

### Step 3: Semantic fallback (only when rule score is below threshold)

1. Read `references/matching_rules.md`
2. Read `.working/$0/job.json` and `.working/$0/jira_issues.json`
3. Apply matching rules and pick at most one ticket (or none)
4. Write `.working/$0/semantic_match.json` matching `schemas/semantic_matches.schema.json`:

```json
{
  "matches": [
    {
      "job_id": "$0",
      "ticket_key": "GPTEINFRA-12345",
      "confidence": "high",
      "rationale": "One sentence explaining the match"
    }
  ]
}
```

Use `"ticket_key": null` and `"confidence": "none"` when no ticket fits.

### Step 4: Finalize and present

```bash
python scripts/cli.py finalize --job-id $0
```

Read `.working/$0/final_result.json` and present to the user:
- **ticket_link** — Jira URL or null
- **ticket_match_method** — `rule`, `semantic`, or null
- **ticket_match_confidence** — for semantic matches only
- **ticket_match_rationale** — for semantic matches only
- **ticket_match_score** — rule score

---

## Files

| File | Purpose |
|------|---------|
| `.working/<job-id>/job.json` | Job context parsed from job log (and optional RCA step5) |
| `.working/<job-id>/jira_issues.json` | Fetched open sprint tickets |
| `.working/<job-id>/rule_result.json` | Rule match outcome |
| `.working/<job-id>/semantic_match.json` | Claude semantic match (when needed) |
| `.working/<job-id>/final_result.json` | Final linked ticket result |
