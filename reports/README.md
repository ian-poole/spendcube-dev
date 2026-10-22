# reports/ - single-file interactive HTML reports

Reports are built with Jinja2 (templating) and Chart.js (charts) into **one self-contained
`.html` file**: Chart.js, styles, and data are all inside it. It works offline, can be emailed
or dropped on a shared drive, and makes no network requests.

```
reports/
  build.py            build script (managed, don't edit)
  templates/
    _base.html        page shell: styles, Chart.js, data, Report.* helpers (managed)
    _chart_helpers.html  extra Report.* chart helpers: axes, ticks, segments, markers (managed)
    _macros.html      chart_card / kpi_card / table_card / metrics_chart (managed)
    _skeleton.html    starting point for new reports (managed)
    <name>.html       YOUR reports (extend _base.html)
  data/               optional JSON inputs for your reports
  vendor/             pinned Chart.js + license (managed)
  tests/test_build.py checks for the build pipeline (managed)
```
"Managed" files are refreshed by the html-report skill's `init_reports.py --upgrade`. Your own
templates (anything not starting with `_`) and `data/` are never touched.

## Use

```bash
pip install jinja2
python reports/build.py --new sales             # creates templates/sales.html from the skeleton
python reports/build.py --list
python reports/build.py sales --data reports/data/sales.json --title "Sales"
```
Output: `outputs/html/sales.html`. From Python: `from build import build_report`
(with `reports/` on `sys.path`) then `build_report("sales", data=my_dict_or_dataframe)`.
Dates, NaN, Decimal, numpy and pandas values are converted to JSON-safe values automatically.

## In a template
- `data` is your data inside Jinja; `Report.data` is the same data in JavaScript.
- `Report.chart(canvasId, chartJsConfig)` draws a chart (palette colours are filled in if you
  don't set any). `Report.table(tableId, columns, rows)` builds a sortable table.
- Macros: `{% import "_macros.html" as ui %}` then `ui.chart_card(id, title)`,
  `ui.kpi_card(label, value, note)`, `ui.table_card(id, title)`, and
  `ui.metrics_chart(id, title, qualifier, legend, notes, height, legend_title)` for the Metrics view (title
  with an optional lighter qualifier, a one-line swatch-and-name legend, optionally led by a bold
  `legend_title` such as "Action Category", the plot, then notes such as the scope note). `legend` is a
  list of `{label, color, shape}` where shape is `bar`, `square` (small, for column series) or `dash`.
  `ui.scorecard_chart_box` takes the same `legend_title`, and `more_charts` (a list of `{id, title, subtitle,
  legend, legend_title, height}`) for further charts under the first one in the same box.
- Scorecard + chart box (see `references/scorecard-chart-box.md` in the html-report skill):
  `ui.scorecard_chart_box(id, title, periods, good_direction, target, count_label, decimals, unit, subtitle,
  legend, explanation, updates, definitions, note, height, compare, estimate, estimate_label, estimate_note)`
  lays out the title, a scorecard above the chart (a colored better/worse chevron on the latest period, or
  on the period named by `compare`, versus the one before it; with `estimate=true` an "Est." column after
  each partly tracked period (optional, off by default; `tracked` of `of` sub-periods): `estimate_method="gross"` (tracked so far plus
  its average for each sub-period left) or `"given"` (the period's own `estimate_value`); period notes
  beside or, with `note_below=true`, under the label; an optional target),
  the subtitle, legend and chart, a text panel on the far right (explanation, updates, data definitions;
  empty parts are left out; `explanation` may be a list of paragraphs) and an optional note. `good_direction` (`"lower"` or `"higher"`) is required
  and decides the green/red coloring. The pieces are also available alone as `ui.scorecard(...)` and `ui.side_panel(...)`,
  and `ui.lorem_ipsum` is the standard placeholder text.
- Override blocks from `_base.html`: `content`, `scripts`, `styles`, `header`, `footer`.

## Chart helpers (in `Report`, from `_chart_helpers.html`)
Each helper that needs both an axis/dataset setting and a drawing plugin returns an object with a
`scale`/`fill` part and a `plugin` part; put the first in the chart config and the plugin in `plugins`.

| Helper | Use |
|---|---|
| `Report.metricsOptions(overrides)` | Static options for the Metrics view: no hover or tooltips, no built-in legend, headroom for labels. |
| `Report.yTicks({gap, length, ...})` | Left y axis with thin black tick marks a fixed gap after each label, none at zero. `yt.scale(overrides)` and `yt.plugin`. |
| `Report.hierarchicalAxis({levels})` | Only the lowest category is labelled on the axis; each higher level is a bracket spanning its members with one label and optional info lines above it. A level is `{keys, label(key), info(key)}` with one key per bar (consecutive equal keys group); list levels from the one nearest the axis outward. `ax.scale(overrides)` (adds the room it needs) and `ax.plugin`. A level can also have `below: (key) => lines` (small notes under its label, e.g. "Q1 only"); the config takes `hideTicks: true` (hide the normal category labels when the bracket label is the only label) and `labelFont: "14px"`. |
| `Report.segmentedBars({parts, mode, segments})` | Segmented bar fill computed from data. `parts(i)` returns the numbers for bar `i`, bottom to top (or `null` for a plain bar). `mode: "percent"` means parts are percentages of the bar; `"total"` means they are amounts that add up to the bar. `seg.fill` goes in the dataset's `backgroundColor`; `seg.plugin` labels each segment. |
| `Report.barDataset({data, color/fill})` | Solid slim bars, grey by default, drawn behind markers. |
| `Report.dashDataset({data, color, size})` | Short dash markers; `size` is the dash width as a fraction of the bar width, so overlapping series can differ. List the smaller markers first so they sit on top. Use the same `barPercentage` as the bars. |
| `Report.periodAxis(points)` | One category per period. Brackets (via `hierarchicalAxis`) only when some period has `info` lines; otherwise plain labels, with `below` notes as extra label lines. Returns `{labels, scale(overrides), plugin}`. Used by `scorecardChart` and `clusteredBars`. |
| `Report.clusteredBars(id, {labels | points, series, lines, partial, partialFill, y})` | Clustered columns, one colour per series (`Report.mutedPalette` when none is given), with optional line series on top. An in-progress period's columns get a light tint of the series colour plus a dotted outline in the full colour (`partialFill: "none"` leaves them empty); lines are dotted into it. Pair with a `square` legend. `Report.tint(hex, alpha)` gives the tint. |
| `Report.lineDataset({data, color, partial})` | Line series. Points flagged `partial` (the current, incomplete fiscal year) get a dotted segment leading into them (markers stay filled). Pass `partial` as an array of booleans or a function of the index. |
| `Report.scorecardChart(id, {points, series, partial, y})` | The line chart for the scorecard + chart box in one call: no gridlines, y-axis ticks, a bracket under each period with info lines above it and small notes below it, and dotted segments into in-progress periods. |
| `Report.barLabels({text(i, value)})` | Text above chosen bars (return `null` to skip a bar). |
| `Report.format.int / compact` | `1,234` and `5.7K`. |

See `references/design-rules.md` in the html-report skill for when and how to use them.

## Conventions
- **Self-contained:** no CDN links, remote fonts or images. Embed images as `data:` URIs. The
  build fails if it finds external resources (`--allow-external` overrides).
- **Data is visible to anyone with the file.** Embed only what the charts need, preferably
  aggregated. Never embed secrets, credentials, or personal data that recipients shouldn't see.
- Give every chart a title (the macros do this). Axis titles are off by default (put units in the tick
  labels). Don't rely on colour alone.
- Keep data separate from the template; keep logic out of `build.py`.
- Reports are snapshots: the build time is in the page's `<meta name="generated">` tag (not shown on the
  page). There is no page title or date at the top by default; each box carries its own title. Override
  the `header` block to add a page heading.
- Generated reports go to `outputs/`, which is gitignored by default. Commit one deliberately.
