"""Rapoo MT760 over USB cable, 2.4 GHz receiver or Bluetooth.

Protocol (recovered from RapooDevice.dll and verified on the device, see NOTES.md):
    request : output report 0xBA, 32 bytes, on the 32-byte vendor collection
              BA <sub> A4 <len> <addr:u32 LE>          read config memory (len multiple of 8)
              BA <sub> A5 <len> <addr:u32 LE> <data>   write config memory
              BA <sub> A3                              firmware version
              BA <sub> AA                              battery (getElectricity)
    sub     : FF on the cable, A5 through the receiver
Bluetooth : same config memory over the Telink GATT service with one-byte opcodes; see
            BluetoothMouse. (The HID vendor collection over Bluetooth only echoes requests.)
    reply   : HidD_GetInputReport(0xBA) -> [status] [04 04 01] [data...]
              status 01 = OK, 02 = timeout (receiver can't reach the mouse), 00 = no answer yet
"""
import ctypes as C
import ctypes.wintypes as W
import re
import threading
import time
from dataclasses import dataclass

import keymap
from hidlib import Dev, hid, paths
from hidlib import k as k32

OP_READ, OP_WRITE = 0xA4, 0xA5
OP_FIRMWARE = 0xA3
OP_BATTERY = 0xAA  # internal command 0x7DA, getElectricity
STATUS_OK, STATUS_TIMEOUT = 0x01, 0x02

# Config memory map (current profile). Verified against A HUB's DPI page:
# 0x638: 7 x u16 DPI/50 (800/1000/1200/2400/4000/3200/4000), 0x646: levels-1, 0x648: current.
ADDR_DPI_BLOCK = 0x638
OFF_TABLE = 0x00
OFF_LEVELS = 0x0E
OFF_CURRENT = 0x10
ADDR_DPI_LEVEL = ADDR_DPI_BLOCK + OFF_CURRENT  # 0x648, verified by diff and write
DPI_TABLE_SLOTS = 7
DPI_UNIT = 50
ADDR_POLLING = 0x634  # 01 while A HUB showed 250 Hz
POLLING_RATES = {0: 125, 1: 250, 2: 500, 3: 1000}  # index order from A HUB, values unverified

REPORT_CONFIG_CHANGED = 0xBC  # A HUB re-reads DPI when this arrives (MouseForTelink8373 0x6fec3c00)
REPORT_STATUS = 0xBB          # BB B0 01 <dpi u16 LE> 01 <battery %>, sent on every DPI change


def parse_status(report):
    """(dpi, battery %) from a BB B0 status report, or None. Verified: bb b0 01 60 09 01 63 =
    2400 DPI, 99 %. It arrives on every DPI button press in all three connection modes."""
    if len(report) >= 7 and report[0] == REPORT_STATUS and report[1] == 0xB0:
        return report[3] | report[4] << 8, min(report[6], 100)
    return None


@dataclass(frozen=True)
class Transport:
    name: str           # shown in the UI
    match: tuple        # substrings every HID path of this connection contains
    sub: int            # second byte of every request
    reply_timeout: float  # how long to wait for the mouse's answer
    retries: int = 0      # resends after a timeout reply


# Tried in this order.
TRANSPORTS = (
    Transport("USB cable", ("vid_24ae", "pid_4500"), 0xFF, 0.3),
    Transport("2.4 GHz receiver", ("vid_24ae", "pid_1870"), 0xA5, 0.8, 2),
)
VENDOR_CHANNELS = ("col04", "col05", "mi_02")


class DeviceError(OSError):
    pass


class MouseUnreachable(DeviceError):
    """The receiver is plugged in but the mouse isn't answering (asleep or in another mode)."""


def _instances(transport):
    """Group a transport's vendor HID paths by physical device (receivers can be plugged in twice)."""
    groups, extra = {}, []
    for p in paths(list(transport.match)):
        pl = p.lower()
        if not any(c in pl for c in VENDOR_CHANNELS):
            continue
        if "mi_02" in pl:
            # Windows gives MI_02 its own instance id, unrelated to MI_01's collections, so it
            # can't be matched to a receiver; listening on an extra channel is harmless.
            extra.append(p)
            continue
        # collections of one interface share the instance id up to the last "&<index>"
        key = pl.split("#")[2].rsplit("&", 1)[0] if pl.count("#") >= 2 else pl
        groups.setdefault(key, []).append(p)
    return [g + extra for g in groups.values()]


class EventListener:
    """Reads the mouse's unsolicited reports on every vendor channel of one connection.

    Uses its own handles: a blocking ReadFile on a shared handle would stall the worker's
    requests. on_report(bytes) is called from the reader threads.
    """

    def __init__(self, device_paths, on_report):
        self.paths = device_paths
        self.on_report = on_report
        self.devs = []
        self.threads = []
        self.running = False

    def start(self):
        self.running = True
        for p in self.paths:
            try:
                d = Dev(p)
            except OSError:
                continue
            if not d.caps.In:
                d.close()
                continue
            self.devs.append(d)
            t = threading.Thread(target=self._loop, args=(d,), name="mt760-events", daemon=True)
            t.start()
            self.threads.append(t)

    def _loop(self, dev):
        buf = C.create_string_buffer(max(dev.caps.In, 8))
        n = W.DWORD()
        while self.running:
            if not k32.ReadFile(C.c_void_p(dev.h), buf, dev.caps.In, C.byref(n), None):
                break  # cancelled on stop, or the mouse went away
            if n.value:
                try:
                    self.on_report(buf.raw[:n.value])
                except Exception:
                    pass

    def stop(self):
        self.running = False
        for d in self.devs:
            k32.CancelIoEx(C.c_void_p(d.h), None)
        for t in self.threads:
            t.join(1)
        for d in self.devs:
            d.close()
        self.devs, self.threads = [], []


@dataclass
class DpiInfo:
    levels: int
    current: int  # 0-based
    values: list  # DPI per level


class MT760:
    """Connect over the first transport where the mouse actually answers.

    Raises MouseUnreachable if only a receiver is present, DeviceError if nothing is found.
    """

    configurable = True  # settings can be read
    writable = True      # settings can be changed

    def __init__(self, transports=TRANSPORTS):
        self.cmd = None
        self.transport = None
        self.paths = []
        receiver_only = False
        for t in transports:
            for group in _instances(t):
                cmd = self._open_command_channel(group)
                if not cmd:
                    continue
                self.cmd, self.transport, self.paths = cmd, t, group
                try:
                    self.firmware()  # proves the mouse itself answers, not just a receiver
                    return
                except MouseUnreachable:
                    receiver_only = True
                except DeviceError:
                    pass
                self.close()
        if receiver_only:
            raise MouseUnreachable("Receiver found, but the mouse isn't answering")
        raise DeviceError("MT760 not found")

    @staticmethod
    def _open_command_channel(group):
        for p in group:
            try:
                d = Dev(p)
            except OSError:
                continue
            if d.caps.Out == 32:
                return d
            d.close()
        return None

    @property
    def name(self):
        return self.transport.name if self.transport else ""

    def close(self):
        if self.cmd:
            self.cmd.close()
        self.cmd = None

    # -- requests ---------------------------------------------------------------------------------
    def _request(self, payload):
        """Send BA <sub> <payload...> and return the reply once the mouse has answered.
        Wireless links drop the odd packet, so a timeout is retried before giving up."""
        tries = 1 + self.transport.retries
        for attempt in range(tries):
            try:
                return self._request_once(payload)
            except MouseUnreachable:
                if attempt == tries - 1:
                    raise
                time.sleep(0.05)

    def _request_once(self, payload):
        ok, _ = self.cmd.write([0xBA, self.transport.sub, *payload])
        if not ok:
            raise DeviceError("write to mouse failed")
        deadline = time.monotonic() + self.transport.reply_timeout
        time.sleep(0.015)
        while True:
            b = C.create_string_buffer(32)
            b[0] = 0xBA
            if not hid.HidD_GetInputReport(C.c_void_p(self.cmd.h), b, 32):
                raise DeviceError("no reply from mouse")
            r = b.raw
            if r[0] == STATUS_OK:
                return r
            if r[0] == STATUS_TIMEOUT:
                raise MouseUnreachable("the mouse didn't answer")
            if time.monotonic() > deadline:
                raise DeviceError(f"no answer (status {r[0]:#x})")
            time.sleep(0.01)

    def read(self, addr, length):
        want = length
        length = (length + 7) & ~7
        out = b""
        while length > 0:
            n = min(length, 0x18)
            r = self._request([OP_READ, n, *addr.to_bytes(4, "little")])
            out += r[4:4 + n]
            addr += n
            length -= n
        return out[:want]

    def write(self, addr, data):
        data = bytes(data)
        if len(data) > 0x18:
            raise ValueError("write too long")
        self._request([OP_WRITE, len(data), *addr.to_bytes(4, "little"), *data])

    def firmware(self):
        """'V0.1.4.4' style version; every reply carries it reversed after the status byte."""
        r = self._request([OP_FIRMWARE])
        return f"V0.{r[3]}.{r[2]}.{r[1]}"

    def polling_rate(self):
        """Polling rate in Hz, or None if the stored index is unknown."""
        return POLLING_RATES.get(self.read(ADDR_POLLING, 1)[0])

    def dpi_level(self):
        """Current DPI level (0-based) with a single 8-byte read, cheap enough to poll fast."""
        return self.read(ADDR_DPI_LEVEL, 1)[0]

    def dpi_info(self):
        b = self.read(ADDR_DPI_BLOCK, OFF_CURRENT + 1)
        levels = max(1, min(DPI_TABLE_SLOTS, b[OFF_LEVELS] + 1))
        values = [int.from_bytes(b[OFF_TABLE + 2 * i:OFF_TABLE + 2 * i + 2], "little") * DPI_UNIT
                  for i in range(DPI_TABLE_SLOTS)]
        return DpiInfo(levels, b[OFF_CURRENT], values[:levels])

    def set_dpi_level(self, level):
        """Set the 0-based DPI level. Each write uses up part of the mouse's save counter."""
        self.write(ADDR_DPI_LEVEL, [level])
        if self.read(ADDR_DPI_LEVEL, 1)[0] != level:
            raise DeviceError("DPI level did not stick")

    def keymap(self):
        """control -> 4-byte entry hex for the whole button table."""
        b = self.read(keymap.TABLE_ADDR, 4 * len(keymap.ORDER))
        return {c: b[4 * i:4 * i + 4].hex() for i, c in enumerate(keymap.ORDER)}

    def sync_keymap(self, desired):
        """Write only the entries that differ (each write uses up part of the save counter)."""
        current = self.keymap()
        for control, entry in desired.items():
            if current.get(control) != entry:
                self.write(keymap.address(control), bytes.fromhex(entry))
        return self.keymap()

    def battery(self):
        """(percent, state) via getElectricity (opcode 0xAA), as A HUB does.

        Reply: [status 01] [BatStatus] [percent]. A HUB caps percent at 100 and passes BatStatus
        through; on the cable it reads 1, presumably "charging".
        """
        r = self._request([OP_BATTERY])
        return min(r[2], 100), r[1]


# -- Bluetooth --------------------------------------------------------------------------------
# HID\{00001812-...}_DEV_VID&0224AE_PID&4500_REV&0404_<address>&COL04 exists only while connected.
# Settings go over the Telink GATT service with A HUB's one-byte Bluetooth opcodes
# (command table in FUN_6fd300e0): 0x7D5 write = 01, 0x7D4 read = 02, 0x7DB = 03,
# 0x7DA battery = 04, 0x7D3 firmware = 05. Requests go to ...ba03, replies arrive on ...ba02:
#     [status 01] [3 bytes] [data...]   (battery: [01] [percent])
BT_MATCH = ("00001812-", "vid&0224ae_pid&4500", "col04")
BT_SERVICE = "00010203-0405-0607-0809-0a0b0c0dba01"
BT_WRITE = "00010203-0405-0607-0809-0a0b0c0dba03"
BT_NOTIFY = "00010203-0405-0607-0809-0a0b0c0dba02"
BT_OP_WRITE, BT_OP_READ, BT_OP_BATTERY, BT_OP_FIRMWARE = 0x01, 0x02, 0x04, 0x05
BT_CHUNK = 0x10        # a 20-byte notification holds 4 header bytes + 16 data bytes
BT_DPI_BLOCK = 0x64C   # second DPI block, used while on Bluetooth
BT_OFF_TABLE, BT_OFF_LEVELS, BT_OFF_CURRENT = 0x00, 0x0E, 0x10
BT_REPLY_TIMEOUT = 1.0


class BluetoothMouse(MT760):
    """The mouse over Bluetooth LE: settings are readable, but the firmware acknowledges memory
    writes (opcode 01) without applying them, so changes need the cable or the receiver.
    Never send 03 here: it's 0x7DB SET_DG_RESTORE."""

    configurable = True
    writable = False
    transport = Transport("Bluetooth", BT_MATCH, 0, BT_REPLY_TIMEOUT, 2)
    paths = []  # no HID event channels; the worker polls the DPI level instead

    def __init__(self, address):
        import blegatt
        self.address = address
        self.cmd = None
        self._lock = threading.Lock()
        self._reply = None
        self._got = threading.Event()
        paths_ = blegatt.service_paths(BT_SERVICE, address)
        if not paths_:
            raise DeviceError("Bluetooth service not available")
        try:
            self.channel = blegatt.GattChannel(paths_[0], BT_WRITE, BT_NOTIFY, self._on_notify)
        except OSError as e:
            raise DeviceError(f"Bluetooth: {e}")
        self.firmware()  # proves the mouse answers

    @classmethod
    def find(cls):
        """Connect to the first Bluetooth-connected MT760, or return None."""
        for p in paths(list(BT_MATCH)):
            m = re.search(r"_([0-9a-f]{12})&col04", p.lower())
            if m:
                try:
                    return cls(int(m.group(1), 16))
                except DeviceError:
                    continue
        return None

    def present(self):
        return any(f"{self.address:012x}&col04" in p.lower() for p in paths(list(BT_MATCH)))

    def close(self):
        if getattr(self, "channel", None):
            self.channel.close()
            self.channel = None

    on_event = None  # set by the worker: unsolicited reports (BB B0 status) go there

    def _on_notify(self, data):
        if data and data[0] == REPORT_STATUS:
            if self.on_event:
                self.on_event(bytes(data))
            return
        self._reply = data
        self._got.set()

    def _bt_request(self, payload):
        with self._lock:
            for attempt in range(1 + self.transport.retries):
                self._got.clear()
                try:
                    self.channel.write(payload)
                except OSError as e:
                    raise DeviceError(f"Bluetooth write failed: {e}")
                if self._got.wait(self.transport.reply_timeout):
                    r = self._reply
                    if r and r[0] == STATUS_OK:
                        return r
                time.sleep(0.05)
            raise MouseUnreachable("the mouse didn't answer over Bluetooth")

    # The high-level methods of MT760 (dpi_info, set_dpi_level, keymap, ...) use these.
    def read(self, addr, length):
        want = length
        length = (length + 7) & ~7
        out = b""
        while length > 0:
            n = min(length, BT_CHUNK)
            r = self._bt_request([BT_OP_READ, n, *addr.to_bytes(4, "little")])
            out += r[4:4 + n]
            addr += n
            length -= n
        return out[:want]

    def write(self, addr, data):
        raise DeviceError("Over Bluetooth the mouse's settings are read-only; use the cable or receiver.")

    def dpi_info(self):
        """Over Bluetooth the mouse uses the second DPI block: table at 0x64C (7 x u16 / 50),
        levels-1 at 0x65A, stored level at 0x65C. DPI presses over Bluetooth aren't saved there, so
        the live value comes from BB B0 status reports."""
        b = self.read(BT_DPI_BLOCK, BT_OFF_CURRENT + 1)
        levels = max(1, min(DPI_TABLE_SLOTS, b[BT_OFF_LEVELS] + 1))
        values = [int.from_bytes(b[BT_OFF_TABLE + 2 * i:BT_OFF_TABLE + 2 * i + 2], "little") * DPI_UNIT
                  for i in range(DPI_TABLE_SLOTS)]
        current = b[BT_OFF_CURRENT] if b[BT_OFF_CURRENT] < levels else 0
        return DpiInfo(levels, current, values[:levels])

    def dpi_level(self):
        return self.read(BT_DPI_BLOCK + BT_OFF_CURRENT, 1)[0]

    def firmware(self):
        r = self._bt_request([BT_OP_FIRMWARE])
        return f"V0.{r[3]}.{r[2]}.{r[1]}"

    def battery(self):
        r = self._bt_request([BT_OP_BATTERY])
        return min(r[1], 100), 0
