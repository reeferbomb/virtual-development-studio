"""Render a portable production dashboard without scripts or network resources."""

from collections import Counter
from html import escape
from pathlib import Path


STYLE = """
*{box-sizing:border-box}
:root{color-scheme:light;font:16px/1.5 system-ui,sans-serif;color:#202f32;background:#f4f1e9}
body{margin:0}main{max-width:76rem;margin:auto;padding:2rem clamp(1rem,4vw,4rem) 4rem}
header{padding:2rem 0;border-bottom:4px solid #17645b}
h1,h2,h3,p{margin:0}h1,h2{font-family:Georgia,serif;line-height:1.15}
h1{font-size:clamp(2.3rem,6vw,4rem)}h2{font-size:2rem}h3{margin:1.5rem 0 .6rem}
article{margin-top:1.5rem;background:#fffdf8;border:1px solid #cecfc5;border-radius:12px;padding:clamp(1rem,3vw,2rem)}
.project-id,code{font: .83rem ui-monospace,monospace;color:#455e5b}
.project-id{margin-bottom:.4rem}.objective{margin:.7rem 0;max-width:75ch}
.meta,.counts{display:flex;gap:.5rem 1.5rem;flex-wrap:wrap;margin:.75rem 0}
.meta div{min-width:7rem}dt{font-size:.8rem;font-weight:700;color:#4e6260}dd{margin:0}
ul{margin:.5rem 0;padding:0;list-style:none}li{padding:.8rem 0;border-top:1px solid #d8dcd4}
.task-head{display:flex;align-items:baseline;gap:.6rem;flex-wrap:wrap}
.pill{font-size:.8rem;font-weight:700;border-radius:1rem;padding:.12rem .65rem;color:#354441;background:#e9ece7}
.passed{background:#d9eedc;color:#215426}.active{background:#d9eafb;color:#17486e}
.blocked{background:#ffebba;color:#694500}.failed{background:#f8deda;color:#802c27}
.details{display:grid;grid-template-columns:max-content 1fr;gap:.2rem .8rem;margin:.5rem 0 0}
.details dd,.objective,.meta dd,.detail{white-space:pre-line}article,header{overflow-wrap:anywhere}
.empty,.detail{color:#53635e}.detail{margin-top:.25rem}
@media(max-width:35rem){main{padding-top:.5rem}.details{display:block}.details dd{margin:0 0 .4rem}.meta{gap:.5rem}}
@media print{main{max-width:none;padding:0}article{border-radius:0}li{break-inside:avoid}}
"""

STATUSES = ("pending", "active", "blocked", "passed", "failed")


def _text(value):
    if isinstance(value, (list, tuple)):
        return ", ".join(_text(item) for item in value)
    if isinstance(value, dict):
        return ", ".join(f"{_text(key)}: {_text(item)}" for key, item in value.items())
    return escape(str(value), quote=True) if value is not None else ""


def _status(value):
    label = str(value or "unreported")
    style = label if label in STATUSES else ""
    return f'<span class="pill {style}">{_text(label.capitalize())}</span>'


def _task(task):
    details = "".join(
        f"<dt>{label}</dt><dd>{_text(task[key])}</dd>"
        for key, label in (("owner", "Owner"), ("depends_on", "Depends on"),
                           ("acceptance", "Acceptance"), ("evidence", "Evidence"))
        if task.get(key)
    )
    return (
        f'<li><div class="task-head">{_status(task.get("status"))}'
        f'<code>{_text(task.get("id"))}</code><strong>{_text(task.get("title"))}</strong></div>'
        + (f'<dl class="details">{details}</dl>' if details else "") + "</li>"
    )


def _check(check):
    return (
        f'<li><div class="task-head">{_status(check.get("status"))}'
        f'<strong>{_text(check.get("name"))}</strong></div>'
        f'<p class="detail">{_text(check.get("detail"))}</p></li>'
    )


def _items(rows, render, empty):
    return ("<ul>" + "".join(render(row) for row in rows) + "</ul>"
            if rows else f'<p class="empty">{empty}</p>')


def _project(project):
    tasks = project.get("tasks") or []
    counts = Counter(str(task.get("status") or "unreported") for task in tasks)
    summary = " · ".join(f"{count} {_text(status)}" for status, count in counts.items())
    metadata = "".join(
        f"<div><dt>{label}</dt><dd>{_text(project[key])}</dd></div>"
        for key, label in (("source", "Source"), ("platform", "Platform"), ("engine", "Engine"))
        if project.get(key)
    )
    return (
        f'<article><p class="project-id">{_text(project["id"])}</p><h2>{_text(project["name"])}</h2>'
        f'<p class="objective">{_text(project.get("objective"))}</p><dl class="meta">{metadata}</dl>'
        f'<h3>Tasks</h3><p class="counts">{summary}</p>'
        + _items(tasks, _task, "No tasks recorded.")
        + "<h3>Verification checks</h3>"
        + _items(project.get("checks") or [], _check, "No verification checks recorded.")
        + "</article>"
    )


def render_dashboard(projects: list[dict], destination: Path) -> None:
    """Write a UTF-8 HTML snapshot of the supplied project records."""
    body = "".join(_project(project) for project in projects)
    if not body:
        body = '<p class="empty">No projects recorded.</p>'
    page = (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        '<title>Graveforge Studios production dashboard</title><style>' + STYLE
        + '</style></head><body><main><header><h1>Graveforge Studios production dashboard</h1></header>'
        + body + "</main></body></html>"
    )
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(page, encoding="utf-8")
