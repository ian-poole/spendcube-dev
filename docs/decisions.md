# Decision log

Newest first. One entry per non-obvious choice.

## 2026-10-23 - Concur and database investigation: findings and rebuild decisions
Decided (by the owner):
- **Parent entries stay out of `dbo.predictions`** in the rebuild.
- `srm`, `amex_pcard` and the `cidadata` schema are historical only; BOA pCard no longer loads.
- The 2025 and 2026 bulk Concur allocation files are catch-ups, not part of the daily feed.
- Source extracts are deltas; each daily Concur file holds one paid date and files do not overlap.
- Anything that looks like a load problem in the 143 Parent groups (below) is investigated during the
  rebuild.

Measured (read-only, spendcube database, 2026-10-23):
- **The 1,814 Concur entries with no amount are all Parents** ($858,981). A Parent's allocation row is
  blank by design; its Child entries carry the amounts. The extract has no Parent -> Child key; matching
  by report_legacy_key + vendor, Children equal their Parents in 1,559 of 1,708 groups and cover 98% of
  Parent dollars. 149 groups differ or have no Children (net -$16.9k): some are exactly 2x (duplicated
  Children), some half or less (missing Children, probably the days the allocations run was down).
  Do not fall back to the entry amount for Parents; that would double count.
- **2,249 Concur entries are overcounted** (two rows each at 100%, $527k excess). 1,679 are loaded twice
  far apart in `index` (the old script version wrote `funding_source`; the current one writes it after
  `to_sql`, so the later row has it NULL), and some entries appear in two consecutive daily files. No
  whole-row duplicates exist. Cause is the "newest created file" load plus no natural key or load log.
- **Disbursements has 79,470 rows with corrupt `join_key_datasource` and a null `level_0`**, 945 repeated
  `index` values and 74,314 whole-row duplicates; `predictions` is missing rows for Ariba (~130k) and
  disbursements, and has duplicate disbursement join keys (59k). Re-profile before the rebuild.
- Daily allocation files are missing for about half the days since 2025 (the allocations run was not
  running); entries files exist for every day.
- Not yet checked: Ariba and BOA duplicates.

Checks: `sql/checks/concur_allocation_checks.sql` (run in SSMS; builds temp tables only). It excludes
Parents from the amount checks and reconciles Parents to Children (checks 10 to 12).

Planned rebuild direction (not built yet): one job per source, each with its own monitored run; a load
log keyed on file name and content hash; Concur entries and allocations paired by file date; natural
keys so reruns skip rows already loaded; predictions built from source rows that have none, with a
numeric `amount`; keep the `dbo.predictions` columns `V_Predictions` selects.

## 2026-10-23 - dbo.V_Predictions_With_Funds_Sources is broken and unused
- Its output columns are labelled one position off from `amount` onward (for example
  `p.funding_source AS amount`, `p.amount AS datasource`), and nothing reads it. Do not rebuild it;
  it can be dropped in the future.
- The views Power BI depends on are `dbo.V_Predictions` and `dbo.V_all_funds_sources`. Snapshot of all
  three definitions: `docs/view_definitions_snapshot.sql`. The rebuild must keep the `dbo.predictions`
  column names `V_Predictions` selects, and the funds-source columns `V_all_funds_sources` reads from
  each source table (plus a unique, matching `join_key_datasource`).

## 2026-10-22 - Load job moved to cida_toolkit and monitored_run
- `src/spendcube/sql_load_automation.py` (from PYODBC_spendcube_SQL_LOAD_automation.py) now imports
  from `cida_toolkit`, runs inside `monitored_run("spendcube_sql_load")`, builds the engine with
  `make_engine`, and reads settings and source folders only through `config.py`.
- Hardcoded SQL password removed; it now comes from `CIDA_SQL_PASSWORD` in `.env`.
- Business logic unchanged. Column cleaning uses `columnreplaceforsqlload(strict=False)` because
  toolkit 0.3.0 defaults to strict names, which would rename `g/l_account` and others in SQL.
- Kept: per-source try/except (one failing source does not stop the rest; sets `run.failure = 1`),
  and `result = "Success"` after the predictions step even if an earlier source failed.
- Changed: the monitoring script name is now `spendcube_sql_load` (was the running exe's name); an
  unrecoverable error now re-raises after logging, so Task Scheduler shows the failure.
- ODBC driver stays "ODBC Driver 13 for SQL Server" as before.

## 2026-10-22 - Project created
- Scaffolded structure; Excel/CSV treated as data only, Power BI stored as PBIP.
