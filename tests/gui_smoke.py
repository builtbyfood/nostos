# Nostos 0.2.4 - tests/gui_smoke.py
"""Drive the real window through whole moves without a screen.

  QT_QPA_PLATFORM=offscreen python3 tests/gui_smoke.py [screenshot-folder]

Run 1: a drive/folder source.  Run 2: the Windows app link (the agent is
built for Linux and connected with the code the window shows; needs Go).
"""
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
GO = shutil.which("go")
HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))
tmp = Path(tempfile.mkdtemp(prefix="nostos-gui-"))
os.environ["HOME"] = str(tmp / "home")
os.environ["XDG_CURRENT_DESKTOP"] = "KDE"
(tmp / "home").mkdir()

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402
from test_core import make_windows  # noqa: E402

from nostos import discovery, gui  # noqa: E402

shots = Path(sys.argv[1]) if len(sys.argv) > 1 else None
windows = make_windows(tmp / "C")
discovery.find_hosts = lambda: [discovery.Host("192.168.1.23", "ACER-LAPTOP")]
app = QApplication([])
font = app.font()
font.setPointSizeF(11)
app.setFont(font)
home = Path(os.environ["HOME"])


def wait(cond, secs=30):
    end = time.time() + secs
    while time.time() < end:
        app.processEvents()
        if cond():
            return
        time.sleep(0.01)
    raise SystemExit("timed out waiting")


def shot(win, name):
    app.processEvents()
    if shots:
        shots.mkdir(parents=True, exist_ok=True)
        win.grab().save(str(shots / f"{name}.png"))


# ---------------------------------------------------------------- run 1 ----
win = gui.Window()
win.show()
shot(win, "1-start")
win.go(win.network)
wait(lambda: win.network.hosts.count() == 1)
assert win.network.address.text() == "ACER-LAPTOP"
shot(win, "2-network")
win.back()
win.go(win.drive)
win.drive.open_path(str(windows))
wait(lambda: win.stack.currentWidget() is win.choose and win.choose.found.bookmarks)
wait(lambda: win.next_btn.isEnabled())
assert len(win.choose.checks["folders"]) == 6 and len(win.choose.checks["apps"]) >= 3
assert len(win.choose.checks["steam"]) == 1          # found on the "drive"
for box, _ in win.choose.checks["apps"]:
    box.setChecked(False)                            # no flatpak in the test box
shot(win, "3-choose")
win.next_btn.click()
wait(lambda: win.stack.currentWidget() is win.done)
shot(win, "5-done")
assert (home / "Documents/letter.docx").exists()
assert (home / "Documents/Bookmarks from Windows.html").exists()
assert win.done.report.exists()
print("drive source passed:", win.done.summary.text())
win.close()

# ---------------------------------------------------------------- run 2 ----
if not GO:
    print("Go is not installed: skipping the Windows app run")
    raise SystemExit(0)
agent = tmp / "nostos-agent"
subprocess.run([GO, "build", "-o", str(agent), "."], cwd=HERE.parent / "agent", check=True)
shutil.rmtree(home)
home.mkdir()

win = gui.Window()
win.show()
win.go(win.app)
wait(lambda: win.app.listener is not None and win.app.code.text())
shot(win, "2-app")
code, port = win.app.code.text(), win.app.listener.port
assert len(code) == 14
proc = subprocess.Popen([str(agent), "-no-ui", "-connect", f"127.0.0.1:{port}",
                         "-code", code, "-share", f"C={windows}",
                         "-share", f"Extra={windows / 'Program Files (x86)'}"])
wait(lambda: win.stack.currentWidget() is win.choose and win.next_btn.isEnabled())
choose = win.choose
assert choose.prof.name == "Dana" and len(choose.checks["folders"]) == 6

dialog = gui.FolderDialog(choose.prof.browse_fs)        # the "more folders" picker
roots = [dialog.tree.topLevelItem(i) for i in range(dialog.tree.topLevelItemCount())]
assert [r.text(0) for r in roots] == ["C", "Extra"]
dialog.tree.expandItem(roots[1])
app.processEvents()
steam = roots[1].child(0)
assert steam.text(0) == "Steam"
steam.setCheckState(0, Qt.CheckState.Checked)
assert dialog.chosen() == ["Extra/Steam"]
choose.more += [(choose.prof.browse_fs, p) for p in dialog.chosen()]
choose._build()
assert len(choose.checks["more"]) == 1
for box, _ in choose.checks["apps"]:
    box.setChecked(False)
shot(win, "3-choose-app")
win.next_btn.click()
wait(lambda: win.stack.currentWidget() is win.done)
assert (home / "Documents/letter.docx").exists()
assert (home / "From Windows/Steam/steamapps/appmanifest_440.acf").exists()
print("Windows app link passed:", win.done.summary.text())
win.close()
assert proc.wait(10) == 0
