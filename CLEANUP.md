# Customer-Facing Repo — Cleanup Action Item (PARKED until dev is done)

The internal working artifacts below are already excluded in `.gitignore`, but
`.gitignore` only stops *future* tracking — **they remain in the working tree and in
git history.** Do this cleanup once development is complete, before the repo is handed
to / shared with Princeton.

## Files to remove (internal-only)
- `docs/superpowers/` — build specs, plans, design docs
- `docs/SCENARIO_TRACKER.md` — internal status / prompt-test bookkeeping
- `docs/CONFIG.md` — stale deployment notes (retired `storage_root`, internal profiles)
- `docs/training_agenda_email.html` — internal draft
- `.isaac/` — agent/tooling config
- `Princeton University RFP POC Vendor Platform test scenarios.docx` — customer's own doc, marked CONFIDENTIAL — Do Not Distribute
- `princeton_scenarios_extracted.txt` — our extract of the above

## Keep (the deliverable)
`foundation/ engineer/ businessanalyst/ datascientist/ runbook_app/ scripts/`,
`databricks.yml`, `docs/runbook/` (E9/E10/E11 walkthroughs), the per-persona `RUNBOOK.md` files.

## Also scrub for internal specifics before handoff
- Sandbox warehouse id `5d42098cbe21ce49` and host `fe-sandbox-serverless-sandbox-princeton`
  in any committed file (they get repointed at deploy, but shouldn't ship as literals).
- Internal profile names in docs (`dbx_shared_demo`, etc.).

## Recommended approach (decide at cleanup time)
1. **Fresh clean repo (most defensible):** copy the keep-list into a new repo with no history.
   Nothing internal ever existed in it. Best for a true customer handoff.
2. **Purge in place:** `git rm -r --cached <paths>` + commit, then rewrite history with
   `git filter-repo --invert-paths --path <each>` to remove from history. Keeps the URL but
   rewrites history — coordinate with anyone holding clones/branches (e.g. open DS branches).

Decision on approach: **TBD at cleanup time.**
