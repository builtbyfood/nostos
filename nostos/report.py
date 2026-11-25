# Nostos 0.2.3 - report.py
"""Write a plain-English "what happened" page the user can keep."""
from __future__ import annotations

import html
import time
from pathlib import Path

from . import __version__
from .copier import CopyResult, human
from .profile import xdg_dir

CSS = """body{font-family:sans-serif;max-width:46em;margin:2em auto;padding:0 1em;
line-height:1.5;color:#222}h1{font-size:1.6em}h2{font-size:1.15em;margin-top:1.6em;
border-bottom:1px solid #ccc;padding-bottom:.2em}li{margin:.3em 0}
.small{color:#666;font-size:.9em}code{background:#eee;padding:0 .3em}"""


def write_report(source: str, result: CopyResult | None, done: list[str],
                 todo: list[str], path: Path | None = None) -> Path:
    path = path or xdg_dir("DOCUMENTS", "Documents") / "Moving from Windows - report.html"
    e = html.escape
    out = [f"<!DOCTYPE html><html><head><meta charset='utf-8'>"
           f"<title>Moving from Windows</title><style>{CSS}</style></head><body>",
           "<h1>Moving from Windows: what happened</h1>",
           f"<p class='small'>{time.strftime('%A %d %B %Y, %H:%M')} &middot; "
           f"from {e(source)} &middot; Nostos {__version__}</p>"]
    if result is not None:
        out.append("<h2>Files</h2><ul>")
        if result.cancelled:
            out.append("<li><b>The copy was stopped before it finished.</b> Run "
                       "Nostos again and it carries on where it left off.</li>")
        out.append(f"<li>{result.copied:,} file{'' if result.copied == 1 else 's'} copied "
                   f"({human(result.copied_bytes)}).</li>")
        for label, n in sorted(result.per_job.items()):
            out.append(f"<li class='small'>{e(label)}: {n:,} file{'' if n == 1 else 's'}</li>")
        if result.already_there:
            out.append(f"<li>{result.already_there:,} files were already here "
                       "and were left alone.</li>")
        if result.renamed:
            out.append(f"<li>{len(result.renamed):,} files had the same name as "
                       "a different file already here. Both were kept; the "
                       "Windows one has \"(from Windows)\" in its name.</li>")
        out.append("</ul>")
        if result.errors:
            out.append(f"<h2>Files that could not be copied "
                       f"({len(result.errors):,})</h2><ul>")
            for name, why in result.errors[:300]:
                out.append(f"<li><code>{e(name)}</code>: {e(why)}</li>")
            if len(result.errors) > 300:
                out.append(f"<li>and {len(result.errors) - 300:,} more</li>")
            out.append("</ul>")
        if result.unreadable_folders:
            out.append("<h2>Folders Windows would not open</h2><ul>")
            for name in result.unreadable_folders[:100]:
                out.append(f"<li><code>{e(name)}</code></li>")
            out.append("</ul>")
    if done:
        out.append("<h2>Also done</h2><ul>")
        out += [f"<li>{e(line)}</li>" for line in done]
        out.append("</ul>")
    if todo:
        out.append("<h2>Things left for you to do</h2><ul>")
        out += [f"<li>{e(line)}</li>" for line in todo]
        out.append("</ul>")
    out.append("</body></html>")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(out), encoding="utf-8")
    return path
