# Spendcube - project context

General conventions (toolkit first, where data lives, SQL/SAP/DAX/Python/report rules, secrets)
come from `C:\Users\<you>\dev\CLAUDE.md` and `~/.claude/rules/` (managed in
`dev\claude_config`). This file holds only what is specific to this project. Status and open items
live in `docs/`, not here.

## What this project is
<!-- Fill in: what it does, who uses its outputs, the main deliverables. -->

## Data sources
<!-- One line per source; details in docs/data_dictionary.md. Name the exact folders read. -->
| Source | Where | Read through |
|---|---|---|
| Project data (default) | `OneDrive - Boston University\Data Projects\spendcube` | `config.DATA_DIR` |
| <!-- e.g. a CIDA Projects folder --> | <!-- `CIDA Projects\<area>\<project>\Data` --> | <!-- `config.PROJECT_DATA_DIR` --> |
| <!-- e.g. SAP PA0001 extracts --> | <!-- `Automation and Data\SAP-PA0001` --> | <!-- `config.SAP_PA0001_DIR` --> |
| <!-- e.g. SQL Server or an API --> | <!-- database / endpoint name, no credentials --> | <!-- `config.<NAME>` --> |

Data can live anywhere (OneDrive, SharePoint libraries, SQL, APIs); delete the rows that don't apply.
Never scan or glob a whole library; read only the folders named here.

SQL Server database for this project: `SPENDCUBE_SQL_DATABASE`.

## Read before you change
<!-- Map areas of the code to the docs that explain them, e.g.
| If you touch... | Read first |
|---|---|
| `sql/*.sql` | `docs/pipeline.md` | -->

## Project-specific rules
<!-- Names that must not change, queries not to touch, definitions agreed with stakeholders. -->
