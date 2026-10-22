# Spendcube

_Created 2026-10-22._

## Purpose
One or two sentences: what question does this project answer, and for whom?

## Tools in use
<!-- Delete what doesn't apply: Python, Excel/CSV, databases/APIs, Power BI, HTML reports -->

## Setup
```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
pip install -e C:\Users\<you>\dev\toolkit   # shared cida_toolkit (or the pinned version in pyproject.toml)
cp .env.example .env      # then fill in values; .env is never committed
pytest
```

Settings are read through `src/spendcube/config.py`. Add new variables to `.env.example`.
Code lives in this repo (local, outside OneDrive). Data is never in the repo and can live anywhere:
by default the matching OneDrive folder (`...\Data Projects\spendcube`, with `raw`, `interim`,
`processed`, `sample`, found through `DATA_DIR` in `.env`), or a synced SharePoint folder, SQL
Server, or an API. Sources and locations are listed in `docs/data_dictionary.md` and `config.py`.

## Layout
| Path | Contents |
|------|----------|
| `DATA_DIR\raw` | Untouched source files (not in Git; if data lives elsewhere, replace with that source) |
| `DATA_DIR\interim`, `DATA_DIR\processed` | Intermediate and cleaned data |
| `DATA_DIR\sample` | Small anonymized samples |
| `outputs/` | Generated reports and deliverables (not in Git by default) |
| `src/spendcube` | Reusable Python code |
| `notebooks/` | Exploration only |
| `powerbi/` | Power BI Project (.pbip) |
| `reports/` | HTML report tooling (Jinja2 + Chart.js), if set up |
| `docs/` | Data dictionary, pipeline outline, decision log |
