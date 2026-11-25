# Nostos 0.2.3 - engine.py
"""Ties everything together. No GUI code here, so it can be tested alone."""
from __future__ import annotations

import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

from . import items, onedrive
from . import log_exception
from .agentlink import SubFS
from .copier import CopyJob, CopyResult, copy, free_space, human, scan
from .profile import KNOWN_FOLDERS, WinProfile, find_profiles, xdg_dir
from .report import write_report


@dataclass
class Found:
    """What Nostos found in a Windows profile (shown on the choices page)."""
    bookmarks: list = field(default_factory=list)
    wallpaper: bool = False
    wifi: list = field(default_factory=list)
    shares: list = field(default_factory=list)
    apps: list = field(default_factory=list)          # list[AppMatch] from the table
    guesses: list = field(default_factory=list)       # list[AppMatch] from Flathub search
    unknown_apps: list = field(default_factory=list)
    printers: list = field(default_factory=list)
    steam: list = field(default_factory=list)         # list[SteamLibrary]
    steam_unreachable: list = field(default_factory=list)
    problems: list = field(default_factory=list)      # parts that could not be checked
    has_manifest: bool = False


def look(prof: WinProfile, suggest: bool = True) -> Found:
    """Look at everything on offer. Each part is independent: if one cannot
    be worked out, it is noted in ``problems`` and the rest still shows."""
    found = Found(has_manifest=bool(prof.manifest))

    def part(label: str, fn, default):
        try:
            return fn()
        except Exception as exc:
            log_exception(f"look: {label}")
            found.problems.append(f"{label} ({exc})")
            return default

    apps, unknown = part("programs", lambda: items.detect_apps(prof), ([], []))
    guesses: list = []
    if suggest:
        guesses, unknown = part("app store search",
                                lambda: items.suggest_flatpaks(unknown), ([], unknown))
    steam, steam_unreachable = part("Steam games", lambda: items.detect_steam(prof), ([], []))
    found.apps, found.guesses, found.unknown_apps = apps, guesses, unknown
    found.steam, found.steam_unreachable = steam, steam_unreachable
    found.bookmarks = part("bookmarks", lambda: items.detect_bookmarks(prof), [])
    found.wallpaper = part("wallpaper", lambda: items.detect_wallpaper(prof), False)
    found.wifi = part("Wi-Fi", lambda: items.detect_wifi(prof), [])
    found.shares = part("network drives", lambda: items.detect_shares(prof), [])
    found.printers = part("printers", lambda: items.detect_printers(prof), [])
    return found


def prepare_profiles(fs, profiles: list) -> list:
    """For a share, a drive or a folder: note what else can be browsed."""
    for p in profiles:
        p.browse_fs = fs
        if p.rel.lower().startswith("users/"):      # the source is a whole drive
            p.drive_fs = fs
    return profiles


def profiles_from_agent(fs) -> list:
    """Turn what the Windows app shares into profiles to choose from.

    If only loose folders were shared (no user folder among them), one
    stand-in entry is returned whose ``preselected`` folders are exactly
    the ones the user picked on the Windows PC.
    """
    info = fs.info()
    roots = info.get("roots") or []
    manifest = info.get("manifest") or {}
    user = str(manifest.get("user") or "").lower()
    home = str(manifest.get("profile") or "").replace("/", "\\").rstrip("\\").lower()
    profiles = []
    for root in roots:
        sub = SubFS(fs, root["name"], f"{fs.computer} ({root.get('label') or root['name']})")
        is_drive = len(str(root.get("path", "")).rstrip("\\/")) == 2
        for p in find_profiles(sub):
            if not p.rel:                              # the root itself is a profile
                p.name = str(root.get("label") or p.name)
            p.browse_fs, p.roots = fs, roots
            p.drive_fs = sub if is_drive else None
            profiles.append(p)

    def is_owner(p) -> bool:
        real = str(next((r.get("path", "") for r in roots
                         if r["name"] == p.fs.prefix), "")).rstrip("\\/")
        full = (real + "\\" + p.rel.replace("/", "\\")).rstrip("\\").lower()
        return full == home or p.name.lower() == user

    profiles.sort(key=lambda p: not is_owner(p))
    if profiles:
        owner = profiles[0]
        owner.manifest = manifest          # Wi-Fi, mapped drives: the signed-in user's
        for other in profiles[1:]:
            other.manifest = {k: manifest[k] for k in ("apps", "printers", "steam_path",
                                                        "computer") if k in manifest}
        return profiles
    stand_in = WinProfile(fs, "", fs.computer, manifest=manifest)
    stand_in.browse_fs, stand_in.roots = fs, roots
    stand_in.preselected = [(fs, r["name"]) for r in roots]
    return [stand_in]


@dataclass
class Selection:
    folders: list[str] = field(default_factory=list)        # "Documents", ...
    extra_folders: list[str] = field(default_factory=list)  # other profile folders
    onedrive_local: bool = False      # copy the OneDrive folder from the PC
    picked: list = field(default_factory=list)   # [(source, path)] chosen by browsing
    steam: list = field(default_factory=list)    # SteamLibrary objects to copy
    bookmarks: bool = False
    wallpaper: bool = False
    wifi: bool = False
    shares: list = field(default_factory=list)
    apps: list = field(default_factory=list)                # AppMatch to install
    onedrive_connect: bool = False
    onedrive_download: bool = False


class NotEnoughSpace(Exception):
    def __init__(self, need: int, free: int):
        super().__init__(f"needs {human(need)}, only {human(free)} free")
        self.need, self.free = need, free


def from_windows_dir() -> Path:
    return Path.home() / "From Windows"


def build_jobs(prof: WinProfile, sel: Selection) -> list[CopyJob]:
    jobs = []
    for win in sel.folders:
        key, fallback = KNOWN_FOLDERS[win]
        dest = xdg_dir(key, fallback)
        for src in prof.folders.get(win, []):
            jobs.append(CopyJob(win, prof.fs, src, dest))
    for name in sel.extra_folders:
        jobs.append(CopyJob(name, prof.fs, prof.path(name), from_windows_dir() / name))
    if sel.onedrive_local:
        skip = frozenset(k.lower() for k in KNOWN_FOLDERS)   # copied above
        for od in prof.onedrive_dirs:
            jobs.append(CopyJob(od, prof.fs, prof.path(od),
                                from_windows_dir() / od, exclude=skip))
    used = {j.dest for j in jobs}
    for fs, rel in sel.picked:
        name = rel.strip("/").split("/")[-1] or "Folder"
        dest, n = from_windows_dir() / name, 2
        while dest in used:
            dest = from_windows_dir() / f"{name} {n}"
            n += 1
        used.add(dest)
        jobs.append(CopyJob(dest.name, fs, rel, dest))
    for lib in sel.steam:
        jobs.append(CopyJob("Steam games", lib.fs, lib.rel,
                            items.steam_library_dir() / "steamapps",
                            exclude=items.STEAM_SKIP))
    return jobs


def run(prof: Optional[WinProfile], found: Found, sel: Selection,
        status: Callable[[str], None] = lambda s: None,
        progress: Callable[..., None] = lambda *a: None,
        cancel: Optional[threading.Event] = None,
        report_path: Optional[Path] = None) -> tuple[Path, CopyResult]:
    cancel = cancel or threading.Event()
    result = CopyResult()
    done: list[str] = []
    todo: list[str] = []

    jobs = build_jobs(prof, sel) if prof else []
    if jobs:
        status("Counting your files…")
        plan, total = scan(jobs, result, cancel,
                           tick=lambda n, b: status(f"Counting your files… {n:,} so far"))
        if not cancel.is_set():
            free = min(free_space(j.dest) for j in jobs)
            if total > free - 2 * 1024 ** 3:
                raise NotEnoughSpace(total, free)
            status(f"Copying {len(plan):,} files ({human(total)})")
            copy(plan, total, result, cancel, progress)
    result.cancelled = result.cancelled or cancel.is_set()

    def step(label: str, fn):
        if cancel.is_set():
            return
        status(label)
        try:
            done.extend(fn() or [])
        except Exception as exc:
            todo.append(f"{label.rstrip('…')} did not work: {exc}")

    have = items.flatpak_installed() if sel.apps else set()
    for app in sel.apps:
        if cancel.is_set():
            break
        if app.kind != "flatpak":
            continue
        if app.id in have:
            done.append(f"{app.linux} was already installed.")
            continue
        status(f"Installing {app.linux}…")
        ok, why = items.install_flatpak(app.id)
        if ok:
            done.append(f"Installed {app.linux} (replaces {app.windows}).")
        else:
            todo.append(f"{app.linux} could not be installed automatically. "
                        f"Open your software centre and search for \"{app.linux}\". ({why})")

    if sel.steam and not cancel.is_set():
        todo.extend(items.finish_steam())
    if sel.bookmarks:
        step("Bringing over bookmarks…", lambda: items.apply_bookmarks(found.bookmarks))
    if sel.wallpaper and prof:
        step("Setting your wallpaper…", lambda: items.apply_wallpaper(prof))
    if sel.wifi:
        step("Remembering Wi-Fi networks…", lambda: items.apply_wifi(found.wifi))
    if sel.shares:
        step("Adding network folders…", lambda: items.apply_shares(sel.shares))

    if sel.onedrive_connect and not cancel.is_set():
        status("Connecting OneDrive… (a sign-in page opens in the browser)")
        ok, why = onedrive.connect()
        if ok:
            ok2, why2 = onedrive.enable_folder()
            if ok2:
                done.append("OneDrive is connected. It is the \"OneDrive\" folder "
                            "in Home and in the side panel of your file manager.")
            else:
                todo.append(f"OneDrive signed in, but its folder did not start: {why2}")
            if sel.onedrive_download:
                status("Downloading everything from OneDrive…")
                dest = from_windows_dir() / "OneDrive download"
                ok3, why3 = onedrive.download_all(dest, progress, cancel)
                (done if ok3 else todo).append(
                    f"A full copy of OneDrive is in {items.show(dest)}." if ok3 else
                    f"The OneDrive download did not finish ({why3}). Run Nostos again.")
        else:
            todo.append(f"OneDrive was not connected: {why}")

    # Advice that needs a person.
    chosen = {a.id for a in sel.apps}
    for app in found.apps:
        if app.kind == "web":
            todo.append(f"{app.windows}: use {app.linux} at {app.id}")
        elif app.kind == "none":
            todo.append(f"{app.windows}: {app.note}")
        elif app.kind == "flatpak" and app.note and app.id in chosen:
            todo.append(f"{app.windows} -> {app.linux}: {app.note}")
        elif app.kind == "flatpak" and app.id not in chosen:
            todo.append(f"{app.windows}: not installed this time. The Linux "
                        f"choice is {app.linux}; find it in your software centre.")
    for app in found.guesses:
        if app.id not in chosen:
            todo.append(f"{app.windows}: possibly \"{app.linux}\" in your software "
                        "centre (found by search, not checked).")
    if found.unknown_apps:
        todo.append("Programs from Windows with no Linux match found: "
                    + ", ".join(found.unknown_apps[:80]) + ". Search for the "
                    "name plus \"Linux alternative\", or check whether it has a "
                    "website version.")
    if found.steam_unreachable:
        todo.append("Steam also keeps games in " + ", ".join(found.steam_unreachable)
                    + ", which was not shared with Nostos. Share that drive and "
                    "run again to copy them, or let Steam download them.")
    if found.printers:
        todo.append("Printers used on Windows: " + ", ".join(found.printers) +
                    ". Network printers usually appear by themselves in your "
                    "printer settings.")
    if result.errors or result.unreadable_folders:
        todo.append("Some files could not be copied. They are listed above.")

    status("Writing the report…")
    path = write_report(prof.fs.label if prof else "OneDrive",
                        result if jobs else None, done, todo, report_path)
    return path, result
