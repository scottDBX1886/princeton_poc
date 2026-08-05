# Databricks notebook source
# MAGIC %md
# MAGIC # E8 · Task 6 — completion notification (SE-31)
# MAGIC Final task in the chain. The **primary** notification mechanism is the job-level
# MAGIC `email_notifications` / `webhook_notifications` block in e8_orchestration.job.yml
# MAGIC (fires on success/failure with no code — the recommended pattern). This task adds an
# MAGIC in-pipeline confirmation so the notification step is also visible as a DAG node, and
# MAGIC is where a Slack/Teams webhook post would go if desired.

# COMMAND ----------
import re, json

dbutils.widgets.text("catalog", "princeton_poc_dev")
CATALOG = dbutils.widgets.get("catalog")
user = spark.sql("SELECT current_user()").first()[0]
WS = f"{CATALOG}.wksp_" + re.sub(r"[^a-zA-Z0-9]", "_", user)

summary = spark.read.table(f"{WS}.e8_summary")
payload = {
    "job": "E8 Orchestration Demo",
    "status": "completed",
    "wksp": WS,
    "summary": [r.asDict() for r in summary.collect()],
}
print("SE-31 notification payload:")
print(json.dumps(payload, indent=2))

# --- Optional Slack/Teams webhook (left commented; wire a UC secret scope to enable) ---
# import urllib.request
# hook = dbutils.secrets.get("princeton_poc_e8", "slack_webhook")
# req = urllib.request.Request(hook, data=json.dumps({"text": f"E8 done for {WS}"}).encode(),
#                              headers={"Content-Type": "application/json"})
# urllib.request.urlopen(req, timeout=15)

print("SE-31: completion notification emitted (job-level email/webhook also fires).")
