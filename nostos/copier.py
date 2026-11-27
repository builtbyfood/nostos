# Nostos 0.2.4 - copier.py
"""Copy engine: count first, then copy; safe to stop and run again.

Rules that keep it safe for a beginner:
  * Nothing on the Windows side is ever changed (sources are read-only).
  * Nothing on the Linux side is ever overwritten. A file that is already
    there and identical is skipped; a different file with the same name is
    kept, and the Windows one lands next to it as "name (from Windows).ext".
  * Files are written to a ".nostos-part" name and renamed when complete, so
    a cancelled run never leaves a half-written file behind under its real name.
"""
from __future__ import annotations

import os
import shutil
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

from .fsaccess import BaseFS, Entry

CHUNK = 4 * 1024 * 1024
PART = ".nostos-part"
JUNK_NAMES = {"desktop.ini", "thumbs.db", "ntuser.dat", "ehthumbs.db",
              ".ds_store", "iconcache.db"}
JUNK_DIRS = {"$recycle.bin", "system volume information", "nostosexport"}
JUNK_SUFFIXES = (".lnk", ".tmp", PART)


def is_junk(path: str, e: Entry) -> bool:
    low = e.name.lower()
    if e.is_dir:
        return low in JUNK_DIRS
    return (low in JUNK_NAMES or low.endswith(JUNK_SUFFIXES)
            or low.startswith(("~$", "ntuser.")))


@dataclass
class CopyJob:
    label: str          # shown to the user: "Documents"
    fs: BaseFS
    src: str            # folder inside the source
    dest: Path          # folder on this computer
    exclude: frozenset = frozenset()   # top-level folder names to leave out


@dataclass
class PlannedFile:
    job: CopyJob
    rel: str            # path below job.src
    size: int
    mtime: float


@dataclass
class CopyResult:
    copied: int = 0
    copied_bytes: int = 0
    already_there: int = 0
    renamed: list[str] = field(default_factory=list)
    errors: list[tuple[str, str]] = field(default_factory=list)
    unreadable_folders: list[str] = field(default_factory=list)
    cancelled: bool = False
    per_job: dict[str, int] = field(default_factory=dict)


def scan(jobs: list[CopyJob], result: CopyResult,
         cancel: Optional[threading.Event] = None,
         tick: Optional[Callable[[int, int], None]] = None
         ) -> tuple[list[PlannedFile], int]:
    """Count every file to copy. Returns (plan, total bytes)."""
    plan: list[PlannedFile] = []
    total = 0
    for job in jobs:
        base = job.src.strip("/")
        cut = len(base) + 1 if base else 0

        def on_error(path, exc, _job=job):
            result.unreadable_folders.append(f"{_job.label}: {path}")

        def skip(path, e, _job=job, _cut=cut):
            if is_junk(path, e):
                return True
            return e.is_dir and path[_cut:].lower() in _job.exclude

        for path, e in job.fs.walk(base, skip=skip, on_error=on_error):
            if cancel is not None and cancel.is_set():
                return plan, total
            plan.append(PlannedFile(job, path[cut:], e.size, e.mtime))
            total += e.size
            if tick and len(plan) % 200 == 0:
                tick(len(plan), total)
    if tick:
        tick(len(plan), total)
    return plan, total


def free_space(path: Path) -> int:
    probe = path
    while not probe.exists() and probe != probe.parent:
        probe = probe.parent
    return shutil.disk_usage(probe).free


def _same(dest: Path, size: int, mtime: float) -> bool:
    try:
        st = dest.stat()
    except OSError:
        return False
    return st.st_size == size and abs(st.st_mtime - mtime) <= 2.0


def _alternative(dest: Path) -> Path:
    stem, suffix = dest.stem, dest.suffix
    cand = dest.with_name(f"{stem} (from Windows){suffix}")
    n = 2
    while cand.exists():
        cand = dest.with_name(f"{stem} (from Windows {n}){suffix}")
        n += 1
    return cand


def copy(plan: list[PlannedFile], total: int, result: CopyResult,
         cancel: Optional[threading.Event] = None,
         progress: Optional[Callable[[int, int, str], None]] = None) -> CopyResult:
    """Copy the plan.

    ``progress(done_bytes, total_bytes, current_file, skipped_bytes)``:
    ``skipped_bytes`` is the part of ``done_bytes`` that was already on this
    computer and was not sent again, so the caller can show a true speed.
    """
    done = 0
    skipped = 0
    last = 0.0

    def report(name: str, force: bool = False):
        nonlocal last
        now = time.monotonic()
        if progress and (force or now - last > 0.1):
            last = now
            progress(done, total, name, skipped)

    for pf in plan:
        if cancel is not None and cancel.is_set():
            result.cancelled = True
            break
        dest = pf.job.dest / pf.rel
        shown = f"{pf.job.label}/{pf.rel}"
        report(shown)
        try:
            if _same(dest, pf.size, pf.mtime):
                result.already_there += 1
                done += pf.size
                skipped += pf.size
                continue
            target = dest
            if dest.exists():
                alt = dest.with_name(f"{dest.stem} (from Windows){dest.suffix}")
                if _same(alt, pf.size, pf.mtime):   # copied on an earlier run
                    result.already_there += 1
                    done += pf.size
                    skipped += pf.size
                    continue
                target = _alternative(dest)
                result.renamed.append(str(target))
            target.parent.mkdir(parents=True, exist_ok=True)
            part = target.with_name(target.name + PART)
            start = done
            try:
                with pf.job.fs.open(f"{pf.job.src.strip('/')}/{pf.rel}".strip("/")) as src, \
                        open(part, "wb") as out:
                    while True:
                        if cancel is not None and cancel.is_set():
                            raise InterruptedError
                        buf = src.read(CHUNK)
                        if not buf:
                            break
                        out.write(buf)
                        done += len(buf)
                        report(shown)
                if pf.mtime:
                    os.utime(part, (pf.mtime, pf.mtime))
                os.replace(part, target)
            except BaseException:
                done = start + pf.size
                try:
                    part.unlink()
                except OSError:
                    pass
                raise
            done = start + pf.size
            result.copied += 1
            result.copied_bytes += pf.size
            result.per_job[pf.job.label] = result.per_job.get(pf.job.label, 0) + 1
        except InterruptedError:
            result.cancelled = True
            break
        except Exception as exc:
            result.errors.append((shown, _why(exc)))
    report("", force=True)
    return result


def _why(exc: Exception) -> str:
    text = str(exc).lower()
    if "sharing" in text or "being used" in text or "lock" in text:
        return "in use on the Windows PC (close the program using it and run again)"
    if "access" in text and "denied" in text:
        return "Windows would not allow it to be read"
    if "cloud" in text or "offline" in text or "0x8007016a" in text:
        return "stored only in OneDrive, not on the Windows PC"
    if isinstance(exc, OSError) and exc.errno == 28:
        return "this computer is out of space"
    return str(exc) or type(exc).__name__


def human(n: float) -> str:
    for unit in ("bytes", "KB", "MB", "GB", "TB"):
        if n < 1024 or unit == "TB":
            return f"{n:.0f} {unit}" if unit in ("bytes", "KB") else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"
