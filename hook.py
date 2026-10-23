"""Low-level mouse + keyboard hooks for button actions.

Mouse hook (WH_MOUSE_LL): side buttons, middle click and wheel tilt.
Keyboard hook (WH_KEYBOARD_LL): the spare F13-F17 keys that firmware-remapped controls
(DPI, DIY, right click, wheel) send; see keymap.py. Those keys are always swallowed, and a
press without an action falls back to the control's factory behaviour.

Mouse hook details:

Works in every connection mode (cable, 2.4 GHz, Bluetooth) because it sees what Windows
receives, not the mouse protocol. Rules:
  - A button with no bindings (or while paused) passes straight through.
  - A bound button is swallowed; on release we decide click / double / long press.
  - If the decided trigger isn't bound (e.g. only "long" is set and you short-click), the
    original click is replayed so the button keeps its normal behaviour.
The hook callback must return fast (Windows drops hooks that take ~300 ms+), so it only
does bookkeeping; actions are handed to the runner's thread pool.
"""
import ctypes as C
import ctypes.wintypes as W
import threading
import time

import keymap
import winput
from config import GESTURES, SCROLLS

user32 = C.WinDLL("user32", use_last_error=True)
kernel32 = C.WinDLL("kernel32", use_last_error=True)

WH_KEYBOARD_LL = 13
WH_MOUSE_LL = 14
WM_KEYDOWN, WM_KEYUP, WM_SYSKEYDOWN, WM_SYSKEYUP = 0x0100, 0x0101, 0x0104, 0x0105
WM_QUIT = 0x0012
WM_MBUTTONDOWN, WM_MBUTTONUP = 0x0207, 0x0208
WM_XBUTTONDOWN, WM_XBUTTONUP = 0x020B, 0x020C
WM_MOUSEMOVE, WM_MOUSEWHEEL, WM_MOUSEHWHEEL = 0x0200, 0x020A, 0x020E
TILT_REPEAT_S = 0.25  # holding the wheel sideways repeats; treat a burst as one click

LRESULT = C.c_ssize_t
HOOKPROC = C.WINFUNCTYPE(LRESULT, C.c_int, W.WPARAM, W.LPARAM)


class MSLLHOOKSTRUCT(C.Structure):
    _fields_ = [("pt", W.POINT), ("mouseData", W.DWORD), ("flags", W.DWORD), ("time", W.DWORD),
                ("dwExtraInfo", C.c_size_t)]


class KBDLLHOOKSTRUCT(C.Structure):
    _fields_ = [("vkCode", W.DWORD), ("scanCode", W.DWORD), ("flags", W.DWORD), ("time", W.DWORD),
                ("dwExtraInfo", C.c_size_t)]


user32.SetWindowsHookExW.argtypes = [C.c_int, HOOKPROC, W.HINSTANCE, W.DWORD]
user32.SetWindowsHookExW.restype = C.c_void_p
user32.CallNextHookEx.argtypes = [C.c_void_p, C.c_int, W.WPARAM, W.LPARAM]
user32.CallNextHookEx.restype = LRESULT
user32.UnhookWindowsHookEx.argtypes = [C.c_void_p]
user32.GetMessageW.argtypes = [C.POINTER(W.MSG), W.HWND, W.UINT, W.UINT]
user32.PostThreadMessageW.argtypes = [W.DWORD, W.UINT, W.WPARAM, W.LPARAM]
kernel32.GetModuleHandleW.argtypes = [W.LPCWSTR]
kernel32.GetModuleHandleW.restype = W.HMODULE
user32.GetCursorPos.argtypes = [C.POINTER(W.POINT)]


class _State:
    def __init__(self):
        self.swallowed = False
        self.long_fired = False
        self.long_timer = None
        self.pending = None  # timer waiting to see whether a second click follows
        self.triggers = {}
        self.last_tilt = 0.0
        self.gesture = False   # gesture triggers bound: freeze the cursor and track movement
        self.start = (0, 0)
        self.dx = self.dy = 0
        self.used = False      # a gesture or hold+scroll consumed this press


class ButtonHook:
    def __init__(self, config, on_trigger, on_default=None):
        """on_trigger(button, trigger) is called from hook/timer threads; keep it quick.
        on_default(button) performs a factory behaviour we can't inject (DPI cycle)."""
        self.config = config
        self.on_trigger = on_trigger
        self.on_default = on_default
        self.state = {}
        self.held = None  # button currently held with gesture or scroll triggers
        self.lock = threading.Lock()
        self.thread = None
        self.tid = None
        self.error = None
        self._ready = threading.Event()

    # -- lifecycle ---------------------------------------------------------------------------
    def start(self):
        self.thread = threading.Thread(target=self._run, name="mouse-hook", daemon=True)
        self.thread.start()
        self._ready.wait(5)
        if self.error:
            raise OSError(f"SetWindowsHookEx failed ({self.error})")

    def stop(self):
        if self.tid:
            user32.PostThreadMessageW(self.tid, WM_QUIT, 0, 0)
        if self.thread:
            self.thread.join(2)

    def _run(self):
        self.tid = kernel32.GetCurrentThreadId()
        self._cb = HOOKPROC(self._proc)  # keep references or they get garbage-collected
        self._kcb = HOOKPROC(self._key_proc)
        module = kernel32.GetModuleHandleW(None)
        hook = user32.SetWindowsHookExW(WH_MOUSE_LL, self._cb, module, 0)
        khook = user32.SetWindowsHookExW(WH_KEYBOARD_LL, self._kcb, module, 0)
        if not hook or not khook:
            self.error = C.get_last_error()
            for h in (hook, khook):
                if h:
                    user32.UnhookWindowsHookEx(h)
            self._ready.set()
            return
        self._ready.set()
        msg = W.MSG()
        while user32.GetMessageW(C.byref(msg), None, 0, 0) > 0:
            pass
        user32.UnhookWindowsHookEx(hook)
        user32.UnhookWindowsHookEx(khook)

    # -- hook ----------------------------------------------------------------------------------
    def _proc(self, n, wparam, lparam):
        if n == 0:
            info = C.cast(lparam, C.POINTER(MSLLHOOKSTRUCT)).contents
            if info.dwExtraInfo != winput.MAGIC:
                try:
                    if self._handle(wparam, info):
                        return 1
                except Exception:
                    pass  # never let an exception break the user's mouse
        return user32.CallNextHookEx(None, n, wparam, lparam)

    def _key_proc(self, n, wparam, lparam):
        if n == 0:
            info = C.cast(lparam, C.POINTER(KBDLLHOOKSTRUCT)).contents
            control = keymap.VK_TO_CONTROL.get(info.vkCode)
            if control and info.dwExtraInfo != winput.MAGIC:
                try:
                    down = wparam in (WM_KEYDOWN, WM_SYSKEYDOWN)
                    self._firmware_key(control, down)
                except Exception:
                    pass
                return 1  # the spare key itself never reaches applications
        return user32.CallNextHookEx(None, n, wparam, lparam)

    def _firmware_key(self, control, down):
        if control in keymap.WHEEL_CONTROLS:
            if down and self._chord_scroll(control == "wheel_up"):
                return
            if down:
                if "click" in self._bound(control):
                    self.on_trigger(control, "click")
                else:
                    self._default(control)
            return
        with self.lock:
            st = self.state.setdefault(control, _State())
            if down:
                if not st.swallowed:  # ignore key autorepeat while held
                    self._press(control, st, force=True)
            else:
                self._release(control, st)

    def _default(self, button):
        """Perform a button's normal behaviour after we swallowed it."""
        if button == "dpi":
            if self.on_default:
                self.on_default(button)
            return
        # Not from inside a hook callback: injected input is delivered to our own hooks.
        threading.Thread(target=winput.click_button, args=(button,), daemon=True).start()

    def _bound(self, button):
        if self.config.settings.get("paused"):
            return {}
        return self.config.bindings.get(button, {})

    def _handle(self, msg, info):
        if msg in (WM_XBUTTONDOWN, WM_XBUTTONUP):
            button = {1: "xbutton1", 2: "xbutton2"}.get((info.mouseData >> 16) & 0xFFFF)
            down = msg == WM_XBUTTONDOWN
        elif msg in (WM_MBUTTONDOWN, WM_MBUTTONUP):
            button, down = "middle", msg == WM_MBUTTONDOWN
        elif msg == WM_MOUSEMOVE:
            return self._move(info.pt.x, info.pt.y) if self.held else False
        elif msg == WM_MOUSEWHEEL:
            delta = C.c_short((info.mouseData >> 16) & 0xFFFF).value
            return self._chord_scroll(delta > 0) if self.held else False
        elif msg == WM_MOUSEHWHEEL:
            delta = C.c_short((info.mouseData >> 16) & 0xFFFF).value
            return self._tilt("tilt_right" if delta > 0 else "tilt_left")
        else:
            return False
        if not button:
            return False
        with self.lock:
            st = self.state.setdefault(button, _State())
            return self._press(button, st) if down else self._release(button, st)

    def _press(self, button, st, force=False):
        triggers = self._bound(button)
        if not triggers and not force:
            st.swallowed = False
            return False
        st.swallowed, st.long_fired, st.triggers = True, False, triggers
        st.used, st.dx, st.dy = False, 0, 0
        st.gesture = any(g in triggers for g in GESTURES)
        if st.gesture or any(t in triggers for t in SCROLLS):
            pt = W.POINT()
            user32.GetCursorPos(C.byref(pt))
            st.start = (pt.x, pt.y)
            self.held = (button, st)
        if "long" in triggers:
            st.long_timer = threading.Timer(self.config.settings["long_press_ms"] / 1000,
                                            self._long, (button, st))
            st.long_timer.start()
        return True

    def _release(self, button, st):
        if not st.swallowed:
            return False
        st.swallowed = False
        if self.held and self.held[0] == button:
            self.held = None
        if st.long_timer:
            st.long_timer.cancel()
            st.long_timer = None
        if st.long_fired or st.used:
            return True
        direction = self._gesture_direction(st)
        if direction:
            if direction in st.triggers:
                self.on_trigger(button, direction)
            return True
        if "double" in st.triggers:
            if st.pending:
                st.pending.cancel()
                st.pending = None
                self.on_trigger(button, "double")
            else:
                st.pending = threading.Timer(self.config.settings["double_click_ms"] / 1000,
                                             self._single, (button, st, st.triggers))
                st.pending.start()
        else:
            self._single(button, st, st.triggers)
        return True

    def _single(self, button, st, triggers):
        st.pending = None
        if "click" in triggers:
            self.on_trigger(button, "click")
        else:
            self._default(button)

    # -- gestures and hold + scroll -----------------------------------------------------------
    def _gesture_direction(self, st):
        if not st.gesture:
            return None
        if max(abs(st.dx), abs(st.dy)) < self.config.settings.get("gesture_px", 60):
            return None
        if abs(st.dx) >= abs(st.dy):
            return "gesture_right" if st.dx > 0 else "gesture_left"
        return "gesture_down" if st.dy > 0 else "gesture_up"

    def _move(self, x, y):
        held = self.held
        if not held:
            return False
        button, st = held
        if not st.gesture:
            return False
        # The cursor stays frozen while we swallow moves, so each event's offset from the
        # press point is just that event's movement.
        st.dx += x - st.start[0]
        st.dy += y - st.start[1]
        if st.long_timer and max(abs(st.dx), abs(st.dy)) >= self.config.settings.get("gesture_px", 60):
            st.long_timer.cancel()  # moving turns a hold into a gesture, not a long press
            st.long_timer = None
        return True

    def _chord_scroll(self, up):
        held = self.held
        if not held:
            return False
        button, st = held
        trigger = "scroll_up" if up else "scroll_down"
        if trigger not in st.triggers:
            return False
        st.used = True
        if st.long_timer:
            st.long_timer.cancel()
            st.long_timer = None
        self.on_trigger(button, trigger)
        return True

    def _long(self, button, st):
        with self.lock:
            if not st.swallowed or st.used:
                return
            st.long_fired = True
        self.on_trigger(button, "long")

    def _tilt(self, button):
        if "click" not in self._bound(button):
            return False
        with self.lock:
            st = self.state.setdefault(button, _State())
            now = time.monotonic()
            repeat = now - st.last_tilt < TILT_REPEAT_S
            st.last_tilt = now
        if not repeat:
            self.on_trigger(button, "click")
        return True
