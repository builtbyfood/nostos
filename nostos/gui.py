# Nostos 0.2.4 - gui.py
"""The step-by-step window. One question per page, big buttons, plain words."""
from __future__ import annotations

import getpass
import os
import shutil
import sys
import threading
import time
from pathlib import Path

from PySide6.QtCore import Qt, QThread, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QFont, QIcon
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QCommandLinkButton, QDialog,
    QDialogButtonBox, QFileDialog, QFormLayout, QFrame, QHBoxLayout, QLabel,
    QLineEdit, QListWidget, QListWidgetItem, QMainWindow, QMessageBox,
    QProgressBar, QPushButton, QScrollArea, QSizePolicy, QStackedWidget,
    QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget)

from . import (APP_NAME, __version__, agentlink, discovery, engine, log_exception,
               log_path, onedrive)
from .copier import human
from .fsaccess import LocalFS, SmbFS, SourceError
from .profile import KNOWN_FOLDERS, find_profiles, xdg_dir

HELPER_DIR = Path(__file__).parent / "windows_helper"
STEPS = ["Start", "Connect", "Choose", "Copy", "Done"]


# ----------------------------------------------------------------- helpers --
class Task(QThread):
    """Run one function off the main thread."""
    ok = Signal(object)
    failed = Signal(object)

    def __init__(self, fn, parent=None):
        super().__init__(parent)
        self._fn = fn

    def run(self):
        try:
            self.ok.emit(self._fn())
        except Exception as exc:     # shown to the user in plain words
            if not isinstance(exc, SourceError):
                log_exception("background task")
            self.failed.emit(exc)


class MoveTask(QThread):
    status = Signal(str)
    progress = Signal(object, object, str, object)  # object: byte counts exceed 32 bit
    ok = Signal(object, object)
    failed = Signal(object)

    def __init__(self, prof, found, sel, parent=None):
        super().__init__(parent)
        self.prof, self.found, self.sel = prof, found, sel
        self.cancel = threading.Event()

    def run(self):
        try:
            path, result = engine.run(
                self.prof, self.found, self.sel, status=self.status.emit,
                progress=lambda d, t, n, s=0: self.progress.emit(d, t, n, s),
                cancel=self.cancel)
            self.ok.emit(path, result)
        except Exception as exc:
            if not isinstance(exc, engine.NotEnoughSpace):
                log_exception("copy")
            self.failed.emit(exc)


def heading(text: str) -> QLabel:
    lab = QLabel(text)
    f = lab.font()
    f.setPointSizeF(f.pointSizeF() * 1.7)
    f.setWeight(QFont.Weight.DemiBold)
    lab.setFont(f)
    lab.setWordWrap(True)
    return lab


def para(text: str, dim: bool = False) -> QLabel:
    lab = QLabel(text)
    lab.setWordWrap(True)
    lab.setTextFormat(Qt.TextFormat.RichText)
    lab.setOpenExternalLinks(True)
    if dim:
        lab.setEnabled(False)
    return lab


def section(text: str) -> QLabel:
    lab = QLabel(text)
    f = lab.font()
    f.setWeight(QFont.Weight.DemiBold)
    f.setPointSizeF(f.pointSizeF() * 1.1)
    lab.setFont(f)
    lab.setContentsMargins(0, 14, 0, 2)
    return lab


class Notice(QLabel):
    """Inline message box: errors in red-ish, tips in the highlight colour."""

    def __init__(self):
        super().__init__()
        self.setWordWrap(True)
        self.setTextFormat(Qt.TextFormat.PlainText)
        self.setContentsMargins(12, 10, 12, 10)
        self.hide()

    def show_text(self, text: str, error: bool = False):
        colour = "rgba(218, 68, 83, 0.18)" if error else "rgba(61, 174, 233, 0.18)"
        edge = "#da4453" if error else "#3daee9"
        self.setStyleSheet(f"background:{colour}; border-left:4px solid {edge};"
                           "border-radius:4px;")
        self.setText(text)
        self.show()


class Page(QWidget):
    def __init__(self, win: "Window"):
        super().__init__()
        self.win = win
        self.box = QVBoxLayout(self)
        self.box.setContentsMargins(32, 28, 32, 20)
        self.box.setSpacing(10)

    def entered(self):
        pass


# ------------------------------------------------------------------- pages --
class StartPage(Page):
    def __init__(self, win):
        super().__init__(win)
        self.box.addWidget(heading("Let's bring your things over from Windows"))
        self.box.addWidget(para(
            "Your documents, pictures, bookmarks and more are copied to this "
            "computer. Nothing on the Windows PC is changed or removed, and "
            "nothing already on this computer is overwritten."))
        self.box.addSpacing(10)
        self.box.addWidget(section("Where are your things right now?"))
        for title, text, slot in (
            ("On my Windows PC: use the Nostos app there (recommended)",
             "Run a small app on the Windows PC and type a code. No Windows "
             "settings to change. Reaches every drive, including games.",
             lambda: win.go(win.app)),
            ("On my Windows PC: use Windows file sharing",
             "No app on Windows, but sharing has to be set up there first.",
             lambda: win.go(win.network)),
            ("On a USB drive, or I have the Windows disk",
             "Use a backup drive, a USB stick, or the old PC's disk plugged in here.",
             lambda: win.go(win.drive)),
            ("In OneDrive",
             "Sign in to OneDrive and keep it as a folder on this computer.",
             win.onedrive_only),
        ):
            b = QCommandLinkButton(title, text)
            b.setMinimumHeight(70)
            b.clicked.connect(slot)
            self.box.addWidget(b)
        self.box.addStretch(1)
        self.box.addWidget(para(f"{APP_NAME} {__version__}", dim=True))


class AppPage(Page):
    """Pair with the Nostos app running on the Windows PC."""

    def __init__(self, win):
        super().__init__(win)
        self.box.addWidget(heading("Connect with the Nostos app"))
        self.box.addWidget(para(
            "<b>1.</b> Put the Windows app on a USB stick with the button below.<br>"
            "<b>2.</b> On the Windows PC, open the USB stick and double-click "
            "<b>NostosAgent</b>. A page opens in its web browser.<br>"
            "<b>3.</b> Type this code into that page and press <b>Connect</b>."))
        row = QHBoxLayout()
        usb = QPushButton(QIcon.fromTheme("drive-removable-media"),
                          "Put the Windows app on a USB stick…")
        usb.clicked.connect(lambda: win.save_helper(self.notice))
        row.addWidget(usb)
        row.addStretch(1)
        self.box.addLayout(row)
        self.box.addSpacing(12)

        self.code = QLabel("")
        f = self.code.font()
        f.setPointSizeF(f.pointSizeF() * 2.6)
        f.setWeight(QFont.Weight.DemiBold)
        f.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 3)
        self.code.setFont(f)
        self.code.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.code.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.code.setFrameShape(QFrame.Shape.StyledPanel)
        self.code.setContentsMargins(10, 16, 10, 16)
        self.box.addWidget(self.code)
        self.where = para("", dim=True)
        self.where.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.box.addWidget(self.where)

        self.box.addSpacing(8)
        self.waiting = QLabel("Waiting for the Windows PC…")
        self.box.addWidget(self.waiting)
        self.bar = QProgressBar()
        self.bar.setRange(0, 0)
        self.bar.setTextVisible(False)
        self.bar.setMaximumHeight(8)
        self.box.addWidget(self.bar)
        self.notice = Notice()
        self.box.addWidget(self.notice)
        self.box.addStretch(1)
        self.box.addWidget(para(
            "If the Windows app says it cannot find this computer, press "
            "“Type the address myself” there and enter the address shown "
            "above. Both computers must be on the same network.", dim=True))
        self.listener = None
        self.cancel = None
        self.fs = None

    def entered(self):
        self.win.set_next("Waiting…", None, enabled=False)
        if self.fs is not None:           # came back: start a fresh pairing
            self.fs.close()
            self.fs = None
        self.stop()
        try:
            self.listener = agentlink.Listener()
        except Exception as exc:
            self.notice.show_text(f"Could not start waiting for the Windows PC: {exc}",
                                  error=True)
            return
        self.code.setText(self.listener.code)
        addrs = sorted(discovery.own_addresses())
        port = "" if self.listener.port == agentlink.TCP_PORT else f":{self.listener.port}"
        self.where.setText(
            f"This computer: <b>{self.listener.hostname}</b>" +
            ("   ·   address " + "  or  ".join(f"<b>{a}{port}</b>" for a in addrs)
             if addrs else ""))
        self.waiting.setText("Waiting for the Windows PC…")
        self.bar.show()
        self.cancel = threading.Event()
        listener, cancel = self.listener, self.cancel

        def work():
            fs = listener.accept(cancel)
            if fs is None:
                return None
            return fs, engine.profiles_from_agent(fs)

        t = Task(work, self)
        t.ok.connect(self._paired)
        t.failed.connect(lambda e: self.notice.show_text(str(e), error=True))
        t.start()

    def stop(self):
        if self.cancel is not None:
            self.cancel.set()
        if self.listener is not None:
            self.listener.close()
        self.listener = self.cancel = None

    def _paired(self, result):
        if result is None or self.win.stack.currentWidget() is not self:
            if result:
                result[0].close()
            return
        self.fs, profiles = result
        self.stop()
        self.notice.hide()
        self.win.choose.load(profiles)
        self.win.go(self.win.choose)


class NetworkPage(Page):
    def __init__(self, win):
        super().__init__(win)
        self.box.addWidget(heading("Connect to the Windows PC"))
        steps = para(
            "<b>1.</b> Put the Nostos helper on a USB stick with the button below.<br>"
            "<b>2.</b> On the Windows PC, open the USB stick and double-click "
            "<b>Prepare this PC</b>. Choose <b>Yes</b> when Windows asks.<br>"
            "<b>3.</b> It shows a PC name, a user name and a password. Type them here.")
        self.box.addWidget(steps)
        row = QHBoxLayout()
        usb = QPushButton(QIcon.fromTheme("drive-removable-media"),
                          "Put the helper on a USB stick…")
        usb.clicked.connect(lambda: win.save_helper(self.notice))
        row.addWidget(usb)
        row.addStretch(1)
        self.box.addLayout(row)

        self.box.addWidget(section("Windows PCs found on your network"))
        self.hosts = QListWidget()
        self.hosts.setMaximumHeight(110)
        self.hosts.itemClicked.connect(self.pick_host)
        self.box.addWidget(self.hosts)
        row = QHBoxLayout()
        self.scan_label = para("", dim=True)
        again = QPushButton(QIcon.fromTheme("view-refresh"), "Look again")
        again.clicked.connect(self.scan)
        row.addWidget(self.scan_label, 1)
        row.addWidget(again)
        self.box.addLayout(row)

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        self.address = QLineEdit()
        self.address.setPlaceholderText("its name, or its address such as 192.168.1.23")
        self.user = QLineEdit("nostos")
        self.password = QLineEdit()
        self.password.setEchoMode(QLineEdit.EchoMode.Password)
        self.password.setPlaceholderText("the password shown on the Windows PC")
        self.eye = self.password.addAction(
            QIcon.fromTheme("view-visible"), QLineEdit.ActionPosition.TrailingPosition)
        self.eye.setToolTip("Show or hide the password")
        self.eye.triggered.connect(self._toggle_password)
        self.share = QLineEdit("Nostos")
        form.addRow("Windows PC:", self.address)
        form.addRow("User name:", self.user)
        form.addRow("Password:", self.password)
        self.share_label = QLabel("Shared folder:")
        form.addRow(self.share_label, self.share)
        self.box.addLayout(form)
        self.more = QCheckBox("I shared a folder myself (show the shared folder name)")
        self.more.toggled.connect(self._toggle_more)
        self.box.addWidget(self.more)
        self._toggle_more(False)

        self.notice = Notice()
        self.box.addWidget(self.notice)
        self.box.addStretch(1)
        self._scanned = False
        self.known: dict[str, str] = {}     # PC name -> address, from the scan

    def _toggle_password(self):
        hidden = self.password.echoMode() == QLineEdit.EchoMode.Password
        self.password.setEchoMode(QLineEdit.EchoMode.Normal if hidden
                                  else QLineEdit.EchoMode.Password)
        self.eye.setIcon(QIcon.fromTheme("view-hidden" if hidden else "view-visible"))

    def _toggle_more(self, on):
        self.share.setVisible(on)
        self.share_label.setVisible(on)

    def entered(self):
        self.win.set_next("Connect", self.connect_pc)
        if not self._scanned:
            self.scan()

    def scan(self):
        self._scanned = True
        self.hosts.clear()
        self.scan_label.setText("Looking for computers…")
        t = Task(discovery.find_hosts, self)
        t.ok.connect(self._scan_done)
        t.failed.connect(lambda e: self.scan_label.setText(
            "Could not look. Type the PC name or address below."))
        t.start()

    def _scan_done(self, hosts):
        self.known = {h.name: h.address for h in hosts if h.name}
        for h in hosts:
            item = QListWidgetItem(QIcon.fromTheme("computer"), h.title)
            item.setData(Qt.ItemDataRole.UserRole, h.name or h.address)
            self.hosts.addItem(item)
        self.scan_label.setText(
            "Pick yours, or type its name below." if hosts else
            "None found yet. That is fine: type the name or address from the "
            "helper window below.")
        if len(hosts) == 1 and not self.address.text():
            self.address.setText(hosts[0].name or hosts[0].address)

    def pick_host(self, item):
        self.address.setText(item.data(Qt.ItemDataRole.UserRole))
        self.password.setFocus()

    def connect_pc(self):
        server = self.address.text().strip().lstrip("\\/")
        user, pw = self.user.text().strip(), self.password.text().strip()
        share = self.share.text().strip() or "Nostos"
        if not server or not user or not pw:
            self.notice.show_text("Fill in the Windows PC, user name and password "
                                  "shown in the helper window.", error=True)
            return
        self.notice.show_text("Connecting…")
        self.win.busy(True)

        known = dict(self.known)

        def work():
            # Windows PC names often cannot be looked up from Linux, so the
            # connection is always made to the address.
            address = discovery.resolve(server, known)
            if not address:
                raise SourceError(
                    f"Could not find a computer called \"{server}\".\n"
                    "Type its address instead. It looks like 192.168.1.23 and "
                    "is shown in the helper window, or on the Windows PC under "
                    "Settings > Network > Properties (IPv4 address).")
            return connect_to(address)

        def connect_to(server):
            try:
                fs = SmbFS(server, share, user, pw)
            except SourceError:
                # Not prepared with the helper? Try what Windows shares normally.
                others = [s for s in discovery.list_shares(server, user, pw)
                          if s.lower() in ("users", "c$") or s.lower() == user.lower()]
                if share != "Nostos" or not others:
                    raise
                fs = SmbFS(server, others[0], user, pw)
            profiles = find_profiles(fs)
            if not profiles:
                raise SourceError("Connected, but no Windows user folders were "
                                  "found in that shared folder.")
            fs.label = f"{server_name} ({fs.share})"
            return engine.prepare_profiles(fs, profiles)

        server_name = server
        t = Task(work, self)
        t.ok.connect(self._connected)
        t.failed.connect(self._failed)
        t.start()

    def _connected(self, profiles):
        self.win.busy(False)
        self.notice.hide()
        self.win.choose.load(profiles)
        self.win.go(self.win.choose)

    def _failed(self, exc):
        self.win.busy(False)
        self.notice.show_text(str(exc), error=True)


class DrivePage(Page):
    def __init__(self, win):
        super().__init__(win)
        self.box.addWidget(heading("Pick the drive or folder"))
        self.box.addWidget(para(
            "Plug in the USB drive or the Windows disk. It can be the whole "
            "Windows disk, a <i>Users</i> folder, or one person's folder."))
        self.list = QListWidget()
        self.list.itemDoubleClicked.connect(lambda *_: self.use_selected())
        self.box.addWidget(self.list, 1)
        row = QHBoxLayout()
        again = QPushButton(QIcon.fromTheme("view-refresh"), "Look again")
        again.clicked.connect(self.refresh)
        browse = QPushButton(QIcon.fromTheme("folder-open"), "Choose a folder…")
        browse.clicked.connect(self.browse)
        row.addWidget(again)
        row.addWidget(browse)
        row.addStretch(1)
        self.box.addLayout(row)
        self.notice = Notice()
        self.box.addWidget(self.notice)

    def entered(self):
        self.win.set_next("Use this drive", self.use_selected)
        self.refresh()

    def refresh(self):
        self.list.clear()
        user = getpass.getuser()
        seen = []
        for base in (f"/run/media/{user}", f"/media/{user}", "/mnt"):
            if os.path.isdir(base):
                for d in sorted(Path(base).iterdir()):
                    if d.is_dir() and os.access(d, os.R_OK):
                        seen.append(d)
        for d in seen:
            item = QListWidgetItem(QIcon.fromTheme("drive-harddisk"), f"{d.name}   ({d})")
            item.setData(Qt.ItemDataRole.UserRole, str(d))
            self.list.addItem(item)
        if seen:
            self.list.setCurrentRow(0)
            self.notice.hide()
        else:
            self.notice.show_text(
                "No drive is plugged in yet. Plug it in, open it once in the "
                "Files window so it unlocks, then press \"Look again\".")

    def browse(self):
        folder = QFileDialog.getExistingDirectory(self, "Choose the folder with your Windows files")
        if folder:
            self.open_path(folder)

    def use_selected(self):
        item = self.list.currentItem()
        if item is None:
            self.notice.show_text("Pick a drive in the list, or choose a folder.", error=True)
            return
        self.open_path(item.data(Qt.ItemDataRole.UserRole))

    def open_path(self, path):
        self.win.busy(True)

        def work():
            fs = LocalFS(path)
            profiles = find_profiles(fs)
            if not profiles:
                raise SourceError(
                    "No Windows user folders were found there. Pick the Windows "
                    "disk, its \"Users\" folder, or the folder with your name on it.")
            return engine.prepare_profiles(fs, profiles)

        t = Task(work, self)
        t.ok.connect(lambda p: (self.win.busy(False), self.win.choose.load(p),
                                self.win.go(self.win.choose)))
        t.failed.connect(lambda e: (self.win.busy(False),
                                    self.notice.show_text(str(e), error=True)))
        t.start()


class ChoosePage(Page):
    def __init__(self, win):
        super().__init__(win)
        self.box.addWidget(heading("What would you like to bring over?"))
        row = QHBoxLayout()
        self.who_label = QLabel("Windows user:")
        self.who = QComboBox()
        self.who.currentIndexChanged.connect(self._profile_changed)
        row.addWidget(self.who_label)
        row.addWidget(self.who, 1)
        self.box.addLayout(row)
        self.notice = Notice()
        self.box.addWidget(self.notice)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.box.addWidget(self.scroll, 1)
        self.profiles, self.prof, self.found = [], None, engine.Found()
        self.checks: dict[str, list] = {}
        self.more: list = []            # [(source, path)] added with "More folders"

    def entered(self):
        self.win.set_next("Start copying", self.start)

    def load(self, profiles):
        self.profiles = profiles
        self.who.blockSignals(True)
        self.who.clear()
        self.who.addItems([p.name for p in profiles])
        self.who.blockSignals(False)
        many = len(profiles) > 1
        self.who.setVisible(many)
        self.who_label.setVisible(many)
        self._profile_changed(0)

    def load_onedrive_only(self):
        self.profiles, self.prof, self.found = [], None, engine.Found()
        self.more = []
        self.who.setVisible(False)
        self.who_label.setVisible(False)
        self._build()

    def _profile_changed(self, index):
        if not (0 <= index < len(self.profiles)):
            return
        self.prof = self.profiles[index]
        self.more = list(self.prof.preselected)
        self.notice.show_text("Looking at what is there… (this can take a minute)")
        self.win.busy(True)
        t = Task(lambda: engine.look(self.prof), self)
        t.ok.connect(self._looked)
        t.failed.connect(lambda e: (self.win.busy(False),
                                    self.notice.show_text(str(e), error=True)))
        t.start()

    def _looked(self, found):
        self.win.busy(False)
        self.found = found
        self._build()

    def _add(self, lay, group, text, data=None, checked=True, hint=""):
        box = QCheckBox(text)
        box.setChecked(checked)
        if hint:
            box.setToolTip(hint)
        lay.addWidget(box)
        self.checks.setdefault(group, []).append((box, data))
        return box

    def _build(self):
        self.checks = {}
        body = QWidget()
        lay = QVBoxLayout(body)
        lay.setContentsMargins(0, 0, 12, 0)
        lay.setSpacing(6)
        prof, found = self.prof, self.found

        if prof is not None:
            if found.problems:
                self.notice.show_text(
                    "Everything below is ready to use. These could not be "
                    "checked and are left out: " + "; ".join(found.problems)
                    + f".\nDetails are in {log_path()}", error=True)
            elif found.has_manifest:
                self.notice.hide()
            else:
                self.notice.show_text(
                    "Tip: files and bookmarks are ready to copy. To also bring "
                    "programs, Wi-Fi, network drives and games, go back and use "
                    "the Nostos app on the Windows PC instead.")
            lay.addWidget(section("Your files"))
            for win_name in KNOWN_FOLDERS:
                if win_name in prof.folders:
                    key, fallback = KNOWN_FOLDERS[win_name]
                    self._add(lay, "folders", f"{win_name}", win_name,
                              hint=f"Goes into {xdg_dir(key, fallback)}")
            for name in prof.extra_folders:
                self._add(lay, "extra", f"{name}   (goes into “From Windows”)", name)
            if prof.onedrive_dirs:
                self._add(lay, "onedrive_local",
                          "Files in the OneDrive folder on the Windows PC", True,
                          checked=False,
                          hint="Not needed if you connect OneDrive below.")
            source = prof.browse_fs or prof.fs
            for item in self.more:
                where = item[1].replace("/", " › ")
                self._add(lay, "more", f"{where}   (goes into “From Windows”)", item)
            row = QHBoxLayout()
            more_btn = QPushButton(QIcon.fromTheme("folder-open"),
                                   "Choose more folders…")
            more_btn.setToolTip("Pick any other folder the Windows PC shares, "
                                "for example on a second drive.")
            more_btn.clicked.connect(lambda: self.choose_more(source))
            row.addWidget(more_btn)
            row.addStretch(1)
            lay.addLayout(row)

            if found.steam:
                lay.addWidget(section("Games"))
                for lib in found.steam:
                    top = ", ".join(name for name, _ in lib.games[:6])
                    self._add(lay, "steam",
                              f"Steam games in {lib.where}   ({len(lib.games)} game{'' if len(lib.games) == 1 else 's'}, "
                              f"{human(lib.size)})", lib, checked=False,
                              hint=f"Largest: {top}.\nCopied to SteamLibrary-Windows so "
                                   "Steam does not have to download them again.")
                lay.addWidget(para(
                    "Experimental. Games made for Windows run through Steam Play "
                    "(Proton); Steam checks the files after you add the folder. "
                    "Leave unticked to let Steam download them instead.", dim=True))

            extras = []
            if found.bookmarks:
                names = ", ".join(sorted({b.browser for b in found.bookmarks}))
                n = sum(b.count for b in found.bookmarks)
                extras.append(("bookmarks", f"Bookmarks and favourites ({n} from {names})", True))
            if found.wallpaper:
                extras.append(("wallpaper", "Desktop wallpaper", True))
            if found.wifi:
                extras.append(("wifi", f"Saved Wi-Fi networks ({len(found.wifi)})", True))
            if extras or found.shares:
                lay.addWidget(section("Also bring"))
            for group, text, data in extras:
                self._add(lay, group, text, data)
            for share in found.shares:
                self._add(lay, "shares",
                          f"Network drive {share['letter']}  {share['share']} on {share['server']}",
                          share)

            installable = [a for a in found.apps if a.kind == "flatpak"]
            builtin = [a for a in found.apps if a.kind == "builtin"]
            if found.apps or found.unknown_apps or found.guesses:
                lay.addWidget(section("Programs"))
            for app in installable:
                same = app.linux.lower() in app.windows.lower()
                text = app.linux if same else f"{app.linux}   (instead of {app.windows})"
                self._add(lay, "apps", "Install " + text, app, hint=app.note)
            if builtin:
                lay.addWidget(para("Already on this computer: " + ", ".join(
                    f"{a.linux} (for {a.windows})" for a in builtin) + ".", dim=True))
            if found.guesses:
                lay.addWidget(para(
                    "<b>Possible matches</b> found by searching the app store. "
                    "Tick only the ones that are the program you mean:"))
                for app in found.guesses:
                    self._add(lay, "apps", f"Install {app.linux}   (for {app.windows}?)",
                              app, checked=False, hint=app.id)
            others = len(found.unknown_apps) + sum(a.kind in ("web", "none") for a in found.apps)
            if others:
                lay.addWidget(para(f"{others} other programs are listed in the "
                                   "report at the end, with what to use instead.", dim=True))

        lay.addWidget(section("OneDrive"))
        if not onedrive.rclone_available():
            lay.addWidget(para("OneDrive needs a small extra piece called rclone. "
                               "Ask whoever set up this computer to run "
                               "<code>sudo dnf install rclone</code>.", dim=True))
        else:
            already = onedrive.is_connected()
            od = self._add(lay, "onedrive_connect",
                           "Keep OneDrive as a folder on this computer"
                           + (" (already signed in)" if already else
                              " (opens a Microsoft sign-in page)"),
                           True, checked=prof is None)
            dl = self._add(lay, "onedrive_download",
                           "Also download a full copy of everything in OneDrive",
                           True, checked=False)
            dl.setEnabled(od.isChecked())
            dl.setContentsMargins(24, 0, 0, 0)
            od.toggled.connect(dl.setEnabled)
        lay.addStretch(1)
        self.scroll.setWidget(body)

    def _picked(self, group):
        return [data for box, data in self.checks.get(group, [])
                if box.isChecked() and box.isEnabled()]

    def choose_more(self, source):
        unticked = {id(d) for b, d in self.checks.get("more", []) if not b.isChecked()}
        self.more = [m for m in self.more if id(m) not in unticked]
        state = {g: [b.isChecked() for b, _ in items] for g, items in self.checks.items()}
        dialog = FolderDialog(source, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            have = {m[1] for m in self.more}
            self.more += [(source, p) for p in dialog.chosen() if p not in have]
        self._build()
        for group, flags in state.items():          # keep earlier ticks as they were
            if group == "more":
                continue
            for (box, _), on in zip(self.checks.get(group, []), flags):
                box.setChecked(on)

    def start(self):
        sel = engine.Selection(
            folders=self._picked("folders"), extra_folders=self._picked("extra"),
            onedrive_local=bool(self._picked("onedrive_local")),
            picked=self._picked("more"), steam=self._picked("steam"),
            bookmarks=bool(self._picked("bookmarks")),
            wallpaper=bool(self._picked("wallpaper")),
            wifi=bool(self._picked("wifi")), shares=self._picked("shares"),
            apps=self._picked("apps"),
            onedrive_connect=bool(self._picked("onedrive_connect")),
            onedrive_download=bool(self._picked("onedrive_download")))
        if not any(vars(sel).values()):
            self.notice.show_text("Tick at least one thing to bring over.", error=True)
            return
        self.win.copying.begin(self.prof, self.found, sel)
        self.win.go(self.win.copying)


class FolderDialog(QDialog):
    """Browse the Windows PC and tick any folders to bring over."""

    def __init__(self, fs, parent=None):
        super().__init__(parent)
        self.fs = fs
        self.setWindowTitle("Choose more folders")
        self.resize(560, 520)
        lay = QVBoxLayout(self)
        lay.addWidget(para("Tick the folders to bring over. Click the small "
                           "arrow to look inside a folder."))
        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.itemExpanded.connect(self._expand)
        lay.addWidget(self.tree, 1)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                                   QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        lay.addWidget(buttons)
        self._fill(self.tree.invisibleRootItem(), "")

    def _fill(self, parent, rel):
        QApplication.setOverrideCursor(Qt.CursorShape.BusyCursor)
        try:
            names = sorted((e.name for e in self.fs.listdir(rel)
                            if e.is_dir and not e.name.startswith("$")),
                           key=str.lower)
        except Exception:
            names = []
        finally:
            QApplication.restoreOverrideCursor()
        for name in names:
            item = QTreeWidgetItem(parent, [name])
            item.setIcon(0, QIcon.fromTheme("folder"))
            item.setData(0, Qt.ItemDataRole.UserRole, f"{rel}/{name}".strip("/"))
            item.setCheckState(0, Qt.CheckState.Unchecked)
            item.setChildIndicatorPolicy(
                QTreeWidgetItem.ChildIndicatorPolicy.ShowIndicator)
        if parent is not self.tree.invisibleRootItem():
            parent.setData(0, Qt.ItemDataRole.UserRole + 1, True)
            if not names:
                parent.setChildIndicatorPolicy(
                    QTreeWidgetItem.ChildIndicatorPolicy.DontShowIndicator)

    def _expand(self, item):
        if not item.data(0, Qt.ItemDataRole.UserRole + 1):
            self._fill(item, item.data(0, Qt.ItemDataRole.UserRole))

    def chosen(self) -> list[str]:
        out = []

        def walk(item):
            for i in range(item.childCount()):
                child = item.child(i)
                if child.checkState(0) == Qt.CheckState.Checked:
                    out.append(child.data(0, Qt.ItemDataRole.UserRole))
                else:                       # a ticked folder already covers its insides
                    walk(child)

        walk(self.tree.invisibleRootItem())
        return out


class CopyPage(Page):
    def __init__(self, win):
        super().__init__(win)
        self.title = heading("Copying your things…")
        self.box.addWidget(self.title)
        self.box.addWidget(para("You can keep using this computer. Leave the "
                                "Windows PC switched on and plugged in."))
        self.box.addStretch(1)
        self.status = QLabel("Getting ready…")
        self.status.setWordWrap(True)
        self.box.addWidget(self.status)
        self.bar = QProgressBar()
        self.bar.setRange(0, 0)
        self.bar.setMinimumHeight(28)
        self.box.addWidget(self.bar)
        self.detail = QLabel("")
        self.detail.setEnabled(False)
        self.detail.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.box.addWidget(self.detail)
        self.amount = QLabel("")
        self.box.addWidget(self.amount)
        self.box.addStretch(2)
        self.task = None
        self._started = 0.0

    def entered(self):
        self.win.set_next("Stop", self.stop, enabled=True, back=False)

    def begin(self, prof, found, sel):
        self.status.setText("Getting ready…")
        self.detail.setText("")
        self.amount.setText("")
        self.bar.setRange(0, 0)
        self._started = time.monotonic()
        self.task = MoveTask(prof, found, sel, self)
        self.task.status.connect(self._status)
        self.task.progress.connect(self._progress)
        self.task.ok.connect(self._done)
        self.task.failed.connect(self._failed)
        self.task.start()

    def _status(self, text):
        self.status.setText(text)
        if not text.startswith(("Copying", "Downloading")):
            self.bar.setRange(0, 0)
            self.detail.setText("")
            self.amount.setText("")
        else:
            self._started = time.monotonic()

    def _progress(self, done, total, name, skipped=0):
        if total:
            self.bar.setRange(0, 1000)
            self.bar.setValue(int(done * 1000 / total))
            # Speed and time left come only from what was really transferred;
            # files already here from an earlier run are skipped in an instant.
            elapsed = time.monotonic() - self._started
            sent = max(0, done - skipped)
            speed = left = ""
            if elapsed > 3 and sent > 0:
                rate = sent / elapsed
                speed = f"   {human(rate)}/s"
                if elapsed > 8 and done < total:
                    secs = (total - done) / rate
                    if secs > 5400:
                        left = "   about %.1f hours left" % (secs / 3600)
                    elif secs > 90:
                        left = "   about %d min left" % round(secs / 60)
                    else:
                        left = "   less than a minute left"
            self.amount.setText(f"{human(done)} of {human(total)}{speed}{left}")
        metrics = self.detail.fontMetrics()
        self.detail.setText(metrics.elidedText(name, Qt.TextElideMode.ElideMiddle,
                                               max(200, self.detail.width())))

    def stop(self):
        if self.task and self.task.isRunning():
            self.task.cancel.set()
            self.status.setText("Stopping after the current file…")
            self.win.set_next("Stopping…", None, enabled=False, back=False)

    def _done(self, report, result):
        self.win.done.show_result(report, result)
        self.win.go(self.win.done)

    def _failed(self, exc):
        if isinstance(exc, engine.NotEnoughSpace):
            text = (f"There is not enough room on this computer.\n\nYour choices "
                    f"need {human(exc.need)} and {human(exc.free)} is free. Go "
                    "back and untick something large (Videos or Pictures are "
                    "usually the biggest), or free up space first.")
        else:
            text = f"Something went wrong:\n\n{exc}\n\nDetails are in {log_path()}"
        QMessageBox.warning(self, APP_NAME, text)
        self.win.go(self.win.choose)


class DonePage(Page):
    def __init__(self, win):
        super().__init__(win)
        self.title = heading("All done")
        self.box.addWidget(self.title)
        self.summary = para("")
        self.box.addWidget(self.summary)
        self.box.addSpacing(8)
        self.report_btn = QCommandLinkButton(
            "See what happened", "A short report, including anything left for you to do.")
        self.files_btn = QCommandLinkButton(
            "Open my files", "Your Documents, Pictures and the rest are in Home.")
        for b in (self.report_btn, self.files_btn):
            b.setMinimumHeight(70)
            self.box.addWidget(b)
        self.files_btn.clicked.connect(
            lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(Path.home()))))
        self.box.addStretch(1)
        self.cleanup = para(
            "<b>Last step:</b> on the Windows PC, press <b>Enter</b> in the "
            "helper window. That removes the temporary password and sharing.")
        self.box.addWidget(self.cleanup)
        self.report = None
        self.report_btn.clicked.connect(
            lambda: self.report and QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.report))))

    def entered(self):
        self.win.set_next("Close", self.win.close, back=False)

    def show_result(self, report, result):
        self.report = report
        prof = self.win.choose.prof
        source = (prof.browse_fs or prof.fs) if prof is not None else None
        if isinstance(source, agentlink.AgentFS):
            self.cleanup.setText(
                "<b>Last step:</b> when you are finished, close this window. "
                "The app on the Windows PC then says <b>Finished</b> and can "
                "be closed too. Nothing was changed there.")
            self.cleanup.setVisible(True)
        else:
            self.cleanup.setVisible(isinstance(source, SmbFS))
        bits = []
        if result.copied or result.already_there:
            bits.append(f"<b>{result.copied:,}</b> files copied ({human(result.copied_bytes)})")
        if result.already_there:
            bits.append(f"{result.already_there:,} were already here")
        if result.errors:
            bits.append(f"<b>{len(result.errors):,}</b> could not be copied (see the report)")
        if result.cancelled:
            self.title.setText("Stopped")
            bits.append("You stopped before the end. Start Nostos again any "
                        "time and it carries on where it left off")
        else:
            self.title.setText("All done" if not result.errors else "Done, with a few things to check")
        self.summary.setText(".<br>".join(bits) + "." if bits else "Finished.")


# ------------------------------------------------------------------ window --
class Window(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Move from Windows")
        self.setWindowIcon(QIcon.fromTheme("system-switch-user"))
        self.resize(860, 660)
        self.setMinimumSize(720, 560)

        root = QWidget()
        outer = QVBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        self.crumbs = QWidget()
        crow = QHBoxLayout(self.crumbs)
        crow.setContentsMargins(32, 14, 32, 6)
        self.crumb_labels = []
        for i, name in enumerate(STEPS):
            lab = QLabel(f"{i + 1}  {name}")
            crow.addWidget(lab)
            self.crumb_labels.append(lab)
            if i < len(STEPS) - 1:
                line = QFrame()
                line.setFrameShape(QFrame.Shape.HLine)
                line.setEnabled(False)
                crow.addWidget(line, 1)
        outer.addWidget(self.crumbs)

        self.stack = QStackedWidget()
        outer.addWidget(self.stack, 1)

        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setFrameShadow(QFrame.Shadow.Sunken)
        outer.addWidget(line)
        nav = QHBoxLayout()
        nav.setContentsMargins(32, 12, 32, 16)
        self.back_btn = QPushButton(QIcon.fromTheme("go-previous"), "Back")
        self.back_btn.clicked.connect(self.back)
        self.next_btn = QPushButton("Next")
        self.next_btn.setDefault(True)
        self.next_btn.setMinimumWidth(170)
        for b in (self.back_btn, self.next_btn):
            b.setMinimumHeight(38)
        nav.addWidget(self.back_btn)
        nav.addStretch(1)
        nav.addWidget(self.next_btn)
        outer.addLayout(nav)
        self.setCentralWidget(root)

        self.start = StartPage(self)
        self.app = AppPage(self)
        self.network = NetworkPage(self)
        self.drive = DrivePage(self)
        self.choose = ChoosePage(self)
        self.copying = CopyPage(self)
        self.done = DonePage(self)
        self.step_of = {self.start: 0, self.app: 1, self.network: 1, self.drive: 1,
                        self.choose: 2, self.copying: 3, self.done: 4}
        for p in self.step_of:
            self.stack.addWidget(p)
        self.history: list[Page] = []
        self._next_slot = None
        self._next_enabled = False
        self._busy = False
        self.next_btn.clicked.connect(lambda: self._next_slot and self._next_slot())
        self.go(self.start)

    def go(self, page: Page, remember: bool = True):
        cur = self.stack.currentWidget()
        if remember and cur is not page and cur in (self.start, self.app,
                                                    self.network, self.drive):
            self.history.append(cur)
        self.stack.setCurrentWidget(page)
        self.set_next("", None, enabled=False, back=bool(self.history))
        self.next_btn.setVisible(page is not self.start)
        step = self.step_of[page]
        for i, lab in enumerate(self.crumb_labels):
            f = lab.font()
            f.setBold(i == step)
            lab.setFont(f)
            lab.setEnabled(i <= step)
        page.entered()

    def back(self):
        if self.stack.currentWidget() is self.app:
            self.app.stop()
        if self.history:
            self.go(self.history.pop(), remember=False)

    def set_next(self, text, slot, enabled=True, back=True):
        self.next_btn.setText(text or "Next")
        self._next_slot = slot
        self._next_enabled = enabled and slot is not None
        self.next_btn.setEnabled(self._next_enabled and not self._busy)
        self.back_btn.setVisible(back and bool(self.history))

    def busy(self, on: bool):
        self._busy = on
        self.next_btn.setEnabled(not on and self._next_enabled)
        self.back_btn.setEnabled(not on)
        if on:
            QApplication.setOverrideCursor(Qt.CursorShape.BusyCursor)
        else:
            QApplication.restoreOverrideCursor()

    def onedrive_only(self):
        self.choose.load_onedrive_only()
        self.go(self.choose)

    def save_helper(self, notice: Notice):
        """Copy the Windows app (and the file-sharing helper) to a USB stick."""
        start = f"/run/media/{getpass.getuser()}"
        if not os.path.isdir(start):
            start = f"/media/{getpass.getuser()}"
        folder = QFileDialog.getExistingDirectory(
            self, "Choose the USB stick", start if os.path.isdir(start) else str(Path.home()))
        if not folder:
            return
        dest = Path(folder) / "Nostos for Windows"
        try:
            dest.mkdir(exist_ok=True)
            for f in HELPER_DIR.iterdir():
                if f.is_file():
                    shutil.copy2(f, dest / f.name)
        except OSError as exc:
            notice.show_text(f"Could not write to that drive: {exc}", error=True)
            return
        if not (dest / "NostosAgent.exe").exists():
            notice.show_text(
                "The Windows app (NostosAgent.exe) is missing from this copy of "
                "Nostos. Build it with ./build-agent.sh, or use Windows file "
                "sharing instead.", error=True)
            return
        notice.show_text(
            f"Saved to \"{dest}\". Safely remove the stick, plug it into the "
            "Windows PC, open the \"Nostos for Windows\" folder and "
            "double-click NostosAgent.")

    def closeEvent(self, event):
        task = self.copying.task
        if task and task.isRunning():
            answer = QMessageBox.question(
                self, APP_NAME, "Copying is still going. Stop and close?\n\n"
                "Nothing is lost: start Nostos again and it carries on.")
            if answer != QMessageBox.StandardButton.Yes:
                event.ignore()
                return
            task.cancel.set()
            task.wait(15000)
        self.app.stop()
        prof = self.choose.prof
        if prof is not None:
            (prof.browse_fs or prof.fs).close()
        event.accept()


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationDisplayName(APP_NAME)
    app.setDesktopFileName("nostos")
    font = app.font()
    if font.pointSizeF() < 11:
        font.setPointSizeF(11)
        app.setFont(font)
    win = Window()
    win.show()
    return app.exec()
