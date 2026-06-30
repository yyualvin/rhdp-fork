# Semantic Jira Ticket Matching Rules

You are matching failed RHDP/AAP jobs to open Jira sprint tickets.

For each job below, pick at most ONE ticket from the Jira list, or use null when no ticket fits.

## Matching rules (priority order)

1. Explicit references in ticket text (job_id, guid, catalog_item)
2. Catalog item to workshop name mapping
   - Example: zt-rhel-bu-lab-developer-cnv maps to OpenShift Virtualization / CNV workshops
   - tests.test-empty-config and similar test catalogs usually have no sprint ticket
3. Platform (openshift_cnv, rosa, etc.) vs ticket summary keywords
4. Root cause category vs ticket scope (do not match SSL/DNS maintenance tickets unless the failure is clearly for that workshop)

Do NOT match solely on generic words (OpenShift, SSL, DNS) without catalog/workshop alignment.

## Confidence levels

- **high**: strong catalog/workshop alignment or explicit reference
- **medium**: reasonable domain alignment with some uncertainty
- **low**: weak or generic overlap only
- **none**: no suitable ticket

## Output format

Return ONLY valid JSON (no markdown fences) with this shape:

```json
{
  "matches": [
    {
      "job_id": "2594913",
      "ticket_key": "GPTEINFRA-16879",
      "confidence": "high",
      "rationale": "One sentence explaining the match"
    }
  ]
}
```

Use `ticket_key` null and confidence `none` when no ticket fits.

For a single-job interactive run, the `matches` array should contain exactly one entry for the requested job_id.
