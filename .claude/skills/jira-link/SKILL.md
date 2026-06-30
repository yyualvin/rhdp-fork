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

**Job ID:** $0

Read `skills/jira-link/SKILL.md` and follow its workflow for job `$0` from start to finish.

Do not skip steps. Run the CLI commands from `skills/jira-link/` as documented there.
