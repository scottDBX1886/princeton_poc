#!/usr/bin/env python3
"""Generate the BA-02 'Enrollment by Department' AI/BI dashboard (enrollment_by_department.lvdash.json).

Runs locally (emits JSON only). Every query was tested against silver_dev on the dev warehouse
before this file was written. The dashboard is read-only over the shared foundation, so all
analysts can view/subscribe/export concurrently. Regenerate: python businessanalyst/src/dashboards/build_dashboard.py
"""
import json, pathlib

# enrollment has no dept_id — a course's department is course.dept_id. Join
# enrollment -> course -> department -> term. Verified live (960 dept x term groups).
BASE_JOIN = """
FROM princeton_poc_dev.silver_dev.enrollment e
JOIN princeton_poc_dev.silver_dev.course c ON e.course_id = c.course_id
JOIN princeton_poc_dev.silver_dev.department d ON c.dept_id = d.dept_id
JOIN princeton_poc_dev.silver_dev.term t ON e.term_id = t.term_id
""".strip()

# Detail grain: department x term (the subscribable/exportable table).
SUMMARY = f"""
SELECT d.name AS department, t.year, t.season, t.term_id,
  count(e.enrollment_id) AS enrollment_count,
  count(DISTINCT e.student_id) AS unique_students,
  round(avg(e.gpa_points), 2) AS avg_gpa
{BASE_JOIN}
GROUP BY d.name, t.year, t.season, t.term_id
ORDER BY t.year DESC, enrollment_count DESC
"""

# Top-15 departments by total enrollment (bar chart — bounded cardinality).
BY_DEPT = f"""
SELECT d.name AS department, count(e.enrollment_id) AS enrollment_count,
  round(avg(e.gpa_points), 2) AS avg_gpa
{BASE_JOIN}
GROUP BY d.name
ORDER BY enrollment_count DESC
LIMIT 15
"""

# Enrollment trend by year (line chart).
BY_YEAR = f"""
SELECT t.year, count(e.enrollment_id) AS enrollment_count
{BASE_JOIN}
GROUP BY t.year
ORDER BY t.year
"""

KPI = f"""
SELECT count(e.enrollment_id) AS total_enrollments,
  count(DISTINCT e.student_id) AS distinct_students,
  count(DISTINCT d.dept_id) AS departments,
  round(avg(e.gpa_points), 2) AS overall_avg_gpa
{BASE_JOIN}
"""


def lines(sql):
    return [l + "\n" for l in sql.strip().splitlines()]


def counter(name, field, title, x):
    return {"widget": {"name": name,
            "queries": [{"name": "main_query", "query": {"datasetName": "kpi",
                "fields": [{"name": field, "expression": f"`{field}`"}], "disaggregated": True}}],
            "spec": {"version": 2, "widgetType": "counter",
                     "encodings": {"value": {"fieldName": field, "displayName": title}},
                     "frame": {"title": title, "showTitle": True}}},
            "position": {"x": x, "y": 2, "width": 2, "height": 3}}


def text(name, line, y):
    return {"widget": {"name": name, "multilineTextboxSpec": {"lines": [line]}},
            "position": {"x": 0, "y": y, "width": 6, "height": 1}}


dashboard = {
    "datasets": [
        {"name": "kpi", "displayName": "KPI totals", "queryLines": lines(KPI)},
        {"name": "by_dept", "displayName": "Top departments", "queryLines": lines(BY_DEPT)},
        {"name": "by_year", "displayName": "Enrollment by year", "queryLines": lines(BY_YEAR)},
        {"name": "summary", "displayName": "Dept x term detail", "queryLines": lines(SUMMARY)},
    ],
    "pages": [{
        "name": "enrollment",
        "displayName": "Enrollment by Department",
        "pageType": "PAGE_TYPE_CANVAS",
        "layout": [
            text("title", "## Enrollment by Department — Weekly Report (BA-02)", 0),
            text("subtitle",
                 "Enrollment summary by department & term over the shared foundation. "
                 "Use the **Subscribe** and **Export** buttons (top-right) — no SQL. Read-only.", 1),
            counter("kpi-enroll", "total_enrollments", "Total enrollments", 0),
            counter("kpi-students", "distinct_students", "Distinct students", 2),
            counter("kpi-gpa", "overall_avg_gpa", "Overall avg GPA", 4),
            # Top departments bar
            {"widget": {"name": "dept-bar",
                "queries": [{"name": "main_query", "query": {"datasetName": "by_dept",
                    "fields": [{"name": "department", "expression": "`department`"},
                               {"name": "enrollment_count", "expression": "`enrollment_count`"}],
                    "disaggregated": True}}],
                "spec": {"version": 3, "widgetType": "bar",
                         "encodings": {
                             "x": {"fieldName": "enrollment_count", "scale": {"type": "quantitative"}, "displayName": "Enrollments"},
                             "y": {"fieldName": "department", "scale": {"type": "categorical"}, "displayName": "Department"}},
                         "frame": {"title": "Top 15 departments by enrollment", "showTitle": True}}},
             "position": {"x": 0, "y": 5, "width": 3, "height": 6}},
            # Trend by year
            {"widget": {"name": "year-line",
                "queries": [{"name": "main_query", "query": {"datasetName": "by_year",
                    "fields": [{"name": "year", "expression": "`year`"},
                               {"name": "enrollment_count", "expression": "`enrollment_count`"}],
                    "disaggregated": True}}],
                "spec": {"version": 3, "widgetType": "line",
                         "encodings": {
                             "x": {"fieldName": "year", "scale": {"type": "categorical"}, "displayName": "Year"},
                             "y": {"fieldName": "enrollment_count", "scale": {"type": "quantitative"}, "displayName": "Enrollments"}},
                         "frame": {"title": "Enrollment trend by year", "showTitle": True}}},
             "position": {"x": 3, "y": 5, "width": 3, "height": 6}},
            text("detail-header", "### Department × term detail (subscribe or export this)", 11),
            {"widget": {"name": "summary-table",
                "queries": [{"name": "main_query", "query": {"datasetName": "summary",
                    "fields": [{"name": "department", "expression": "`department`"},
                               {"name": "year", "expression": "`year`"},
                               {"name": "season", "expression": "`season`"},
                               {"name": "enrollment_count", "expression": "`enrollment_count`"},
                               {"name": "unique_students", "expression": "`unique_students`"},
                               {"name": "avg_gpa", "expression": "`avg_gpa`"}],
                    "disaggregated": True}}],
                "spec": {"version": 2, "widgetType": "table",
                         "encodings": {"columns": [
                             {"fieldName": "department", "displayName": "Department"},
                             {"fieldName": "year", "displayName": "Year"},
                             {"fieldName": "season", "displayName": "Season"},
                             {"fieldName": "enrollment_count", "displayName": "Enrollments"},
                             {"fieldName": "unique_students", "displayName": "Unique students"},
                             {"fieldName": "avg_gpa", "displayName": "Avg GPA"}]},
                         "frame": {"title": "Enrollment by department & term", "showTitle": True}}},
             "position": {"x": 0, "y": 12, "width": 6, "height": 7}},
        ],
    }],
}

out = pathlib.Path(__file__).parent / "enrollment_by_department.lvdash.json"
out.write_text(json.dumps(dashboard, indent=2))
print(f"wrote {out} ({len(json.dumps(dashboard))} bytes)")
