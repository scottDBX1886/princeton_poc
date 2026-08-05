# Databricks notebook source
# MAGIC %md
# MAGIC # E8 · Task 4 — external process call (SE-32)
# MAGIC Calls out to an external process/command. On serverless there is no shell task type,
# MAGIC so we invoke a subprocess from Python — the same "call an external command and act on
# MAGIC its output" pattern an Oracle/Informatica engineer expects (e.g. a post-load script).

# COMMAND ----------
import subprocess, sys

# Run an external OS command and capture its output (SE-32).
result = subprocess.run(
    ["python", "--version"],
    capture_output=True, text=True, check=True)
external_out = (result.stdout or result.stderr).strip()
print(f"external command returned: {external_out}")

# Demonstrate branching on the external result (what a real post-load hook would do).
rc = subprocess.run(["echo", "external task done"], capture_output=True, text=True).stdout.strip()
print(f"external echo: {rc}")
assert "done" in rc, "external command did not complete as expected"
print("SE-32: external process call succeeded")
