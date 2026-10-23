"""Bridge between the QML interface and the hub (device worker, config, action runner)."""
import ctypes as C
import ctypes.wintypes as W
import os
import sys
import time
import winreg

from PySide6.QtCore import Property, QObject, QThread, QTimer, QUrl, Qt, Signal, Slot

import keymap
import winput
import winsys
from actions import ACTION_TYPES, MEDIA, _process_path, describe
from config import APP_DIR, BUTTONS, DEFAULT_PROFILE, TRIGGERS, triggers_for
from device import (REPORT_CONFIG_CHANGED, BluetoothMouse, DeviceError, EventListener, MouseUnreachable,
                    MT760, parse_status)

POLL_MS = 250              # fast tick: check the current DPI level byte
CONNECT_TICKS = 4          # look for the mouse once a second while it's unplugged
DPI_TABLE_TICKS = 12       # full DPI table every 3 s (the level alone is checked every tick)
WIRELESS_LEVEL_TICKS = 2   # wireless: check the level twice a second (receiver ~26 ms, Bluetooth ~55 ms a read)
BATTERY_REFRESH_TICKS = 40  # 10 s; battery reports from the mouse also update it at once
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
RUN_NAME = "MT760Hub"
ACTIVITY_MAX = 200
FOREGROUND_MS = 400

_user32 = C.WinDLL("user32")
_user32.GetForegroundWindow.restype = W.HWND
_user32.GetWindowThreadProcessId.argtypes = [W.HWND, C.POINTER(W.DWORD)]
_user32.IsWindowVisible.argtypes = [W.HWND]
_user32.GetWindowTextLengthW.argtypes = [W.HWND]
_user32.GetWindowTextW.argtypes = [W.HWND, W.LPWSTR, C.c_int]

# Every control A HUB lists for the MT760, in its order.
#   hook     key the button hooks bind ("" = can't be assigned)
#   firmware True when assigning it remaps the button on the mouse (Phase 3)
#   view/x/y hotspot on assets/mouse_top.svg or mouse_bottom.svg (fractions of the image)
CONTROLS = [
    {"key": "left", "label": "Left click", "hook": "", "firmware": False, "view": "top", "x": 0.386, "y": 0.205},
    {"key": "right", "label": "Right click", "hook": "right", "firmware": True, "view": "top", "x": 0.69, "y": 0.205},
    {"key": "middle", "label": "Middle click", "hook": "middle", "firmware": False, "view": "top", "x": 0.529, "y": 0.18},
    {"key": "forward", "label": "Forward", "hook": "xbutton2", "firmware": False, "view": "top", "x": 0.212, "y": 0.414},
    {"key": "back", "label": "Back", "hook": "xbutton1", "firmware": False, "view": "top", "x": 0.198, "y": 0.598},
    {"key": "dpi", "label": "DPI button", "hook": "dpi", "firmware": True, "view": "top", "x": 0.529, "y": 0.345},
    {"key": "diy", "label": "DIY button", "hook": "diy", "firmware": True, "view": "bottom", "x": 0.581, "y": 0.407},
    {"key": "wheel_up", "label": "Wheel forward", "hook": "wheel_up", "firmware": True, "view": "top", "x": 0.529, "y": 0.118},
    {"key": "wheel_down", "label": "Wheel back", "hook": "wheel_down", "firmware": True, "view": "top", "x": 0.529, "y": 0.245},
    {"key": "thumb_left", "label": "Thumb wheel left", "hook": "tilt_left", "firmware": False, "view": "top", "x": 0.198, "y": 0.507},
    {"key": "thumb_right", "label": "Thumb wheel right", "hook": "tilt_right", "firmware": False, "view": "top", "x": 0.198, "y": 0.507},
]


class Worker(QObject):
    """Owns the device. Lives on its own thread so HID timeouts never freeze the window."""

    connection = Signal(bool, str)
    battery = Signal(int, int)
    dpi = Signal(object)
    info = Signal(str, int)  # firmware, polling rate Hz (0 = unknown)
    liveDpi = Signal(int)    # DPI the mouse just announced (BB B0 status report)
    keymap = Signal(object)  # control -> entry hex, as stored on the mouse
    error = Signal(str)
    _event = Signal(bytes)   # from the listener threads, delivered on the worker thread

    def __init__(self, config):
        super().__init__()
        self.config = config
        self.dev = None
        self.listener = None
        self.ticks = 0
        self.timer = None
        self.level = -1
        self._event.connect(self._on_event)

    @Slot()
    def start(self):
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.poll)
        self.timer.start(POLL_MS)
        self.ticks = CONNECT_TICKS - 1  # connect on the first tick
        self.poll()

    def _drop(self, msg):
        if self.listener:
            self.listener.stop()
            self.listener = None
        if self.dev:
            self.dev.close()
            self.dev = None
        self.connection.emit(False, msg)

    def _emit_dpi(self):
        info = self.dev.dpi_info()
        self.level = info.current
        self.dpi.emit(info)

    @Slot(bytes)
    def _on_event(self, report):
        """Unsolicited report from the mouse: react at once, like A HUB does."""
        if not self.dev:
            return
        try:
            status = parse_status(report)
            if status:
                dpi, pct = status
                self.liveDpi.emit(dpi)
                self.battery.emit(pct, 0)
            elif report[0] == REPORT_CONFIG_CHANGED:
                self._emit_dpi()
        except OSError:
            pass  # the next tick notices a real disconnect

    @Slot()
    def poll(self):
        self.ticks += 1
        if not self.dev:
            if self.ticks % CONNECT_TICKS:
                return
            status = "Mouse not found. Turn it on or plug in the cable."
            try:
                self.dev = MT760()
            except MouseUnreachable:
                status = "Receiver connected, mouse asleep or in another mode"
            except DeviceError:
                pass
            except OSError as e:
                status = f"Cannot open mouse ({e})"
            if not self.dev:
                self.dev = BluetoothMouse.find()
                if not self.dev:
                    self.connection.emit(False, status)
                    return
            self.ticks = 0
            try:
                self.info.emit(self.dev.firmware(), self.dev.polling_rate() or 0)
            except OSError:
                pass
            self.connection.emit(True, self.dev.name)
            self.sync_keymap()
            self.listener = EventListener(self.dev.paths, self._event.emit)
            self.listener.start()
            if isinstance(self.dev, BluetoothMouse):
                self.dev.on_event = self._event.emit  # status reports arrive as GATT notifications
        try:
            if self.ticks % BATTERY_REFRESH_TICKS == 0:
                self.battery.emit(*self.dev.battery())
            wired = self.dev.name == "USB cable"
            check_level = wired or self.ticks % WIRELESS_LEVEL_TICKS == 0
            if self.ticks % DPI_TABLE_TICKS == 0 or (check_level and self.dev.dpi_level() != self.level):
                self._emit_dpi()
        except OSError:
            self._drop("Connection lost. Close A HUB if it's running.")

    @Slot()
    def sync_keymap(self):
        """Make the mouse's button table match the profile (Phase 3 remaps)."""
        if not self.dev or not self.dev.writable:
            return
        try:
            self.keymap.emit(self.dev.sync_keymap(keymap.desired_table(self.config.bound_controls)))
        except OSError as e:
            self.error.emit(f"Could not update the mouse's buttons: {e}")

    @Slot(int)
    def set_level(self, level):
        if not self.dev or not self.dev.writable:
            self.error.emit("DPI can be changed over the cable or the 2.4 GHz receiver (read-only over Bluetooth).")
            return
        try:
            self.dev.set_dpi_level(level)
            self._emit_dpi()
        except OSError as e:
            self.error.emit(f"Could not set DPI level: {e}")

    @Slot(str, int)
    def dpi_action(self, mode, level):
        if not self.dev or not self.dev.writable:
            self.error.emit("DPI action skipped: changing DPI needs the cable or the 2.4 GHz receiver.")
            return
        try:
            info = self.dev.dpi_info()
            if mode == "next":
                target = (info.current + 1) % info.levels
            elif mode == "prev":
                target = (info.current - 1) % info.levels
            else:
                target = max(0, min(info.levels - 1, level - 1))
            if target != info.current:
                self.dev.set_dpi_level(target)
            self._emit_dpi()
        except OSError as e:
            self.error.emit(f"DPI action failed: {e}")

    @Slot()
    def stop(self):
        if self.timer:
            self.timer.stop()
        if self.listener:
            self.listener.stop()
            self.listener = None
        if self.dev:
            self.dev.close()
            self.dev = None


class Hub(QObject):
    deviceChanged = Signal()
    bindingsChanged = Signal()
    settingsChanged = Signal()
    activityChanged = Signal()
    windowsChanged = Signal()
    toast = Signal(str)
    hideRequested = Signal()
    pausedToggled = Signal(bool)
    _requestLevel = Signal(int)
    _requestStop = Signal()
    dpiActionRequested = Signal(str, int)
    logRequested = Signal(str)
    _requestSync = Signal()
    profilesChanged = Signal()

    def __init__(self, config, runner):
        super().__init__()
        self.config = config
        self.runner = runner
        self._connected = False
        self._conn_text = "Searching..."
        self._battery = -1
        self._charging = False
        self._dpi_values = []
        self._dpi_current = -1
        self._firmware = ""
        self._polling = 0
        self._activity = []
        self._rev = 0
        self._keymap = {}
        self._live_dpi = 0
        self._editing = DEFAULT_PROFILE
        self._last_exe = ""
        self._dpi_restore = 0  # level to go back to after leaving a profile that set DPI
        self._fg_timer = QTimer(self)
        self._fg_timer.timeout.connect(self._check_foreground)
        self._fg_timer.start(FOREGROUND_MS)

        self.thread = QThread(self)
        self.worker = Worker(config)
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.start)
        self.worker.connection.connect(self._on_connection)
        self.worker.battery.connect(self._on_battery)
        self.worker.dpi.connect(self._on_dpi)
        self.worker.info.connect(self._on_info)
        self.worker.liveDpi.connect(self._on_live_dpi)
        self.worker.error.connect(self.log)
        self.worker.keymap.connect(self._on_keymap)
        self._requestSync.connect(self.worker.sync_keymap)
        self._requestLevel.connect(self.worker.set_level)
        self.dpiActionRequested.connect(self.worker.dpi_action)
        self.logRequested.connect(self.log)
        self._requestStop.connect(self.worker.stop, Qt.BlockingQueuedConnection)
        self.thread.start()

    def shutdown(self):
        self._requestStop.emit()
        self.thread.quit()
        self.thread.wait(2000)

    # -- worker -> UI -----------------------------------------------------------------------
    def _on_connection(self, ok, text):
        if ok != self._connected or text != self._conn_text:
            self._connected, self._conn_text = ok, text
            if not ok:
                self._battery = -1
            if not ok or text == BluetoothMouse.transport.name:  # Bluetooth uses its own DPI table
                self._dpi_values, self._dpi_current, self._polling, self._firmware = [], -1, 0, ""
                self._live_dpi = 0
            self.deviceChanged.emit()

    def _on_battery(self, pct, state):
        # The state byte reads 1 on cable and wireless alike, so it isn't a charging flag;
        # the mouse charges whenever it's on the USB cable.
        self._battery, self._charging = pct, self._conn_text == "USB cable"
        self.deviceChanged.emit()

    def _on_dpi(self, info):
        self._dpi_values, self._dpi_current = list(info.values), info.current
        if self._conn_text == BluetoothMouse.transport.name and self._live_dpi in info.values:
            # Bluetooth doesn't save button presses to memory: the announced value is the truth
            self._dpi_current = info.values.index(self._live_dpi)
        elif 0 <= info.current < len(info.values):
            self._live_dpi = info.values[info.current]
        self.deviceChanged.emit()

    def _on_live_dpi(self, dpi):
        """The mouse announced its DPI (button press). Over Bluetooth this is the only way to
        see it, since the change isn't written to the mouse's memory."""
        self._live_dpi = dpi
        if not (0 <= self._dpi_current < len(self._dpi_values) and self._dpi_values[self._dpi_current] == dpi):
            self._dpi_current = self._dpi_values.index(dpi) if dpi in self._dpi_values else -1
        self.deviceChanged.emit()

    def _on_info(self, firmware, polling):
        self._firmware, self._polling = firmware, polling
        self.deviceChanged.emit()

    def _on_keymap(self, table):
        changed = [c for c in keymap.FIRMWARE_KEYS if self._keymap.get(c) not in (None, table.get(c))]
        self._keymap = dict(table)
        for c in changed:
            self.log(f"Mouse: {BUTTONS[c]} now sends {keymap.describe_entry(table[c])}")
        self.bindingsChanged.emit()

    @Slot(str)
    def log(self, msg):
        self._activity.insert(0, f"{time.strftime('%H:%M:%S')}  {msg}")
        del self._activity[ACTIVITY_MAX:]
        self.activityChanged.emit()

    # -- device properties --------------------------------------------------------------------
    connected = Property(bool, lambda s: s._connected, notify=deviceChanged)
    connectionText = Property(str, lambda s: s._conn_text, notify=deviceChanged)
    # cable or receiver: settings can be read and changed (not over Bluetooth)
    configurable = Property(bool, lambda s: s._connected, notify=deviceChanged)
    # settings can be changed: cable or receiver (Bluetooth is read-only)
    writable = Property(bool, lambda s: s._connected and s._conn_text != BluetoothMouse.transport.name,
                        notify=deviceChanged)
    battery = Property(int, lambda s: s._battery, notify=deviceChanged)
    charging = Property(bool, lambda s: s._charging, notify=deviceChanged)
    dpiValues = Property("QVariantList", lambda s: s._dpi_values, notify=deviceChanged)
    dpiCurrent = Property(int, lambda s: s._dpi_current, notify=deviceChanged)
    liveDpi = Property(int, lambda s: s._live_dpi, notify=deviceChanged)
    firmware = Property(str, lambda s: s._firmware, notify=deviceChanged)
    pollingRate = Property(int, lambda s: s._polling, notify=deviceChanged)
    activity = Property("QVariantList", lambda s: s._activity, notify=activityChanged)

    @Slot(int)
    def setDpiLevel(self, level):
        if level != self._dpi_current:
            self._requestLevel.emit(level)

    # -- controls and bindings ----------------------------------------------------------------
    controls = Property("QVariantList", lambda s: CONTROLS, constant=True)
    revision = Property(int, lambda s: s._rev, notify=bindingsChanged)
    actionTypes = Property("QVariantList", lambda s: [{"key": k, "label": v} for k, v in ACTION_TYPES.items()],
                           constant=True)
    mediaKeys = Property("QVariantList", lambda s: [{"key": k, "label": v} for k, v in MEDIA.items()],
                         constant=True)

    @Slot(str, result="QVariantList")
    def triggersFor(self, hook):
        if not hook:
            return []
        return [{"key": t, "label": TRIGGERS[t]} for t in triggers_for(hook)]

    @Slot(str, str, result="QVariantMap")
    def binding(self, hook, trigger):
        """The editing profile's own action for this trigger ({} if it doesn't set one)."""
        return dict(self.config.get_in(self._editing, hook, trigger) or {})

    @Slot(str, str, result=str)
    def inherited(self, hook, trigger):
        """For app profiles: what Default does for a trigger the profile leaves unset."""
        if self._editing == DEFAULT_PROFILE:
            return ""
        return describe(self.config.get_in(DEFAULT_PROFILE, hook, trigger) or {})

    @Slot(str, result=int)
    def bindingCount(self, hook):
        if not hook:
            return 0
        return len(self.config.profile(self._editing).get("bindings", {}).get(hook, {}))

    @Slot(str, result="QVariantMap")
    def mouseEntry(self, hook):
        """What the mouse's own table says for a firmware control: label + whether it's ours."""
        entry = self._keymap.get(hook)
        if not entry or hook not in keymap.FIRMWARE_KEYS:
            return {}
        return {"label": keymap.describe_entry(entry), "ours": entry == keymap.signal_entry(hook),
                "synced": entry == keymap.desired_table(self.config.bound_controls)[hook]}

    @Slot()
    def resetMouseButtons(self):
        """Drop all Phase 3 actions and put the factory mapping back on the mouse."""
        for name in self.config.profile_names():
            for c in keymap.FIRMWARE_KEYS:
                for t in list(self.config.profile(name)["bindings"].get(c, {})):
                    self.config.set_binding(c, t, None, profile=name)
        self._rev += 1
        self.bindingsChanged.emit()
        self._after_binding_change("right")
        self.log("Mouse buttons reset to factory mapping.")

    def _after_binding_change(self, hook):
        if hook in keymap.FIRMWARE_KEYS:
            if self._connected:
                self._requestSync.emit()
            else:
                self.toast.emit("Saved. It's stored on the mouse the next time it connects.")

    @Slot("QVariantMap", result=str)
    def describe(self, action):
        return describe(dict(action)) if action else ""

    @Slot(str, str, "QVariantMap", result=str)
    def saveBinding(self, hook, trigger, action):
        """Validate and store. Returns an error message, or '' on success."""
        a = {k: v for k, v in dict(action).items() if v not in (None, "")}
        t = a.get("type")
        if t in ("run", "focus"):
            path = str(a.get("path", "")).strip().strip('"')
            if not os.path.exists(path):
                return "That program or script doesn't exist."
            a["path"] = os.path.normpath(path)
            a["admin"] = bool(a.get("admin"))
            if t == "run":
                a["hidden"] = bool(a.get("hidden"))
            else:
                a.pop("hidden", None)
        elif t == "open":
            if not str(a.get("target", "")).strip():
                return "Enter a file, folder or website to open."
        elif t == "keys":
            try:
                winput.parse_combo(str(a.get("combo", "")))
            except ValueError as e:
                return f"Shortcut not recognised: {e}"
            a["combo"] = str(a["combo"]).strip().lower()
        elif t == "media":
            if a.get("key") not in MEDIA:
                return "Choose a media key."
        elif t == "dpi":
            a["mode"] = a.get("mode", "next")
            a["level"] = int(a.get("level", 1))
        else:
            return "Choose an action type."
        self.config.set_binding(hook, trigger, a, profile=self._editing)
        self._rev += 1
        self.bindingsChanged.emit()
        self.log(f"Saved ({self._editing}): {BUTTONS[hook]} {TRIGGERS[trigger].lower()} -> {describe(a)}")
        self._after_binding_change(hook)
        return ""

    @Slot(str, str)
    def clearBinding(self, hook, trigger):
        self.config.set_binding(hook, trigger, None, profile=self._editing)
        self._rev += 1
        self.bindingsChanged.emit()
        self._after_binding_change(hook)

    @Slot(str, str)
    def testBinding(self, hook, trigger):
        action = (self.config.get_in(self._editing, hook, trigger)
                  or self.config.get_in(DEFAULT_PROFILE, hook, trigger))
        if action:
            self.runner.submit(action, f"Test {BUTTONS[hook]}")

    @Slot(QUrl, result=str)
    def localPath(self, url):
        return os.path.normpath(url.toLocalFile()) if url.isLocalFile() else url.toString()

    # -- settings -----------------------------------------------------------------------------
    paused = Property(bool, lambda s: bool(s.config.settings.get("paused")), notify=settingsChanged)
    longPressMs = Property(int, lambda s: s.config.settings["long_press_ms"], notify=settingsChanged)
    doubleClickMs = Property(int, lambda s: s.config.settings["double_click_ms"], notify=settingsChanged)
    gesturePx = Property(int, lambda s: s.config.settings.get("gesture_px", 60), notify=settingsChanged)
    autoSwitch = Property(bool, lambda s: bool(s.config.settings.get("auto_switch", True)), notify=settingsChanged)

    @Slot(int)
    def setGesturePx(self, v):
        self.config.set_setting("gesture_px", int(v))
        self.settingsChanged.emit()

    @Slot(bool)
    def setAutoSwitch(self, on):
        self.config.set_setting("auto_switch", on)
        self.settingsChanged.emit()
        self._check_foreground()

    darkMode = Property(bool, lambda s: s.config.settings.get("theme", "dark") == "dark", notify=settingsChanged)
    configDir = Property(str, lambda s: APP_DIR, constant=True)

    @Slot(bool)
    def setPaused(self, on):
        if bool(self.config.settings.get("paused")) != on:
            self.config.set_setting("paused", on)
            self.settingsChanged.emit()
            self.pausedToggled.emit(on)
            self.log("Button actions paused." if on else "Button actions resumed.")

    @Slot(int)
    def setLongPressMs(self, v):
        self.config.set_setting("long_press_ms", int(v))
        self.settingsChanged.emit()

    @Slot(int)
    def setDoubleClickMs(self, v):
        self.config.set_setting("double_click_ms", int(v))
        self.settingsChanged.emit()

    @Slot(bool)
    def setDarkMode(self, on):
        self.config.set_setting("theme", "dark" if on else "light")
        self.settingsChanged.emit()

    def _autostart(self):
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as k:
                winreg.QueryValueEx(k, RUN_NAME)
                return True
        except OSError:
            return False

    autostart = Property(bool, _autostart, notify=settingsChanged)

    @Slot(bool)
    def setAutostart(self, on):
        pyw = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
        exe = pyw if os.path.exists(pyw) else sys.executable
        main = os.path.join(os.path.dirname(os.path.abspath(__file__)), "main.py")
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as k:
                if on:
                    winreg.SetValueEx(k, RUN_NAME, 0, winreg.REG_SZ, f'"{exe}" "{main}" --tray')
                else:
                    try:
                        winreg.DeleteValue(k, RUN_NAME)
                    except FileNotFoundError:
                        pass
        except OSError as e:
            self.toast.emit(f"Could not change startup setting: {e}")
        self.settingsChanged.emit()

    # -- profiles ----------------------------------------------------------------------------
    profiles = Property("QVariantList", lambda s: s.config.profile_names(), notify=profilesChanged)
    activeProfile = Property(str, lambda s: s.config.active, notify=profilesChanged)
    editingProfile = Property(str, lambda s: s._editing, notify=profilesChanged)
    foregroundApp = Property(str, lambda s: s._last_exe, notify=profilesChanged)

    @Slot(str)
    def setEditingProfile(self, name):
        if name in self.config.data["profiles"] and name != self._editing:
            self._editing = name
            self.profilesChanged.emit()
            self._rev += 1
            self.bindingsChanged.emit()

    @Slot(str, result="QVariantMap")
    def profileInfo(self, name):
        p = self.config.profile(name)
        if not p:
            return {}
        return {"name": name, "apps": p.get("apps", []), "dpiLevel": p.get("dpi_level", 0),
                "actions": sum(len(t) for t in p.get("bindings", {}).values()),
                "isDefault": name == DEFAULT_PROFILE, "active": name == self.config.active}

    @Slot(str, result=str)
    def addProfile(self, name):
        name = name.strip()
        if not name:
            return "Enter a name."
        if name in self.config.data["profiles"]:
            return "A profile with that name already exists."
        self.config.add_profile(name)
        self.profilesChanged.emit()
        self.setEditingProfile(name)
        return ""

    @staticmethod
    def _exe_name(path_or_exe):
        return os.path.basename(path_or_exe.strip().strip('"')).lower()

    @Slot(str, result=str)
    def addProfileForApp(self, path_or_exe):
        """New profile named after an app, matching that app."""
        exe = self._exe_name(path_or_exe)
        if not exe.endswith(".exe"):
            return "Choose an .exe file."
        existing = self.config.profile_for_exe(exe)
        if existing != DEFAULT_PROFILE:
            return f"{exe} already belongs to profile '{existing}'."
        base = os.path.splitext(exe)[0].capitalize()
        name, n = base, 2
        while name in self.config.data["profiles"]:
            name, n = f"{base} {n}", n + 1
        self.config.add_profile(name, [exe])
        self.profilesChanged.emit()
        self.setEditingProfile(name)
        return ""

    @Slot(str)
    def deleteProfile(self, name):
        if name == DEFAULT_PROFILE:
            return
        self.config.delete_profile(name)
        if self._editing == name:
            self._editing = DEFAULT_PROFILE
        self.profilesChanged.emit()
        self._rev += 1
        self.bindingsChanged.emit()
        self._after_binding_change("right")  # its firmware controls may no longer be needed

    @Slot(str, str, result=str)
    def renameProfile(self, old, new):
        new = new.strip()
        if not self.config.rename_profile(old, new):
            return "That name can't be used."
        if self._editing == old:
            self._editing = new
        self.profilesChanged.emit()
        return ""

    @Slot(str, str, result=str)
    def addProfileApp(self, name, path_or_exe):
        exe = self._exe_name(path_or_exe)
        if not exe.endswith(".exe"):
            return "Choose an .exe file."
        other = self.config.profile_for_exe(exe)
        if other not in (DEFAULT_PROFILE, name):
            return f"{exe} already belongs to profile '{other}'."
        self.config.set_profile_apps(name, self.config.profile(name)["apps"] + [exe])
        self.profilesChanged.emit()
        self._check_foreground()
        return ""

    @Slot(str, str)
    def removeProfileApp(self, name, exe):
        self.config.set_profile_apps(name, [a for a in self.config.profile(name)["apps"] if a != exe])
        self.profilesChanged.emit()
        self._check_foreground()

    @Slot(str, int)
    def setProfileDpi(self, name, level):
        self.config.set_profile_dpi(name, level)
        self.profilesChanged.emit()

    @Slot(result="QVariantList")
    def runningApps(self):
        """Apps with visible windows right now, for the "add app" picker."""
        seen = {}
        skip = {"explorer.exe", "applicationframehost.exe", "textinputhost.exe", "shellexperiencehost.exe"}
        proc = C.WINFUNCTYPE(W.BOOL, W.HWND, W.LPARAM)

        def cb(hwnd, _):
            if _user32.IsWindowVisible(hwnd) and _user32.GetWindowTextLengthW(hwnd):
                pid = W.DWORD()
                _user32.GetWindowThreadProcessId(hwnd, C.byref(pid))
                if pid.value != os.getpid():
                    exe = os.path.basename(_process_path(pid.value)).lower()
                    if exe and exe not in seen and exe not in skip:
                        buf = C.create_unicode_buffer(256)
                        _user32.GetWindowTextW(hwnd, buf, 256)
                        seen[exe] = buf.value
            return True

        _user32.EnumWindows(proc(cb), 0)
        return [{"exe": e, "title": t} for e, t in sorted(seen.items())]

    def _check_foreground(self):
        hwnd = _user32.GetForegroundWindow()
        if not hwnd:
            return
        pid = W.DWORD()
        _user32.GetWindowThreadProcessId(hwnd, C.byref(pid))
        if pid.value == os.getpid():
            return  # editing in the hub shouldn't switch profiles
        exe = os.path.basename(_process_path(pid.value)).lower()
        auto = self.config.settings.get("auto_switch", True)
        target = self.config.profile_for_exe(exe) if auto else DEFAULT_PROFILE
        changed_exe = exe != self._last_exe
        self._last_exe = exe
        if target == self.config.active:
            if changed_exe:
                self.profilesChanged.emit()
            return
        self.config.set_active(target)
        self.log(f"Profile: {target}" + (f" ({exe})" if target != DEFAULT_PROFILE else ""))
        self._apply_profile_dpi(target)
        self.profilesChanged.emit()

    def _apply_profile_dpi(self, name):
        # Each DPI change is a write to the mouse's flash, so only profiles that ask for it do.
        level = self.config.profile(name).get("dpi_level", 0)
        if level:
            if not self._dpi_restore and self._dpi_current >= 0:
                self._dpi_restore = self._dpi_current + 1
            if level != self._dpi_current + 1:
                self.dpiActionRequested.emit("set", level)
        elif self._dpi_restore:
            if self._dpi_restore != self._dpi_current + 1:
                self.dpiActionRequested.emit("set", self._dpi_restore)
            self._dpi_restore = 0

    # -- Windows mouse settings ---------------------------------------------------------------
    wheelLines = Property(int, lambda s: winsys.wheel_lines(), notify=windowsChanged)
    pointerSpeed = Property(int, lambda s: winsys.pointer_speed(), notify=windowsChanged)

    @Slot(int)
    def setWheelLines(self, lines):
        winsys.set_wheel_lines(lines)
        self.windowsChanged.emit()

    @Slot(int)
    def setPointerSpeed(self, speed):
        winsys.set_pointer_speed(speed)
        self.windowsChanged.emit()

    @Slot()
    def hideWindow(self):
        self.hideRequested.emit()
