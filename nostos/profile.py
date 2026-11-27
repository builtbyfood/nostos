# Nostos 0.2.4 - profile.py
"""Find Windows user profiles in a source and work out where things live."""
from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from .fsaccess import BaseFS, join

MANIFEST = "NostosExport/manifest.json"
SYSTEM_PROFILES = {"public", "default", "default user", "all users",
                   "defaultuser0", "wdagutilityaccount", "nostos"}

# Windows folder -> (xdg-user-dir key, fallback folder name on Linux)
KNOWN_FOLDERS = {
    "Desktop": ("DESKTOP", "Desktop"),
    "Documents": ("DOCUMENTS", "Documents"),
    "Pictures": ("PICTURES", "Pictures"),
    "Music": ("MUSIC", "Music"),
    "Videos": ("VIDEOS", "Videos"),
    "Downloads": ("DOWNLOAD", "Downloads"),
}
# Things in a Windows profile that are never the user's own documents.
PROFILE_NOISE = {
    "appdata", "application data", "cookies", "local settings", "my documents",
    "nethood", "printhood", "recent", "sendto", "start menu", "templates",
    "intelgraphicsprofiles", "microsoftedgebackups", "nostosexport",
    "searches", "links", "contacts", "saved games", "3d objects", "favorites",
    "ansel", "source", "tracing",
}


@dataclass
class WinProfile:
    fs: BaseFS
    rel: str                       # path of the profile inside the source
    name: str
    manifest: dict = field(default_factory=dict)
    # Windows folder name -> list of source paths (plain + OneDrive-redirected)
    folders: dict[str, list[str]] = field(default_factory=dict)
    extra_folders: list[str] = field(default_factory=list)
    onedrive_dirs: list[str] = field(default_factory=list)
    # Set by the window when more than the profile is reachable:
    browse_fs: Optional[BaseFS] = None   # everything the user may pick from
    drive_fs: Optional[BaseFS] = None    # root of the Windows drive (C:)
    roots: list = field(default_factory=list)   # Windows app: shared folders
    preselected: list = field(default_factory=list)  # [(source, path)] ticked at start

    def win_to_rel(self, winpath: str) -> Optional[tuple[BaseFS, str]]:
        """Map r"D:\\SteamLibrary" to (source, path) if that place is reachable."""
        norm = winpath.replace("/", "\\").rstrip("\\").lower()
        best = None
        for root in self.roots:
            base = str(root.get("path", "")).replace("/", "\\").rstrip("\\").lower()
            if base and (norm == base or norm.startswith(base + "\\")) and self.browse_fs:
                if best is None or len(base) > len(best[0]):
                    best = (base, root["name"])
        if best:
            rest = winpath.replace("/", "\\").rstrip("\\")[len(best[0]):]
            return self.browse_fs, join(best[1], rest.replace("\\", "/"))
        if self.drive_fs is not None and len(norm) >= 2 and norm[1] == ":" \
                and norm[0] == "c":
            return self.drive_fs, winpath.replace("\\", "/")[2:].strip("/")
        return None

    def path(self, *parts: str) -> str:
        return join(self.rel, *parts)


def _looks_like_profile(names: set[str]) -> bool:
    return "ntuser.dat" in names or ("appdata" in names and "desktop" in names) \
        or len({"desktop", "documents", "downloads", "pictures"} & names) >= 3


def find_profiles(fs: BaseFS) -> list[WinProfile]:
    """Accept a profile, a Users folder, or a whole Windows drive."""
    def names(rel):
        try:
            return {e.name.lower(): e for e in fs.listdir(rel)}
        except Exception:
            return {}

    root = names("")
    if _looks_like_profile(set(root)):
        return [load_profile(fs, "", Path(fs.label).name or "Windows user")]
    found = []
    for base in ("", "Users"):
        listing = root if base == "" else names(base)
        if base == "Users" and "users" not in root:
            continue
        for low, e in sorted(listing.items()):
            if not e.is_dir or low in SYSTEM_PROFILES:
                continue
            rel = join(base, e.name)
            if _looks_like_profile(set(names(rel))):
                found.append(load_profile(fs, rel, e.name))
        if found:
            break
    return found


def load_profile(fs: BaseFS, rel: str, name: str) -> WinProfile:
    prof = WinProfile(fs, rel, name)
    try:
        top = fs.listdir(rel)
    except Exception:
        top = []
    dirs = {e.name.lower(): e.name for e in top if e.is_dir}

    for d in dirs.values():
        if d.lower().startswith("onedrive"):
            prof.onedrive_dirs.append(d)

    for win in KNOWN_FOLDERS:
        sources = []
        if win.lower() in dirs:
            sources.append(prof.path(dirs[win.lower()]))
        for od in prof.onedrive_dirs:   # OneDrive "folder backup" moves these
            try:
                sub = {e.name.lower(): e.name for e in fs.listdir(prof.path(od))
                       if e.is_dir}
            except Exception:
                sub = {}
            if win.lower() in sub:
                sources.append(prof.path(od, sub[win.lower()]))
        if sources:
            prof.folders[win] = sources

    known = {k.lower() for k in KNOWN_FOLDERS}
    for low, real in sorted(dirs.items()):
        if low in known or low in PROFILE_NOISE or low.startswith((".", "onedrive")):
            continue
        prof.extra_folders.append(real)

    try:
        raw = fs.read_bytes(prof.path(MANIFEST), 8 * 1024 * 1024)
        prof.manifest = json.loads(raw.decode("utf-8-sig"))
    except Exception:
        prof.manifest = {}
    return prof


def xdg_dir(key: str, fallback: str) -> Path:
    """Where this Linux desktop keeps Documents, Pictures and so on."""
    home = Path.home()
    if shutil.which("xdg-user-dir"):
        try:
            out = subprocess.run(["xdg-user-dir", key], capture_output=True,
                                 text=True, timeout=5).stdout.strip()
            if out and Path(out) != home:
                return Path(out)
        except Exception:
            pass
    return home / fallback
