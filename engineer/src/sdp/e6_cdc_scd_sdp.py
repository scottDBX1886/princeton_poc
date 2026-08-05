# E6 — CDC + SCD as a Lakeflow SDP (SE-03, SE-21, SE-22, SE-23)
#
# apply_changes_from_snapshot compares two student snapshots (v1 baseline, v2 with planted
# changes) and INFERS inserts/updates/deletes — the declarative, isolation-safe form of the
# day-2 change script. Applied two ways:
#   - e6_student_scd1 : SCD Type 1 (overwrite / latest)      -> SE-21
#   - e6_student_scd2 : SCD Type 2 (history, __START_AT/END) -> SE-22
# Deletes propagate (SE-03) and changes become new current rows (SE-23). Known-answer
# oracle from the setup: 10 inserts / 20 updates / 5 deletes.

from pyspark import pipelines as dp
from typing import Optional, Tuple
from pyspark.sql import DataFrame

WKSP = spark.conf.get("wksp_schema")  # princeton_poc_dev.wksp_<user> (holds the two snapshots)


# Callable feeds v1 (version 1) then v2 (version 2); returns None when done.
def _next_snapshot(latest_version: Optional[int]) -> Optional[Tuple[DataFrame, int]]:
    if latest_version is None:
        return (spark.read.table(f"{WKSP}.student_snapshot_v1"), 1)
    if latest_version == 1:
        return (spark.read.table(f"{WKSP}.student_snapshot_v2"), 2)
    return None


# SE-21 — SCD Type 1 (overwrite, keep only latest state)
dp.create_streaming_table(name="e6_student_scd1",
                          comment="SE-21 SCD Type 1 — latest state after CDC diff")
dp.create_auto_cdc_from_snapshot_flow(
    target="e6_student_scd1",
    source=_next_snapshot,
    keys=["student_id"],
    stored_as_scd_type=1)


# SE-22 — SCD Type 2 (full history with __START_AT / __END_AT)
dp.create_streaming_table(name="e6_student_scd2",
                          comment="SE-22 SCD Type 2 — full history from CDC diff")
dp.create_auto_cdc_from_snapshot_flow(
    target="e6_student_scd2",
    source=_next_snapshot,
    keys=["student_id"],
    stored_as_scd_type=2)
