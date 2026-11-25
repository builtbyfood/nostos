# Nostos 0.2.3 - onedrive.py
"""OneDrive on Linux, using rclone.

Three things:
  connect()        sign in once through the web browser
  enable_folder()  a "OneDrive" folder in Home that stays connected
                   (systemd user service, starts at login)
  download_all()   optional full copy of everything onto this computer

STATUS: the rclone command lines here follow the rclone documentation,
but the sign-in conversation has NOT been run against a live Microsoft
account from this code yet. See README "Verified / unverified".
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Callable, Optional

from . import places

REMOTE = "onedrive"
UNIT = "nostos-onedrive.service"


def rclone_available() -> bool:
    return shutil.which("rclone") is not None


def is_connected() -> bool:
    if not rclone_available():
        return False
    out = subprocess.run(["rclone", "listremotes"], capture_output=True,
                         text=True).stdout
    return f"{REMOTE}:" in out.split()


def connect() -> tuple[bool, str]:
    """Open the browser for the Microsoft sign-in and save the connection.

    rclone asks a short series of questions ("which kind of OneDrive",
    "which drive"). We accept its suggested answer for each, which is the
    right one for a normal personal or Microsoft 365 account.
    """
    if not rclone_available():
        return False, "rclone is not installed (sudo dnf install rclone)."
    if is_connected():
        return True, "already connected"
    cmd = ["rclone", "config", "create", REMOTE, "onedrive", "--non-interactive"]
    for _ in range(12):
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        if r.returncode != 0:
            _forget()
            return False, (r.stderr.strip().splitlines() or ["rclone failed"])[-1]
        try:
            reply = json.loads(r.stdout)
        except ValueError:
            break
        state = reply.get("State") or ""
        if reply.get("Error"):
            _forget()
            return False, reply["Error"]
        if not state:
            break
        option = reply.get("Option") or {}
        answer = option.get("Default")
        if answer in (None, "") and option.get("Examples"):
            answer = option["Examples"][0].get("Value", "")
        if isinstance(answer, bool):
            answer = "true" if answer else "false"
        cmd = ["rclone", "config", "update", REMOTE, "--non-interactive",
               "--continue", "--state", state, "--result", str(answer or "")]
    if is_connected() and _works():
        return True, "connected"
    _forget()
    return False, "The sign-in did not finish. Please try again."


def _works() -> bool:
    r = subprocess.run(["rclone", "lsf", f"{REMOTE}:", "--max-depth", "1"],
                       capture_output=True, text=True, timeout=120)
    return r.returncode == 0


def _forget() -> None:
    subprocess.run(["rclone", "config", "delete", REMOTE], capture_output=True)


def folder() -> Path:
    return Path.home() / "OneDrive"


def unit_text() -> str:
    rclone = shutil.which("rclone") or "/usr/bin/rclone"
    fuser = shutil.which("fusermount3") or "/usr/bin/fusermount3"
    return f"""# Written by Nostos. Keeps the OneDrive folder in Home connected.
[Unit]
Description=OneDrive folder (Nostos)
After=network-online.target
Wants=network-online.target

[Service]
Type=notify
ExecStartPre=/usr/bin/mkdir -p %h/OneDrive
ExecStart={rclone} mount {REMOTE}: %h/OneDrive --vfs-cache-mode full --vfs-cache-max-size 20G --vfs-cache-max-age 720h --dir-cache-time 5m --poll-interval 1m
ExecStop={fuser} -u %h/OneDrive
Restart=on-failure
RestartSec=30

[Install]
WantedBy=default.target
"""


def enable_folder() -> tuple[bool, str]:
    unit = Path.home() / ".config/systemd/user" / UNIT
    unit.parent.mkdir(parents=True, exist_ok=True)
    unit.write_text(unit_text(), encoding="utf-8")
    subprocess.run(["systemctl", "--user", "daemon-reload"], capture_output=True)
    r = subprocess.run(["systemctl", "--user", "enable", "--now", UNIT],
                       capture_output=True, text=True)
    if r.returncode != 0:
        return False, r.stderr.strip() or "could not start the OneDrive folder"
    places_ok = False
    try:
        places_ok = places.add_place(folder().as_uri(), "OneDrive", "folder-cloud")
    except Exception:
        pass
    return True, "added to Places" if places_ok else "running"


def download_all(dest: Path, progress: Optional[Callable[[int, int, str], None]] = None,
                 cancel=None) -> tuple[bool, str]:
    """Copy everything in OneDrive into ``dest``. Safe to run again."""
    dest.mkdir(parents=True, exist_ok=True)
    cmd = ["rclone", "copy", f"{REMOTE}:", str(dest), "--stats", "1s",
           "--use-json-log", "--log-level", "INFO", "--exclude", "Personal Vault/**"]
    proc = subprocess.Popen(cmd, stderr=subprocess.PIPE, stdout=subprocess.DEVNULL,
                            text=True)
    last_error = ""
    assert proc.stderr is not None
    for line in proc.stderr:
        if cancel is not None and cancel.is_set():
            proc.terminate()
            return False, "stopped"
        try:
            msg = json.loads(line)
        except ValueError:
            continue
        stats = msg.get("stats")
        if stats and progress:
            current = ""
            if stats.get("transferring"):
                current = stats["transferring"][0].get("name", "")
            progress(int(stats.get("bytes", 0)), int(stats.get("totalBytes", 0)),
                     current)
        elif msg.get("level") == "error":
            last_error = msg.get("msg", "")
    code = proc.wait()
    return code == 0, last_error
