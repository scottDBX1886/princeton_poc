# DS-08: Version control for analytical code

**Scenario:** analytical code — notebooks, not just pipelines — is version-controlled,
reviewable, and reproducible, so work survives the person who wrote it.

**What it proves:** every Data Scientist notebook in this POC is a file in a Git repository,
edited locally *or* in the browser, reviewed through pull requests, and traceable to a commit.

> **There is nothing to build for DS-08.** The scenario is satisfied by how the POC was made.
> Everything cited below is a real commit, PR, or incident in `scottDBX1886/princeton_poc` —
> the demo is opening the Git panel and walking actual history, not touring features.

---

## 1. Where the notebooks live

Databricks **Git folders** clone a repo into the workspace. A notebook in a Git folder is a
file on a branch, not a workspace object with hidden revision history.

```
/Workspace/Users/<you>/princeton_poc          <- Git folder, tracks a branch
  datascientist/src/
    ds_01_sql_genie_exploration.py       DS-01
    ds_02_python_pandas_notebook.py      DS-02
    ds_03_r_analysis_notebook.r          DS-03
    ds_04_byo_data_blend.py              DS-04
    ds_05_large_dataset_query.py         DS-05
    ds_06b_mlflow_training.py            DS-06(b)
    ds_07_scheduled_analysis.py          DS-07
    _isolation.py                     shared helper, imported by all of them
```

Two things to know before demonstrating:

- **The clone is per-user.** Each person clones under their own `/Workspace/Users/<them>/`, so
  ~20 participants get independent working copies with no shared checkout to collide on.
  (Older docs say `/Repos/<user>/`; both exist, `/Workspace/Users/` is current.)
- **Notebooks lose the extension in the workspace listing.** `ds_05_large_dataset_query.py` on
  disk shows as `ds_05_large_dataset_query`, type NOTEBOOK. Git still sees the `.py`. Only
  surprising if you diff a workspace listing against the repo — which is how one real merge
  tangle started during this build.

---

## 2. Both directions are real

```
local clone ──commit──▶ branch ──push──▶ pull request ──review──▶ main
     ▲                                                             │
     └───────────── pull ◀──── Git folder in workspace ◀────────────┘
```

**Local → workspace** is the bulk of it: code written in an editor, committed, pushed, pulled
into the Git folder, run against live data.

**Workspace → Git** is what a data scientist actually does mid-analysis: fix the thing that
just broke, in the browser, and commit it. Two real examples from this POC, both authored from
the workspace editor:

| Commit | What happened |
|---|---|
| `32270a8` | DS-05 captured the query plan through a JVM-internal call that fails in a notebook session. Found by running it, fixed in the browser, committed from the Git panel. |
| `efa2b64` | DS-07 used `summary.cache()`, which serverless rejects with `NOT_SUPPORTED_WITH_SERVERLESS: PERSIST TABLE`. Same path: run, fail, fix in the browser, commit. |

`32270a8` in full — the fix replaced an internal API with the public one:

```python
# before — fails in a notebook session
plan = spark.sql(heavy_sql)._jdf.queryExecution().explainString(...)

# after
buf = io.StringIO()
with contextlib.redirect_stdout(buf):
    spark.sql(heavy_sql).explain(mode="formatted")
plan = buf.getvalue()
```

That is DS-08 in one commit: a defect surfaced at runtime, corrected where it was found,
versioned immediately, visible to everyone on the next pull.

---

## 3. What version control actually caught

The strongest evidence isn't that history exists — it's that having it **prevented losing
work**. Two incidents from this build, both worth telling:

### The stranded fix

`efa2b64` (the `.cache()` fix above) was committed to a feature branch — but **after** that
branch's PR had already merged. The commit was real, pushed, and visible in the branch history,
yet `main` still carried the bug.

Verified with one command:

```bash
git merge-base --is-ancestor efa2b64 origin/main   # -> false
```

It was recovered by cherry-picking onto a fresh branch (`97ca45d`). Without version control the
fix would simply have been lost when the branch was deleted — and the bug only manifests when
the notebook runs as a *scheduled job*, so it would have resurfaced in front of the customer.

**The lesson to state out loud:** a commit on a branch is not a commit in `main`. Verify, don't
assume.

### The reorg that would have deleted merged work

Mid-build, the repo was restructured into persona-scoped folders (`datascientist/src/` instead
of `src/datascientist/`). Feature branches created *before* that reorg still diffed against the
old layout — so opening a PR from one would have shown ~900 deletions, removing work that had
already merged.

Caught by checking each branch's diff against `main` before opening the PR, and fixed by
rebuilding the branches on the new base. Git made the damage visible *before* it happened; it
also made the recovery mechanical.

---

## 4. Reviewing analytical code

Notebook changes go through pull requests like any other code. Merged, for this persona alone:

| PR | Carried |
|---|---|
| #36 | DS-A — SQL + Genie exploration, plus the shared `_isolation.py` helper |
| #37 | DS-B — Python, R, and BYO-data notebooks |
| #38 | DS-C — large-dataset query and profiling |
| #40 | DS-D — connectivity guide, plus two portability fixes |
| #42 | DS-E/F — MLflow training and the scheduled job |

Because notebooks are stored as source with `# COMMAND ----------` cell markers, a GitHub diff
shows cell-level changes as ordinary line diffs — reviewable without opening Databricks.

**Worth showing:** PR #42's diff, where the notebook change and the tracker row that records
its verification appear in the same review. Analytical code and the evidence for it move
together.

---

## 5. The Git panel in the workspace

Open any notebook in a Git folder and click the branch name (top left):

| Action | Use |
|---|---|
| **Commit & Push** | Version an edit made in the browser (how `32270a8` and `efa2b64` happened) |
| **Pull** | Take teammates' merged work |
| **Branch switch / create** | Move between features without leaving the UI |
| **Diff** | Review uncommitted changes before committing |
| **History** | Every commit touching the file |

> **There is no auto-save-to-Git.** Saving a notebook writes it in the workspace; it does not
> create a commit. Committing is explicit. This is the most common misconception about Git
> folders, and it silently loses edits when someone switches branches.

---

## 6. Reverting and reproducibility

**Uncommitted, single notebook** — Git panel → the file → *Revert*. Restores the branch version.

**A merged change** — `git revert <sha>` on a branch, then a PR. This is the same mechanism
SE-39 (deployment rollback) demonstrates; notebooks are the same files in the same repo, so
they get it for free.

Because every notebook is pinned to a commit, "run exactly what I ran" is a SHA rather than a
description. That's the reproducibility claim the RFP is asking about — and it extends past the
notebook: DS-07's **schedule** is declared in
`datascientist/resources/ds_07_scheduled.job.yml`, so the cron expression, timezone, and paused
state are versioned too. A schedule clicked together in the Jobs UI would have no history at all.

---

## 7. Sharing: code and data are governed separately

Two different things, often conflated:

**Sharing the code** — send the repo path or a GitHub link. The recipient clones and gets the
notebook at a known commit. This is the reproducible route.

**Sharing a running notebook** — the workspace *Share* button grants `CAN_VIEW`, `CAN_RUN`,
`CAN_EDIT`, or `CAN_MANAGE` on that workspace object.

**The part that matters:** notebook permissions and *data* permissions are independent.
`CAN_VIEW` on a notebook does **not** grant `SELECT` on the tables it queries. A recipient
without access opens the notebook, reads the code, and gets `PERMISSION_DENIED` when they run
it. Unity Catalog governs the data regardless of who holds the notebook.

So sharing analytical code is safe by default — the code is not a data leak. Same point
DS-06(a) makes for laptop clients: governance sits at the data, not the tool.

---

## 8. What to show, in order

1. Open `datascientist/src/ds_05_large_dataset_query` in a Git folder → click the branch name →
   **History**. Real commits, real authors, mixed local and browser origins.
2. Show `32270a8` — a bug found by running the notebook, fixed in the browser, committed from
   the Git panel.
3. Tell the **stranded fix** story (`efa2b64` → `97ca45d`). It's the most honest demonstration
   of why history matters: the fix was recoverable because it was committed.
4. Open PR #42 on GitHub → **Files changed**. Cell-level notebook diff alongside the tracker
   update.
5. Switch branches in the Git panel — independent lines of work in one workspace.
6. Share a notebook with a restricted user → they read the code, and the query fails on UC
   permissions.

Step 6 is the one that lands: version control and governance are separate systems, and sharing
code doesn't share data.

---

## Verification checklist

- [ ] Git folder exists under `/Workspace/Users/<you>/princeton_poc` and shows a branch name
- [ ] The Git panel lists commit history for at least one notebook
- [ ] `32270a8` and `efa2b64` are both visible in history (the two browser-authored commits)
- [ ] PR #42's *Files changed* renders a notebook cell diff on GitHub
- [ ] `datascientist/resources/ds_07_scheduled.job.yml` shows the schedule is versioned too
- [ ] A second principal without `SELECT` is available for the sharing demo (step 6)
