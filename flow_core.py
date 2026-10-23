"""Flow: clipboard sync between PCs that share the MT760 (network side, no Qt).

Discovery  UDP broadcast on DISCOVERY_PORT every few seconds:
           {"t": "hello", "v": 1, "id": <uuid>, "name": <pc name>, "port": <tcp port>}
Pairing    TCP connection that starts with b"P", then plain length-prefixed JSON frames:
             A -> B  {"t": "pair1", id, name, pub}     X25519 public keys (base64)
             B -> A  {"t": "pair2", id, name, pub}
           Both derive key = HKDF(X25519 shared secret, transcript) and show the same 6-digit
           code from it. The user compares the codes (stops a man in the middle) and accepts on
           both PCs; each side then sends {"t": "pair3", ok, mac} with mac = HMAC(key, "confirm"+id).
Messages   TCP connection that starts with b"E" + sender id (16 bytes), then frames
           [len u32][nonce 12][ChaCha20-Poly1305 ciphertext], AAD = sender id + receiver id.
           Plaintext = [header len u32][header JSON][payload]. Headers carry a timestamp; old
           ones are refused. Only paired PCs can send these.
Keys are stored with Windows DPAPI (only this Windows user can decrypt them).
"""
import base64
import ctypes as C
import ctypes.wintypes as W
import hashlib
import hmac
import json
import os
import secrets
import socket
import struct
import threading
import time
import uuid

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey, X25519PublicKey
from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

DISCOVERY_PORT = 47760
SERVICE_PORT = 47761
ANNOUNCE_S = 3.0
PEER_TIMEOUT_S = 12.0
PAIR_TIMEOUT_S = 120.0
MAX_MESSAGE = 1024 * 1024 * 1024  # hard cap; the UI setting is lower
MAX_AGE_S = 300                   # refuse messages older than this (replay protection)
PROTOCOL = 1


# -- DPAPI ---------------------------------------------------------------------------------------
class _BLOB(C.Structure):
    _fields_ = [("cbData", W.DWORD), ("pbData", C.POINTER(C.c_char))]


def _dpapi(data, protect):
    crypt32 = C.WinDLL("crypt32")
    kernel32 = C.WinDLL("kernel32")
    buf = C.create_string_buffer(data, len(data))
    src = _BLOB(len(data), C.cast(buf, C.POINTER(C.c_char)))
    dst = _BLOB()
    fn = crypt32.CryptProtectData if protect else crypt32.CryptUnprotectData
    if not fn(C.byref(src), None, None, None, None, 0, C.byref(dst)):
        raise OSError("DPAPI failed")
    try:
        return C.string_at(dst.pbData, dst.cbData)
    finally:
        kernel32.LocalFree(dst.pbData)


def protect(key):
    return base64.b64encode(_dpapi(key, True)).decode()


def unprotect(text):
    return _dpapi(base64.b64decode(text), False)


# -- framing ---------------------------------------------------------------------------------------
def _recv_exact(sock, n):
    out = bytearray()
    while len(out) < n:
        chunk = sock.recv(min(n - len(out), 1 << 20))
        if not chunk:
            raise ConnectionError("connection closed")
        out += chunk
    return bytes(out)


def _send_frame(sock, data):
    sock.sendall(struct.pack(">I", len(data)) + data)


def _recv_frame(sock, limit=MAX_MESSAGE + 64):
    (n,) = struct.unpack(">I", _recv_exact(sock, 4))
    if n > limit:
        raise ValueError("frame too large")
    return _recv_exact(sock, n)


def _json_frame(sock, obj):
    _send_frame(sock, json.dumps(obj).encode())


def _recv_json(sock):
    return json.loads(_recv_frame(sock, 64 * 1024))


def _derive(shared, pub_a, pub_b, id_a, id_b):
    # transcript is order-independent so both sides derive the same key
    parts = sorted([(id_a, pub_a), (id_b, pub_b)])
    info = b"MT760-Flow-v1" + b"".join(i.encode() + p for i, p in parts)
    return HKDF(algorithm=hashes.SHA256(), length=32, salt=None, info=info).derive(shared)


def pairing_code(key):
    n = int.from_bytes(hmac.new(key, b"code", hashlib.sha256).digest()[:4], "big") % 1_000_000
    return f"{n:06d}"


def _pub_bytes(priv):
    return priv.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)


class PairSession:
    def __init__(self, sock, peer_id, peer_name, key, initiator):
        self.sock, self.peer_id, self.peer_name, self.key = sock, peer_id, peer_name, key
        self.initiator = initiator
        self.code = pairing_code(key)
        self.local = None   # None until the user answers
        self.remote = None
        self.done = threading.Event()


class FlowCore:
    """Discovery, pairing and encrypted messaging. All callbacks run on background threads."""

    def __init__(self, store_path, events, name=None, discovery_port=DISCOVERY_PORT,
                 service_port=SERVICE_PORT, announce_ports=None, announce_host="<broadcast>"):
        self.store_path = store_path
        self.events = events
        self.discovery_port = discovery_port
        self.service_port = service_port
        self.announce_ports = announce_ports or [discovery_port]
        self.announce_host = announce_host
        self.lock = threading.RLock()
        self.data = self._load()
        if name:
            self.data["name"] = name
        self.id = self.data["id"]
        self.discovered = {}  # id -> {"name", "host", "port", "seen"}
        self.sessions = {}    # peer id -> PairSession
        self.running = False
        self.threads = []
        self.sockets = []

    # -- store ----------------------------------------------------------------------------------
    def _load(self):
        try:
            with open(self.store_path, encoding="utf-8") as f:
                data = json.load(f)
        except FileNotFoundError:
            data = {}
        data.setdefault("id", str(uuid.uuid4()))
        data.setdefault("name", socket.gethostname())
        data.setdefault("peers", {})
        return data

    def _save(self):
        os.makedirs(os.path.dirname(self.store_path), exist_ok=True)
        tmp = self.store_path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self.data, f, indent=2)
        os.replace(tmp, self.store_path)

    @property
    def name(self):
        return self.data["name"]

    def peers(self):
        with self.lock:
            return {pid: dict(p) for pid, p in self.data["peers"].items()}

    def _key(self, peer_id):
        p = self.data["peers"].get(peer_id)
        return unprotect(p["key"]) if p else None

    def unpair(self, peer_id):
        with self.lock:
            self.data["peers"].pop(peer_id, None)
            self._save()
        self.events.on_peers_changed()

    # -- lifecycle ------------------------------------------------------------------------------
    def start(self):
        if self.running:
            return
        tcp = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            tcp.bind(("", self.service_port))
            tcp.listen(8)
            udp.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            udp.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            udp.bind(("", self.discovery_port))
            self._save()
        except OSError:
            tcp.close()
            udp.close()
            raise
        self.running = True
        self.sockets = [tcp, udp]
        for target in (lambda: self._serve(tcp), lambda: self._listen(udp), self._announce):
            t = threading.Thread(target=target, daemon=True, name="flow")
            t.start()
            self.threads.append(t)

    def stop(self):
        self.running = False
        for s in self.sockets:
            try:
                s.close()
            except OSError:
                pass
        self.sockets = []

    # -- discovery ------------------------------------------------------------------------------
    def _announce(self):
        out = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        out.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        while self.running:
            msg = json.dumps({"t": "hello", "v": PROTOCOL, "id": self.id, "name": self.name,
                              "port": self.service_port,
                              "discovery_port": self.discovery_port}).encode()
            for port in self.announce_ports:
                try:
                    out.sendto(msg, (self.announce_host, port))
                except OSError:
                    pass
            self._expire()
            time.sleep(ANNOUNCE_S)
        out.close()

    def _listen(self, udp):
        while self.running:
            try:
                data, addr = udp.recvfrom(2048)
                msg = json.loads(data)
            except (OSError, ValueError):
                continue
            if msg.get("t") != "hello" or msg.get("id") == self.id or msg.get("v") != PROTOCOL:
                continue
            host = addr[0]
            with self.lock:
                new = msg["id"] not in self.discovered
                self.discovered[msg["id"]] = {"name": str(msg.get("name", "?"))[:64], "host": host,
                                              "port": int(msg.get("port", SERVICE_PORT)),
                                              "seen": time.monotonic()}
                peer = self.data["peers"].get(msg["id"])
                if peer and (peer.get("host"), peer.get("port")) != (host, int(msg.get("port", 0))):
                    peer["host"], peer["port"] = host, int(msg["port"])
                    self._save()
            if new:
                self.events.on_peers_changed()
            # Announcements come from an ephemeral UDP source port. Reply to the sender's
            # advertised listener port so it can discover us even if its broadcast is missed.
            if not msg.get("reply"):
                reply = json.dumps({"t": "hello", "v": PROTOCOL, "id": self.id,
                                    "name": self.name, "port": self.service_port,
                                    "discovery_port": self.discovery_port,
                                    "reply": True}).encode()
                try:
                    reply_port = int(msg.get("discovery_port", DISCOVERY_PORT))
                    udp.sendto(reply, (host, reply_port))
                except (OSError, TypeError, ValueError):
                    pass

    def _expire(self):
        now = time.monotonic()
        with self.lock:
            gone = [i for i, d in self.discovered.items() if now - d["seen"] > PEER_TIMEOUT_S]
            for i in gone:
                del self.discovered[i]
        if gone:
            self.events.on_peers_changed()

    def _address(self, peer_id):
        with self.lock:
            d = self.discovered.get(peer_id) or self.data["peers"].get(peer_id) or {}
            return (d["host"], d["port"]) if d.get("host") else None

    # -- server ---------------------------------------------------------------------------------
    def _serve(self, tcp):
        while self.running:
            try:
                sock, addr = tcp.accept()
            except OSError:
                break
            threading.Thread(target=self._handle, args=(sock, addr), daemon=True).start()

    def _handle(self, sock, addr):
        try:
            sock.settimeout(30)
            kind = _recv_exact(sock, 1)
            if kind == b"P":
                self._pair_respond(sock, addr)
                return
            if kind == b"E":
                self._receive(sock)
        except Exception as e:
            self.events.on_log(f"Flow: connection from {addr[0]} failed: {e}")
        finally:
            try:
                sock.close()
            except OSError:
                pass

    # -- pairing --------------------------------------------------------------------------------
    def pair_with(self, peer_id):
        threading.Thread(target=self._pair_initiate, args=(peer_id,), daemon=True).start()

    def _pair_initiate(self, peer_id):
        addr = self._address(peer_id)
        if not addr:
            self.events.on_pair_result(peer_id, False, "That PC isn't reachable right now.")
            return
        try:
            sock = socket.create_connection(addr, timeout=10)
            sock.settimeout(PAIR_TIMEOUT_S)
            priv = X25519PrivateKey.generate()
            sock.sendall(b"P")
            _json_frame(sock, {"t": "pair1", "id": self.id, "name": self.name,
                               "pub": base64.b64encode(_pub_bytes(priv)).decode()})
            reply = _recv_json(sock)
            if reply.get("t") != "pair2" or reply.get("id") != peer_id:
                raise ValueError("unexpected reply")
            self._pair_finish(sock, priv, reply, initiator=True)
        except Exception as e:
            if isinstance(e, (TimeoutError, socket.timeout)):
                msg = ("No response from the other PC. Check that MT760 Hub is open with Flow on, "
                       "and allow it through Windows Firewall (TCP port 47761).")
            else:
                msg = f"Pairing failed: {e}"
            self.events.on_pair_result(peer_id, False, msg)
        finally:
            try:
                sock.close()
            except (OSError, UnboundLocalError):
                pass

    def _pair_respond(self, sock, addr):
        sock.settimeout(PAIR_TIMEOUT_S)
        hello = _recv_json(sock)
        if hello.get("t") != "pair1" or not hello.get("id") or hello["id"] == self.id:
            return
        priv = X25519PrivateKey.generate()
        _json_frame(sock, {"t": "pair2", "id": self.id, "name": self.name,
                           "pub": base64.b64encode(_pub_bytes(priv)).decode()})
        self._pair_finish(sock, priv, hello, initiator=False)

    def _pair_finish(self, sock, priv, other, initiator):
        peer_id, peer_name = other["id"], str(other.get("name", "?"))[:64]
        peer_pub = base64.b64decode(other["pub"])
        shared = priv.exchange(X25519PublicKey.from_public_bytes(peer_pub))
        key = _derive(shared, _pub_bytes(priv), peer_pub, self.id, peer_id)
        s = PairSession(sock, peer_id, peer_name, key, initiator)
        with self.lock:
            self.sessions[peer_id] = s
        self.events.on_pair_request(peer_id, peer_name, s.code, initiator)

        def read_remote():
            try:
                msg = _recv_json(sock)
                ok = msg.get("t") == "pair3" and msg.get("ok") is True and hmac.compare_digest(
                    msg.get("mac", ""), hmac.new(key, b"confirm" + peer_id.encode(), hashlib.sha256).hexdigest())
                s.remote = bool(ok)
            except Exception:
                s.remote = False
            s.done.set()

        threading.Thread(target=read_remote, daemon=True).start()
        deadline = time.monotonic() + PAIR_TIMEOUT_S
        while s.local is None and time.monotonic() < deadline:  # wait for this user's answer
            time.sleep(0.1)
        accepted = s.local is True
        try:
            _json_frame(sock, {"t": "pair3", "ok": accepted,
                               "mac": hmac.new(key, b"confirm" + self.id.encode(), hashlib.sha256).hexdigest()})
        except OSError:
            pass
        s.done.wait(max(0.0, deadline - time.monotonic()) if accepted else 2)
        with self.lock:
            self.sessions.pop(peer_id, None)
        if accepted and s.remote:
            host, _ = sock.getpeername()
            port = (self.discovered.get(peer_id) or {}).get("port", SERVICE_PORT)
            with self.lock:
                self.data["peers"][peer_id] = {"name": peer_name, "key": protect(key), "host": host,
                                               "port": port, "paired": time.time()}
                self._save()
            self.events.on_peers_changed()
            self.events.on_pair_result(peer_id, True, f"Paired with {peer_name}.")
        else:
            why = "You declined." if not accepted else f"{peer_name} declined or didn't answer."
            self.events.on_pair_result(peer_id, False, why)

    def answer_pairing(self, peer_id, accept):
        with self.lock:
            s = self.sessions.get(peer_id)
        if s:
            s.local = bool(accept)

    # -- encrypted messages ---------------------------------------------------------------------
    def send(self, peer_id, header, payload=b""):
        """Encrypt and deliver one message. Raises on failure."""
        key = self._key(peer_id)
        addr = self._address(peer_id)
        if not key or not addr:
            raise ConnectionError("peer not paired or not reachable")
        header = dict(header, ts=time.time(), to=peer_id)
        hb = json.dumps(header).encode()
        plain = struct.pack(">I", len(hb)) + hb + payload
        nonce = secrets.token_bytes(12)
        aad = uuid.UUID(self.id).bytes + uuid.UUID(peer_id).bytes
        ct = ChaCha20Poly1305(key).encrypt(nonce, plain, aad)
        with socket.create_connection(addr, timeout=10) as sock:
            sock.settimeout(120)
            sock.sendall(b"E" + uuid.UUID(self.id).bytes)
            _send_frame(sock, nonce + ct)

    def send_all(self, header, payload=b""):
        sent = []
        for pid, p in self.peers().items():
            try:
                self.send(pid, header, payload)
                sent.append(p["name"])
            except Exception as e:
                self.events.on_log(f"Flow: couldn't reach {p['name']} ({e})")
        return sent

    def _receive(self, sock):
        sender = str(uuid.UUID(bytes=_recv_exact(sock, 16)))
        key = self._key(sender)
        if not key:
            return  # not paired: ignore without reading further
        frame = _recv_frame(sock)
        aad = uuid.UUID(sender).bytes + uuid.UUID(self.id).bytes
        plain = ChaCha20Poly1305(key).decrypt(frame[:12], frame[12:], aad)  # raises if tampered
        (hl,) = struct.unpack(">I", plain[:4])
        header = json.loads(plain[4:4 + hl])
        payload = plain[4 + hl:]
        if header.get("to") != self.id or abs(time.time() - float(header.get("ts", 0))) > MAX_AGE_S:
            return
        self.events.on_message(sender, self.data["peers"][sender]["name"], header, payload)
