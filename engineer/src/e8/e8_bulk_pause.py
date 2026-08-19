# Databricks notebook source
# MAGIC %md
# MAGIC # E8b — Bulk disable / pause of workloads (SE-31)
# MAGIC The RFP asks for a **maintenance-window** control: suspend *all* scheduled pipelines in a
# MAGIC single operation, then re-enable them afterward. Databricks has no one-button "pause
# MAGIC everything", so the native, admin-grade answer is a small script over the Jobs API — which
# MAGIC is exactly how a platform admin would run a maintenance window.
# MAGIC
# MAGIC **Scope:** this targets only **Engineer (SE/E) workloads** — jobs whose name carries an
# MAGIC Engineer scenario tag like `(E8)` or `(SE-09)`. Data Scientist, Business Analyst, and
# MAGIC Platform-Admin jobs are deliberately left alone (a different owner runs those maintenance
# MAGIC windows). One run pauses every matching scheduled job; `action=resume` restores them.
# MAGIC It only touches jobs whose schedule is currently the *opposite* state, so re-running is
# MAGIC idempotent, and it reports a before/after count as the proof.

# COMMAND ----------
import re
from databricks.sdk import WorkspaceClient
from databricks.sdk.service.jobs import CronSchedule, PauseStatus

dbutils.widgets.dropdown("action", "pause", ["pause", "resume"])
# Only Engineer-owned jobs: name contains an (E<n>) or (SE-<n>) scenario tag. This excludes
# DS-*, BA-*, PA-* and shared infra jobs by construction.
dbutils.widgets.text("include_regex", r"\((E\d+|SE-\d+)\)")
action = dbutils.widgets.get("action")
include_re = re.compile(dbutils.widgets.get("include_regex"))

target = PauseStatus.PAUSED if action == "pause" else PauseStatus.UNPAUSED
w = WorkspaceClient()

# COMMAND ----------
# Find every scheduled Engineer job. Two filters: (1) the name carries an Engineer scenario
# tag, so DS/BA/PA jobs are never in scope; (2) it has a schedule — a bulk pause is about
# stopping the clock, so jobs without a schedule are untouched.
scheduled = []
for j in w.jobs.list(expand_tasks=False):
    name = j.settings.name or ""
    sched = j.settings.schedule
    if include_re.search(name) and sched is not None:
        scheduled.append((j.job_id, name, sched))

print(f"Found {len(scheduled)} scheduled Engineer job(s) matching {include_re.pattern!r}")
for jid, name, sched in scheduled:
    print(f"  {jid}  {sched.pause_status.value:9}  {name}")

# COMMAND ----------
# Apply the target state in a single pass. This IS the "single operation" the RFP asks for —
# one run flips every matching schedule.
changed = 0
for jid, name, sched in scheduled:
    if sched.pause_status == target:
        continue  # already in the desired state → idempotent no-op
    new_sched = CronSchedule(
        quartz_cron_expression=sched.quartz_cron_expression,
        timezone_id=sched.timezone_id,
        pause_status=target,
    )
    w.jobs.update(job_id=jid, new_settings={"schedule": new_sched.as_dict()})
    changed += 1
    print(f"  {action.upper():6} → {name}")

print(f"\nSE-31: {action}d {changed} of {len(scheduled)} scheduled job(s) in one operation.")

# COMMAND ----------
# Proof: re-read the live state so the before/after is verifiable, not asserted.
after = {PauseStatus.PAUSED.value: 0, PauseStatus.UNPAUSED.value: 0}
for j in w.jobs.list(expand_tasks=False):
    name = j.settings.name or ""
    if include_re.search(name) and j.settings.schedule is not None:
        after[j.settings.schedule.pause_status.value] += 1

print("Scheduled Engineer-job state after run:")
print(f"  PAUSED   : {after['PAUSED']}")
print(f"  UNPAUSED : {after['UNPAUSED']}")
print("\nMaintenance window: run with action=pause to suspend all Engineer schedules; "
      "action=resume to restore them. DS/BA/PA jobs are out of scope by design.")
