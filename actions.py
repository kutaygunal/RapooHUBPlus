"""Action engine: what a button does.

Action dicts (stored in profiles.json):
    {"type": "run",   "path": ..., "args": "", "cwd": "", "admin": false, "hidden": false}
    {"type": "focus", "path": ..., "args": "", "cwd": "", "admin": false}   launch, or bring to front
    {"type": "open",  "target": "C:\\folder" | "https://..." | "file.pdf"}
    {"type": "keys",  "combo": "ctrl+shift+t"}
    {"type": "media", "key": "play_pause" | "next_track" | ... (see MEDIA)}
    {"type": "dpi",   "mode": "next" | "prev" | "set", "level": 1}
Actions run on a small thread pool so the mouse hook never waits on them.
"""
import ctypes as C
import ctypes.wintypes as W
import os
import shutil
import sys
from concurrent.futures import ThreadPoolExecutor

import winput

shell32 = C.WinDLL("shell32", use_last_error=True)
user32 = C.WinDLL("user32", use_last_error=True)
kernel32 = C.WinDLL("kernel32", use_last_error=True)

shell32.ShellExecuteW.argtypes = [W.HWND, W.LPCWSTR, W.LPCWSTR, W.LPCWSTR, W.LPCWSTR, C.c_int]
shell32.ShellExecuteW.restype = C.c_void_p

SW_HIDE, SW_SHOWNORMAL, SW_RESTORE, SW_MINIMIZE = 0, 1, 9, 6

ACTION_TYPES = {
    "run": "Run program or script",
    "focus": "Launch or focus app",
    "open": "Open file, folder or website",
    "keys": "Keyboard shortcut",
    "media": "Media / volume key",
    "dpi": "Change DPI level",
}
MEDIA = {
    "play_pause": "Play / pause", "next_track": "Next track", "prev_track": "Previous track",
    "stop_media": "Stop", "mute": "Mute", "volume_up": "Volume up", "volume_down": "Volume down",
}
SCRIPT_FILTER = "Programs and scripts (*.exe *.bat *.cmd *.ps1 *.py *.pyw *.sh *.lnk);;All files (*)"


def describe(action):
    if not action:
        return ""
    t = action.get("type")
    if t in ("run", "focus"):
        name = os.path.basename(action.get("path", "")) or "?"
        extra = " (admin)" if action.get("admin") else ""
        return f"{'Run' if t == 'run' else 'Launch/focus'} {name}{extra}"
    if t == "open":
        return f"Open {action.get('target', '')}"
    if t == "keys":
        return f"Press {action.get('combo', '')}"
    if t == "media":
        return MEDIA.get(action.get("key"), action.get("key", ""))
    if t == "dpi":
        m = action.get("mode")
        return f"DPI level {action.get('level')}" if m == "set" else f"DPI {m}"
    return t or ""


# --- launching ------------------------------------------------------------------------------
def _find_bash():
    for p in (r"C:\Program Files\Git\bin\bash.exe", r"C:\Program Files (x86)\Git\bin\bash.exe"):
        if os.path.exists(p):
            return p
    found = shutil.which("bash")
    if found and "system32" not in found.lower():  # System32\bash.exe is the WSL shim
        return found
    return None


def _wsl_path(path):
    drive, rest = os.path.splitdrive(os.path.abspath(path))
    return f"/mnt/{drive[0].lower()}{rest.replace(os.sep, '/')}"


def _python(hidden):
    exe_dir = os.path.dirname(sys.executable)
    name = "pythonw.exe" if hidden else "python.exe"
    cand = os.path.join(exe_dir, name)
    return cand if os.path.exists(cand) else sys.executable


def resolve_command(path, args=""):
    """Map a file to (executable, parameters) for ShellExecute, by extension."""
    ext = os.path.splitext(path)[1].lower()
    q = f'"{path}"'
    if ext == ".ps1":
        return "powershell.exe", f"-NoProfile -ExecutionPolicy Bypass -File {q} {args}".strip()
    if ext in (".py", ".pyw"):
        return _python(ext == ".pyw"), f"{q} {args}".strip()
    if ext == ".sh":
        bash = _find_bash()
        if bash:
            return bash, f"{q} {args}".strip()
        if shutil.which("wsl.exe"):
            return "wsl.exe", f'-e bash "{_wsl_path(path)}" {args}'.strip()
        raise RuntimeError("No bash found for .sh (install Git for Windows or WSL)")
    if ext in (".bat", ".cmd"):
        return "cmd.exe", f'/c "{q} {args}"'
    return path, args  # .exe, .lnk, documents: let Windows decide


def run_program(path, args="", cwd="", admin=False, hidden=False):
    if not path:
        raise RuntimeError("no program set")
    if not os.path.exists(path):
        raise RuntimeError(f"not found: {path}")
    exe, params = resolve_command(path, args)
    cwd = cwd or os.path.dirname(path)
    rc = shell32.ShellExecuteW(None, "runas" if admin else "open", exe, params or None, cwd or None,
                               SW_HIDE if hidden else SW_SHOWNORMAL)
    if (rc or 0) <= 32:
        raise RuntimeError(f"Windows could not start it (code {rc})")


def open_target(target):
    if not target:
        raise RuntimeError("nothing to open")
    rc = shell32.ShellExecuteW(None, "open", target, None, None, SW_SHOWNORMAL)
    if (rc or 0) <= 32:
        raise RuntimeError(f"Windows could not open it (code {rc})")


# --- launch or focus ------------------------------------------------------------------------
WNDENUMPROC = C.WINFUNCTYPE(W.BOOL, W.HWND, W.LPARAM)
user32.EnumWindows.argtypes = [WNDENUMPROC, W.LPARAM]
user32.GetWindowThreadProcessId.argtypes = [W.HWND, C.POINTER(W.DWORD)]
user32.IsWindowVisible.argtypes = [W.HWND]
user32.GetWindow.argtypes = [W.HWND, W.UINT]
user32.GetWindow.restype = W.HWND
user32.GetForegroundWindow.restype = W.HWND
user32.IsIconic.argtypes = [W.HWND]
user32.ShowWindow.argtypes = [W.HWND, C.c_int]
user32.SetForegroundWindow.argtypes = [W.HWND]
user32.GetWindowTextLengthW.argtypes = [W.HWND]
kernel32.OpenProcess.restype = W.HANDLE
kernel32.QueryFullProcessImageNameW.argtypes = [W.HANDLE, W.DWORD, W.LPWSTR, C.POINTER(W.DWORD)]
kernel32.CloseHandle.argtypes = [W.HANDLE]
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
GW_OWNER = 4


def _process_path(pid):
    h = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not h:
        return ""
    try:
        buf = C.create_unicode_buffer(1024)
        n = W.DWORD(1024)
        return buf.value if kernel32.QueryFullProcessImageNameW(h, 0, buf, C.byref(n)) else ""
    finally:
        kernel32.CloseHandle(h)


def find_app_window(exe_path):
    want = os.path.normcase(os.path.abspath(exe_path))
    found = []
    cache = {}

    def cb(hwnd, _):
        if not user32.IsWindowVisible(hwnd) or user32.GetWindow(hwnd, GW_OWNER):
            return True
        if not user32.GetWindowTextLengthW(hwnd):
            return True
        pid = W.DWORD()
        user32.GetWindowThreadProcessId(hwnd, C.byref(pid))
        if pid.value not in cache:
            cache[pid.value] = os.path.normcase(_process_path(pid.value))
        if cache[pid.value] == want:
            found.append(hwnd)
            return False
        return True

    user32.EnumWindows(WNDENUMPROC(cb), 0)
    return found[0] if found else None


def bring_to_front(hwnd):
    if user32.IsIconic(hwnd):
        user32.ShowWindow(hwnd, SW_RESTORE)
    # Windows only lets the process that last received input steal focus; tapping Alt
    # (sent by us, so tagged and ignored by our hook) satisfies that rule.
    winput.tap_key(0x12)
    user32.SetForegroundWindow(hwnd)


def launch_or_focus(path, args="", cwd="", admin=False):
    if path.lower().endswith(".exe"):
        hwnd = find_app_window(path)
        if hwnd:
            if hwnd == user32.GetForegroundWindow():
                user32.ShowWindow(hwnd, SW_MINIMIZE)
            else:
                bring_to_front(hwnd)
            return
    run_program(path, args, cwd, admin)


# --- runner ---------------------------------------------------------------------------------
class ActionRunner:
    def __init__(self, dpi_callback=None, log=None):
        self.pool = ThreadPoolExecutor(max_workers=4, thread_name_prefix="action")
        self.dpi_callback = dpi_callback
        self.log = log or (lambda msg: None)

    def submit(self, action, source=""):
        self.pool.submit(self._run, action, source)

    def _run(self, action, source):
        label = describe(action)
        try:
            self.execute(action)
            self.log(f"{source}: {label}")
        except Exception as e:  # report every failure in the activity log
            self.log(f"{source}: {label} FAILED: {e}")

    def execute(self, a):
        t = a.get("type")
        if t == "run":
            run_program(a.get("path", ""), a.get("args", ""), a.get("cwd", ""),
                        a.get("admin", False), a.get("hidden", False))
        elif t == "focus":
            launch_or_focus(a.get("path", ""), a.get("args", ""), a.get("cwd", ""), a.get("admin", False))
        elif t == "open":
            open_target(a.get("target", ""))
        elif t == "keys":
            winput.send_combo(a.get("combo", ""))
        elif t == "media":
            winput.tap_key(winput.NAMED_KEYS[a.get("key", "play_pause")])
        elif t == "dpi":
            if not self.dpi_callback:
                raise RuntimeError("mouse not available")
            self.dpi_callback(a.get("mode", "next"), int(a.get("level", 1)))
        else:
            raise RuntimeError(f"unknown action type {t!r}")

    def shutdown(self):
        self.pool.shutdown(wait=False, cancel_futures=True)
