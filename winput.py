"""SendInput helpers. Everything we inject carries MAGIC in dwExtraInfo so our own hook ignores it."""
import ctypes as C
import ctypes.wintypes as W

user32 = C.WinDLL("user32", use_last_error=True)

MAGIC = 0x4D543736  # "MT76"

INPUT_MOUSE, INPUT_KEYBOARD = 0, 1
KEYEVENTF_EXTENDEDKEY, KEYEVENTF_KEYUP = 0x1, 0x2
MOUSEEVENTF_MIDDLEDOWN, MOUSEEVENTF_MIDDLEUP = 0x20, 0x40
MOUSEEVENTF_XDOWN, MOUSEEVENTF_XUP = 0x80, 0x100
MOUSEEVENTF_HWHEEL = 0x1000
XBUTTON1, XBUTTON2 = 1, 2


class MOUSEINPUT(C.Structure):
    _fields_ = [("dx", W.LONG), ("dy", W.LONG), ("mouseData", W.DWORD), ("dwFlags", W.DWORD),
                ("time", W.DWORD), ("dwExtraInfo", C.c_size_t)]


class KEYBDINPUT(C.Structure):
    _fields_ = [("wVk", W.WORD), ("wScan", W.WORD), ("dwFlags", W.DWORD), ("time", W.DWORD),
                ("dwExtraInfo", C.c_size_t)]


class HARDWAREINPUT(C.Structure):
    _fields_ = [("uMsg", W.DWORD), ("wParamL", W.WORD), ("wParamH", W.WORD)]


class _U(C.Union):
    _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT), ("hi", HARDWAREINPUT)]


class INPUT(C.Structure):
    _fields_ = [("type", W.DWORD), ("u", _U)]


user32.SendInput.argtypes = [W.UINT, C.POINTER(INPUT), C.c_int]
user32.SendInput.restype = W.UINT


def _send(items):
    arr = (INPUT * len(items))(*items)
    user32.SendInput(len(items), arr, C.sizeof(INPUT))


def _mouse(flags, data=0):
    i = INPUT(type=INPUT_MOUSE)
    i.u.mi = MOUSEINPUT(0, 0, data, flags, 0, MAGIC)
    return i


def _key(vk, up=False):
    flags = (KEYEVENTF_KEYUP if up else 0) | (KEYEVENTF_EXTENDEDKEY if vk in EXTENDED else 0)
    i = INPUT(type=INPUT_KEYBOARD)
    i.u.ki = KEYBDINPUT(vk, 0, flags, 0, MAGIC)
    return i


MOUSEEVENTF_RIGHTDOWN, MOUSEEVENTF_RIGHTUP = 0x08, 0x10
MOUSEEVENTF_WHEEL = 0x0800


def click_button(button):
    """Replay a press+release of a mouse button we swallowed (or a remapped control's default)."""
    if button == "right":
        _send([_mouse(MOUSEEVENTF_RIGHTDOWN), _mouse(MOUSEEVENTF_RIGHTUP)])
    elif button in ("wheel_up", "wheel_down"):
        delta = 120 if button == "wheel_up" else -120
        _send([_mouse(MOUSEEVENTF_WHEEL, delta & 0xFFFFFFFF)])
    elif button == "diy":
        tap_key(ord("7"))  # factory DIY mapping is the "7" key
    elif button == "middle":
        _send([_mouse(MOUSEEVENTF_MIDDLEDOWN), _mouse(MOUSEEVENTF_MIDDLEUP)])
    elif button in ("xbutton1", "xbutton2"):
        x = XBUTTON1 if button == "xbutton1" else XBUTTON2
        _send([_mouse(MOUSEEVENTF_XDOWN, x), _mouse(MOUSEEVENTF_XUP, x)])
    elif button in ("tilt_left", "tilt_right"):
        delta = 120 if button == "tilt_right" else -120
        _send([_mouse(MOUSEEVENTF_HWHEEL, delta & 0xFFFFFFFF)])


# --- keyboard -------------------------------------------------------------------------------
MODIFIERS = {"ctrl": 0x11, "control": 0x11, "shift": 0x10, "alt": 0x12, "win": 0x5B}
NAMED_KEYS = {
    "enter": 0x0D, "return": 0x0D, "tab": 0x09, "esc": 0x1B, "escape": 0x1B, "space": 0x20,
    "backspace": 0x08, "delete": 0x2E, "del": 0x2E, "insert": 0x2D, "home": 0x24, "end": 0x23,
    "pgup": 0x21, "pageup": 0x21, "pgdn": 0x22, "pagedown": 0x22,
    "left": 0x25, "up": 0x26, "right": 0x27, "down": 0x28,
    "printscreen": 0x2C, "prtsc": 0x2C, "capslock": 0x14, "menu": 0x5D,
    "play_pause": 0xB3, "next_track": 0xB0, "prev_track": 0xB1, "stop_media": 0xB2,
    "mute": 0xAD, "volume_down": 0xAE, "volume_up": 0xAF,
    "-": 0xBD, "=": 0xBB, "[": 0xDB, "]": 0xDD, ";": 0xBA, "'": 0xDE, ",": 0xBC, ".": 0xBE,
    "/": 0xBF, "\\": 0xDC, "`": 0xC0,
}
for _i in range(1, 25):
    NAMED_KEYS[f"f{_i}"] = 0x6F + _i
EXTENDED = {0x21, 0x22, 0x23, 0x24, 0x25, 0x26, 0x27, 0x28, 0x2D, 0x2E, 0x5B, 0x5D,
            0xAD, 0xAE, 0xAF, 0xB0, 0xB1, 0xB2, 0xB3}


def parse_combo(text):
    """'ctrl+shift+t' -> ([0x11, 0x10], 0x54). Raises ValueError on unknown keys."""
    parts = [p.strip().lower() for p in text.replace(" ", "").split("+") if p.strip()]
    if not parts:
        raise ValueError("empty shortcut")
    mods = []
    for p in parts[:-1]:
        if p not in MODIFIERS:
            raise ValueError(f"unknown modifier '{p}'")
        mods.append(MODIFIERS[p])
    last = parts[-1]
    if last in MODIFIERS:
        key = MODIFIERS[last]
    elif last in NAMED_KEYS:
        key = NAMED_KEYS[last]
    elif len(last) == 1 and last.isalnum():
        key = ord(last.upper())
    else:
        raise ValueError(f"unknown key '{last}'")
    return mods, key


def send_combo(text):
    mods, key = parse_combo(text)
    seq = [_key(m) for m in mods] + [_key(key), _key(key, True)] + [_key(m, True) for m in reversed(mods)]
    _send(seq)


def tap_key(vk):
    _send([_key(vk), _key(vk, True)])
