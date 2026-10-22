# vendor/

Third-party code that is inlined into every report so each report is one self-contained file.

| File | Source | Version | License |
|------|--------|---------|---------|
| `chart.umd.min.js` | npm package `chart.js`, file `dist/chart.umd.min.js` | 4.5.1 | MIT (see `CHARTJS_LICENSE.md`) |

This copy is pinned on purpose: reports don't change when the internet does, and they work
offline and behind firewalls. To upgrade Chart.js, replace `chart.umd.min.js` with the new
build, update the version above, and run `pytest reports/tests`. Note that
`init_reports.py --upgrade` restores the version shipped with the skill, so make the change
in the skill's `assets/project/vendor/` too if you want it to stick.
