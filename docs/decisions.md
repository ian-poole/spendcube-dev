# Decision log

Newest first. One entry per non-obvious choice.

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
