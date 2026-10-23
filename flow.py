"""Flow: copy on one PC, switch the MT760 to the other PC, paste there.

The mouse is only the trigger; clipboards travel over the local network (flow_core.py).
  - Mouse leaves this PC (connection lost)  -> send the clipboard to paired PCs, if it changed.
  - A clipboard arrives                      -> held as pending; applied when the mouse arrives
                                                here (or right away if it just did). A sleeping
                                                mouse on the other PC therefore can't overwrite
                                                this clipboard.
  - Mouse arrives here                       -> ask paired PCs for their clipboard ("pull"),
                                                in case the other PC didn't notice the switch.
Clipboard access stays on the Qt main thread; network callbacks are marshalled with signals.
"""
import hashlib
import io
import os
import threading
import time
import zipfile

from PySide6.QtCore import Property, QBuffer, QByteArray, QIODevice, QMimeData, QObject, QUrl, Signal, Slot
from PySide6.QtGui import QDesktopServices, QGuiApplication, QImage

from config import APP_DIR
from flow_core import FlowCore

STORE_PATH = os.path.join(APP_DIR, "flow.json")
PENDING_S = 120          # a received clipboard waits this long for the mouse to arrive
JUST_ARRIVED_S = 15      # mouse arrived this recently: apply incoming clipboards at once
DEFAULT_SAVE_DIR = os.path.join(os.path.expanduser("~"), "Downloads", "MT760 Flow")


def _human(n):
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024


class _Events(QObject):
    """Thread-safe bridge: FlowCore calls these from network threads."""
    peersChanged = Signal()
    log = Signal(str)
    pairRequest = Signal(str, str, str, bool)
    pairResult = Signal(str, bool, str)
    message = Signal(str, str, "QVariantMap", bytes)

    def on_peers_changed(self):
        self.peersChanged.emit()

    def on_log(self, msg):
        self.log.emit(msg)

    def on_pair_request(self, peer_id, name, code, initiator):
        self.pairRequest.emit(peer_id, name, code, initiator)

    def on_pair_result(self, peer_id, ok, msg):
        self.pairResult.emit(peer_id, ok, msg)

    def on_message(self, peer_id, name, header, payload):
        self.message.emit(peer_id, name, header, payload)


class Flow(QObject):
    changed = Signal()
    pairingChanged = Signal()
    toast = Signal(str)
    logRequested = Signal(str)

    def __init__(self, store_path=STORE_PATH, core_kwargs=None, clipboard=None):
        super().__init__()
        self.clipboard = clipboard or QGuiApplication.clipboard()  # injectable for tests
        self.events = _Events()
        self.core = FlowCore(store_path, self.events, **(core_kwargs or {}))
        self.settings = self.core.data.setdefault("settings", {
            "enabled": False, "files": True, "max_mb": 200, "save_dir": DEFAULT_SAVE_DIR})
        self._pairing = {}       # {"id", "name", "code", "initiator", "answered"}
        self._mouse_here = False
        self._arrived_at = 0.0
        self._left_at = None     # when the mouse last left this PC (None: it never has)
        self._pending = None     # (time, name, header, payload)
        self._last_sent = ""     # hash of the clipboard we last sent
        self._last_applied = ""  # hash of the clipboard we last applied (never echo it back)
        self._last_event = ""
        self.events.peersChanged.connect(self.changed)
        self.events.log.connect(self.logRequested)
        self.events.pairRequest.connect(self._on_pair_request)
        self.events.pairResult.connect(self._on_pair_result)
        self.events.message.connect(self._on_message)
        if self.settings.get("enabled"):
            self._start()

    def _start(self):
        try:
            self.core.start()
        except OSError as e:
            self.settings["enabled"] = False
            self.toast.emit(f"Flow couldn't start: {e}")

    def shutdown(self):
        self.core.stop()

    def _save_settings(self):
        self.core.data["settings"] = self.settings
        self.core._save()
        self.changed.emit()

    def _note(self, text):
        self._last_event = text
        self.logRequested.emit(text)
        self.changed.emit()

    # -- properties for QML ---------------------------------------------------------------------
    enabled = Property(bool, lambda s: bool(s.settings.get("enabled")), notify=changed)
    thisName = Property(str, lambda s: s.core.name, notify=changed)
    includeFiles = Property(bool, lambda s: bool(s.settings.get("files", True)), notify=changed)
    maxMb = Property(int, lambda s: int(s.settings.get("max_mb", 200)), notify=changed)
    saveDir = Property(str, lambda s: s.settings.get("save_dir", DEFAULT_SAVE_DIR), notify=changed)
    lastEvent = Property(str, lambda s: s._last_event, notify=changed)
    pairing = Property("QVariantMap", lambda s: dict(s._pairing), notify=pairingChanged)

    def _nearby(self):
        paired = self.core.peers()
        with self.core.lock:
            found = {i: dict(d) for i, d in self.core.discovered.items()}
        return [{"id": i, "name": d["name"], "host": d["host"], "paired": i in paired}
                for i, d in sorted(found.items(), key=lambda x: x[1]["name"].lower())]

    def _paired(self):
        with self.core.lock:
            online = set(self.core.discovered)
        return [{"id": i, "name": p["name"], "host": p.get("host", ""), "online": i in online}
                for i, p in sorted(self.core.peers().items(), key=lambda x: x[1]["name"].lower())]

    nearby = Property("QVariantList", _nearby, notify=changed)
    paired = Property("QVariantList", _paired, notify=changed)

    # -- settings slots -------------------------------------------------------------------------
    @Slot(bool)
    def setEnabled(self, on):
        self.settings["enabled"] = on
        if on:
            self._start()
        else:
            self.core.stop()
        self._save_settings()

    @Slot(bool)
    def setIncludeFiles(self, on):
        self.settings["files"] = on
        self._save_settings()

    @Slot(int)
    def setMaxMb(self, mb):
        self.settings["max_mb"] = max(1, int(mb))
        self._save_settings()

    @Slot(str)
    def setSaveDir(self, path):
        if path:
            self.settings["save_dir"] = path
            self._save_settings()

    @Slot()
    def openSaveDir(self):
        os.makedirs(self.saveDir, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(self.saveDir))

    # -- pairing --------------------------------------------------------------------------------
    @Slot(str)
    def pair(self, peer_id):
        self.core.pair_with(peer_id)

    @Slot(str)
    def unpair(self, peer_id):
        self.core.unpair(peer_id)

    @Slot(bool)
    def answerPairing(self, accept):
        if self._pairing:
            self.core.answer_pairing(self._pairing["id"], accept)
            self._pairing["answered"] = True
            self.pairingChanged.emit()

    def _on_pair_request(self, peer_id, name, code, initiator):
        self._pairing = {"id": peer_id, "name": name, "code": f"{code[:3]} {code[3:]}",
                         "initiator": initiator, "answered": False}
        self.pairingChanged.emit()

    def _on_pair_result(self, peer_id, ok, msg):
        if self._pairing.get("id") == peer_id:
            self._pairing = {}
            self.pairingChanged.emit()
        self.toast.emit(msg)
        self._note(msg)

    # -- clipboard ------------------------------------------------------------------------------
    def snapshot(self):
        """(header, payload, hash) of the current clipboard, or None if there's nothing to send."""
        md = self.clipboard.mimeData()
        if md is None:
            return None
        if md.hasUrls() and any(u.isLocalFile() for u in md.urls()):
            if not self.settings.get("files", True):
                return None
            paths = [u.toLocalFile() for u in md.urls() if u.isLocalFile() and os.path.exists(u.toLocalFile())]
            size = sum(self._size(p) for p in paths)
            if size > self.maxMb * 1024 * 1024:
                self._note(f"Flow: clipboard files are {_human(size)}, over the {self.maxMb} MB limit; not sent")
                return None
            payload = self._zip(paths)
            header = {"kind": "files", "names": [os.path.basename(p.rstrip("/\\")) for p in paths],
                      "size": size}
            # Hash names and sizes, not zip bytes: a received copy re-zips differently (timestamps)
            # but must still count as the same clipboard, or it would be sent straight back.
            listing = sorted(self._listing(paths))
            digest = hashlib.sha256(b"files" + repr(listing).encode()).hexdigest()
            header["hash"] = digest
            return header, payload, digest
        elif md.hasImage():
            img = self.clipboard.image()
            if img.isNull():
                return None
            ba = QByteArray()
            buf = QBuffer(ba)
            buf.open(QIODevice.WriteOnly)
            img.save(buf, "PNG")
            payload = bytes(ba)
            header = {"kind": "image", "w": img.width(), "h": img.height()}
        elif md.hasText() and md.text():
            payload = md.text().encode("utf-8")
            header = {"kind": "text", "chars": len(md.text())}
        else:
            return None
        digest = hashlib.sha256(header["kind"].encode() + payload).hexdigest()
        header["hash"] = digest
        return header, payload, digest

    @staticmethod
    def _size(path):
        if os.path.isfile(path):
            return os.path.getsize(path)
        return sum(os.path.getsize(os.path.join(r, f)) for r, _, fs in os.walk(path) for f in fs)

    @staticmethod
    def _listing(paths):
        for p in paths:
            base = os.path.dirname(os.path.abspath(p.rstrip("/\\")))
            if os.path.isfile(p):
                yield os.path.relpath(p, base).replace(os.sep, "/"), os.path.getsize(p)
            else:
                for root, _, files in os.walk(p):
                    for f in files:
                        full = os.path.join(root, f)
                        yield os.path.relpath(full, base).replace(os.sep, "/"), os.path.getsize(full)

    @staticmethod
    def _zip(paths):
        out = io.BytesIO()
        with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
            for p in paths:
                base = os.path.dirname(os.path.abspath(p.rstrip("/\\")))
                if os.path.isfile(p):
                    z.write(p, os.path.relpath(p, base))
                else:
                    for root, _, files in os.walk(p):
                        for f in files:
                            full = os.path.join(root, f)
                            z.write(full, os.path.relpath(full, base))
        return out.getvalue()

    def _apply(self, name, header, payload):
        kind = header.get("kind")
        cb = self.clipboard
        if kind == "text":
            text = payload.decode("utf-8", "replace")
            cb.setText(text)
            what = f"text ({len(text)} characters)"
        elif kind == "image":
            img = QImage.fromData(payload, "PNG")
            cb.setImage(img)
            what = f"image ({img.width()}x{img.height()})"
        elif kind == "files":
            folder = os.path.join(self.saveDir, time.strftime("%Y-%m-%d %H-%M-%S"))
            os.makedirs(folder, exist_ok=True)
            with zipfile.ZipFile(io.BytesIO(payload)) as z:
                for member in z.namelist():  # refuse paths that would escape the folder
                    target = os.path.realpath(os.path.join(folder, member))
                    if not target.startswith(os.path.realpath(folder) + os.sep):
                        raise ValueError("unsafe path in received files")
                z.extractall(folder)
            md = QMimeData()
            md.setUrls([QUrl.fromLocalFile(os.path.join(folder, n)) for n in header.get("names", [])])
            cb.setMimeData(md)
            what = f"{len(header.get('names', []))} file(s), {_human(header.get('size', len(payload)))}"
        else:
            return
        self._last_applied = header.get("hash", "")
        self._last_sent = self._last_applied  # don't send it back when the mouse leaves
        self.toast.emit(f"Clipboard from {name}: {what}. Ready to paste.")
        self._note(f"Flow: received {what} from {name}")

    # -- triggers -------------------------------------------------------------------------------
    @Slot(bool)
    def mouseConnection(self, connected):
        """Called when the hub's mouse connection changes."""
        if connected == self._mouse_here:
            return
        self._mouse_here = connected
        if not self.enabled or not self.core.peers():
            return
        if connected:
            self._arrived_at = time.monotonic()
            if self._pending and time.monotonic() - self._pending[0] < PENDING_S:
                _, name, header, payload = self._pending
                self._pending = None
                self._apply(name, header, payload)
            else:
                threading.Thread(target=self.core.send_all, args=({"kind": "pull"},), daemon=True).start()
        else:
            self._left_at = time.monotonic()
            self.sendClipboard(reason="mouse switched away")

    @Slot()
    def sendNow(self):
        self.sendClipboard(reason="sent by hand", force=True)

    def sendClipboard(self, reason="", force=False):
        snap = self.snapshot()
        if not snap:
            if force:
                self.toast.emit("Nothing to send: the clipboard is empty or not supported.")
            return
        header, payload, digest = snap
        if not force and digest in (self._last_sent, self._last_applied):
            return
        if force:
            header["now"] = True  # apply on arrival instead of waiting for the mouse
        self._last_sent = digest
        what = header["kind"] if header["kind"] != "files" else f"{len(header['names'])} file(s)"

        def send():  # network on a worker thread so big files don't freeze the window
            sent = self.core.send_all(header, payload)
            if sent:
                self.logRequested.emit(f"Flow: sent {what} to {', '.join(sent)} ({reason})")
            else:
                self._last_sent = ""

        threading.Thread(target=send, daemon=True, name="flow-send").start()

    def _on_message(self, peer_id, name, header, payload):
        if not self.enabled:
            return
        kind = header.get("kind")
        if kind == "pull":
            # Only answer if the mouse really switched away from this PC just now; otherwise
            # starting the hub on the other PC would overwrite its clipboard with ours.
            if (not self._mouse_here and self._left_at is not None
                    and time.monotonic() - self._left_at < PENDING_S):
                self.sendClipboard(reason=f"{name} asked")
            return
        just_arrived = self._mouse_here and time.monotonic() - self._arrived_at < JUST_ARRIVED_S
        if header.get("now") or just_arrived:
            self._apply(name, header, payload)
        else:
            self._pending = (time.monotonic(), name, header, payload)
            self._note(f"Flow: {kind} from {name} waiting for the mouse")
