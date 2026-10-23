"""MT760 button table (firmware remapping), decoded from A HUB's writes.

The table lives at 0x600 in config memory: 11 entries of 4 bytes, in A HUB's order.
Entry formats (verified with A HUB + Frida, see NOTES.md):
    03 00 <mask> 00    mouse button (01 left, 02 right, 04 middle, 08 back, 10 forward)
    01 00 <usage> 00   keyboard key (HID usage id)
    02 00 <mods> <usage>  key combination (mods = HID modifier mask: 01 ctrl, 02 shift, 04 alt, 08 win)
    08 00 03 00        DPI cycle+
    0c 00 01|02 00     wheel forward / back
    0b 00 01|02 00     wheel left / right (thumb wheel)

Phase 3: a control that has actions is remapped to a spare key (F13...) that only this hub
listens for; clearing its actions restores the factory entry.
"""
TABLE_ADDR = 0x600
ORDER = ["left", "middle", "right", "diy", "dpi", "forward", "back",
         "wheel_up", "wheel_down", "wheel_left", "wheel_right"]
DEFAULTS = {
    "left": "03000100", "middle": "03000400", "right": "03000200", "diy": "01002400",
    "dpi": "08000300", "forward": "03001000", "back": "03000800",
    "wheel_up": "0c000100", "wheel_down": "0c000200",
    "wheel_left": "0b000100", "wheel_right": "0b000200",
}

# Controls the hub remaps in firmware, and the spare F-key each one sends.
FIRMWARE_KEYS = {"dpi": 13, "diy": 14, "right": 15, "wheel_up": 16, "wheel_down": 17}
WHEEL_CONTROLS = ("wheel_up", "wheel_down")  # no press/hold: click trigger only


def address(control):
    return TABLE_ADDR + 4 * ORDER.index(control)


def f_key_entry(n):
    """Entry that makes the button send F<n> (F13..F24)."""
    return bytes([0x01, 0x00, 0x68 + n - 13, 0x00]).hex()


def f_key_vk(n):
    return 0x7C + n - 13  # VK_F13 = 0x7C


def signal_entry(control):
    return f_key_entry(FIRMWARE_KEYS[control])


VK_TO_CONTROL = {f_key_vk(n): c for c, n in FIRMWARE_KEYS.items()}

_MOUSE = {0x01: "Left click", 0x02: "Right click", 0x04: "Middle click", 0x08: "Back", 0x10: "Forward"}
_MODS = [(0x01, "Ctrl"), (0x02, "Shift"), (0x04, "Alt"), (0x08, "Win")]


def usage_name(u):
    if 0x04 <= u <= 0x1D:
        return chr(ord("A") + u - 0x04)
    if 0x1E <= u <= 0x26:
        return str(u - 0x1D)
    if u == 0x27:
        return "0"
    if 0x3A <= u <= 0x45:
        return f"F{u - 0x39}"
    if 0x68 <= u <= 0x73:
        return f"F{u - 0x5B}"
    return {0x28: "Enter", 0x29: "Esc", 0x2A: "Backspace", 0x2B: "Tab", 0x2C: "Space"}.get(u, f"key 0x{u:02x}")


def describe_entry(hexstr):
    b = bytes.fromhex(hexstr)
    if len(b) != 4 or b == b"\xff\xff\xff\xff":
        return "unset"
    t = b[0]
    if t == 0x03:
        return _MOUSE.get(b[2], f"mouse 0x{b[2]:02x}")
    if t == 0x01:
        return usage_name(b[2])
    if t == 0x02:
        mods = [n for m, n in _MODS if b[2] & m]
        return "+".join(mods + [usage_name(b[3])])
    if t == 0x08:
        return "DPI cycle"
    if t == 0x0C:
        return "Wheel forward" if b[2] == 1 else "Wheel back"
    if t == 0x0B:
        return "Wheel left" if b[2] == 1 else "Wheel right"
    return hexstr


def desired_table(bound_controls):
    """control -> entry hex the mouse should hold, for every firmware-remappable control.
    bound_controls: controls with actions in any profile, so switching apps never rewrites the mouse."""
    return {c: signal_entry(c) if c in bound_controls else DEFAULTS[c] for c in FIRMWARE_KEYS}
