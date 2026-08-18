# DS-08: Version control for analytical code

**Scenario:** analytical code — notebooks, not just pipelines — is version-controlled,
reviewable, and shareable, so work is reproducible and doesn't live on one person's laptop.

**What it proves:** every notebook in this POC is a file in a Git repository, edited either
locally or in the workspace, reviewed through pull requests, and traceable to a commit. The
evidence is not a feature tour — **it is this repository's own history.**

> **No separate artifact to build.** DS-08 is satisfied by how the POC was built. The demo is
> opening the Git panel on a real notebook and walking its actual history. Everything cited
> below is a real commit or PR in `scottDBX1886/princeton_poc`.

---

## 1. Where the notebooks live

Databricks **Git folders** (formerly Repos) clone a repo into the workspace. A notebook in a
Git folder is a file on a branch — not a workspace object with hidden revision history.

```
/Workspace/Users/<you>/princeton_poc          <- Git folder, tracks a branch
  datascientist/src/01_sql_genie_exploration.py
  datascientist/src/02_python_pandas_notebook.py
  datascientist/src/03_r_analysis_notebook.r
  ...
```

Two things worth knowing before demonstrating:

- **The folder path is per-user.** Each person clones the repo under their own
  `/Workspace/Users/<them>/`, so ~20 participants each get an independent working copy.
  There is no shared checkout to collide on. (Older docs reference `/Repos/<user>/`; both
  forms exist, and `/Workspace/Users/` is the current default.)
- **Notebooks lose the file extension in the workspace listing.** `01_sql_genie_exploration.py`
  on disk appears as `01_sql_genie_exploration` (type NOTEBOOK). Same file, and Git sees the
  `.py`. Only surprising if you're diffing a workspace listing against the repo.

---

## 2. The workflow this POC actually used

```
local clone  ──commit──▶  feature branch  ──push──▶  pull request  ──review──▶  main
     ▲                                                                            │
     └──────────────────────── pull ◀───── Git folder in workspace ◀──────────────┘
```

Both directions are real and both were used here:

**Local → workspace.** Code written in an editor, committed to a branch, pushed, then pulled
into the Git folder to run against live data.

**Workspace → Git.** A notebook edited in the browser, committed from the Git panel. This is
the path a data scientist takes when they fix something mid-analysis.

**A real example of the second path.** DS-05 shipped with a broken call — it used a
JVM-internal API to capture the query plan:

```python
plan = spark.sql(heavy_sql)._jdf.queryExecution().explainString(...)   # fails in a notebook
```

That was found by running the notebook, fixed in the workspace editor, and committed from the
Git panel as `32270a8`. The fix used the public API instead:

```python
buf = io.StringIO()
with contextlib.redirect_stdout(buf):
    spark.sql(heavy_sql).explain(mode="formatted")
plan = buf.getvalue()
```

That is DS-08 in one commit: a defect found at runtime, corrected in the workspace, versioned
immediately, and visible to everyone else on the next pull. Scott's `6554839`
(*"fix(e1): Excel Auto Loader needs a directory, not a file"*) is the same shape from the
Engineer track.

---

## 3. Reviewing analytical code

Notebook changes go through pull requests like any other code. Merged examples in this repo:

| PR | What it carried |
|---|---|
| #36 | DS-A — SQL + Genie exploration, plus the shared isolation helper |
| #37 | DS-B — the Python, R, and BYO-data notebooks |
| #38 | DS-C — large-dataset query and profiling |
| #39 | PA Task 0 — the `admin_demo` security harness |

Because notebooks are stored as source files with `# COMMAND ----------` cell markers, a
GitHub diff shows cell-level changes as ordinary line diffs — reviewable without opening
Databricks.

**Worth showing in the demo:** PR #38's diff, where the tracker row and the notebook change
appear side by side. Analytical code and the evidence of its verification move together.

---

## 4. What the Git panel gives you in the workspace

Open any notebook in a Git folder and click the branch name (top left):

| Action | Use |
|---|---|
| **Commit & Push** | Version an edit made in the browser |
| **Pull** | Take teammates' merged work |
| **Branch switch / create** | Move between features without leaving the UI |
| **Diff** | See uncommitted changes before committing |
| **History** | Every commit touching the file |

> **There is no auto-save-to-Git.** Saving a notebook writes it in the workspace; it does
> **not** create a commit. Committing is explicit. Anyone expecting silent sync will lose
> edits when they switch branches — worth stating plainly, because it's the most common
> misconception about Git folders.

---

## 5. Reverting

Two levels, both demonstrable:

**A single notebook, uncommitted** — Git panel → the file → *Revert*. Discards local changes
and restores the branch version.

**A merged change** — `git revert <sha>` on a branch, then a PR. The POC's SE-39 (rollback)
scenario covers this for deployments; the same mechanism applies to notebooks, since they are
the same files in the same repo.

Because every notebook is pinned to a commit, "run exactly what I ran" is a SHA, not a
description. That is the reproducibility claim the RFP is asking about.

---

## 6. Sharing

Two different things, often conflated:

**Sharing the code** — send the repo path or a GitHub link. The recipient clones the Git
folder and gets the notebook at a known commit. This is the reproducible route.

**Sharing a running notebook** — the workspace *Share* button grants `CAN_VIEW`, `CAN_RUN`,
`CAN_EDIT`, or `CAN_MANAGE` on that workspace object.

**The important part:** notebook permissions and *data* permissions are independent. Granting
`CAN_VIEW` on a notebook does **not** grant access to the tables it queries. A recipient
without `SELECT` on `gold_dev.enrollment_history` opens the notebook, sees the code, and gets
`PERMISSION_DENIED` when they run it. Unity Catalog governs the data regardless of who holds
the notebook — the same point DS-06(a) makes for laptop clients.

That means sharing analytical code is safe by default: the code is not a data leak.

---

## 7. What to show, in order

1. Open `datascientist/src/05_large_dataset_query` in a Git folder → click the branch name →
   **History**. Real commits, real authors.
2. Show `32270a8` — a bug found by running the notebook, fixed in the browser, committed from
   the Git panel.
3. Open PR #38 on GitHub → the **Files changed** tab. Cell-level diff of a notebook, plus the
   tracker update in the same review.
4. Switch branches in the Git panel to show independent lines of work in one workspace.
5. Share the notebook with a restricted user → they read the code, and the query fails on UC
   permissions.

Step 5 is the one that lands: version control and governance are separate systems, and
sharing code doesn't share data.

---

## Verification checklist

- [ ] Git folder exists under `/Workspace/Users/<you>/princeton_poc` and shows a branch name
- [ ] The Git panel opens and lists commit history for at least one notebook
- [ ] `32270a8` is visible in that history (or another workspace-authored commit)
- [ ] PR #38's *Files changed* renders a notebook cell diff on GitHub
- [ ] A second principal without `SELECT` is available for the sharing demo (step 5)
