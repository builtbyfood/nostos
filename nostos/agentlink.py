# Nostos 0.2.3 - agentlink.py
"""The link to the Nostos app running on the Windows PC.

Nostos (this side) waits; the Windows app dials in. That way Windows needs
no file sharing, no firewall rule, no password and no account changes.

Security, in plain terms:
  * The connection is encrypted (TLS) with a certificate made fresh for
    each session.
  * Both sides must prove they know the pairing code shown on this screen.
    The proof is tied to that certificate, so a machine sitting in between
    with its own certificate cannot pass it on. The code has about 60 bits
    of randomness, so it cannot be guessed during a session.
  * The protocol only has "info", "list" and "read". Nothing on the Windows
    PC can be changed through it, and the Windows app only serves folders
    its user agreed to share.
"""
from __future__ import annotations

import datetime
import hashlib
import hmac
import json
import os
import secrets
import socket
import ssl
import struct
import tempfile
import threading
from typing import Optional

from .fsaccess import BaseFS, Entry, SourceError, join

TCP_PORT = 47801
UDP_PORT = 47800
ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"      # no 0/O or 1/I look-alikes
MAX_FRAME = 16 << 20
READ_CHUNK = 4 << 20


def new_code() -> str:
    raw = "".join(secrets.choice(ALPHABET) for _ in range(12))
    return f"{raw[:4]}-{raw[4:8]}-{raw[8:]}"


def normalize_code(code: str) -> str:
    return "".join(c for c in code.upper() if c.isalnum())


def _proof(code: str, who: str, fingerprint: bytes, nonce_s: str, nonce_a: str) -> str:
    msg = b"\0".join([who.encode(), fingerprint, nonce_s.encode(), nonce_a.encode()])
    return hmac.new(normalize_code(code).encode(), msg, hashlib.sha256).hexdigest()


def _send(sock, obj) -> None:
    data = json.dumps(obj).encode()
    sock.sendall(struct.pack(">I", len(data)) + data)


def _recv_exact(sock, n: int) -> bytes:
    chunks, got = [], 0
    while got < n:
        chunk = sock.recv(min(n - got, 1 << 20))
        if not chunk:
            raise ConnectionError("connection closed")
        chunks.append(chunk)
        got += len(chunk)
    return b"".join(chunks)


def _recv(sock) -> dict:
    (n,) = struct.unpack(">I", _recv_exact(sock, 4))
    if n > MAX_FRAME:
        raise ConnectionError("message too large")
    return json.loads(_recv_exact(sock, n))


def _make_certificate() -> tuple[ssl.SSLContext, bytes]:
    """A throw-away certificate for this session. Returns (context, sha256)."""
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.x509.oid import NameOID

    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "nostos-session")])
    now = datetime.datetime.now(datetime.timezone.utc)
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name)
            .public_key(key.public_key()).serial_number(x509.random_serial_number())
            .not_valid_before(now - datetime.timedelta(days=1))
            .not_valid_after(now + datetime.timedelta(days=7))
            .sign(key, hashes.SHA256()))
    der = cert.public_bytes(serialization.Encoding.DER)
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.minimum_version = ssl.TLSVersion.TLSv1_2
    with tempfile.TemporaryDirectory(prefix="nostos-cert-") as tmp:
        cert_path, key_path = os.path.join(tmp, "c.pem"), os.path.join(tmp, "k.pem")
        fd = os.open(key_path, os.O_WRONLY | os.O_CREAT, 0o600)
        with os.fdopen(fd, "wb") as fh:
            fh.write(key.private_bytes(serialization.Encoding.PEM,
                                       serialization.PrivateFormat.PKCS8,
                                       serialization.NoEncryption()))
        with open(cert_path, "wb") as fh:
            fh.write(cert.public_bytes(serialization.Encoding.PEM))
        ctx.load_cert_chain(cert_path, key_path)
    return ctx, hashlib.sha256(der).digest()


class Listener:
    """Waits for the Windows app. Show ``code`` and ``addresses`` to the user."""

    def __init__(self, port: int = TCP_PORT, udp_port: int = UDP_PORT):
        self.code = new_code()
        self._ctx, self._fingerprint = _make_certificate()
        self._closed = threading.Event()
        self.bad_codes = 0
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            self._sock.bind(("0.0.0.0", port))
        except OSError:
            self._sock.bind(("0.0.0.0", 0))        # port busy: any free one
        self._sock.listen(4)
        self._sock.settimeout(0.5)
        self.port = self._sock.getsockname()[1]
        self.hostname = socket.gethostname().split(".")[0]
        self._udp = None
        try:
            self._udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self._udp.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self._udp.bind(("0.0.0.0", udp_port))
            self._udp.settimeout(0.5)
            threading.Thread(target=self._answer_discovery, daemon=True).start()
        except OSError:
            self._udp = None                       # typing the address still works

    def _answer_discovery(self) -> None:
        reply = f"NOSTOS!1 {self.port} {self.hostname}".encode()
        while not self._closed.is_set():
            try:
                data, addr = self._udp.recvfrom(64)
            except socket.timeout:
                continue
            except OSError:
                return
            if data.startswith(b"NOSTOS?1"):
                try:
                    self._udp.sendto(reply, addr)
                except OSError:
                    pass

    def accept(self, cancel: Optional[threading.Event] = None) -> Optional["AgentFS"]:
        """Block until a Windows app with the right code connects.
        Returns None if cancelled or closed."""
        while not self._closed.is_set() and not (cancel and cancel.is_set()):
            try:
                raw, addr = self._sock.accept()
            except socket.timeout:
                continue
            except OSError:
                return None
            try:
                raw.settimeout(20)
                conn = self._ctx.wrap_socket(raw, server_side=True)
                nonce_s = secrets.token_hex(16)
                _send(conn, {"hello": "nostos", "v": 1, "nonce": nonce_s,
                             "name": self.hostname})
                hello = _recv(conn)
                nonce_a = str(hello.get("nonce", ""))
                want = _proof(self.code, "agent", self._fingerprint, nonce_s, nonce_a)
                if hello.get("hello") != "agent" or not hmac.compare_digest(
                        str(hello.get("proof", "")), want):
                    self.bad_codes += 1
                    _send(conn, {"ok": False, "error": "code"})
                    conn.close()
                    continue
                _send(conn, {"ok": True, "proof": _proof(
                    self.code, "server", self._fingerprint, nonce_s, nonce_a)})
                conn.settimeout(120)
                return AgentFS(conn, str(hello.get("computer") or addr[0]), addr[0])
            except Exception:
                try:
                    raw.close()
                except OSError:
                    pass
                continue
        return None

    def close(self) -> None:
        self._closed.set()
        for s in (self._sock, self._udp):
            try:
                if s is not None:
                    s.close()
            except OSError:
                pass


class AgentFS(BaseFS):
    """Files on the Windows PC, as served by the Nostos app there."""

    def __init__(self, conn, computer: str, address: str):
        self._conn = conn
        self._lock = threading.Lock()
        self.computer, self.address = computer, address
        self.label = computer
        self._info: Optional[dict] = None

    def _ask(self, request: dict) -> dict:
        try:
            _send(self._conn, request)
            reply = _recv(self._conn)
        except (OSError, ConnectionError, ValueError) as exc:
            raise SourceError(
                "The connection to the Windows PC was lost. Check that it is "
                "still on and the Nostos app is still open there, then start "
                "again. Files already copied are kept.") from exc
        return reply

    def info(self) -> dict:
        with self._lock:
            if self._info is None:
                self._info = self._ask({"op": "info"})
        return self._info

    def listdir(self, rel: str = "") -> list[Entry]:
        with self._lock:
            reply = self._ask({"op": "list", "path": rel.strip("/")})
        if not reply.get("ok"):
            raise OSError(reply.get("error") or "cannot open folder")
        return [Entry(e["n"], bool(e.get("d")), int(e.get("s", 0)), float(e.get("m", 0)))
                for e in reply.get("entries", [])]

    def read_at(self, rel: str, offset: int, length: int) -> tuple[bytes, bool]:
        with self._lock:
            reply = self._ask({"op": "read", "path": rel.strip("/"),
                               "off": offset, "len": length})
            if not reply.get("ok"):
                raise OSError(reply.get("error") or "cannot read file")
            n = int(reply.get("n", 0))
            try:
                data = _recv_exact(self._conn, n) if n else b""
            except (OSError, ConnectionError) as exc:
                raise SourceError("The connection to the Windows PC was lost.") from exc
        return data, bool(reply.get("eof")) or n == 0

    def open(self, rel: str) -> "AgentFile":
        return AgentFile(self, rel)

    def close(self) -> None:
        try:
            with self._lock:
                self._conn.settimeout(3)
                _send(self._conn, {"op": "bye"})
                _recv(self._conn)
        except Exception:
            pass
        try:
            self._conn.close()
        except OSError:
            pass


class AgentFile:
    def __init__(self, fs: AgentFS, rel: str):
        self._fs, self._rel = fs, rel
        self._offset, self._eof = 0, False
        # Fail now, not on first read, if the file cannot be opened.
        self._first: Optional[bytes] = None
        self._first, self._eof = fs.read_at(rel, 0, READ_CHUNK)

    def read(self, n: int = -1) -> bytes:
        out = []
        want = n if n is not None and n >= 0 else None
        while want is None or want > 0:
            if self._first is not None:
                data, self._first = self._first, None
                if want is not None and len(data) > want:      # keep the rest
                    data, self._first = data[:want], data[want:]
            elif self._eof:
                break
            else:
                data, self._eof = self._fs.read_at(
                    self._rel, self._offset, min(want or READ_CHUNK, READ_CHUNK))
            self._offset += len(data)
            out.append(data)
            if want is not None:
                want -= len(data)
            if not data:
                break
        return b"".join(out)

    def close(self) -> None:
        pass

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


class SubFS(BaseFS):
    """One folder of another source, presented as if it were the root."""

    def __init__(self, fs: BaseFS, prefix: str, label: str = ""):
        self.fs, self.prefix = fs, prefix.strip("/")
        self.label = label or f"{fs.label} ({self.prefix})"

    def listdir(self, rel: str = "") -> list[Entry]:
        return self.fs.listdir(join(self.prefix, rel))

    def open(self, rel: str):
        return self.fs.open(join(self.prefix, rel))

    def close(self) -> None:
        self.fs.close()
