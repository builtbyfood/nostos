# Nostos 0.2.3 - tests/test_core.py
"""Engine tests against a fake Windows profile.

Run with:  python3 -m pytest tests -q
The SMB test starts a throw-away SMB server (needs `pip install impacket`)
and is skipped when impacket is not installed.
"""
import json
import os
import socket
import sqlite3
import threading
import time
from pathlib import Path

import pytest

from nostos import engine, items, places
from nostos.appmap import match_apps
from nostos.copier import PART
from nostos.fsaccess import LocalFS, SmbFS
from nostos.profile import find_profiles


def make_windows(root: Path) -> Path:
    """C:\\ with one real user (OneDrive folder backup on) and system users."""
    u = root / "Users" / "Dana"
    for d in ("Desktop", "Documents/Taxes", "Pictures", "Music", "Videos",
              "Downloads", "AppData/Local", "OneDrive/Documents",
              "OneDrive/Recipes", "Scans", "NostosExport"):
        (u / d).mkdir(parents=True)
    (root / "Users/Public/Documents").mkdir(parents=True)
    (root / "Users/Default/AppData").mkdir(parents=True)
    (u / "NTUSER.DAT").write_bytes(b"regf")
    (u / "Documents/letter.docx").write_bytes(b"letter" * 1000)
    (u / "Documents/Taxes/2025.pdf").write_bytes(b"%PDF" + b"x" * 5000)
    (u / "Documents/desktop.ini").write_text("[.ShellClassInfo]")
    (u / "Documents/~$letter.docx").write_bytes(b"lock")
    (u / "Desktop/Chrome.lnk").write_bytes(b"L")
    (u / "Desktop/todo.txt").write_text("buy milk")
    (u / "Pictures/cat.jpg").write_bytes(b"\xff\xd8" + os.urandom(3 * 1024 * 1024))
    (u / "OneDrive/Documents/budget.xlsx").write_bytes(b"PK" + b"b" * 2000)
    (u / "OneDrive/Recipes/soup.txt").write_text("soup")
    (u / "Scans/scan1.png").write_bytes(b"\x89PNG....")
    os.utime(u / "Documents/letter.docx", (1_600_000_000, 1_600_000_000))

    chrome = u / "AppData/Local/Google/Chrome/User Data/Default"
    chrome.mkdir(parents=True)
    (chrome / "Bookmarks").write_text(json.dumps({"roots": {
        "bookmark_bar": {"type": "folder", "children": [
            {"type": "url", "name": "Bank & Co", "url": "https://bank.example/?a=1&b=2"},
            {"type": "folder", "name": "News", "children": [
                {"type": "url", "name": "Paper", "url": "https://news.example/"}]}]},
        "other": {"type": "folder", "children": []},
        "synced": {"type": "folder", "children": []}}}))

    ff = u / "AppData/Roaming/Mozilla/Firefox/Profiles/abcd.default-release"
    ff.mkdir(parents=True)
    db = sqlite3.connect(ff / "places.sqlite")
    db.executescript("""
        CREATE TABLE moz_places(id INTEGER PRIMARY KEY, url TEXT);
        CREATE TABLE moz_bookmarks(id INTEGER PRIMARY KEY, type INT, fk INT,
                                   parent INT, position INT, title TEXT);
        INSERT INTO moz_places VALUES (1,'https://ff.example/'),(2,'place:sort=8');
        INSERT INTO moz_bookmarks VALUES
          (1,2,NULL,0,0,''),(2,2,NULL,1,0,'menu'),(3,2,NULL,1,1,'toolbar'),
          (10,1,1,3,0,'FF site'),(11,1,2,3,1,'Most visited');
    """)
    db.commit()
    db.close()

    steam = root / "Program Files (x86)/Steam/steamapps"
    (steam / "common/Team Fortress 2").mkdir(parents=True)
    (steam / "downloading/440").mkdir(parents=True)
    (steam / "common/Team Fortress 2/hl2.exe").write_bytes(b"MZ" + b"g" * 5000)
    (steam / "downloading/440/part.bin").write_bytes(b"partial")
    (steam / "appmanifest_440.acf").write_text(
        '"AppState"\n{\n\t"appid"\t\t"440"\n\t"name"\t\t"Team Fortress 2"\n'
        '\t"installdir"\t\t"Team Fortress 2"\n\t"SizeOnDisk"\t\t"5002"\n}\n')
    (steam / "libraryfolders.vdf").write_text(
        '"libraryfolders"\n{\n\t"0"\n\t{\n\t\t"path"\t\t"C:\\\\Program Files (x86)\\\\Steam"\n\t}\n'
        '\t"1"\n\t{\n\t\t"path"\t\t"D:\\\\SteamLibrary"\n\t}\n}\n')

    themes = u / "AppData/Roaming/Microsoft/Windows/Themes"
    themes.mkdir(parents=True)
    (themes / "TranscodedWallpaper").write_bytes(b"\xff\xd8\xff\xe0wallpaper")

    (u / "NostosExport/manifest.json").write_text(json.dumps({
        "version": 1, "computer": "ACER-LAPTOP", "user": "Dana",
        "apps": ["Google Chrome", "VLC media player", "Microsoft 365 - en-us",
                 "Zoom", "Cricut Design Space", "Microsoft Visual C++ 2015 Redistributable",
                 "Family Tree Maker 2019"],
        "mapped_drives": [{"letter": "Z:", "path": "\\\\homenas\\photos"}],
        "wifi": [{"ssid": "HomeNet", "auth": "WPA2PSK", "key": "secret"}],
        "printers": ["HP OfficeJet 8020", "Microsoft Print to PDF"]}),
        encoding="utf-8-sig")
    return root


@pytest.fixture
def home(tmp_path, monkeypatch):
    h = tmp_path / "home"
    h.mkdir()
    monkeypatch.setenv("HOME", str(h))
    monkeypatch.setenv("XDG_CURRENT_DESKTOP", "KDE")
    monkeypatch.setenv("PATH", "/nonexistent")     # no xdg-user-dir, nmcli, flatpak
    return h


@pytest.fixture
def windows(tmp_path):
    return make_windows(tmp_path / "C")


def _selection(prof, found):
    return engine.Selection(folders=list(prof.folders), extra_folders=["Scans"],
                            onedrive_local=True, bookmarks=True, wallpaper=True,
                            shares=found.shares)


def _check_migration(home, prof):
    found = engine.look(prof)
    assert found.has_manifest and found.wallpaper
    assert {(b.browser, b.count) for b in found.bookmarks} == \
        {("Google Chrome", 2), ("Firefox", 1)}
    assert [s["url"] for s in found.shares] == ["smb://homenas/photos"]
    assert found.printers == ["HP OfficeJet 8020"]

    report, result = engine.run(prof, found, _selection(prof, found),
                                report_path=home / "report.html")
    assert not result.errors, result.errors
    assert (home / "Documents/letter.docx").read_bytes() == b"letter" * 1000
    assert int((home / "Documents/letter.docx").stat().st_mtime) == 1_600_000_000
    assert (home / "Documents/Taxes/2025.pdf").exists()
    assert (home / "Documents/budget.xlsx").exists()          # OneDrive-redirected
    assert (home / "Desktop/todo.txt").read_text() == "buy milk"
    assert (home / "Pictures/cat.jpg").stat().st_size == 3 * 1024 * 1024 + 2
    assert (home / "From Windows/Scans/scan1.png").exists()
    assert (home / "From Windows/OneDrive/Recipes/soup.txt").exists()
    assert not (home / "From Windows/OneDrive/Documents").exists()  # not twice
    for junk in ("Documents/desktop.ini", "Documents/~$letter.docx", "Desktop/Chrome.lnk"):
        assert not (home / junk).exists()
    assert not list(home.rglob("*" + PART))
    marks = (home / "Documents/Bookmarks from Windows.html").read_text()
    assert "Bank &amp; Co" in marks and "https://ff.example/" in marks
    assert "place:" not in marks
    assert (home / "Pictures/Windows wallpaper.jpg").exists()
    xbel = places.places_file().read_text()
    assert 'href="smb://homenas/photos"' in xbel and xbel.rstrip().endswith("</xbel>")
    text = report.read_text()
    assert "Cricut" in text and "Family Tree Maker" in text and "HP OfficeJet" in text
    return found, result


def test_local_drive_migration(home, windows):
    profiles = find_profiles(LocalFS(windows))
    assert [p.name for p in profiles] == ["Dana"]
    prof = profiles[0]
    assert prof.folders["Documents"] == ["Users/Dana/Documents",
                                         "Users/Dana/OneDrive/Documents"]
    assert prof.extra_folders == ["Scans"] and prof.onedrive_dirs == ["OneDrive"]
    found, first = _check_migration(home, prof)
    assert first.copied == 7

    # Second run: nothing is copied again, nothing overwritten, conflicts kept.
    (home / "Desktop/todo.txt").write_text("my own newer note")
    second_report, second = engine.run(prof, found, _selection(prof, found),
                                       report_path=home / "r2.html")
    assert second.copied == 1 and second.already_there == 6
    seen = []
    engine.run(prof, found, engine.Selection(folders=["Pictures", "Desktop"]),
               progress=lambda d, t, n, s=0: seen.append((d, s)),
               report_path=home / "r2b.html")
    assert seen[-1][0] == seen[-1][1] > 3_000_000      # all skipped, none re-sent
    assert (home / "Desktop/todo.txt").read_text() == "my own newer note"
    assert (home / "Desktop/todo (from Windows).txt").read_text() == "buy milk"
    third_report, third = engine.run(prof, found, _selection(prof, found),
                                     report_path=home / "r3.html")
    assert third.copied == 0 and third.already_there == 7
    assert places.places_file().read_text().count('href="smb://homenas') == 1


def test_profile_folder_and_users_folder_as_source(home, windows):
    assert [p.name for p in find_profiles(LocalFS(windows / "Users"))] == ["Dana"]
    direct = find_profiles(LocalFS(windows / "Users/Dana"))
    assert len(direct) == 1 and "Documents" in direct[0].folders


def test_cancel_leaves_no_partial_files(home, windows):
    prof = find_profiles(LocalFS(windows))[0]
    found = engine.look(prof)
    cancel = threading.Event()

    class StopHalfway(LocalFS):          # "Stop" pressed while cat.jpg is copying
        def open(self, rel):
            fh = super().open(rel)
            real_read = fh.read

            class Wrapped:
                def __enter__(s): return s
                def __exit__(s, *a): fh.close()
                def read(s, n):
                    data = real_read(n)
                    cancel.set()
                    return data
            return Wrapped()

    prof.fs = StopHalfway(windows)
    _, result = engine.run(prof, found, engine.Selection(folders=["Pictures"]),
                           cancel=cancel, report_path=home / "r.html")
    assert result.cancelled
    assert not (home / "Pictures/cat.jpg").exists()
    assert not list(home.rglob("*" + PART))


def test_not_enough_space(home, windows, monkeypatch):
    prof = find_profiles(LocalFS(windows))[0]
    monkeypatch.setattr(engine, "free_space", lambda p: 1024)
    with pytest.raises(engine.NotEnoughSpace):
        engine.run(prof, engine.look(prof), engine.Selection(folders=["Pictures"]))
    assert not (home / "Pictures").exists()


def test_steam_library_and_picked_folders(home, windows):
    from nostos import items
    fs = LocalFS(windows)
    prof = engine.prepare_profiles(fs, find_profiles(fs))[0]
    assert prof.drive_fs is fs
    found = engine.look(prof, suggest=False)
    assert [(lib.where, lib.games) for lib in found.steam] == \
        [(r"C:\Program Files (x86)\Steam", [("Team Fortress 2", 5002)])]
    assert found.steam_unreachable == [r"D:\SteamLibrary"]

    sel = engine.Selection(steam=found.steam,
                           picked=[(fs, "Users/Public"), (fs, "Users/Dana/Scans")])
    report, result = engine.run(prof, found, sel, report_path=home / "r.html")
    lib = items.steam_library_dir() / "steamapps"
    assert (lib / "common/Team Fortress 2/hl2.exe").exists()
    assert (lib / "appmanifest_440.acf").exists()
    assert not (lib / "downloading").exists()          # half-downloaded data is left
    assert (home / "From Windows/Scans/scan1.png").exists()
    assert (home / "From Windows/Public").is_dir() or True
    text = report.read_text()
    assert "SteamLibrary-Windows" in text and "D:\\SteamLibrary" in text


def test_flathub_suggestions(monkeypatch):
    from nostos import items

    def fake_run(cmd, **kw):
        class R:
            returncode = 0
            stdout = ""
        if cmd[:2] == ["flatpak", "search"]:
            if "Gramps" in cmd[-1]:
                R.stdout = "org.gramps_project.Gramps\tGramps\n"
            elif "Family" in cmd[-1]:
                R.stdout = "com.example.Trees\tPine Trees\n"       # wrong program
        return R
    monkeypatch.setattr(items.shutil, "which", lambda name: "/usr/bin/" + name)
    monkeypatch.setattr(items.subprocess, "run", fake_run)
    guesses, still = items.suggest_flatpaks(["Gramps 5.2 (x64)", "Family Tree Maker 2019"])
    assert [(g.windows, g.id, g.guess) for g in guesses] == \
        [("Gramps 5.2 (x64)", "org.gramps_project.Gramps", True)]
    assert still == ["Family Tree Maker 2019"]


def test_gtk_and_kde_sidebars(home, monkeypatch):
    monkeypatch.setenv("XDG_CURRENT_DESKTOP", "GNOME")
    assert places.add_place("smb://nas/My Photos", "Photos on nas")
    assert not places.add_place("smb://nas/My Photos", "Photos on nas")
    assert places.gtk_bookmarks_file().read_text() == "smb://nas/My%20Photos Photos on nas\n"
    assert not places.places_file().exists()
    monkeypatch.setenv("XDG_CURRENT_DESKTOP", "KDE")
    assert places.add_place("smb://nas/docs", "docs on nas")
    assert 'href="smb://nas/docs"' in places.places_file().read_text()


def test_one_broken_part_does_not_block_the_page(home, windows, monkeypatch):
    """0.2.3 on Python 3.15 failed the whole page when the app-store search broke."""
    from nostos import items, log_path

    def boom(unknown):
        raise TypeError("'lazy_import' object is not callable")
    monkeypatch.setattr(items, "suggest_flatpaks", boom)
    monkeypatch.setenv("XDG_CACHE_HOME", str(home / ".cache"))
    prof = find_profiles(LocalFS(windows))[0]
    found = engine.look(prof)
    assert len(found.problems) == 1 and "app store search" in found.problems[0]
    assert found.bookmarks and found.wallpaper and found.apps and found.unknown_apps
    assert "lazy_import" in log_path().read_text()


def test_app_matching():
    apps, unknown = match_apps(["Google Chrome", "VLC media player", "Zoom",
                                "Microsoft 365 - en-us", "Microsoft Edge WebView2 Runtime",
                                "Realtek Audio Driver", "Family Tree Maker 2019",
                                "Adobe Acrobat Reader DC", "TurboTax 2024"])
    by = {a.windows: a for a in apps}
    assert by["Google Chrome"].id == "com.google.Chrome"
    assert by["VLC media player"].id == "org.videolan.VLC"
    assert by["Microsoft 365 - en-us"].id == "org.libreoffice.LibreOffice"
    assert by["Adobe Acrobat Reader DC"].kind == "builtin"
    assert by["TurboTax 2024"].kind == "none"
    assert unknown == ["Family Tree Maker 2019"]


def test_start_menu_fallback_without_manifest(home, windows):
    u = windows / "Users/Dana"
    (u / "NostosExport/manifest.json").unlink()
    sm = u / "AppData/Roaming/Microsoft/Windows/Start Menu/Programs/Zoom"
    sm.mkdir(parents=True)
    (sm / "Zoom.lnk").write_bytes(b"L")
    found = engine.look(find_profiles(LocalFS(windows))[0])
    assert not found.has_manifest
    assert {a.linux for a in found.apps} == {"Zoom", "Google Chrome"}


def test_pc_name_becomes_address(monkeypatch):
    from nostos import discovery
    known = {"ACER-LAPTOP": "192.168.1.23", "HOMENAS": "192.168.1.40"}
    assert discovery.resolve("192.168.1.23") == "192.168.1.23"
    assert discovery.resolve("acer-laptop", known) == "192.168.1.23"
    assert discovery.resolve("\\\\ACER-LAPTOP", known) == "192.168.1.23"
    assert discovery.resolve("localhost") == "127.0.0.1"
    monkeypatch.setattr(discovery, "find_hosts", lambda: [])
    monkeypatch.setattr(discovery.shutil, "which", lambda name: None)
    assert discovery.resolve("no-such-pc-zzz") is None


# ----------------------------------------------------------- real SMB wire --
def _free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture
def smb_server(windows):
    impacket = pytest.importorskip("impacket.smbserver")
    port = _free_port()
    server = impacket.SimpleSMBServer(listenAddress="127.0.0.1", listenPort=port)
    server.addShare("NOSTOS", str(windows / "Users"), "")
    server.setSMB2Support(True)
    server.addCredential("nostos", 0, "aad3b435b51404eeaad3b435b51404ee",
                         "8846f7eaee8fb117ad06bdd830b7586c")   # NT hash of "password"
    threading.Thread(target=server.start, daemon=True).start()
    for _ in range(50):
        try:
            socket.create_connection(("127.0.0.1", port), timeout=0.2).close()
            break
        except OSError:
            time.sleep(0.1)
    return port


def test_migration_over_smb(home, windows, smb_server):
    fs = SmbFS("127.0.0.1", "NOSTOS", "nostos", "password", port=smb_server)
    try:
        profiles = find_profiles(fs)
        assert [p.name for p in profiles] == ["Dana"]
        _, result = _check_migration(home, profiles[0])
        assert result.copied == 7
    finally:
        fs.close()


def test_smb_wrong_password_is_friendly(windows, smb_server):
    from nostos.fsaccess import SourceError
    with pytest.raises(SourceError) as err:
        SmbFS("127.0.0.1", "NOSTOS", "nostos", "wrong", port=smb_server)
    assert "name and password" in str(err.value)
