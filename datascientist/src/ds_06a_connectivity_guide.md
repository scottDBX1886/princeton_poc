# DS-06(a): Local connectivity — Python, R, SAS, SPSS from a laptop

**Scenario:** a data scientist works in the tool they already know, on their own machine,
against governed platform data — without exporting extracts.

**What it proves:** Databricks is reachable from any ODBC/JDBC-capable client, and Unity
Catalog permissions (including row filters and column masks) apply **to the connection**,
not to the notebook UI. The same query returns different data for different users, from
their laptop, with no extra configuration.

> **This is a reference document, not a runnable artifact.** There is no notebook to
> execute — the demo is the SA (or a DMIA participant) running one of these snippets from
> their own machine during the session. Snippets are unverified end-to-end from a laptop;
> each needs the workspace host, an HTTP path, and a token filled in.

---

## 1. Fill these in first

| Value | Where to get it | Example |
|---|---|---|
| **Server hostname** | Workspace URL, no `https://` | `fe-sandbox-serverless-sandbox-x7sksm.cloud.databricks.com` |
| **HTTP path** | SQL Warehouse → Connection details | `/sql/1.0/warehouses/<warehouse_id>` |
| **Token** | User Settings → Developer → Access tokens | `dapi…` |
| **Catalog / schemas** | Set per bundle target | `princeton_poc_dev` · `silver_dev`, `gold_dev` |

The build workspace is **AWS Databricks**, so the hostname ends in
`.cloud.databricks.com`. An Azure workspace would be `adb-<id>.<n>.azuredatabricks.net`
instead — the snippets are otherwise identical, only the host changes. Get the exact host
and HTTP path from **SQL Warehouse → Connection details**, which renders ready-to-copy
values for each client type, rather than assembling them by hand.

**Never hardcode the token.** Every snippet below reads it from an environment variable:

```bash
export DATABRICKS_HOST="fe-sandbox-serverless-sandbox-x7sksm.cloud.databricks.com"
export DATABRICKS_HTTP_PATH="/sql/1.0/warehouses/<warehouse_id>"
export DATABRICKS_TOKEN="dapi..."
```

---

## 2. Python — `databricks-sql-connector`

The first-class path: a pure-Python client, no ODBC driver to install.

```bash
pip install databricks-sql-connector
```

```python
import os
from databricks import sql

with sql.connect(
    server_hostname=os.environ["DATABRICKS_HOST"],
    http_path=os.environ["DATABRICKS_HTTP_PATH"],
    access_token=os.environ["DATABRICKS_TOKEN"],
) as connection:
    with connection.cursor() as cursor:
        cursor.execute("""
            SELECT dept_id, count(*) AS enrollments
            FROM princeton_poc_dev.gold_dev.enrollment_history
            GROUP BY dept_id
            ORDER BY enrollments DESC
            LIMIT 10
        """)
        for row in cursor.fetchall():
            print(row)
```

Straight into pandas:

```python
import os
import pandas as pd
from databricks import sql

with sql.connect(
    server_hostname=os.environ["DATABRICKS_HOST"],
    http_path=os.environ["DATABRICKS_HTTP_PATH"],
    access_token=os.environ["DATABRICKS_TOKEN"],
) as connection:
    df = pd.read_sql("SELECT * FROM princeton_poc_dev.silver_dev.student LIMIT 1000",
                     connection)
print(df.head())
print(df.dtypes)
```

Two notes on the snippet above:

- The parameter is **`access_token`**. `auth_type="pat"` + `token=` is not the current
  signature and will raise a `TypeError`.
- `pd.read_sql` emits a SQLAlchemy warning with a DBAPI connection. It works; to silence
  it, use `cursor.fetchall_arrow().to_pandas()` instead, which is also faster for large
  results.

---

## 3. R — ODBC

R needs the **Databricks ODBC driver** (not the JDBC one — `odbc::dbConnect` speaks ODBC).

```bash
# macOS
brew install unixodbc
# then install the Databricks ODBC driver from the Databricks downloads portal
```

Configure a DSN in `~/.odbc.ini`:

```ini
[Databricks]
Driver          = /Library/simba/spark/lib/libsparkodbc_sbu.dylib
Host            = fe-sandbox-serverless-sandbox-x7sksm.cloud.databricks.com
Port            = 443
HTTPPath        = /sql/1.0/warehouses/<warehouse_id>
SSL             = 1
ThriftTransport = 2
AuthMech        = 3
UID             = token
```

The driver path varies by platform and version — check the driver's own install notes.
`AuthMech = 3` selects token auth; `ThriftTransport = 2` selects HTTP.

Leave `PWD` out of the file and pass the token at connect time so it never sits on disk:

```r
library(DBI)
library(odbc)

con <- dbConnect(
  odbc::odbc(),
  dsn = "Databricks",
  PWD = Sys.getenv("DATABRICKS_TOKEN")
)

departments <- dbGetQuery(con, "
  SELECT dept_id, name, division
  FROM princeton_poc_dev.silver_dev.department
  ORDER BY dept_id
  LIMIT 10
")
print(departments)

dbDisconnect(con)
```

`dbplyr` also works over this connection if the analyst prefers `dplyr` verbs to SQL:

```r
library(dplyr)
students <- tbl(con, in_catalog("princeton_poc_dev", "silver_dev", "student"))
students %>% count(dept_id) %>% arrange(desc(n)) %>% head(10) %>% collect()
```

---

## 4. SAS — JDBC

Requires **SAS/ACCESS Interface to JDBC** and the Databricks JDBC driver on the SAS
classpath.

```sas
options set=CLASSPATH "/opt/databricks/DatabricksJDBC42.jar";

libname dbx jdbc
  driverclass="com.databricks.client.jdbc.Driver"
  url="jdbc:databricks://fe-sandbox-serverless-sandbox-x7sksm.cloud.databricks.com:443/default;
       transportMode=http;ssl=1;
       httpPath=/sql/1.0/warehouses/<warehouse_id>;
       AuthMech=3;
       ConnCatalog=princeton_poc_dev;ConnSchema=gold_dev"
  user="token"
  password="&DBX_TOKEN";

/* Pull a sample into a SAS dataset */
data work.enrollments;
  set dbx.enrollment_history(obs=1000);
run;

proc means data=work.enrollments;
  var gpa_points;
run;
```

Set the catalog and schema in the JDBC URL (`ConnCatalog` / `ConnSchema`) and reference
tables with a single-level name. SAS libnames are two-level (`libref.table`), so they
cannot express `catalog.schema.table` directly.

Keep the token out of the code:

```sas
%let DBX_TOKEN = %sysget(DATABRICKS_TOKEN);
```

---

## 5. SPSS Statistics — JDBC

Same driver, configured through the UI.

1. Add `DatabricksJDBC42.jar` to the SPSS classpath.
2. **File → Open Database → New Query…**
3. Driver class: `com.databricks.client.jdbc.Driver`
4. JDBC URL: as in the SAS example above.
5. User `token`, password = your personal access token.

Tables in `princeton_poc_dev.silver_dev` and `gold_dev` are then browsable and queryable
through the standard SPSS database wizard.

---

## 6. The point of the scenario: UC governs the connection

Everything above is plumbing. **This** is what the RFP is asking about.

Unity Catalog permissions are enforced at the SQL warehouse, so they apply identically
whether the query arrives from a notebook, a laptop, or a BI tool:

| Situation | What the local client sees |
|---|---|
| No `SELECT` on the table | Query fails — `PERMISSION_DENIED` |
| Row filter defined (PA-09/10) | Only permitted rows returned |
| Column mask defined (PA-07/08) | Masked or redacted values, silently |
| Table dropped or renamed | Query fails — no stale local copy to drift |

Two consequences worth stating to the customer:

1. **There is no "local extract" security gap.** The analyst never holds a copy the
   platform cannot govern — a revoked grant takes effect on the next query.
2. **The same code, run by two people, returns different data.** That is the intended
   behaviour, and it's what makes laptop access safe.

**Demo pairing:** run the Python snippet as an admin, then as a restricted user, after
PA-07 masking is applied to `admin_demo.student`. Same query, same file, different
output — the strongest single demonstration that governance is not a UI-layer feature.

---

## 7. POC vs production authentication

| | POC / this demo | Production |
|---|---|---|
| Method | Personal access token | OAuth 2.0 (U2M) or a service principal (M2M) |
| Identity | The individual | The individual, or a scoped SP for automation |
| Lifetime | Short TTL, rotate | Managed by the OAuth flow |
| Storage | Environment variable, never committed | Secret manager |

PATs are the fastest path for a POC and every snippet here uses one. For production, the
Python connector supports OAuth directly (`auth_type="databricks-oauth"`), which avoids
long-lived tokens entirely. The ODBC and JDBC drivers support OAuth via `AuthMech=11`.

If Princeton uses SSO with SCIM provisioning, OAuth means laptop access inherits the same
identity and group membership as the workspace UI — no separate credential to manage per
analyst.

---

## Verification checklist

Before demonstrating, confirm on the target workspace:

- [ ] Warehouse is running, and its **Connection details** tab matches the host/HTTP path used here
- [ ] The token belongs to a user with `USE CATALOG` on `princeton_poc_dev` and `SELECT` on the target tables
- [ ] `pip install databricks-sql-connector` succeeds on the demo laptop
- [ ] The Python snippet returns rows (fastest signal that host, path, and token are all correct)
- [ ] For the governance pairing: a second, restricted principal exists to contrast against
