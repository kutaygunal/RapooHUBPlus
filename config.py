"""Profiles and settings, stored as JSON in %APPDATA%\\MT760Hub\\profiles.json.

Layout:
    {
      "version": 2,
      "active_profile": "Default",
      "settings": {"long_press_ms": 450, "double_click_ms": 300, "gesture_px": 60,
                   "auto_switch": true, "paused": false, "theme": "dark"},
      "profiles": {
        "Default": {"apps": [], "dpi_level": 0, "bindings": {"xbutton1": {"click": {action}}}},
        "Chrome":  {"apps": ["chrome.exe"], "dpi_level": 4, "bindings": {...}}
      }
    }
An action is a dict with a "type" key; see actions.py for the fields of each type.
App profiles only hold overrides: anything they don't set falls back to Default.
dpi_level is 1-based; 0 means "don't change DPI".
"""
import copy
import json
import os
import threading

APP_DIR = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "MT760Hub")
CONFIG_PATH = os.path.join(APP_DIR, "profiles.json")
DEFAULT_PROFILE = "Default"

BUTTONS = {
    "xbutton1": "Back (side button)",
    "xbutton2": "Forward (side button)",
    "middle": "Middle click",
    "tilt_left": "Thumb wheel left",
    "tilt_right": "Thumb wheel right",
    # Phase 3: remapped on the mouse to a spare F-key (see keymap.py)
    "right": "Right click",
    "dpi": "DPI button",
    "diy": "DIY button",
    "wheel_up": "Wheel forward",
    "wheel_down": "Wheel back",
}
TRIGGERS = {
    "click": "Click",
    "double": "Double click",
    "long": "Long press",
    "gesture_up": "Hold + move up",
    "gesture_down": "Hold + move down",
    "gesture_left": "Hold + move left",
    "gesture_right": "Hold + move right",
    "scroll_up": "Hold + scroll up",
    "scroll_down": "Hold + scroll down",
}
GESTURES = ("gesture_up", "gesture_down", "gesture_left", "gesture_right")
SCROLLS = ("scroll_up", "scroll_down")
CLICK_ONLY = ("click",)  # wheels have no press/release, so only plain clicks

DEFAULT = {
    "version": 2,
    "active_profile": DEFAULT_PROFILE,
    "settings": {"long_press_ms": 450, "double_click_ms": 300, "gesture_px": 60,
                 "auto_switch": True, "paused": False, "theme": "dark"},
    "profiles": {DEFAULT_PROFILE: {"apps": [], "dpi_level": 0, "bindings": {}}},
}


def triggers_for(button):
    return CLICK_ONLY if button.startswith(("tilt", "wheel")) else tuple(TRIGGERS)


class Config:
    """Thread-safe config. The hooks read `bindings`, `bound_controls` and `settings` without
    locking, so changes always replace those objects instead of mutating them."""

    def __init__(self, path=CONFIG_PATH):
        self.path = path
        self._lock = threading.Lock()
        self.data = self._load()
        self.active = DEFAULT_PROFILE  # app profiles activate at runtime, not from the file
        self._publish()

    def _load(self):
        try:
            with open(self.path, encoding="utf-8") as f:
                data = json.load(f)
        except FileNotFoundError:
            return copy.deepcopy(DEFAULT)
        merged = copy.deepcopy(DEFAULT)
        merged.update(data)
        merged["settings"] = {**DEFAULT["settings"], **data.get("settings", {})}
        profiles = merged.setdefault("profiles", {})
        profiles.setdefault(DEFAULT_PROFILE, {})
        for p in profiles.values():
            p.setdefault("apps", [])
            p.setdefault("dpi_level", 0)
            p.setdefault("bindings", {})
        merged["version"] = 2
        return merged

    def _publish(self):
        profiles = self.data["profiles"]
        merged = copy.deepcopy(profiles[DEFAULT_PROFILE]["bindings"])
        if self.active != DEFAULT_PROFILE and self.active in profiles:
            for button, triggers in profiles[self.active]["bindings"].items():
                merged.setdefault(button, {}).update(copy.deepcopy(triggers))
        self.bindings = merged
        self.bound_controls = frozenset(b for p in profiles.values() for b, t in p["bindings"].items() if t)
        self.settings = dict(self.data["settings"])

    def save(self):
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self.data, f, indent=2)
        os.replace(tmp, self.path)

    def _change(self, fn):
        with self._lock:
            fn(self.data)
            self._publish()
            self.save()

    # -- bindings -------------------------------------------------------------------------------
    def get(self, button, trigger):
        """Effective action (active profile over Default), as the hooks see it."""
        return self.bindings.get(button, {}).get(trigger)

    def get_in(self, profile, button, trigger):
        return self.data["profiles"].get(profile, {}).get("bindings", {}).get(button, {}).get(trigger)

    def set_binding(self, button, trigger, action, profile=DEFAULT_PROFILE):
        def fn(d):
            b = d["profiles"][profile]["bindings"]
            if action:
                b.setdefault(button, {})[trigger] = action
            else:
                b.get(button, {}).pop(trigger, None)
                if not b.get(button):
                    b.pop(button, None)
        self._change(fn)

    # -- profiles -------------------------------------------------------------------------------
    def profile_names(self):
        names = [n for n in self.data["profiles"] if n != DEFAULT_PROFILE]
        return [DEFAULT_PROFILE] + sorted(names, key=str.lower)

    def profile(self, name):
        return copy.deepcopy(self.data["profiles"].get(name, {}))

    def add_profile(self, name, apps=()):
        def fn(d):
            d["profiles"].setdefault(name, {"apps": list(apps), "dpi_level": 0, "bindings": {}})
        self._change(fn)

    def delete_profile(self, name):
        if name == DEFAULT_PROFILE:
            return
        self._change(lambda d: d["profiles"].pop(name, None))
        if self.active == name:
            self.set_active(DEFAULT_PROFILE)

    def rename_profile(self, old, new):
        if old == DEFAULT_PROFILE or not new or new in self.data["profiles"]:
            return False
        self._change(lambda d: d["profiles"].__setitem__(new, d["profiles"].pop(old)))
        if self.active == old:
            self.active = new
            self._publish()
        return True

    def set_profile_apps(self, name, apps):
        clean = sorted({a.strip().lower() for a in apps if a.strip()})
        self._change(lambda d: d["profiles"][name].__setitem__("apps", clean))

    def set_profile_dpi(self, name, level):
        self._change(lambda d: d["profiles"][name].__setitem__("dpi_level", int(level)))

    def profile_for_exe(self, exe):
        exe = (exe or "").lower()
        for name, p in self.data["profiles"].items():
            if name != DEFAULT_PROFILE and exe in p.get("apps", []):
                return name
        return DEFAULT_PROFILE

    def set_active(self, name):
        with self._lock:
            self.active = name if name in self.data["profiles"] else DEFAULT_PROFILE
            self._publish()

    # -- settings -------------------------------------------------------------------------------
    def set_setting(self, key, value):
        self._change(lambda d: d["settings"].__setitem__(key, value))
