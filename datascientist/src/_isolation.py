# Multi-user isolation helper (spec §3.1, issue #34).
#
# ~20+ DMIA participants run these runbooks concurrently, per-person. Two rules follow:
#   1. The foundation (silver/gold + landing files) is READ-ONLY. Nothing here writes to it.
#   2. Every scenario write goes to a per-person schema `<catalog>.wksp_<user>`, derived
#      from current_user() so 20 people running the same notebook never collide.
#
# Imported by every DS notebook rather than repeated inline, so the pattern is fixed in
# one place. Notebooks add their own directory to sys.path, then:
#
#     from _isolation import resolve_context
#     ctx = resolve_context(spark, dbutils)
#
import re


def user_schema_name(user: str) -> str:
    """Per-person schema name for `user`. Non-alphanumerics collapse to underscores so
    an email (mehak.juneja@databricks.com) becomes a legal identifier
    (wksp_mehak_juneja_databricks_com). Pure function — unit-testable off-platform."""
    return "wksp_" + re.sub(r"[^a-zA-Z0-9]", "_", user)


def resolve_context(spark, dbutils):
    """Read the standard widgets, derive the per-person schema, and create it if absent.

    Returns a dict with the names every DS notebook needs:
      catalog, suffix  — from widgets, so one notebook runs on dev/qa/prod unedited
      silver, gold     — READ-ONLY foundation schemas
      user, work       — the caller's identity and their private write target

    Widgets are declared here (idempotent) so each notebook does not restate them.
    """
    dbutils.widgets.text("catalog", "princeton_poc")
    dbutils.widgets.text("schema_suffix", "")
    catalog = dbutils.widgets.get("catalog")
    suffix = dbutils.widgets.get("schema_suffix")

    user = spark.sql("SELECT current_user()").first()[0]
    work = f"{catalog}.{user_schema_name(user)}"
    # IF NOT EXISTS keeps this safe when 20 people run the same cell at once.
    spark.sql(f"CREATE SCHEMA IF NOT EXISTS {work}")

    return {
        "catalog": catalog,
        "suffix": suffix,
        "silver": f"{catalog}.silver{suffix}",   # read-only
        "gold": f"{catalog}.gold{suffix}",       # read-only
        "models": f"{catalog}.models{suffix}",   # DS-E model registration
        "user": user,
        "work": work,                            # <- all writes go here
    }
