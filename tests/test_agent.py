# Nostos 0.2.3 - tests/test_agent.py
"""End-to-end tests of the Windows app link.

The agent is the same Go code that is compiled into NostosAgent.exe, built
here for Linux and run without its window. Skipped when Go is not installed.
"""
import json
import shutil
import subprocess
import threading
from pathlib import Path

import pytest

from nostos import agentlink, engine
from nostos.fsaccess import SourceError
from nostos.profile import find_profiles
from test_core import _check_migration, home, make_windows, windows  # noqa: F401

AGENT_SRC = Path(__file__).parent.parent / "agent"


GO = shutil.which("go")      # looked up before any test empties PATH


@pytest.fixture(scope="session")
def agent_bin(tmp_path_factory):
    if not GO:
        pytest.skip("Go is not installed")
    out = tmp_path_factory.mktemp("agent") / "nostos-agent"
    subprocess.run([GO, "build", "-o", str(out), "."], cwd=AGENT_SRC, check=True)
    return out


def _connect(agent_bin, listener, args, code=None):
    proc = subprocess.Popen(
        [str(agent_bin), "-no-ui", "-connect", f"127.0.0.1:{listener.port}",
         "-code", code or listener.code, *args],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    box = {}
    t = threading.Thread(target=lambda: box.setdefault("fs", listener.accept()))
    t.start()
    return proc, t, box


def test_full_move_through_the_agent(home, windows, agent_bin, tmp_path):
    manifest = tmp_path / "m.json"
    shutil.copy(windows / "Users/Dana/NostosExport/manifest.json", manifest)
    shutil.rmtree(windows / "Users/Dana/NostosExport")       # agent supplies it now
    listener = agentlink.Listener(port=0, udp_port=0)
    try:
        proc, t, box = _connect(agent_bin, listener,
                                ["-share", f"C={windows}", "-manifest", str(manifest)])
        t.join(20)
        fs = box["fs"]
        assert fs is not None
        info = fs.info()
        assert [r["name"] for r in info["roots"]] == ["C"]
        assert info["manifest"]["user"] == "Dana"
        assert [e.name for e in fs.listdir("")] == ["C"]

        profiles = engine.profiles_from_agent(fs)
        assert [p.name for p in profiles] == ["Dana"]
        prof = profiles[0]
        assert prof.manifest["user"] == "Dana" and prof.browse_fs is fs
        _, result = _check_migration(home, prof)
        assert result.copied == 7

        # Steam: pretend the shared folder is the real C: drive.
        prof.roots = [{"name": "C", "path": "C:\\"}]
        found = engine.look(prof, suggest=False)
        assert [lib.rel for lib in found.steam] == ["C/Program Files (x86)/Steam/steamapps"]
        assert found.steam_unreachable == [r"D:\SteamLibrary"]

        # The agent refuses anything outside what was shared.
        for bad in ("C/../..", "D", "C/Users/../../etc"):
            with pytest.raises(OSError):
                fs.listdir(bad)
        with pytest.raises(OSError):
            fs.open("C/Users/Dana/nope.txt")
        big = fs.read_bytes("C/Users/Dana/Pictures/cat.jpg")
        assert big == (windows / "Users/Dana/Pictures/cat.jpg").read_bytes()
        fs.close()
        assert proc.wait(10) == 0
        assert "Finished." in proc.stdout.read()
    finally:
        listener.close()


def test_wrong_code_is_refused(agent_bin, windows):
    listener = agentlink.Listener(port=0, udp_port=0)
    try:
        proc, t, box = _connect(agent_bin, listener, ["-share", f"C={windows}"],
                                code="AAAA-BBBB-CCCC")
        assert proc.wait(15) == 1
        assert "code does not match" in proc.stderr.read()
        assert listener.bad_codes == 1
    finally:
        listener.close()
        t.join(5)
    assert box.get("fs") is None


def test_share_only_my_folder(home, windows, agent_bin):
    """-share with one profile folder: Nostos sees only that folder."""
    listener = agentlink.Listener(port=0, udp_port=0)
    try:
        proc, t, box = _connect(agent_bin, listener,
                                ["-share", f"Profile={windows / 'Users/Dana'}"])
        t.join(20)
        fs = box["fs"]
        profiles = engine.profiles_from_agent(fs)
        assert len(profiles) == 1 and "Documents" in profiles[0].folders
        assert not profiles[0].preselected
        with pytest.raises(OSError):
            fs.listdir("Profile/../Public")
        fs.close()
        proc.wait(10)
    finally:
        listener.close()


def test_loose_folders_only(home, windows, agent_bin):
    """Shared folders with no user profile among them are offered as they are."""
    listener = agentlink.Listener(port=0, udp_port=0)
    try:
        proc, t, box = _connect(agent_bin, listener,
                                ["-share", f"Scans={windows / 'Users/Dana/Scans'}",
                                 "-share", f"Tax={windows / 'Users/Dana/Documents/Taxes'}"])
        t.join(20)
        fs = box["fs"]
        prof = engine.profiles_from_agent(fs)[0]
        assert [rel for _, rel in prof.preselected] == ["Scans", "Tax"]
        found = engine.look(prof, suggest=False)
        _, result = engine.run(prof, found, engine.Selection(picked=prof.preselected),
                               report_path=home / "r.html")
        assert (home / "From Windows/Scans/scan1.png").exists()
        assert (home / "From Windows/Tax/2025.pdf").exists()
        fs.close()
        proc.wait(10)
    finally:
        listener.close()


def test_discovery_and_lost_connection(agent_bin, windows):
    listener = agentlink.Listener(port=0)       # default discovery port
    try:
        if listener._udp is None:
            pytest.skip("discovery port in use")
        out = subprocess.run([str(agent_bin), "-find"], capture_output=True, text=True)
        assert f":{listener.port}" in out.stdout and listener.hostname in out.stdout

        proc, t, box = _connect(agent_bin, listener, ["-share", f"C={windows}"])
        t.join(20)
        fs = box["fs"]
        proc.kill()
        proc.wait()
        with pytest.raises(SourceError):
            for _ in range(3):
                fs.listdir("C")
    finally:
        listener.close()
