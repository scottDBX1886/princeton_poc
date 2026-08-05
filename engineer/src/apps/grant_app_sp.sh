#!/usr/bin/env bash
# Grant a Databricks App's service principal UC read access to the foundation.
#
# Each app gets a UNIQUE service principal, created only when the app is created — so this
# runs AFTER `databricks apps deploy`. It resolves the app's SP from the app metadata,
# then issues the UC grants via the SQL API. Reusable for every app (REST, SFTP, ...).
#
# Usage:
#   engineer/src/apps/grant_app_sp.sh <app_name> <profile> <warehouse_id> <catalog> <schema> [table]
# Example:
#   engineer/src/apps/grant_app_sp.sh princeton-mock-api dbx_shared_demo a94a22f8652d85c1 \
#       princeton_poc_dev silver_dev enrollment
set -euo pipefail

APP_NAME="${1:?app_name required}"
PROFILE="${2:?profile required}"
WAREHOUSE_ID="${3:?warehouse_id required}"
CATALOG="${4:?catalog required}"
SCHEMA="${5:?schema required}"
TABLE="${6:-}"   # optional: grant SELECT on a single table; omit to grant on whole schema

echo ">> Resolving service principal for app '$APP_NAME'..."
SP=$(databricks apps get "$APP_NAME" --profile "$PROFILE" -o json \
     | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('service_principal_client_id') or d.get('service_principal_name'))")
if [[ -z "$SP" || "$SP" == "None" ]]; then
  echo "ERROR: could not resolve service principal for $APP_NAME" >&2
  exit 1
fi
echo ">> App SP: $SP"

# Build the grant SQL. SELECT on the schema covers all current+future tables; narrow to a
# single table if one was passed.
if [[ -n "$TABLE" ]]; then
  SELECT_GRANT="GRANT SELECT ON TABLE ${CATALOG}.${SCHEMA}.${TABLE} TO \`${SP}\`;"
else
  SELECT_GRANT="GRANT SELECT ON SCHEMA ${CATALOG}.${SCHEMA} TO \`${SP}\`;"
fi
SQL="GRANT USE CATALOG ON CATALOG ${CATALOG} TO \`${SP}\`; \
GRANT USE SCHEMA ON SCHEMA ${CATALOG}.${SCHEMA} TO \`${SP}\`; \
${SELECT_GRANT}"

echo ">> Granting UC read to $SP ..."
for STMT in "GRANT USE CATALOG ON CATALOG ${CATALOG} TO \`${SP}\`" \
            "GRANT USE SCHEMA ON SCHEMA ${CATALOG}.${SCHEMA} TO \`${SP}\`" \
            "${SELECT_GRANT%;}"; do
  echo "   $STMT"
  databricks api post /api/2.0/sql/statements --profile "$PROFILE" \
    --json "{\"warehouse_id\":\"${WAREHOUSE_ID}\",\"statement\":\"${STMT}\",\"wait_timeout\":\"30s\"}" \
    -o json | python3 -c "import json,sys; d=json.load(sys.stdin); print('   ->', d.get('status',{}).get('state'))"
done
echo ">> Done. $SP can now read ${CATALOG}.${SCHEMA}."
