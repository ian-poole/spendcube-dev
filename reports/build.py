#!/usr/bin/env python3
# MANAGED by the html-report skill. Refreshed by `init_reports.py --upgrade`.
# Put your own code in templates/ and data/, not here.
"""Build single-file, self-contained interactive HTML reports (Jinja2 + Chart.js).

A report is a Jinja2 template in `reports/templates/<name>.html` that extends `_base.html`.
Data is optional; it is embedded as JSON and available to the template as `data` and to
the page's JavaScript as `Report.data`.

CLI:
    python reports/build.py --list
    python reports/build.py --new <name>
    python reports/build.py <name> [--data data.json] [--title "Title"] [--out DIR]

Python:
    from build import build_report          # with reports/ on sys.path
    build_report("sales", data={"rows": [...]}, title="Sales")

Output goes to `<project>/outputs/html/<name>.html` by default.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import decimal
import json
import math
import re
import shutil
import sys
from pathlib import Path
from typing import Any, Iterable, Sequence

try:
    from jinja2 import Environment, FileSystemLoader, StrictUndefined, select_autoescape
    from markupsafe import Markup
except ImportError:  # pragma: no cover
    sys.exit("jinja2 is required: pip install jinja2")

REPORTS_DIR = Path(__file__).resolve().parent
PROJECT_DIR = REPORTS_DIR.parent
TEMPLATES_DIR = REPORTS_DIR / "templates"
VENDOR_DIR = REPORTS_DIR / "vendor"
DEFAULT_OUT = PROJECT_DIR / "outputs" / "html"
CHARTJS_FILE = VENDOR_DIR / "chart.umd.min.js"

# Anything in the finished file that would make a network request or load another file.
_EXTERNAL_PATTERNS = [
    (re.compile(r"<script\b[^>]*\bsrc\s*=", re.I), "external <script src>"),
    (re.compile(r"<link\b[^>]*\bhref\s*=", re.I), "<link href> (stylesheet/font/etc.)"),
    (re.compile(r"<(?:img|iframe|source|video|audio|embed|object)\b[^>]*\b(?:src|data)\s*=\s*[\"']?(?!data:|#)", re.I),
     "media/frame with non-data: source"),
    (re.compile(r"(?<![\w$.])url\(\s*[\"']?(?!data:|#)", re.I), "CSS url() that is not a data: URI"),
    (re.compile(r"@import\b", re.I), "CSS @import"),
]


# --------------------------------------------------------------------------- data cleaning
def _clean(obj: Any) -> Any:
    """Make `obj` JSON-safe: dates -> ISO strings, NaN/inf -> None, numpy/pandas -> plain."""
    if obj is None or isinstance(obj, (str, bool, int)):
        return obj
    if isinstance(obj, float):
        return obj if math.isfinite(obj) else None
    if isinstance(obj, decimal.Decimal):
        return _clean(float(obj))
    if isinstance(obj, (_dt.datetime, _dt.date, _dt.time)):
        return obj.isoformat()
    if isinstance(obj, dict):
        return {str(k): _clean(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple, set, frozenset)):
        return [_clean(v) for v in obj]
    # pandas DataFrame/Series, numpy arrays and scalars (duck-typed, no hard dependency)
    if hasattr(obj, "to_dict") and hasattr(obj, "columns"):  # DataFrame
        return _clean(obj.to_dict(orient="records"))
    if hasattr(obj, "tolist"):  # numpy array / Series
        return _clean(obj.tolist())
    if hasattr(obj, "item"):  # numpy scalar
        return _clean(obj.item())
    return str(obj)


def _read_chartjs() -> Markup:
    """Chart.js source made safe to inline in a <script> element."""
    if not CHARTJS_FILE.exists():
        raise FileNotFoundError(f"Missing {CHARTJS_FILE}. Run init_reports.py --upgrade.")
    js = CHARTJS_FILE.read_text(encoding="utf-8")
    js = re.sub(r"//# sourceMappingURL=\S+\s*$", "", js)  # no reference to a separate file
    js = js.replace("</script", "<\\/script").replace("<!--", "<\\!--")
    return Markup(js)


# --------------------------------------------------------------------------- environment
def make_env(extra_template_dirs: Sequence[Path] = ()) -> Environment:
    env = Environment(
        loader=FileSystemLoader([str(p) for p in (*extra_template_dirs, TEMPLATES_DIR)]),
        autoescape=select_autoescape(["html", "htm", "xml"]),
        undefined=StrictUndefined,  # typos in templates fail loudly instead of rendering blank
        trim_blocks=True,
        lstrip_blocks=True,
    )
    return env


def list_templates() -> list[str]:
    return sorted(p.stem for p in TEMPLATES_DIR.glob("*.html") if not p.name.startswith("_"))


def check_self_contained(html: str) -> list[str]:
    """Return a list of problems that would stop the file working on its own."""
    return [label for pattern, label in _EXTERNAL_PATTERNS if pattern.search(html)]


# --------------------------------------------------------------------------- build
def build_report(
    template: str,
    data: Any = None,
    *,
    title: str | None = None,
    out_dir: Path | str | None = None,
    out_name: str | None = None,
    extra_template_dirs: Sequence[Path] = (),
    allow_external: bool = False,
) -> Path:
    """Render `templates/<template>.html` to one self-contained HTML file and return its path."""
    env = make_env(extra_template_dirs)
    name = template[:-5] if template.endswith(".html") else template
    tmpl = env.get_template(f"{name}.html")

    clean = _clean(data if data is not None else {})
    context = {
        "data": clean,
        "title": title or name.replace("_", " ").replace("-", " ").title(),
        "generated_on": _dt.datetime.now().strftime("%Y-%m-%d %H:%M"),
        "chartjs": _read_chartjs(),
    }
    html = tmpl.render(**context)

    if not allow_external:
        problems = check_self_contained(html)
        if problems:
            raise ValueError(
                "Report is not self-contained: " + "; ".join(problems)
                + ". Inline the resource as a data: URI, or pass allow_external=True."
            )

    out = Path(out_dir) if out_dir else DEFAULT_OUT
    out.mkdir(parents=True, exist_ok=True)
    path = out / (out_name or f"{name}.html")
    path.write_text(html, encoding="utf-8")
    return path


def new_template(name: str) -> Path:
    if not re.match(r"[A-Za-z0-9]", name):
        raise ValueError("Report names must start with a letter or digit.")
    safe = re.sub(r"[^A-Za-z0-9_-]+", "_", name).strip("_")
    dest = TEMPLATES_DIR / f"{safe}.html"
    if dest.exists():
        raise FileExistsError(f"{dest} already exists")
    shutil.copyfile(TEMPLATES_DIR / "_skeleton.html", dest)
    return dest


# --------------------------------------------------------------------------- CLI
def main(argv: Iterable[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Build single-file interactive HTML reports.")
    ap.add_argument("name", nargs="?", help="template name in reports/templates (without .html)")
    ap.add_argument("--data", help="path to a JSON file to embed as the report's data")
    ap.add_argument("--title", help="report title (default: derived from the name)")
    ap.add_argument("--out", help=f"output directory (default: {DEFAULT_OUT})")
    ap.add_argument("--list", action="store_true", help="list available report templates")
    ap.add_argument("--new", metavar="NAME", help="create reports/templates/NAME.html from the skeleton")
    ap.add_argument("--allow-external", action="store_true",
                    help="skip the check that the output has no external resources")
    args = ap.parse_args(list(argv) if argv is not None else None)

    if args.list:
        names = list_templates()
        print("\n".join(names) if names else "(no report templates yet; use --new NAME)")
        return 0
    if args.new:
        print(f"created {new_template(args.new)}")
        return 0
    if not args.name:
        ap.error("give a report name, or use --list / --new")

    data = None
    if args.data:
        data = json.loads(Path(args.data).read_text(encoding="utf-8"))
    path = build_report(args.name, data, title=args.title, out_dir=args.out,
                        allow_external=args.allow_external)
    print(f"built {path}  ({path.stat().st_size / 1024:.0f} KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
