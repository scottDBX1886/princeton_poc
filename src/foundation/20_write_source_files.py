# Databricks notebook source
# MAGIC %md
# MAGIC # Raw source files writer
# MAGIC Renders the SAME core data in five formats onto the landing Volume, each with the
# MAGIC deliberate "gotcha" its ingestion scenario tests. Small + human-inspectable — the
# MAGIC scale story is the fact table, not these files.
# MAGIC
# MAGIC | File | Scenario | Gotcha |
# MAGIC |------|----------|--------|
# MAGIC | students.csv | SE-04 | quoted field w/ embedded comma |
# MAGIC | enrollments.pipe.txt | SE-04 | pipe-delimited; field containing a pipe |
# MAGIC | financial_aid.xlsx | SE-05 | target a *named* sheet, not sheet 1 |
# MAGIC | course_catalog.json | SE-06 | nested objects/arrays; optional keys omitted |
# MAGIC | faculty.xml | SE-07 | repeating elements; optional <tenure> node |

# COMMAND ----------
# MAGIC %pip install openpyxl
# COMMAND ----------
dbutils.library.restartPython()

# COMMAND ----------
import json
import pandas as pd
from xml.sax.saxutils import escape

dbutils.widgets.text("catalog", "princeton_poc")
CATALOG = dbutils.widgets.get("catalog")
SILVER = f"{CATALOG}.silver"
BASE = f"/Volumes/{CATALOG}/landing/files"

# COMMAND ----------
# MAGIC %md ## students.csv — embedded delimiter inside a quoted field (SE-04)
# COMMAND ----------
sp = spark.table(f"{SILVER}.student").limit(2000).toPandas()
# Inject a value that itself contains the delimiter; QUOTE_ALL must protect it.
sp.loc[sp.index[0], "last_name"] = "Doe, John"
sp.to_csv(f"{BASE}/students.csv", index=False, quoting=1)  # csv.QUOTE_ALL
print("students.csv written:", len(sp), "rows")

# COMMAND ----------
# MAGIC %md ## enrollments.pipe.txt — pipe-delimited; one field contains a pipe (SE-04)
# COMMAND ----------
en = spark.table(f"{SILVER}.enrollment").limit(2000).toPandas()
en["grade"] = en["grade"].astype(str)
en.loc[en.index[0], "grade"] = "A|provisional"  # embedded pipe inside a quoted field
en.to_csv(f"{BASE}/enrollments.pipe.txt", sep="|", index=False, quoting=1)
print("enrollments.pipe.txt written:", len(en), "rows")

# COMMAND ----------
# MAGIC %md ## financial_aid.xlsx — 3 sheets; AidDetail is the target (SE-05)
# COMMAND ----------
fa = spark.table(f"{SILVER}.financial_aid").limit(1000).toPandas()
with pd.ExcelWriter(f"{BASE}/financial_aid.xlsx", engine="openpyxl") as w:
    fa.head(5).to_excel(w, sheet_name="Summary", index=False)
    fa.to_excel(w, sheet_name="AidDetail", index=False)   # <- named target sheet
    fa.head(1).to_excel(w, sheet_name="Decoy", index=False)
print("financial_aid.xlsx written: 3 sheets, AidDetail =", len(fa), "rows")

# COMMAND ----------
# MAGIC %md ## course_catalog.json — nested dept -> [courses]; some optional keys omitted (SE-06)
# COMMAND ----------
depts = spark.table(f"{SILVER}.department").limit(10).toPandas()
courses = spark.table(f"{SILVER}.course").toPandas()
catalog = []
for _, d in depts.iterrows():
    dept_courses = courses[courses["dept_id"] == d["dept_id"]].head(5)
    course_list = []
    for idx, (_, c) in enumerate(dept_courses.iterrows()):
        entry = {"course_id": int(c["course_id"]), "title": c["title"],
                 "credits": int(c["credits"]),
                 "sections": [{"section": "A", "seats": 30},
                              {"section": "B", "seats": 25}]}
        # Optional key omitted on some records (SE-06: optional keys absent)
        if idx % 2 == 0:
            entry["prerequisite"] = "None"
        course_list.append(entry)
    catalog.append({"dept_id": int(d["dept_id"]), "name": d["name"],
                    "division": d["division"], "courses": course_list})
with open(f"{BASE}/course_catalog.json", "w") as f:
    json.dump(catalog, f, indent=2)
print("course_catalog.json written:", len(catalog), "departments")

# COMMAND ----------
# MAGIC %md ## faculty.xml — repeating <faculty> children; optional <tenure> node (SE-07)
# COMMAND ----------
fac = spark.table(f"{SILVER}.faculty").limit(200).toPandas()
lines = ['<?xml version="1.0" encoding="UTF-8"?>', "<faculty_roster>"]
current_dept = None
for i, (_, f_row) in enumerate(fac.sort_values("dept_id").iterrows()):
    if f_row["dept_id"] != current_dept:
        if current_dept is not None:
            lines.append("  </department>")
        current_dept = f_row["dept_id"]
        lines.append(f'  <department id="{int(current_dept)}">')
    lines.append("    <faculty>")
    lines.append(f"      <faculty_id>{int(f_row['faculty_id'])}</faculty_id>")
    lines.append(f"      <name>{escape(str(f_row['first_name']))} {escape(str(f_row['last_name']))}</name>")
    lines.append(f"      <rank>{escape(str(f_row['rank']))}</rank>")
    # Optional node present only on some records (SE-07: missing optional -> null, not row-drop)
    if i % 3 == 0:
        lines.append("      <tenure>true</tenure>")
    lines.append("    </faculty>")
lines.append("  </department>")
lines.append("</faculty_roster>")
with open(f"{BASE}/faculty.xml", "w") as f:
    f.write("\n".join(lines))
print("faculty.xml written:", len(fac), "faculty")

# COMMAND ----------
# MAGIC %md ## Verify all five landed
# COMMAND ----------
display(dbutils.fs.ls(f"{BASE}"))
