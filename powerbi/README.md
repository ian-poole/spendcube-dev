# Power BI

Save the report from Power BI Desktop as a **Power BI Project (.pbip)** into this folder
(File -> Save as -> Power BI Project; enable the preview option first if your version
requires it). This produces text-based report and semantic model folders that diff cleanly
in Git.

## Notes
- `.pbix` files are gitignored; use .pbip.
- `.pbi/localSettings.json` and `.pbi/cache.abf` are gitignored (local only).
- The data may come from connections inside the Power BI project, from files in the OneDrive data folder (`DATA_DIR`), or
  from Python outputs; there may be no local data at all. Record each source in
  `docs/data_dictionary.md`.
- PBIP files can contain server and database names. Use Power Query parameters for them, and
  keep real secrets out of the model; check what is being committed.
- To sync a Power BI Service workspace with Git, use the workspace's Git integration.
