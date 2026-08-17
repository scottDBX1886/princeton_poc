#!/usr/bin/env bash
# =============================================================================
# Princeton POC — one-command workspace standup
#
#   ./scripts/setup_new_workspace.sh <profile> [target]
#   e.g.  ./scripts/setup_new_workspace.sh princeton_poc dev
#
# Stands up the ENTIRE POC on a fresh (serverless) Databricks workspace:
#   preflight → deploy → foundation build (catalog+schemas+volume+data+Genie via
#   UC default storage) → mock API app → ingest SP + minted secret + scope → UC
#   grants → run & assert every pre-built object.
#
# Idempotent (safe to re-run) and fail-fast. Prompt-testing (Genie/Designer
# code-gen) is a manual UI follow-up — a script can't drive Genie; this validates
# the BUILD end-to-end. See engineer/RUNBOOK.md for the prompt tests.
# =============================================================================
set -euo pipefail

PROFILE="${1:?usage: setup_new_workspace.sh <profile> [target]}"
TARGET="${2:-dev}"
SCOPE="princeton_poc_e3"
APP="princeton-mock-api"
SP_DISPLAY="princeton-poc-e3-ingest"
CATALOG="princeton_poc_dev"      # fixed by the bundle target vars (notebooks hardcode it)
FILES="/Workspace/Shared/.bundle/princeton_poc/${TARGET}/files"   # deployed source root

cd "$(dirname "${BASH_SOURCE[0]}")/.."

say() { printf '\n\033[1;36m== %s ==\033[0m\n' "$*"; }
ok()  { printf '  \033[1;32m✓\033[0m %s\n' "$*"; }
warn(){ printf '  \033[1;33m!\033[0m %s\n' "$*"; }
die() { printf '\n\033[1;31m✗ %s\033[0m\n' "$*" >&2; exit 1; }

WAREHOUSE_ID=""
# sql "<statement>"  → prints first cell (or 'OK'); exits non-zero on error
sql() {
  python3 - "$WAREHOUSE_ID" "$1" > /tmp/_pp_stmt.json <<'PY'
import json,sys
print(json.dumps({"warehouse_id":sys.argv[1],"statement":sys.argv[2],"wait_timeout":"50s"}))
PY
  databricks api post /api/2.0/sql/statements --profile "$PROFILE" --json @/tmp/_pp_stmt.json 2>&1 | python3 -c "
import json,sys
d=json.load(sys.stdin); st=d.get('status',{}).get('state')
if st!='SUCCEEDED':
    sys.stderr.write('SQL FAILED: '+str(d.get('status',{}).get('error',''))[:300]+'\n'); sys.exit(1)
r=d.get('result',{}).get('data_array',[])
print(r[0][0] if r and r[0] else 'OK')
"
}

# run_notebook "<name>" "<workspace notebook path>" '<base_parameters json>'  (serverless env v5)
run_notebook() {
  local name="$1" path="$2" params="$3"
  python3 - "$name" "$path" "$params" > /tmp/_pp_nb.json <<'PY'
import json,sys
name,path,params=sys.argv[1],sys.argv[2],sys.argv[3]
print(json.dumps({
  "run_name": f"standup: {name}",
  "environments":[{"environment_key":"default","spec":{"environment_version":"5"}}],
  "tasks":[{"task_key":name.replace(' ','_'),"environment_key":"default",
            "notebook_task":{"notebook_path":path,"base_parameters":json.loads(params)}}]
}))
PY
  databricks jobs submit --json @/tmp/_pp_nb.json --profile "$PROFILE" >/dev/null 2>&1
}

# ---------------------------------------------------------------------------
say "1/9  Preflight — auth + warehouse"
USER=$(databricks current-user me --profile "$PROFILE" -o json 2>/dev/null | python3 -c "import json,sys;print(json.load(sys.stdin)['userName'])") \
  || die "not authenticated. Run: databricks auth login --profile $PROFILE"
WS_SCHEMA="wksp_$(printf '%s' "$USER" | tr -c 'a-zA-Z0-9' '_')"
ok "authed as $USER"
WAREHOUSE_ID=$(databricks warehouses list --profile "$PROFILE" -o json 2>/dev/null | python3 -c "
import json,sys
d=json.load(sys.stdin); w=d if isinstance(d,list) else d.get('warehouses',[])
sv=[x for x in w if x.get('enable_serverless_compute')]
print((sv or w)[0]['id'] if (sv or w) else '')")
[ -n "$WAREHOUSE_ID" ] || die "no SQL warehouse found on $PROFILE"
ok "warehouse $WAREHOUSE_ID · test schema $CATALOG.$WS_SCHEMA"

# ---------------------------------------------------------------------------
say "2/9  Pre-create UC namespace on default storage (SQL on serverless)"
# The SDP pipelines validate their target catalog at DEPLOY time, but the catalog is
# normally created by the foundation job's uc_setup task (which runs after deploy). On a
# truly fresh workspace that's a chicken-and-egg: deploy fails with CATALOG_DOES_NOT_EXIST.
# So create the catalog+schemas+volume here first (idempotent — the uc_setup job task then
# no-ops). CREATE CATALOG on a serverless warehouse provisions UC default storage.
sql "CREATE CATALOG IF NOT EXISTS $CATALOG COMMENT 'Princeton POC shared data foundation'" >/dev/null
for s in bronze silver gold landing models; do sql "CREATE SCHEMA IF NOT EXISTS $CATALOG.${s}_dev" >/dev/null; done
sql "CREATE VOLUME IF NOT EXISTS $CATALOG.landing_dev.files" >/dev/null
ok "catalog $CATALOG + 5 schemas + landing volume (default storage)"

# ---------------------------------------------------------------------------
say "3/9  Clear stale local bundle state + deploy"
rm -rf ".databricks/bundle/$TARGET"
databricks bundle deploy -t "$TARGET" --profile "$PROFILE" --var="warehouse_id=$WAREHOUSE_ID" >/dev/null \
  || die "bundle deploy failed"
ok "deployed to $PROFILE ($TARGET)"

# ---------------------------------------------------------------------------
say "4/9  Foundation build (catalog+schemas+volume+data+Genie)"
databricks bundle run foundation_build -t "$TARGET" --profile "$PROFILE" >/dev/null || die "foundation_build failed"
students=$(sql "SELECT count(*) FROM $CATALOG.silver_dev.student")
fact=$(sql "SELECT count(*) FROM $CATALOG.gold_dev.enrollment_history")
[ "$students" = "30000" ] || die "unexpected student count $students (want 30000)"
ok "data: students=$students · enrollment_history=$fact"
# Stage the BA-04/08 sample upload (not part of foundation_build) so the BA workflow can run.
if [ -f businessanalyst/src/sample_uploads/departments_budget_fy2025.csv ]; then
  databricks fs mkdir "dbfs:/Volumes/$CATALOG/landing_dev/files/uploads" --profile "$PROFILE" 2>/dev/null || true
  databricks fs cp businessanalyst/src/sample_uploads/departments_budget_fy2025.csv \
    "dbfs:/Volumes/$CATALOG/landing_dev/files/uploads/departments_budget_fy2025.csv" \
    --overwrite --profile "$PROFILE" >/dev/null 2>&1 && ok "staged BA budget upload" || warn "BA upload staging failed"
fi

# ---------------------------------------------------------------------------
say "5/9  Mock REST API app (E3 source)"
databricks bundle run mock_api -t "$TARGET" --profile "$PROFILE" >/dev/null 2>&1 || true
APP_JSON=$(databricks apps get "$APP" --profile "$PROFILE" -o json 2>/dev/null || echo '{}')
APP_STATE=$(echo "$APP_JSON" | python3 -c "import json,sys;print((json.load(sys.stdin).get('app_status',{}) or {}).get('state','?'))")
APP_SP=$(echo "$APP_JSON"   | python3 -c "import json,sys;print(json.load(sys.stdin).get('service_principal_client_id',''))")
APP_URL=$(echo "$APP_JSON"  | python3 -c "import json,sys;print(json.load(sys.stdin).get('url',''))")
ok "app $APP: $APP_STATE"

# ---------------------------------------------------------------------------
say "6/9  Ingest SP + minted secret → scope $SCOPE"
EXIST=$(databricks service-principals list --profile "$PROFILE" -o json 2>/dev/null | python3 -c "
import json,sys
d=json.load(sys.stdin); sp=d if isinstance(d,list) else d.get('Resources',[])
m=[s for s in sp if s.get('displayName')=='$SP_DISPLAY']
print(m[0]['id']+'|'+m[0].get('applicationId','') if m else '')")
if [ -n "$EXIST" ]; then
  SP_INTERNAL="${EXIST%%|*}"; SP_APPID="${EXIST##*|}"; ok "reusing ingest SP $SP_APPID"
else
  RESP=$(databricks api post /api/2.0/preview/scim/v2/ServicePrincipals --profile "$PROFILE" \
    --json "{\"displayName\":\"$SP_DISPLAY\",\"schemas\":[\"urn:ietf:params:scim:schemas:core:2.0:ServicePrincipal\"]}")
  SP_INTERNAL=$(echo "$RESP" | python3 -c "import json,sys;print(json.load(sys.stdin)['id'])")
  SP_APPID=$(echo "$RESP"    | python3 -c "import json,sys;print(json.load(sys.stdin)['applicationId'])")
  ok "created ingest SP $SP_APPID"
fi
SP_SECRET=$(databricks service-principal-secrets-proxy create "$SP_INTERNAL" --profile "$PROFILE" -o json 2>/dev/null \
  | python3 -c "import json,sys;print(json.load(sys.stdin)['secret'])")
[ -n "$SP_SECRET" ] || die "failed to mint SP secret"
databricks secrets create-scope "$SCOPE" --profile "$PROFILE" 2>/dev/null || true
databricks secrets put-secret "$SCOPE" client_id     --string-value "$SP_APPID"  --profile "$PROFILE"
databricks secrets put-secret "$SCOPE" client_secret --string-value "$SP_SECRET" --profile "$PROFILE"
ok "scope $SCOPE populated"

# ---------------------------------------------------------------------------
say "7/9  Grants — ingest SP CAN_USE on app · app SP reads foundation"
databricks api patch "/api/2.0/permissions/apps/$APP" --profile "$PROFILE" --json "{
  \"access_control_list\":[{\"service_principal_name\":\"$SP_APPID\",\"permission_level\":\"CAN_USE\"}]}" >/dev/null 2>&1 \
  && ok "ingest SP CAN_USE on $APP" || warn "set CAN_USE on $APP manually (permission)"
if [ -n "$APP_SP" ]; then
  sql "GRANT USE CATALOG ON CATALOG $CATALOG TO \`$APP_SP\`" >/dev/null
  sql "GRANT USE SCHEMA ON SCHEMA $CATALOG.silver_dev TO \`$APP_SP\`" >/dev/null
  sql "GRANT SELECT ON SCHEMA $CATALOG.silver_dev TO \`$APP_SP\`" >/dev/null
  ok "app SP $APP_SP granted read on silver_dev"
else
  warn "could not resolve app SP — grant USE CATALOG/SCHEMA + SELECT on silver_dev manually"
fi

# ---------------------------------------------------------------------------
say "8/9  Run pre-builts (dependency order) + assert"
# E1 (files → bronze)
databricks bundle run e1_file_ingestion -t "$TARGET" --profile "$PROFILE" >/dev/null || die "E1 failed"; ok "E1 file ingestion"
# E3 (REST API notebook) — needs app + scope + grants (all done above)
run_notebook "E3" "$FILES/engineer/src/e3_rest_api_ingestion" "{\"catalog\":\"$CATALOG\",\"app_url\":\"$APP_URL\",\"secret_scope\":\"$SCOPE\"}" && ok "E3 REST API" || warn "E3 failed (check app running + grants)"
# E4 (reconciles E1 + E3 outputs) — pipeline
databricks bundle run e4_multisource_merge -t "$TARGET" --profile "$PROFILE" >/dev/null && ok "E4 multi-source merge" || warn "E4 failed"
# E5 (transforms)
databricks bundle run e5_transformations -t "$TARGET" --profile "$PROFILE" >/dev/null || die "E5 failed"; ok "E5 transformations"
# E6 — snapshot-setup notebook first, then the pipeline
run_notebook "E6-setup" "$FILES/engineer/src/e6_snapshot_setup" "{\"catalog\":\"$CATALOG\",\"schema_suffix\":\"_dev\"}" && ok "E6 snapshot setup" || warn "E6 setup failed"
databricks bundle run e6_cdc_scd -t "$TARGET" --profile "$PROFILE" >/dev/null && ok "E6 CDC+SCD" || warn "E6 failed"
# E7 (target loading notebook) — needs E5 output
run_notebook "E7" "$FILES/engineer/src/e7_target_loading" "{\"catalog\":\"$CATALOG\",\"schema_suffix\":\"_dev\"}" && ok "E7 target loading" || warn "E7 failed"
# SE-09, E8, BA workflow (jobs)
databricks bundle run sftp_ingest -t "$TARGET" --profile "$PROFILE" >/dev/null 2>&1 && ok "SE-09 SFTP" || warn "SE-09 failed"
databricks bundle run orchestration_demo -t "$TARGET" --profile "$PROFILE" >/dev/null 2>&1 && ok "E8 orchestration" || warn "E8 failed"
databricks bundle run ba_budget_enrollment_join -t "$TARGET" --profile "$PROFILE" >/dev/null 2>&1 && ok "BA-04/08 workflow" || warn "BA workflow failed"

# ---------------------------------------------------------------------------
say "9/9  Verify key outputs"
gpa_valid=$(sql "SELECT count(*) FROM $CATALOG.$WS_SCHEMA.e5_gpa_valid" 2>/dev/null || echo "n/a")
scd1=$(sql     "SELECT count(*) FROM $CATALOG.$WS_SCHEMA.e6_student_scd1" 2>/dev/null || echo "n/a")
recon=$(sql    "SELECT count(*) FROM $CATALOG.$WS_SCHEMA.e4_enrollment_reconciled" 2>/dev/null || echo "n/a")
e3rows=$(sql   "SELECT count(*) FROM $CATALOG.$WS_SCHEMA.e3_enrollments_from_api" 2>/dev/null || echo "n/a")
e7rows=$(sql   "SELECT count(*) FROM $CATALOG.$WS_SCHEMA.e7_student_target" 2>/dev/null || echo "n/a")

printf '\n\033[1;32m=== STANDUP COMPLETE (%s / %s) ===\033[0m\n' "$PROFILE" "$TARGET"
cat <<EOF
  foundation    students=$students  enrollment_history=$fact
  E3 api rows   $e3rows      (expect 60000)
  E4 reconciled $recon       (expect 60000)
  E5 gpa_valid  $gpa_valid   (expect 59988)
  E6 scd1       $scd1        (expect 1005)
  E7 target     $e7rows      (expect 23999)
  mock API      $APP_STATE   $APP_URL
  ingest SP     $SP_APPID    (secret in scope $SCOPE)
Next → prompt-test scenarios in the UI (Genie/Designer): see engineer/RUNBOOK.md
EOF
