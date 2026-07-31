# Databricks notebook source
# MAGIC %md
# MAGIC # Core entity generator — Princeton POC shared foundation
# MAGIC Deterministic (fixed seed) generation of the normalized higher-ed model into
# MAGIC `princeton_poc.silver`. Small dimensions generated driver-side with Faker;
# MAGIC the large fact lives in `11_generate_fact.py`.
# MAGIC
# MAGIC Deliberate "dirty" conditions are injected for downstream transformation
# MAGIC scenarios (SE-13/14/15/16): mixed date formats, some nulls, mixed-case strings.

# COMMAND ----------
# MAGIC %pip install faker
# COMMAND ----------
dbutils.library.restartPython()

# COMMAND ----------
import random
from datetime import date, timedelta
from faker import Faker

SEED = 42
fake = Faker()
Faker.seed(SEED)
random.seed(SEED)

dbutils.widgets.text("catalog", "princeton_poc")
CATALOG = dbutils.widgets.get("catalog")
SILVER = f"{CATALOG}.silver"

# Domain constants
DIVISIONS = ["Humanities", "Natural Sciences", "Engineering", "Social Sciences", "Arts"]
STATUSES = ["active", "leave", "graduated", "withdrawn"]
RANKS = ["Assistant Professor", "Associate Professor", "Professor", "Lecturer"]
AID_TYPES = ["Grant", "Scholarship", "Work-Study", "Loan", "Fellowship"]
SEASONS = ["Fall", "Spring", "Summer"]
GRADES = ["A", "A-", "B+", "B", "B-", "C+", "C", "D", "F", "W"]
GRADE_POINTS = {"A": 4.0, "A-": 3.7, "B+": 3.3, "B": 3.0, "B-": 2.7,
                "C+": 2.3, "C": 2.0, "D": 1.0, "F": 0.0, "W": None}

# Volume knobs (small dims; fact is separate)
N_DEPT, N_FACULTY, N_COURSE, N_STUDENT, N_AID, N_ENROLL = 40, 2000, 5000, 30000, 50000, 60000

# COMMAND ----------
# MAGIC %md ## department (~40) — the universal RLS key lives here

# COMMAND ----------
departments = []
for i in range(1, N_DEPT + 1):
    departments.append((
        i,
        f"{fake.unique.last_name()} Department",
        random.choice(DIVISIONS),
        f"{fake.building_number()} {fake.street_name()}",
    ))
dept_df = spark.createDataFrame(departments, ["dept_id", "name", "division", "building"])
dept_df.write.mode("overwrite").saveAsTable(f"{SILVER}.department")
dept_ids = [d[0] for d in departments]

# COMMAND ----------
# MAGIC %md ## term (~24) — 8 years x 3 seasons. Time backbone for SCD dates.

# COMMAND ----------
terms = []
tid = 1
for year in range(2018, 2026):
    for season in SEASONS:
        start = {"Fall": date(year, 9, 1), "Spring": date(year, 1, 15),
                 "Summer": date(year, 6, 1)}[season]
        terms.append((tid, year, season, start, start + timedelta(days=100)))
        tid += 1
term_df = spark.createDataFrame(terms, ["term_id", "year", "season", "start_date", "end_date"])
term_df.write.mode("overwrite").saveAsTable(f"{SILVER}.term")
term_ids = [t[0] for t in terms]

# COMMAND ----------
# MAGIC %md ## faculty (~2000) — PII: ssn. FK dept_id.

# COMMAND ----------
faculty = []
for i in range(1, N_FACULTY + 1):
    faculty.append((
        i, fake.first_name(), fake.last_name(), fake.ssn(),
        random.choice(dept_ids), random.choice(RANKS),
        fake.date_between(start_date="-25y", end_date="today"),
    ))
fac_df = spark.createDataFrame(
    faculty, ["faculty_id", "first_name", "last_name", "ssn", "dept_id", "rank", "hire_date"])
fac_df.write.mode("overwrite").saveAsTable(f"{SILVER}.faculty")
faculty_ids = [f[0] for f in faculty]

# COMMAND ----------
# MAGIC %md ## course (~5000) — FK dept + faculty.

# COMMAND ----------
courses = []
for i in range(1, N_COURSE + 1):
    courses.append((
        i, random.choice(dept_ids), random.choice(faculty_ids),
        fake.catch_phrase().title(), random.choice([1, 2, 3, 4]),
    ))
course_df = spark.createDataFrame(
    courses, ["course_id", "dept_id", "faculty_id", "title", "credits"])
course_df.write.mode("overwrite").saveAsTable(f"{SILVER}.course")
course_ids = [c[0] for c in courses]

# COMMAND ----------
# MAGIC %md ## student (~30000) — PII: ssn, dob. dept_id = major (RLS). status = SCD-T2 attribute.
# MAGIC Deliberate dirt: ~2% null email; mixed-case last names; DOB emitted as string in
# MAGIC mixed formats for the date-parsing scenario (SE-15).

# COMMAND ----------
students = []
for i in range(1, N_STUDENT + 1):
    dob = fake.date_of_birth(minimum_age=17, maximum_age=30)
    # mixed date-string formats (SE-15): alternate ISO / US / dotted
    fmt = i % 3
    dob_str = dob.isoformat() if fmt == 0 else (
        dob.strftime("%m/%d/%Y") if fmt == 1 else dob.strftime("%d.%m.%Y"))
    last = fake.last_name()
    last = last.upper() if i % 5 == 0 else last  # mixed case (SE-13)
    email = None if i % 50 == 0 else fake.email()  # ~2% null (SE-14)
    students.append((
        i, fake.first_name(), last, fake.ssn(), dob_str,
        random.choice(dept_ids), random.choice(STATUSES), email,
    ))
student_df = spark.createDataFrame(
    students, ["student_id", "first_name", "last_name", "ssn", "dob",
               "dept_id", "status", "email"])
student_df.write.mode("overwrite").saveAsTable(f"{SILVER}.student")
student_ids = [s[0] for s in students]

# COMMAND ----------
# MAGIC %md ## financial_aid (~50000) — amount = CLS target.

# COMMAND ----------
aid = []
for i in range(1, N_AID + 1):
    aid.append((
        i, random.choice(student_ids),
        round(random.uniform(500, 60000), 2),
        random.choice(AID_TYPES), random.choice(term_ids),
    ))
aid_df = spark.createDataFrame(
    aid, ["aid_id", "student_id", "amount", "aid_type", "term_id"])
aid_df.write.mode("overwrite").saveAsTable(f"{SILVER}.financial_aid")

# COMMAND ----------
# MAGIC %md ## enrollment (~60000, modest) — core fact. Large history is in 11_generate_fact.py.

# COMMAND ----------
enroll = []
for i in range(1, N_ENROLL + 1):
    g = random.choice(GRADES)
    enroll.append((
        i, random.choice(student_ids), random.choice(course_ids),
        random.choice(term_ids), g, GRADE_POINTS[g],
    ))
enroll_df = spark.createDataFrame(
    enroll, ["enrollment_id", "student_id", "course_id", "term_id", "grade", "gpa_points"])
enroll_df.write.mode("overwrite").saveAsTable(f"{SILVER}.enrollment")

# COMMAND ----------
# MAGIC %md ## Summary
# COMMAND ----------
for t in ["department", "term", "faculty", "course", "student", "financial_aid", "enrollment"]:
    print(t, spark.table(f"{SILVER}.{t}").count())
