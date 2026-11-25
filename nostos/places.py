# Nostos 0.2.3 - places.py
"""Add network folders to the file manager sidebar.

KDE (Dolphin) and GTK desktops (GNOME Files, Nemo, Thunar, Caja) keep their
sidebar entries in different files; Nostos writes whichever this desktop uses.

KDE keeps Places in ~/.local/share/user-places.xbel. We add one small
<bookmark> element and leave the rest of the file exactly as it was. A
backup copy is made the first time.
"""
from __future__ import annotations

import os
import shutil
import time
from pathlib import Path
from xml.sax.saxutils import escape, quoteattr

NEW_FILE = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE xbel>
<xbel xmlns:bookmark="http://www.freedesktop.org/standards/desktop-bookmarks" xmlns:kdepriv="http://www.kde.org/kdepriv" xmlns:mime="http://www.freedesktop.org/standards/shared-mime-info">
</xbel>
"""


def places_file() -> Path:
    return Path.home() / ".local/share/user-places.xbel"


def gtk_bookmarks_file() -> Path:
    return Path.home() / ".config/gtk-3.0/bookmarks"


def add_gtk_bookmark(url: str, label: str) -> bool:
    """Sidebar bookmark for GTK file managers (Files, Nemo, Thunar, Caja)."""
    path = gtk_bookmarks_file()
    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    target = url.replace(" ", "%20")
    if any(line.split(" ", 1)[0] == target for line in lines):
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    lines.append(f"{target} {label}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return True


def add_place(url: str, label: str, icon: str = "folder-remote") -> bool:
    """Add to every file manager sidebar this desktop uses.
    Returns True if it was added anywhere, False if it was already there."""
    kde = _is_kde() or places_file().exists()
    added = False
    if kde:
        added = _add_kde_place(url, label, icon)
    if not kde or gtk_bookmarks_file().exists():
        added = add_gtk_bookmark(url, label) or added
    return added


def _is_kde() -> bool:
    return "kde" in os.environ.get("XDG_CURRENT_DESKTOP", "").lower()


def _add_kde_place(url: str, label: str, icon: str = "folder-remote") -> bool:
    path = places_file()
    text = path.read_text(encoding="utf-8") if path.exists() else NEW_FILE
    if f"href={quoteattr(url)}" in text:
        return False
    end = text.rfind("</xbel>")
    if end < 0:
        return False
    if 'xmlns:bookmark=' not in text:
        return False
    if path.exists():
        backup = path.with_name(path.name + ".before-nostos")
        if not backup.exists():
            shutil.copy2(path, backup)
    ident = f"{int(time.time())}/nostos-{abs(hash(url)) % 100000}"
    block = (
        f" <bookmark href={quoteattr(url)}>\n"
        f"  <title>{escape(label)}</title>\n"
        f"  <info>\n"
        f'   <metadata owner="http://freedesktop.org">\n'
        f"    <bookmark:icon name={quoteattr(icon)}/>\n"
        f"   </metadata>\n"
        f'   <metadata owner="http://www.kde.org">\n'
        f"    <ID>{ident}</ID>\n"
        f"   </metadata>\n"
        f"  </info>\n"
        f" </bookmark>\n")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text[:end] + block + text[end:], encoding="utf-8")
    return True
