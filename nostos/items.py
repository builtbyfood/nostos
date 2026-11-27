# Nostos 0.2.4 - items.py
"""Everything that is not a plain folder copy: bookmarks, wallpaper,
Wi-Fi, network drives, programs, printers.

Each ``detect_*`` only reads from the Windows profile. Each ``apply_*``
changes this computer and returns a list of plain-English lines for the
report.
"""
from __future__ import annotations

import html
import json
import os
import re
import shutil
import sqlite3
import subprocess
import tempfile
from concurrent.futures.thread import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path

from . import places
from .appmap import AppMatch, match_apps
from .profile import WinProfile, xdg_dir

# --------------------------------------------------------------- bookmarks --
CHROMIUM = {
    # name: (path in Windows profile, config dir on Linux, flatpak config dir)
    "Google Chrome": ("AppData/Local/Google/Chrome/User Data",
                      ".config/google-chrome",
                      ".var/app/com.google.Chrome/config/google-chrome"),
    "Microsoft Edge": ("AppData/Local/Microsoft/Edge/User Data",
                       ".config/microsoft-edge",
                       ".var/app/com.microsoft.Edge/config/microsoft-edge"),
    "Brave": ("AppData/Local/BraveSoftware/Brave-Browser/User Data",
              ".config/BraveSoftware/Brave-Browser",
              ".var/app/com.brave.Browser/config/BraveSoftware/Brave-Browser"),
}
# How to tell the browser is really installed here: (commands, flatpak id)
CHROMIUM_INSTALLED = {
    "Google Chrome": (("google-chrome", "google-chrome-stable"), "com.google.Chrome"),
    "Microsoft Edge": (("microsoft-edge", "microsoft-edge-stable"), "com.microsoft.Edge"),
    "Brave": (("brave-browser", "brave"), "com.brave.Browser"),
}


def show(path) -> str:
    """A path the way a person would say it: inside Home, without the prefix."""
    try:
        rel = Path(path).resolve().relative_to(Path.home().resolve())
        return f"\"{rel}\" in your Home folder"
    except ValueError:
        return f"\"{path}\""
FIREFOX = "AppData/Roaming/Mozilla/Firefox/Profiles"


@dataclass
class BookmarkSet:
    browser: str
    profile: str                    # "Default", "Profile 1", firefox profile dir
    count: int
    tree: list = field(default_factory=list)   # [("folder", title, [..]) | ("url", title, url)]
    raw: bytes = b""                # Chromium "Bookmarks" file as found


def _chromium_tree(node: dict) -> list:
    out = []
    for child in node.get("children", []):
        if child.get("type") == "folder":
            out.append(("folder", child.get("name", ""), _chromium_tree(child)))
        elif child.get("url"):
            out.append(("url", child.get("name") or child["url"], child["url"]))
    return out


def _count(tree: list) -> int:
    return sum(_count(n[2]) if n[0] == "folder" else 1 for n in tree)


def detect_bookmarks(prof: WinProfile) -> list[BookmarkSet]:
    fs, found = prof.fs, []
    for browser, (winpath, _, _) in CHROMIUM.items():
        base = prof.path(winpath)
        try:
            subs = [e.name for e in fs.listdir(base) if e.is_dir and
                    (e.name == "Default" or e.name.startswith("Profile "))]
        except Exception:
            continue
        for sub in sorted(subs):
            try:
                raw = fs.read_bytes(f"{base}/{sub}/Bookmarks")
                roots = json.loads(raw.decode("utf-8"))["roots"]
            except Exception:
                continue
            tree = []
            for key, title in (("bookmark_bar", "Bookmarks bar"),
                               ("other", "Other bookmarks"),
                               ("synced", "Mobile bookmarks")):
                kids = _chromium_tree(roots.get(key, {}))
                if kids:
                    tree.append(("folder", title, kids))
            if _count(tree):
                found.append(BookmarkSet(browser, sub, _count(tree), tree, raw))
    try:
        ff_profiles = [e.name for e in fs.listdir(prof.path(FIREFOX)) if e.is_dir]
    except Exception:
        ff_profiles = []
    for sub in sorted(ff_profiles):
        tree = _firefox_tree(prof, f"{prof.path(FIREFOX)}/{sub}")
        if _count(tree):
            found.append(BookmarkSet("Firefox", sub, _count(tree), tree))
    return found


def _firefox_tree(prof: WinProfile, base: str) -> list:
    """Read bookmarks from a copy of places.sqlite (never the original)."""
    with tempfile.TemporaryDirectory(prefix="nostos-ff-") as tmp:
        try:
            for name in ("places.sqlite", "places.sqlite-wal"):
                try:
                    Path(tmp, name).write_bytes(
                        prof.fs.read_bytes(f"{base}/{name}", 512 * 1024 * 1024))
                except Exception:
                    if name == "places.sqlite":
                        return []
            db = sqlite3.connect(str(Path(tmp, "places.sqlite")))
            rows = db.execute(
                "SELECT b.id, b.parent, b.type, b.title, p.url, b.position "
                "FROM moz_bookmarks b LEFT JOIN moz_places p ON p.id = b.fk "
                "ORDER BY b.parent, b.position").fetchall()
            db.close()
        except Exception:
            return []
    kids: dict[int, list] = {}
    for row in rows:
        kids.setdefault(row[1], []).append(row)
    names = {2: "Bookmarks menu", 3: "Bookmarks toolbar", 5: "Other bookmarks"}

    def build(parent: int, depth: int = 0) -> list:
        out = []
        for bid, _, btype, title, url, _ in kids.get(parent, []):
            if btype == 2 and depth < 40:
                sub = build(bid, depth + 1)
                if sub:
                    out.append(("folder", names.get(bid) if parent == 1 and not title
                                else (title or names.get(bid, "Folder")), sub))
            elif btype == 1 and url and not url.startswith("place:"):
                out.append(("url", title or url, url))
        return out

    return build(1)


def bookmarks_html(sets: list[BookmarkSet]) -> str:
    """Standard bookmark file that every browser can import."""
    lines = ["<!DOCTYPE NETSCAPE-Bookmark-file-1>",
             '<META HTTP-EQUIV="Content-Type" CONTENT="text/html; charset=UTF-8">',
             "<TITLE>Bookmarks</TITLE>", "<H1>Bookmarks from Windows</H1>", "<DL><p>"]

    def emit(tree, indent):
        pad = "    " * indent
        for node in tree:
            if node[0] == "folder":
                lines.append(f"{pad}<DT><H3>{html.escape(node[1])}</H3>")
                lines.append(f"{pad}<DL><p>")
                emit(node[2], indent + 1)
                lines.append(f"{pad}</DL><p>")
            else:
                lines.append(f'{pad}<DT><A HREF="{html.escape(node[2], quote=True)}">'
                             f"{html.escape(node[1])}</A>")

    for s in sets:
        title = s.browser if s.profile in ("Default",) or s.browser == "Firefox" \
            else f"{s.browser} ({s.profile})"
        emit([("folder", f"From {title}", s.tree)], 1)
    lines.append("</DL><p>")
    return "\n".join(lines) + "\n"


def _running(process: str) -> bool:
    return subprocess.run(["pgrep", "-f", process], capture_output=True).returncode == 0 \
        if shutil.which("pgrep") else False


def apply_bookmarks(sets: list[BookmarkSet]) -> list[str]:
    if not sets:
        return []
    notes = []
    docs = xdg_dir("DOCUMENTS", "Documents")
    docs.mkdir(parents=True, exist_ok=True)
    out = docs / "Bookmarks from Windows.html"
    out.write_text(bookmarks_html(sets), encoding="utf-8")
    total = sum(s.count for s in sets)
    notes.append(f"Saved {total} bookmarks to {show(out)}. In any browser, open "
                 "Bookmarks > Import > \"from HTML file\" and pick that file.")
    flatpaks = flatpak_installed()
    # Same browser on both sides and no bookmarks here yet: put them straight in.
    for s in sets:
        if s.browser not in CHROMIUM or s.profile != "Default" or not s.raw:
            continue
        _, native, flatpak = CHROMIUM[s.browser]
        commands, flatpak_id = CHROMIUM_INSTALLED[s.browser]
        places_to_try = []
        if (Path.home() / native).exists() or any(shutil.which(c) for c in commands):
            places_to_try.append(Path.home() / native)
        if flatpak_id in flatpaks:
            places_to_try.append(Path.home() / flatpak)
        for cfg in places_to_try:           # only where the browser is installed
            target = cfg / "Default" / "Bookmarks"
            if target.exists() or _running(cfg.name):
                continue
            try:
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(s.raw)
                notes.append(f"{s.browser} on this computer had no bookmarks yet, "
                             f"so the Windows ones were put straight in.")
                break
            except OSError:
                pass
    notes.append("Saved passwords cannot be copied (Windows locks them to the "
                 "Windows PC). Sign in to the browser's own sync, or export "
                 "passwords from the old browser's settings and import them here.")
    return notes


# --------------------------------------------------------------- wallpaper --
WALLPAPER = "AppData/Roaming/Microsoft/Windows/Themes/TranscodedWallpaper"


def detect_wallpaper(prof: WinProfile) -> bool:
    return prof.fs.exists(prof.path(WALLPAPER))


def apply_wallpaper(prof: WinProfile) -> list[str]:
    try:
        data = prof.fs.read_bytes(prof.path(WALLPAPER))
    except Exception as exc:
        return [f"The wallpaper could not be read ({exc})."]
    ext = ".png" if data[:4] == b"\x89PNG" else ".jpg"
    pics = xdg_dir("PICTURES", "Pictures")
    pics.mkdir(parents=True, exist_ok=True)
    out = pics / f"Windows wallpaper{ext}"
    out.write_bytes(data)
    if set_wallpaper(out):
        return [f"Your Windows wallpaper is now the desktop background "
                f"(saved as {show(out)})."]
    return [f"Your Windows wallpaper was saved as {show(out)}. Right-click the "
            "desktop to set it as the background."]


def desktop() -> str:
    """kde, gnome, cinnamon, mate, xfce or '' (unknown)."""
    cur = os.environ.get("XDG_CURRENT_DESKTOP", "").lower()
    for name in ("kde", "cinnamon", "mate", "xfce", "gnome", "unity", "budgie"):
        if name in cur:
            return "gnome" if name in ("unity", "budgie") else name
    return ""


def set_wallpaper(path: Path) -> bool:
    uri = path.as_uri()
    desk = desktop()
    commands = []
    if desk == "kde" or shutil.which("plasma-apply-wallpaperimage"):
        commands.append(["plasma-apply-wallpaperimage", str(path)])
    if desk == "gnome":
        commands.append(["gsettings", "set", "org.gnome.desktop.background", "picture-uri", uri])
        commands.append(["gsettings", "set", "org.gnome.desktop.background", "picture-uri-dark", uri])
    elif desk == "cinnamon":
        commands.append(["gsettings", "set", "org.cinnamon.desktop.background", "picture-uri", uri])
    elif desk == "mate":
        commands.append(["gsettings", "set", "org.mate.background", "picture-filename", str(path)])
    ok = False
    for cmd in commands:
        if shutil.which(cmd[0]):
            ok = subprocess.run(cmd, capture_output=True).returncode == 0 or ok
    return ok


# -------------------------------------------------------------------- Wi-Fi --
def detect_wifi(prof: WinProfile) -> list[dict]:
    return [w for w in prof.manifest.get("wifi", []) if w.get("ssid")]


def apply_wifi(networks: list[dict]) -> list[str]:
    """Add the Windows PC's saved Wi-Fi networks to NetworkManager.

    Networks with a password join by themselves, as they did on Windows.
    Open networks (cafes, hotels) are remembered but NOT joined automatically:
    anyone can put up a network with the same name.
    """
    if not networks:
        return []
    if not shutil.which("nmcli"):
        return ["Wi-Fi networks were found but NetworkManager is not available."]
    existing = subprocess.run(["nmcli", "-t", "-f", "NAME", "connection", "show"],
                              capture_output=True, text=True).stdout.splitlines()
    added, open_added, skipped, failed = [], [], [], []
    for net in networks:
        ssid, key = net["ssid"], net.get("key") or ""
        auth = (net.get("auth") or "").upper()
        if ssid in existing:
            skipped.append(ssid)
            continue
        cmd = ["nmcli", "connection", "add", "type", "wifi", "con-name", ssid,
               "ssid", ssid]
        if key and "WPA3" in auth:
            cmd += ["connection.autoconnect", "yes",
                    "wifi-sec.key-mgmt", "sae", "wifi-sec.psk", key]
        elif key:
            cmd += ["connection.autoconnect", "yes",
                    "wifi-sec.key-mgmt", "wpa-psk", "wifi-sec.psk", key]
        elif auth in ("", "OPEN"):
            cmd += ["connection.autoconnect", "no"]
        else:
            failed.append(ssid)   # work/school networks need a sign-in instead
            continue
        ok = subprocess.run(cmd, capture_output=True).returncode == 0
        (failed if not ok else added if key else open_added).append(ssid)
    notes = []
    if added:
        notes.append("Wi-Fi networks remembered: " + ", ".join(added) + ".")
    if open_added:
        notes.append("Open Wi-Fi networks (no password) remembered, but this "
                     "computer will not join them by itself; pick them from the "
                     "Wi-Fi list when you want them: " + ", ".join(open_added) + ".")
    if skipped:
        notes.append("Wi-Fi already known here: " + ", ".join(skipped) + ".")
    if failed:
        notes.append("Wi-Fi networks to join by hand (they need a sign-in): "
                     + ", ".join(failed) + ".")
    return notes


# ----------------------------------------------------------- network drives --
def detect_shares(prof: WinProfile) -> list[dict]:
    """Mapped drives from Windows: [{"letter": "Z:", "path": r"\\\\nas\\share"}]"""
    out = []
    for d in prof.manifest.get("mapped_drives", []):
        path = (d.get("path") or "").replace("/", "\\")
        parts = [p for p in path.split("\\") if p]
        if len(parts) >= 2:
            out.append({"letter": d.get("letter", ""), "server": parts[0],
                        "share": "/".join(parts[1:]),
                        "url": "smb://" + "/".join(parts)})
    return out


def apply_shares(shares: list[dict]) -> list[str]:
    done = []
    for s in shares:
        label = f"{s['share'].split('/')[-1]} on {s['server']}"
        if places.add_place(s["url"], label):
            done.append(label)
    if done:
        return ["Network folders added to the side panel of your file manager: "
                + ", ".join(done) + ". The first time you open one it asks "
                "for the name and password and can remember them."]
    return []


# ----------------------------------------------------------------- programs --
START_MENU = "AppData/Roaming/Microsoft/Windows/Start Menu/Programs"


def detect_apps(prof: WinProfile) -> tuple[list[AppMatch], list[str]]:
    names = list(prof.manifest.get("apps", []))
    if not names:   # no helper manifest: read the Start menu shortcuts instead
        try:
            for path, e in prof.fs.walk(prof.path(START_MENU)):
                if e.name.lower().endswith(".lnk"):
                    names.append(e.name[:-4])
        except Exception:
            pass
    for browser, (winpath, _, _) in CHROMIUM.items():
        if prof.fs.exists(prof.path(winpath)):
            names.append(browser)
    return match_apps(names)


_NOISE = re.compile(
    r"\(.*?\)|\b(x64|x86|64-bit|32-bit|version|edition|for windows|desktop|app|"
    r"launcher|client|setup|pro|free|inc|llc|ltd)\b|v?\d+(\.\d+)+|\b\d{4}\b", re.I)


def search_term(windows_name: str) -> str:
    """'Family Tree Maker 2019 (x64)' -> 'Family Tree Maker'."""
    return " ".join(_NOISE.sub(" ", windows_name).replace("-", " ").split())


def suggest_flatpaks(unknown: list[str], limit: int = 30) -> tuple[list[AppMatch], list[str]]:
    """Ask Flathub about programs the built-in table does not know.

    Returns (guesses, names still unknown). A guess is only kept when the
    app found shares its first real word with the Windows name, and it is
    never ticked by default: the user decides.
    """
    if not shutil.which("flatpak") or not unknown:
        return [], unknown
    def look_up(name: str):
        term = search_term(name)
        words = [w for w in re.findall(r"[a-z0-9]+", term.lower()) if len(w) >= 4]
        if not words:
            return None
        try:
            out = subprocess.run(
                ["flatpak", "search", "--columns=application,name", term],
                capture_output=True, text=True, timeout=15).stdout
        except Exception:
            return None
        wanted = re.findall(r"[a-z0-9]+", term.lower())
        for line in out.splitlines():
            parts = line.split("\t")
            if len(parts) < 2 or "." not in parts[0]:
                continue
            app_id, title = parts[0].strip(), parts[1].strip()
            have = re.findall(r"[a-z0-9]+", title.lower())
            # A one-word name ("Money", "News") matches far too much, so it
            # must BE the title. Longer names must have every word present.
            good = have == wanted if len(wanted) == 1 else all(w in have for w in wanted)
            if good:
                return AppMatch(name, title, "flatpak", app_id,
                                "Found by searching Flathub. Check it is the "
                                "program you mean.", guess=True)
        return None

    todo = unknown[:limit]
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(look_up, todo))
    guesses, seen, still = [], set(), list(unknown[limit:])
    for name, match in zip(todo, results):
        if match and match.id not in seen:
            seen.add(match.id)
            guesses.append(match)
        elif not match:
            still.append(name)
    return guesses, still


def flatpak_installed() -> set[str]:
    if not shutil.which("flatpak"):
        return set()
    out = subprocess.run(["flatpak", "list", "--app", "--columns=application"],
                         capture_output=True, text=True).stdout
    return set(out.split())


def install_flatpak(app_id: str) -> tuple[bool, str]:
    if not shutil.which("flatpak"):
        return False, "Flatpak is not installed"
    subprocess.run(["flatpak", "remote-add", "--user", "--if-not-exists", "flathub",
                    "https://dl.flathub.org/repo/flathub.flatpakrepo"],
                   capture_output=True)
    r = subprocess.run(["flatpak", "install", "--user", "-y", "--noninteractive",
                        "flathub", app_id], capture_output=True, text=True)
    lines = (r.stderr or r.stdout).strip().splitlines()
    return r.returncode == 0, lines[-1] if lines else ""


def detect_printers(prof: WinProfile) -> list[str]:
    skip = ("microsoft", "onenote", "fax", "pdf", "xps")
    return [p for p in prof.manifest.get("printers", [])
            if p and not any(s in p.lower() for s in skip)]


# -------------------------------------------------------------------- Steam --
@dataclass
class SteamLibrary:
    fs: object                 # where it can be read from
    rel: str                   # path of the "steamapps" folder in that source
    where: str                 # shown to the user: r"D:\SteamLibrary"
    games: list = field(default_factory=list)     # [(name, bytes)]

    @property
    def size(self) -> int:
        return sum(size for _, size in self.games)


_VDF_PATH = re.compile(r'"path"\s+"([^"]+)"', re.I)
_VDF_KEY = r'"%s"\s+"([^"]*)"'
STEAM_SKIP = frozenset({"downloading", "temp", "shadercache"})


def detect_steam(prof: WinProfile) -> tuple[list[SteamLibrary], list[str]]:
    """Find Steam game libraries. Returns (reachable libraries, places that
    exist on the PC but were not shared with Nostos)."""
    candidates: list[str] = []
    steam = str(prof.manifest.get("steam_path") or "")
    if steam:
        candidates.append(steam)
    candidates += [r"C:\Program Files (x86)\Steam", r"C:\Program Files\Steam"]

    main = None
    for path in candidates:
        loc = prof.win_to_rel(path)
        if loc and loc[0].exists(f"{loc[1]}/steamapps".strip("/")):
            main = (path, loc)
            break
    if main is None:
        return [], []
    paths = [main[0]]
    try:
        vdf = main[1][0].read_bytes(f"{main[1][1]}/steamapps/libraryfolders.vdf".strip("/"),
                                    1024 * 1024).decode("utf-8", "replace")
        for found in _VDF_PATH.findall(vdf):
            found = found.replace("\\\\", "\\")
            if found.lower().rstrip("\\") not in [p.lower().rstrip("\\") for p in paths]:
                paths.append(found)
    except Exception:
        pass

    libraries, unreachable = [], []
    for path in paths:
        loc = prof.win_to_rel(path)
        if not loc:
            unreachable.append(path)
            continue
        fs, rel = loc[0], f"{loc[1]}/steamapps".strip("/")
        try:
            names = [e.name for e in fs.listdir(rel)
                     if not e.is_dir and e.name.lower().startswith("appmanifest_")]
        except Exception:
            unreachable.append(path)
            continue
        lib = SteamLibrary(fs, rel, path)
        for name in names:
            try:
                acf = fs.read_bytes(f"{rel}/{name}", 256 * 1024).decode("utf-8", "replace")
            except Exception:
                continue
            title = re.search(_VDF_KEY % "name", acf)
            size = re.search(_VDF_KEY % "SizeOnDisk", acf)
            if title:
                lib.games.append((title.group(1), int(size.group(1)) if size and
                                  size.group(1).isdigit() else 0))
        if lib.games:
            lib.games.sort(key=lambda g: -g[1])
            libraries.append(lib)
    return libraries, unreachable


def steam_library_dir() -> Path:
    return Path.home() / "SteamLibrary-Windows"


def finish_steam() -> list[str]:
    """After copying: let a Flatpak Steam see the folder, and say what to do."""
    target = steam_library_dir()
    if shutil.which("flatpak"):
        subprocess.run(["flatpak", "override", "--user", f"--filesystem={target}",
                        "com.valvesoftware.Steam"], capture_output=True)
    return [f"Your Steam games were copied to {show(target)}. To use them: open "
            "Steam, sign in, go to Settings > Storage, add that folder, then "
            "in Settings > Compatibility turn on Steam Play for all titles. "
            "Steam checks each game and downloads only what is missing. Games "
            "that need Windows-only anti-cheat will not run."]
