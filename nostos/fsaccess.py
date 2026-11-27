# Nostos 0.2.4 - fsaccess.py
"""Read-only file access to the old Windows machine.

Two back ends share one small interface, so everything else in Nostos
works the same whether the Windows files come over the network (SMB,
no root and no mount needed) or from a plugged-in drive / folder.

Paths are always relative, forward-slash strings ("" is the root).
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO, Callable, Iterator, Optional


@dataclass
class Entry:
    name: str
    is_dir: bool
    size: int = 0
    mtime: float = 0.0


class SourceError(Exception):
    """A friendly, user-presentable problem with the source."""


def join(*parts: str) -> str:
    return "/".join(p.strip("/") for p in parts if p and p.strip("/"))


class BaseFS:
    label = "source"

    def listdir(self, rel: str = "") -> list[Entry]:
        raise NotImplementedError

    def open(self, rel: str) -> BinaryIO:
        raise NotImplementedError

    def close(self) -> None:
        pass

    # -- helpers built on the two primitives -------------------------------
    def exists(self, rel: str) -> bool:
        parent, _, name = rel.strip("/").rpartition("/")
        if not name:
            return True
        try:
            return any(e.name.lower() == name.lower() for e in self.listdir(parent))
        except Exception:
            return False

    def is_dir(self, rel: str) -> bool:
        try:
            self.listdir(rel)
            return True
        except Exception:
            return False

    def read_bytes(self, rel: str, limit: int = 64 * 1024 * 1024) -> bytes:
        with self.open(rel) as fh:
            return fh.read(limit)

    def walk(
        self,
        rel: str = "",
        skip: Optional[Callable[[str, Entry], bool]] = None,
        on_error: Optional[Callable[[str, Exception], None]] = None,
    ) -> Iterator[tuple[str, Entry]]:
        """Yield (relative path, Entry) for every file below ``rel``."""
        stack = [rel.strip("/")]
        while stack:
            cur = stack.pop()
            try:
                entries = self.listdir(cur)
            except Exception as exc:  # locked / access denied folders are normal
                if on_error:
                    on_error(cur, exc)
                continue
            for e in entries:
                path = join(cur, e.name)
                if skip and skip(path, e):
                    continue
                if e.is_dir:
                    stack.append(path)
                else:
                    yield path, e


class LocalFS(BaseFS):
    """A folder on this computer: USB drive, Windows disk, backup copy."""

    def __init__(self, root: str | os.PathLike):
        self.root = Path(root)
        self.label = str(self.root)
        if not self.root.is_dir():
            raise SourceError(f"The folder {self.root} could not be opened.")

    def _p(self, rel: str) -> Path:
        return self.root / rel if rel else self.root

    def listdir(self, rel: str = "") -> list[Entry]:
        out = []
        with os.scandir(self._p(rel)) as it:
            for d in it:
                try:
                    if d.is_symlink():
                        continue
                    if d.is_dir():
                        out.append(Entry(d.name, True))
                    elif d.is_file():
                        st = d.stat()
                        out.append(Entry(d.name, False, st.st_size, st.st_mtime))
                except OSError:
                    continue
        return out

    def open(self, rel: str) -> BinaryIO:
        return open(self._p(rel), "rb")


ATTR_HIDDEN, ATTR_SYSTEM, ATTR_DIRECTORY, ATTR_REPARSE = 0x2, 0x4, 0x10, 0x400


def _field(info, name):
    """smbprotocol returns a named tuple (new) or a structure (old)."""
    if hasattr(info, name):
        return getattr(info, name)
    return info[name].get_value()


class SmbFS(BaseFS):
    """A shared folder on the Windows PC, read straight over the network."""

    def __init__(self, server: str, share: str, username: str, password: str,
                 port: int = 445):
        try:
            import smbclient  # provided by python3-smbprotocol
        except ImportError as exc:  # pragma: no cover
            raise SourceError(
                "Network support is missing. Install it with:\n"
                "sudo dnf install python3-smbprotocol") from exc
        self._smb = smbclient
        self.server, self.share, self.port = server, share, port
        self.username = username
        self.label = f"{server} ({share})"
        self._kw = {"port": port}
        try:
            try:        # a failed earlier attempt must not be reused
                smbclient.delete_session(server, port=port)
            except Exception:
                pass
            smbclient.register_session(server, username=username,
                                       password=password, port=port,
                                       connection_timeout=15)
            smbclient.listdir(self._p(""), **self._kw)
        except Exception as exc:
            self.close()    # otherwise a background network thread lingers
            raise SourceError(friendly_smb_error(exc, server, share)) from exc

    def _p(self, rel: str) -> str:
        base = rf"\\{self.server}\{self.share}"
        rel = rel.strip("/").replace("/", "\\")
        return base + ("\\" + rel if rel else "")

    def listdir(self, rel: str = "") -> list[Entry]:
        out = []
        for d in self._smb.scandir(self._p(rel), **self._kw):
            try:
                info = d.smb_info       # came with the listing: no extra round trip
                attrs = int(_field(info, "file_attributes"))
                is_dir = bool(attrs & ATTR_DIRECTORY)
                # Old-style junctions ("My Documents", "Application Data") are
                # hidden + system links that only lead to "access denied".
                if is_dir and attrs & ATTR_REPARSE and attrs & ATTR_HIDDEN \
                        and attrs & ATTR_SYSTEM:
                    continue
                if is_dir:
                    out.append(Entry(d.name, True))
                else:
                    out.append(Entry(
                        d.name, False,
                        int(_field(info, "end_of_file")),
                        _field(info, "last_write_time").timestamp()))
            except Exception:
                continue
        return out

    def open(self, rel: str) -> BinaryIO:
        return self._smb.open_file(self._p(rel), mode="rb",
                                   share_access="rwd", **self._kw)

    def close(self) -> None:
        for fn in (lambda: self._smb.delete_session(self.server, port=self.port),
                   self._smb.reset_connection_cache):
            try:
                fn()
            except Exception:
                pass


def friendly_smb_error(exc: Exception, server: str, share: str) -> str:
    text = f"{type(exc).__name__}: {exc}".lower()
    if "logon" in text or "password" in text or "access_denied" in text \
            or "access denied" in text:
        return ("The Windows PC said no to that name and password.\n"
                "Check them against the Nostos helper window on the Windows PC "
                "and try again.")
    if "bad_network_name" in text or "bad network name" in text:
        return (f"The Windows PC was found, but it has no shared folder called "
                f"\"{share}\". Run the Nostos helper on the Windows PC first.")
    if "timed out" in text or "refused" in text or "unreachable" in text \
            or "failed to connect" in text or "name or service" in text \
            or "getaddrinfo" in text:
        return (f"Could not reach \"{server}\".\n"
                "Make sure both computers are on the same Wi-Fi and the "
                "Windows PC is awake, then try again.")
    return f"Could not connect to the Windows PC.\n({exc})"
