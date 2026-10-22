# MANAGED by the html-report skill (refreshed by init_reports.py --upgrade).
"""Checks the build pipeline itself, using a throwaway fixture template (not a real report)."""
import datetime as dt
import json
import re
import sys
from pathlib import Path

import pytest

REPORTS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPORTS))
import build  # noqa: E402

FIXTURE = """\
{% extends "_base.html" %}
{% import "_macros.html" as ui %}
{% block content %}
<div class="grid kpis">{{ ui.kpi_card("Total", "42", "fixture") }}</div>
<div class="grid">{{ ui.chart_card("c1", "Chart one", "sub") }}</div>
{{ ui.table_card("t1", "Table one") }}
{{ ui.metrics_chart("m1", "Metric title", "qual", [{"label": "Legend A", "color": "#bf7b68"}, {"label": "Dash", "color": "#000", "shape": "dash"}], ["Scope note"]) }}
{{ ui.scorecard_chart_box("s1", "Box title", [{"label": "FY26", "value": 13.31, "count": 82}, {"label": "FY27", "value": 7.55, "count": 41, "note": "Q1 only"}], good_direction="lower", target={"label": "FY35 Target", "value": 5}, count_label="terms", subtitle="(As % of population)", legend=[{"label": "Line A", "color": "#1d2330"}], explanation=ui.lorem_ipsum, definitions=[{"field": "Field one", "text": "Meaning one."}], note="Scope note two") }}
{% endblock %}
{% block scripts %}
<script>
Report.chart("c1", {type: "bar", data: {labels: Report.data.labels, datasets: [{label: "x", data: Report.data.values}]}});
Report.table("t1", [{key: "label", label: "Label"}], Report.data.labels.map(function (l) { return {label: l}; }));
</script>
{% endblock %}
"""

HOSTILE = "</script><script>alert(1)</script> & <b>bold</b> ' \""


@pytest.fixture()
def built(tmp_path):
    tdir = tmp_path / "t"
    tdir.mkdir()
    (tdir / "fixture.html").write_text(FIXTURE, encoding="utf-8")
    data = {
        "labels": ["a", HOSTILE],
        "values": [1, float("nan")],
        "when": dt.datetime(2026, 1, 2, 3, 4),
        "day": dt.date(2026, 1, 2),
    }
    path = build.build_report("fixture", data, title="Fixture", out_dir=tmp_path / "out",
                              extra_template_dirs=[tdir])
    return path, path.read_text(encoding="utf-8")


def test_output_is_one_file_with_chartjs_inlined(built):
    path, html = built
    assert path.suffix == ".html" and len(list(path.parent.iterdir())) == 1
    assert "Chart.js v" in html and path.stat().st_size > 150_000


def test_no_external_resources(built):
    _, html = built
    assert build.check_self_contained(html) == []
    assert "sourceMappingURL" not in html


def test_data_is_embedded_as_valid_json_and_cannot_break_out(built):
    _, html = built
    m = re.search(r'<script id="report-data" type="application/json">(.*?)</script>', html, re.S)
    assert m, "data block missing or terminated early"
    payload = json.loads(m.group(1))
    assert payload["labels"][1] == HOSTILE            # round-trips exactly
    assert payload["values"][1] is None               # NaN became null (valid JSON)
    assert payload["when"].startswith("2026-01-02T03:04")
    assert "<script>alert(1)" not in html             # hostile text is escaped in the page


def test_no_page_title_or_date_on_the_page(built):
    _, html = built
    assert "<h1>" not in html and "Generated " not in html               # titles live in the boxes
    assert '<header class="report-header"></header>' in html             # empty, hidden by CSS
    assert re.search(r'<meta name="generated" content="\d{4}-\d\d-\d\d \d\d:\d\d">', html)   # build time kept
    assert "<title>Fixture</title>" in html                               # browser tab title stays


def test_header_block_can_add_a_page_heading(tmp_path):
    html = _build_snippet(tmp_path, "")
    assert "<h1>" not in html
    tdir = tmp_path / "t3"
    tdir.mkdir()
    (tdir / "h.html").write_text('{% extends "_base.html" %}{% block header %}<h1>{{ title }}</h1>{% endblock %}',
                                 encoding="utf-8")
    html = build.build_report("h", {}, title="Page", out_dir=tmp_path / "out3", extra_template_dirs=[tdir]).read_text(encoding="utf-8")
    assert "<h1>Page</h1>" in html


def test_macros_rendered(built):
    _, html = built
    for needle in ('id="c1"', 'id="t1"', "kpi-value", 'role="img"'):
        assert needle in html


def test_metrics_chart_macro_rendered(built):
    _, html = built
    for needle in ('class="mchart"', "Metric title", "(qual)", "Legend A", "mchart-sw dash",
                   "Scope note", 'id="m1"', "max-width: 1080px"):
        assert needle in html


def test_chart_helpers_available(built):
    _, html = built
    for needle in ("R.metricsOptions =", "R.yTicks =", "R.hierarchicalAxis =", "R.segmentedBars =",
                   "R.barDataset =", "R.dashDataset =", "R.lineDataset =", "R.scorecardChart =", "R.barLabels =", "R.format =",
                   "R.clusteredBars =", "R.mutedPalette =", "R.tint =", "R.periodAxis ="):
        assert needle in html


def test_scorecard_chart_box_rendered(built):
    _, html = built
    for needle in ('class="sbox"', "Box title", "FY35 Target", "82 terms", "41 terms", "Q1 only",
                   "(As % of population)", "Lorem ipsum dolor", "Data Definitions:", "Field one",
                   "Scope note two", 'id="s1"', "sc-pct good"):            # 13% -> 8% with lower-is-better = good
        assert needle in html
    assert "Updates:" not in html                                          # no updates given: section left out


def _build_snippet(tmp_path, body):
    tdir = tmp_path / "t2"
    tdir.mkdir(exist_ok=True)
    (tdir / "snippet.html").write_text('{% extends "_base.html" %}{% import "_macros.html" as ui %}{% block content %}' + body + "{% endblock %}", encoding="utf-8")
    return build.build_report("snippet", {}, out_dir=tmp_path / "out2", extra_template_dirs=[tdir]).read_text(encoding="utf-8")


PERIODS = '[{"label": "A", "value": 10}, {"label": "B", "value": 12}]'


def test_scorecard_colors_follow_the_good_direction(tmp_path):
    assert "sc-pct good" in _build_snippet(tmp_path, f'{{{{ ui.scorecard({PERIODS}, good_direction="higher") }}}}')
    assert "sc-pct bad" in _build_snippet(tmp_path, f'{{{{ ui.scorecard({PERIODS}, good_direction="lower") }}}}')
    flat = '[{"label": "A", "value": 10.2}, {"label": "B", "value": 9.9}]'          # equal once rounded
    assert "sc-pct flat" in _build_snippet(tmp_path, f'{{{{ ui.scorecard({flat}, good_direction="lower") }}}}')


def test_scorecard_compare_moves_the_indicator_to_a_prior_period(tmp_path):
    periods = '[{"label": "A", "value": 10}, {"label": "B", "value": 12}, {"label": "C", "value": 3, "note": "Q1 only"}]'
    by_default = _build_snippet(tmp_path, f'{{{{ ui.scorecard({periods}, good_direction="higher") }}}}')
    assert "sc-pct bad" in by_default and 'aria-label="lower than B"' in by_default    # C vs B
    moved = _build_snippet(tmp_path, f'{{{{ ui.scorecard({periods}, good_direction="higher", compare="B") }}}}')
    assert "sc-pct good" in moved and 'aria-label="higher than A"' in moved            # B vs A
    assert "sc-pct bad" not in moved and moved.count('class="sc-arrow"') == 1          # only one indicator


def test_scorecard_compare_must_name_a_period_with_one_before_it(tmp_path):
    import jinja2
    for bad in ("A", "Z"):                                                  # first period / no such period
        with pytest.raises(jinja2.UndefinedError):
            _build_snippet(tmp_path, f'{{{{ ui.scorecard({PERIODS}, good_direction="higher", compare="{bad}") }}}}')


def test_scorecard_estimates_partial_periods(tmp_path):
    periods = ('[{"label": "FY26", "value": 145}, '
               '{"label": "FY27", "value": 62, "note": "Q1 only", "tracked": 1, "of": 4, "estimate_note": "Q1 x {factor}"}]')
    html = _build_snippet(tmp_path, f'{{{{ ui.scorecard({periods}, good_direction="higher", compare="FY27", unit="", '
                                    f'estimate=true) }}}}')
    assert "Est. FY27" in html and "Q1 x 4" in html and ">248<" in html               # 62 x 4 / 1
    assert html.index("Est. FY27") > html.index("FY27<small>Q1 only")                  # right after its period
    off = _build_snippet(tmp_path, f'{{{{ ui.scorecard({periods}, good_direction="higher", unit="") }}}}')
    assert "Est. FY27" not in off                                                       # only when asked
    two = ('[{"label": "H1", "value": 10}, {"label": "H2", "value": 8, "tracked": 2, "of": 3}]')
    html = _build_snippet(tmp_path, f'{{{{ ui.scorecard({two}, good_direction="higher", unit="", estimate=true, '
                                    f'estimate_label="{{label}} projected", estimate_note="{{tracked}} of {{of}}") }}}}')
    assert "H2 projected" in html and "2 of 3" in html and ">12<" in html               # 8 x 3 / 2


def test_scorecard_gross_estimate_adds_the_average_for_each_period_left(tmp_path):
    def est(value, tracked):
        p = f'[{{"label": "A", "value": 1}}, {{"label": "B", "value": {value}, "tracked": {tracked}, "of": 4}}]'
        html = _build_snippet(tmp_path, f'{{{{ ui.scorecard({p}, good_direction="higher", unit="", estimate=true, '
                                        f'estimate_note="") }}}}')
        return html[html.index('<td class="sc-est">'):].split("</div>")[0].split(">")[-1]
    assert est(62, 1) == "248"          # Q1 x 4
    assert est(130, 2) == "260"         # Q1-Q2 x 2
    assert est(150, 3) == "200"         # Q1-Q3 + a third of it


def test_scorecard_given_estimate_and_unknown_method(tmp_path):
    import jinja2
    p = '[{"label": "A", "value": 1}, {"label": "B", "value": 62, "tracked": 1, "of": 4, "estimate_value": 230}]'
    html = _build_snippet(tmp_path, f'{{{{ ui.scorecard({p}, good_direction="higher", unit="", estimate=true, '
                                    f'estimate_method="given") }}}}')
    assert ">230<" in html and ">248<" not in html
    no_value = '[{"label": "A", "value": 1}, {"label": "B", "value": 62, "tracked": 1, "of": 4}]'
    for call in (f'ui.scorecard({no_value}, good_direction="higher", estimate=true, estimate_method="given")',
                 f'ui.scorecard({no_value}, good_direction="higher", estimate=true, estimate_method="net")'):
        with pytest.raises(jinja2.UndefinedError):                          # given needs a value; unknown method
            _build_snippet(tmp_path, "{{ " + call + " }}")


def test_scorecard_note_below_the_label(tmp_path):
    p = '[{"label": "A", "value": 1}, {"label": "B", "value": 2, "note": "Q1 only"}]'
    assert '<small class="below">Q1 only' in _build_snippet(tmp_path, f'{{{{ ui.scorecard({p}, good_direction="higher", note_below=true) }}}}')
    assert "<small>Q1 only" in _build_snippet(tmp_path, f'{{{{ ui.scorecard({p}, good_direction="higher") }}}}')


def test_scorecard_requires_the_good_direction(tmp_path):
    import jinja2
    with pytest.raises(jinja2.UndefinedError):                            # never assumed: it must be given
        _build_snippet(tmp_path, f"{{{{ ui.scorecard({PERIODS}) }}}}")
    with pytest.raises(jinja2.UndefinedError):
        _build_snippet(tmp_path, f'{{{{ ui.scorecard({PERIODS}, good_direction="sideways") }}}}')


def test_side_panel_leaves_out_empty_parts(tmp_path):
    html = _build_snippet(tmp_path, '{{ ui.side_panel(updates=["Update one"]) }}')
    assert "Updates:" in html and "Update one" in html
    assert "Data Definitions:" not in html
    assert '<aside class="sbox-panel">' not in _build_snippet(tmp_path, "{{ ui.side_panel() }}")      # the class also appears in the CSS


def test_external_resource_is_rejected(tmp_path):
    tdir = tmp_path / "t"
    tdir.mkdir()
    (tdir / "bad.html").write_text(
        '{% extends "_base.html" %}{% block content %}<img src="https://example.com/x.png">{% endblock %}',
        encoding="utf-8")
    with pytest.raises(ValueError, match="not self-contained"):
        build.build_report("bad", out_dir=tmp_path / "out", extra_template_dirs=[tdir])


def test_undefined_variable_fails_loudly(tmp_path):
    tdir = tmp_path / "t"
    tdir.mkdir()
    (tdir / "typo.html").write_text(
        '{% extends "_base.html" %}{% block content %}{{ nope }}{% endblock %}', encoding="utf-8")
    with pytest.raises(Exception):
        build.build_report("typo", out_dir=tmp_path / "out", extra_template_dirs=[tdir])


def test_new_template_rejects_reserved_names():
    with pytest.raises(ValueError):
        build.new_template("_hidden")


def test_legend_title_and_square_swatches(tmp_path):
    legend = '[{"label": "Promotions", "color": "#6F8FAF", "shape": "square"}, {"label": "Transfers", "color": "#D9A55B", "shape": "square"}]'
    html = _build_snippet(tmp_path, f'{{{{ ui.metrics_chart("m9", "T", legend={legend}, legend_title="Action Category") }}}}')
    head = html.index('mchart-legend-title">Action Category')
    assert head < html.index(">Promotions<") < html.index(">Transfers<")              # title first, one row
    assert 'class="mchart-sw square"' in html
    box = _build_snippet(tmp_path, f'{{{{ ui.scorecard_chart_box("b9", "T", {PERIODS}, "higher", legend={legend}, '
                                   f'legend_title="Action Category") }}}}')
    assert 'mchart-legend-title">Action Category' in box
    assert 'mchart-legend-title"' not in _build_snippet(tmp_path, f'{{{{ ui.metrics_chart("m8", "T", legend={legend}) }}}}')


def test_scorecard_box_more_charts(tmp_path):
    more = '[{"id": "c2", "title": "Second chart", "subtitle": "(share)", "height": 240}]'
    html = _build_snippet(tmp_path, f'{{{{ ui.scorecard_chart_box("c1", "Box", {PERIODS}, "higher", more_charts={more}) }}}}')
    assert html.index('id="c1"') < html.index('class="sbox-more-title">Second chart') < html.index('id="c2"')
    assert "(share)" in html and "--sbox-h: 240px" in html
    assert 'class="sbox-more"' not in _build_snippet(tmp_path, f'{{{{ ui.scorecard_chart_box("c1", "Box", {PERIODS}, "higher") }}}}')


def test_side_panel_explanation_paragraphs(tmp_path):
    html = _build_snippet(tmp_path, '{{ ui.side_panel(explanation=["First paragraph.", "Second paragraph."]) }}')
    assert "<p>First paragraph.</p><p>Second paragraph.</p>" in html
    assert "<p>Just one.</p>" in _build_snippet(tmp_path, '{{ ui.side_panel(explanation="Just one.") }}')
