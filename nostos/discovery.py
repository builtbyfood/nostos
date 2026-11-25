# Nostos 0.2.3 - discovery.py
"""Find Windows PCs and file servers on the home network.

Windows 10 does not announce itself in a way Linux picks up by default, so
this simply knocks on the file-sharing port (445) of every address on the
local network. That takes a couple of seconds on a normal home network.
"""
from __future__ import annotations

import ipaddress
import os
import shutil
import socket
import subprocess
import tempfile
from concurrent.futures.thread import ThreadPoolExecutor
from dataclasses import dataclass


@dataclass
class Host:
    address: str
    name: str = ""

    @property
    def title(self) -> str:
        return f"{self.name}  ({self.address})" if self.name else self.address


def local_networks() -> list[ipaddress.IPv4Network]:
    nets = []
    if shutil.which("ip"):
        out = subprocess.run(["ip", "-4", "-o", "addr", "show", "scope", "global"],
                             capture_output=True, text=True).stdout
        for line in out.splitlines():
            parts = line.split()
            if "inet" in parts:
                iface = ipaddress.ip_interface(parts[parts.index("inet") + 1])
                net = iface.network
                if net.prefixlen < 24:      # keep the sweep small and quick
                    net = ipaddress.ip_network(f"{iface.ip}/24", strict=False)
                if net not in nets:
                    nets.append(net)
    return nets


def own_addresses() -> set[str]:
    own = set()
    if shutil.which("ip"):
        out = subprocess.run(["ip", "-4", "-o", "addr"], capture_output=True,
                             text=True).stdout
        for line in out.splitlines():
            parts = line.split()
            if "inet" in parts:
                addr = parts[parts.index("inet") + 1].split("/")[0]
                if not addr.startswith("127."):
                    own.add(addr)
    return own


def _knock(addr: str, port: int = 445, timeout: float = 0.5) -> bool:
    try:
        with socket.create_connection((addr, port), timeout=timeout):
            return True
    except OSError:
        return False


def _name_of(addr: str) -> str:
    if shutil.which("nmblookup"):
        try:
            out = subprocess.run(["nmblookup", "-A", addr], capture_output=True,
                                 text=True, timeout=4).stdout
            for line in out.splitlines():
                if "<00>" in line and "<GROUP>" not in line:
                    return line.split()[0]
        except Exception:
            pass
    try:
        socket.setdefaulttimeout(2)
        return socket.gethostbyaddr(addr)[0].split(".")[0]
    except Exception:
        return ""
    finally:
        socket.setdefaulttimeout(None)


def find_hosts() -> list[Host]:
    own = own_addresses()
    addrs = [str(ip) for net in local_networks() for ip in net.hosts()
             if str(ip) not in own]
    if not addrs:
        return []
    with ThreadPoolExecutor(max_workers=128) as pool:
        alive = [a for a, ok in zip(addrs, pool.map(_knock, addrs)) if ok]
        names = list(pool.map(_name_of, alive))
    hosts = [Host(a, n) for a, n in zip(alive, names)]
    return sorted(hosts, key=lambda h: (not h.name, h.title.lower()))


def is_address(text: str) -> bool:
    try:
        ipaddress.ip_address(text)
        return True
    except ValueError:
        return False


def resolve(name: str, known: dict[str, str] | None = None) -> str | None:
    """Turn a PC name into an address. Windows names often do not resolve
    on Linux, so try everything: the scan results, DNS, NetBIOS, mDNS.
    Returns None when nothing works (the caller then asks for the address).
    """
    name = name.strip().strip("\\/")
    if not name or is_address(name):
        return name or None
    short = name.split(".")[0].lower()
    for host, addr in (known or {}).items():
        if host and host.split(".")[0].lower() == short:
            return addr

    def lookup(candidate: str) -> str | None:
        try:
            infos = socket.getaddrinfo(candidate, 445, socket.AF_INET,
                                       socket.SOCK_STREAM)
            return infos[0][4][0] if infos else None
        except OSError:
            return None

    found = lookup(name)
    if found:
        return found
    if shutil.which("nmblookup"):
        try:
            out = subprocess.run(["nmblookup", short], capture_output=True,
                                 text=True, timeout=6).stdout
            for line in out.splitlines():
                first = line.split()[0] if line.split() else ""
                if is_address(first) and "<00>" in line:
                    return first
        except Exception:
            pass
    if "." not in name:
        found = lookup(name + ".local")
        if found:
            return found
    # Last resort: the name may belong to a PC the first scan missed.
    for host in find_hosts():
        if host.name and host.name.split(".")[0].lower() == short:
            return host.address
    return None


def list_shares(server: str, username: str, password: str) -> list[str]:
    """Shared folders on a server (needs the samba-client package)."""
    if not shutil.which("smbclient"):
        return []
    fd, auth = tempfile.mkstemp(prefix="nostos-auth-")
    try:
        with os.fdopen(fd, "w") as fh:      # keeps the password off the command line
            fh.write(f"username = {username}\npassword = {password}\n")
        out = subprocess.run(["smbclient", "-g", "-L", f"//{server}", "-A", auth],
                             capture_output=True, text=True, timeout=20).stdout
    except Exception:
        return []
    finally:
        try:
            os.unlink(auth)
        except OSError:
            pass
    shares = []
    for line in out.splitlines():
        parts = line.split("|")
        if len(parts) >= 2 and parts[0] == "Disk":
            shares.append(parts[1])
    return shares
