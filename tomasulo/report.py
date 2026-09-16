"""Portable offline HTML trace viewer. No server, libraries, or network access."""
import json
from pathlib import Path


def write_html(report: dict, path: Path):
    template = Path(__file__).with_name("viewer.html").read_text()
    payload = json.dumps(report).replace("<", "\\u003c").replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")
    path.write_text(template.replace("__TRACE_DATA__", payload))
