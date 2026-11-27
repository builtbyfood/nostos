# Nostos 0.2.4 - tools/make_screenshots.py
"""Regenerate every screenshot used in the documentation.

    python3 tools/make_screenshots.py            # writes docs/screenshots/*.png

Everything shown is made-up demo data ("Dana" on "ACER-LAPTOP"). The Nostos
window is the real window, driven without a screen. The Windows app page is
the real page (agent/ui.html) fed by a stand-in for the app, so it shows
Windows-style paths. Needs Go (to build the agent) and PySide6 with
QtWebEngine.
"""
import http.server
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QTWEBENGINE_CHROMIUM_FLAGS", "--no-sandbox --disable-gpu")
GO = shutil.which("go")
ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "screenshots"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
tmp = Path(tempfile.mkdtemp(prefix="nostos-shots-"))
os.environ["HOME"] = str(tmp / "home")
os.environ["XDG_CURRENT_DESKTOP"] = "KDE"
(tmp / "home").mkdir()

from PySide6.QtCore import QUrl, Qt  # noqa: E402
from PySide6.QtWebEngineWidgets import QWebEngineView  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402
from test_core import make_windows  # noqa: E402

from nostos import __version__ as VERSION  # noqa: E402
from nostos import agentlink, discovery, engine, gui, items, onedrive  # noqa: E402
from nostos.appmap import AppMatch  # noqa: E402

GB = 1024 ** 3


# ------------------------------------------------------------- demo data ---
def acf(folder: Path, appid: int, name: str, size: int):
    (folder / "common" / name).mkdir(parents=True, exist_ok=True)
    (folder / "common" / name / "game.exe").write_bytes(b"MZ")
    (folder / f"appmanifest_{appid}.acf").write_text(
        f'"AppState"\n{{\n\t"appid"\t\t"{appid}"\n\t"name"\t\t"{name}"\n'
        f'\t"installdir"\t\t"{name}"\n\t"SizeOnDisk"\t\t"{size}"\n}}\n')


def demo_pc() -> tuple[Path, Path, Path]:
    c = make_windows(tmp / "C")
    d = tmp / "D"
    u = c / "Users/Dana"
    shutil.rmtree(u / "NostosExport")
    for name in ("Budget 2026.xlsx", "Recipes.docx", "Insurance.pdf"):
        (u / "Documents" / name).write_bytes(b"x" * 4000)
    (u / "Pictures/2019 Beach").mkdir()
    (u / "Pictures/2019 Beach/IMG_2041.JPG").write_bytes(b"\xff\xd8" + b"p" * 9000)
    (u / "Sewing patterns").mkdir()
    (u / "Sewing patterns/apron.pdf").write_bytes(b"%PDF")
    steam_c = c / "Program Files (x86)/Steam/steamapps"
    acf(steam_c, 413150, "Stardew Valley", int(0.6 * GB))
    steam_d = d / "SteamLibrary/steamapps"
    steam_d.mkdir(parents=True)
    acf(steam_d, 1145360, "Hades", int(11.2 * GB))
    acf(steam_d, 105600, "Terraria", int(0.5 * GB))
    acf(steam_d, 553850, "HELLDIVERS 2", int(136.4 * GB))
    for folder in ("Photo archive/2015", "Photo archive/2016", "Backups", "Music library"):
        (d / folder).mkdir(parents=True)
        (d / folder / "file.bin").write_bytes(b"d" * 3000)
    manifest = tmp / "manifest.json"
    manifest.write_text(json.dumps({
        "version": 2, "computer": "ACER-LAPTOP", "user": "Dana",
        "profile": "C:\\Users\\Dana", "windows": "Microsoft Windows 10 Home",
        "apps": ["Google Chrome", "Mozilla Firefox", "VLC media player", "Spotify", "Zoom",
                 "Steam", "Epic Games Launcher", "Microsoft 365 - en-us", "Adobe Acrobat Reader",
                 "7-Zip 23.01 (x64)", "Cricut Design Space", "Family Tree Maker 2019",
                 "Logitech G HUB", "Norton 360", "WhatsApp", "iTunes", "Discord",
                 "Microsoft Visual C++ 2015-2022 Redistributable (x64)", "Embird 2023"],
        "mapped_drives": [{"letter": "Z:", "path": "\\\\homenas\\photos"}],
        "printers": ["HP OfficeJet 8020", "Microsoft Print to PDF"],
        "drives": [{"letter": "C:", "label": "Windows", "size": 512 * GB, "free": 190 * GB},
                   {"letter": "D:", "label": "Data", "size": 1000 * GB, "free": 420 * GB}],
        "steam_path": "c:/program files (x86)/steam",
        "wifi": [{"ssid": "HomeNet", "auth": "WPA2PSK", "key": "x"},
                 {"ssid": "Mum and Dad", "auth": "WPA2PSK", "key": "x"},
                 {"ssid": "Library-Guest", "auth": "open", "key": ""}]}))
    return c, d, manifest


C, D, MANIFEST = demo_pc()
home = Path(os.environ["HOME"])

# Things the test box does not have: an app store and OneDrive support.
items.suggest_flatpaks = lambda unknown, limit=30: (
    [AppMatch("Family Tree Maker 2019", "Gramps", "flatpak", "org.gramps_project.Gramps",
              "Found by searching Flathub. Check it is the program you mean.", guess=True)],
    [n for n in unknown if not n.startswith("Family")])
onedrive.rclone_available = lambda: True
onedrive.is_connected = lambda: False
discovery.find_hosts = lambda: [discovery.Host("192.168.1.23", "ACER-LAPTOP"),
                                discovery.Host("192.168.1.40", "HOMENAS")]
discovery.own_addresses = lambda: {"192.168.1.50"}
_real_profiles = engine.profiles_from_agent


def windows_style_profiles(fs):
    """The agent here runs on Linux; present its shares as C: and D:."""
    profiles = _real_profiles(fs)
    for p in profiles:
        p.roots = [{"name": "C", "path": "C:\\"}, {"name": "D", "path": "D:\\"}]
        p.drive_fs = agentlink.SubFS(fs, "C")
        p.fs.label = "ACER-LAPTOP (Drive C:)"
    return profiles


engine.profiles_from_agent = windows_style_profiles

app = QApplication([])
font = app.font()
font.setPointSizeF(11)
app.setFont(font)
OUT.mkdir(parents=True, exist_ok=True)
for old in OUT.glob("*.png"):
    old.unlink()


def wait(cond, secs=40):
    end = time.time() + secs
    while time.time() < end:
        app.processEvents()
        if cond():
            return
        time.sleep(0.01)
    raise SystemExit("timed out waiting")


def pause(secs):
    end = time.time() + secs
    while time.time() < end:
        app.processEvents()
        time.sleep(0.01)


def shot(widget, name):
    pause(0.15)
    widget.grab().save(str(OUT / f"{name}.png"))
    print("  ", name)


# ------------------------------------------------- the Windows app page ----
class FakeAgent(http.server.BaseHTTPRequestHandler):
    """Answers the page the way NostosAgent.exe does, with Windows paths."""
    session = {"state": ""}
    found = [{"address": "192.168.1.50:47801", "name": "new-laptop"}]
    tree = {"": [("My files (Dana)", "C:\\Users\\Dana"), ("C:", "C:\\"), ("D:", "D:\\")],
            "D:\\": [("Backups", "D:\\Backups"), ("Music library", "D:\\Music library"),
                     ("Photo archive", "D:\\Photo archive"), ("SteamLibrary", "D:\\SteamLibrary")],
            "D:\\Photo archive": [("2015", "D:\\Photo archive\\2015"),
                                  ("2016", "D:\\Photo archive\\2016")]}

    def log_message(self, *args):
        pass

    def _json(self, obj):
        data = json.dumps(obj).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path.startswith("/api/state"):
            self._json({"version": VERSION, "ready": True, "home": "C:\\Users\\Dana",
                        "computer": "ACER-LAPTOP", "user": "Dana", "drives": ["C:", "D:"],
                        "session": FakeAgent.session})
        elif self.path.startswith("/api/browse"):
            from urllib.parse import parse_qs, urlparse
            path = parse_qs(urlparse(self.path).query).get("path", [""])[0]
            parent = "" if path.count("\\") <= 1 else path.rsplit("\\", 1)[0]
            if parent.endswith(":"):
                parent += "\\"
            self._json({"path": path, "parent": parent,
                        "dirs": [{"name": n, "path": p} for n, p in FakeAgent.tree.get(path, [])]})
        else:
            data = (ROOT / "agent" / "ui.html").read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(data)

    def do_POST(self):
        self.rfile.read(int(self.headers.get("Content-Length") or 0))
        if self.path.startswith("/api/discover"):
            self._json({"found": FakeAgent.found})
        else:
            self._json({"ok": True})


server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), FakeAgent)
threading.Thread(target=server.serve_forever, daemon=True).start()
page_url = f"http://127.0.0.1:{server.server_port}/?t=demo"

print("Windows app page")
view = QWebEngineView()
view.resize(820, 1040)
view.show()
loaded = []
view.loadFinished.connect(loaded.append)
view.load(QUrl(page_url))
wait(lambda: loaded)
pause(2.5)


def js(code, settle=1.2):
    view.page().runJavaScript(code)
    pause(settle)


js("document.getElementById('code').value='K7QM-4XWD-9RTB'; document.activeElement.blur();")
shot(view, "03-windows-app")
js("document.querySelector('input[value=custom]').click();", 1.0)
js("browse('D:\\\\');", 1.2)
js("folders=['D:\\\\Photo archive','C:\\\\Users\\\\Dana']; drawFolders(); window.scrollTo(0, 330);", 0.8)
view.resize(820, 900)
shot(view, "04-windows-app-folders")
view.resize(820, 620)
FakeAgent.session = {"state": "connected", "peer": "new-laptop", "error": "",
                     "bytes": int(31.9 * GB), "files": 6712,
                     "current": "C:\\Users\\Dana\\Pictures\\2019 Beach\\IMG_2041.JPG"}
js("window.scrollTo(0,0); document.getElementById('setup').classList.add('hide');"
   "document.getElementById('running').classList.remove('hide');", 2.2)
shot(view, "05-windows-app-connected")
FakeAgent.session = {"state": "done", "peer": "new-laptop", "error": "",
                     "bytes": int(86.4 * GB), "files": 18204, "current": ""}
pause(2.2)
shot(view, "13-windows-app-finished")
view.hide()

# ------------------------------------------------------ the Nostos window --
print("Nostos window")
agent = tmp / "nostos-agent"
subprocess.run([GO, "build", "-o", str(agent), "."], cwd=ROOT / "agent", check=True)

win = gui.Window()
win.show()
shot(win, "01-start")

win.go(win.network)
wait(lambda: win.network.hosts.count() == 2)
win.network.address.setText("ACER-LAPTOP")
win.network.password.setText("Bhm8-Cwc7-Tkz7")
shot(win, "14-connect-sharing")
win.back()

(tmp / "media").mkdir()
win.go(win.drive)
win.drive.list.clear()
from PySide6.QtGui import QIcon  # noqa: E402
from PySide6.QtWidgets import QListWidgetItem  # noqa: E402
for label in ("Backup Plus   (/run/media/dana/Backup Plus)", "Windows   (/run/media/dana/Windows)"):
    win.drive.list.addItem(QListWidgetItem(QIcon.fromTheme("drive-harddisk"), label))
win.drive.list.setCurrentRow(1)
win.drive.notice.hide()
shot(win, "15-connect-drive")
win.back()

_listener = agentlink.Listener


def demo_listener(*a, **kw):
    lis = _listener(port=0, udp_port=0)
    lis.hostname = "new-laptop"
    lis.code = "K7QM-4XWD-9RTB"
    return lis


agentlink.Listener = demo_listener
win.go(win.app)
wait(lambda: win.app.listener is not None and win.app.code.text())
win.app.where.setText("This computer: <b>new-laptop</b>   ·   address <b>192.168.1.50</b>")
shot(win, "02-connect-app")

proc = subprocess.Popen([str(agent), "-no-ui", "-connect", f"127.0.0.1:{win.app.listener.port}",
                         "-code", win.app.code.text(), "-share", f"C={C}", "-share", f"D={D}",
                         "-manifest", str(MANIFEST)])
wait(lambda: win.stack.currentWidget() is win.choose and not win._busy
     and "folders" in win.choose.checks)
choose = win.choose
shot(win, "06-choose-files")

dialog = gui.FolderDialog(choose.prof.browse_fs, win)
dialog.show()
d_item = dialog.tree.topLevelItem(1)
dialog.tree.expandItem(d_item)
pause(0.3)
for i in range(d_item.childCount()):
    child = d_item.child(i)
    if child.text(0) == "Photo archive":
        child.setCheckState(0, Qt.CheckState.Checked)
        dialog.tree.expandItem(child)
shot(dialog, "07-choose-more-folders")
choose.more += [(choose.prof.browse_fs, p) for p in dialog.chosen()]
dialog.close()
choose._build()
pause(0.3)

bar = choose.scroll.verticalScrollBar()
bar.setValue(int(bar.maximum() * 0.36))
shot(win, "08-choose-games-extras")
bar.setValue(bar.maximum())
shot(win, "09-choose-programs")

for group in ("apps", "onedrive_connect", "wifi", "steam"):
    for box, _ in choose.checks.get(group, []):
        box.setChecked(False)
win.next_btn.click()
wait(lambda: win.stack.currentWidget() is win.done)
report = win.done.report

# The copy page, shown mid-way (the demo copy itself takes under a second).
win.go(win.copying, remember=False)
win.copying.status.setText("Copying 18,204 files (86.4 GB)")
win.copying.bar.setRange(0, 1000)
win.copying.bar.setValue(369)
win.copying.detail.setText("Pictures/2019 Beach/IMG_2041.JPG")
win.copying.amount.setText("31.9 GB of 86.4 GB   42.0 MB/s   about 22 min left")
shot(win, "10-copying")

win.go(win.done, remember=False)
win.done.title.setText("All done")
win.done.summary.setText("<b>18,204</b> files copied (86.4 GB).<br>"
                         "<b>3</b> could not be copied (see the report).")
shot(win, "11-done")

view.resize(860, 1180)
view.show()
loaded.clear()
view.load(QUrl.fromLocalFile(str(report)))
wait(lambda: loaded)
pause(1.5)
shot(view, "12-report")

win.close()
proc.wait(10)
server.shutdown()
print("done:", len(list(OUT.glob("*.png"))), "screenshots in", OUT)
