"""
monitor.py - Window Monitor for Study Guard v2.
Polls the foreground window every second.
Observer mode: classify and log only.
Block mode: redirect browser tabs to interstitial; minimize other EXEs.
"""

import ctypes
import ctypes.wintypes
import subprocess
import threading
import time
from datetime import datetime
from urllib.parse import quote

import db
from jev_classifier import AiClassifier, ai_log

user32 = ctypes.windll.user32
SW_FORCEMINIMIZE = 11

BROWSER_PROCESSES = {
    "chrome.exe", "firefox.exe", "msedge.exe", "opera.exe",
    "brave.exe", "vivaldi.exe", "iexplore.exe",
}

SAFE_PATTERNS = [
    "study guard", "study mode", "task switching", "task manager",
    "file explorer", "settings", "control panel", "localhost:7432",
    "127.0.0.1:7432", "stay focused",
]

REDIRECT_COOLDOWN_SECS = 20  # seconds before re-blocking same title


def get_foreground_window():
    """Return (hwnd, process_name, title) of the active window."""
    hwnd = user32.GetForegroundWindow()
    if not hwnd:
        return 0, "", ""

    length = user32.GetWindowTextLengthW(hwnd)
    buf = ctypes.create_unicode_buffer(length + 1)
    user32.GetWindowTextW(hwnd, buf, length + 1)
    title = buf.value.strip()

    pid = ctypes.wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))

    pname = ""
    try:
        result = subprocess.run(
            ["tasklist", "/FI", f"PID eq {pid.value}", "/FO", "CSV", "/NH"],
            capture_output=True, text=True, timeout=2,
        )
        if result.stdout.strip():
            pname = result.stdout.strip().split(",")[0].strip('"')
    except Exception:
        pass

    return hwnd, pname, title


def minimize_window(hwnd: int) -> None:
    user32.ShowWindow(hwnd, SW_FORCEMINIMIZE)


def redirect_browser(hwnd: int, url: str) -> None:
    """Navigate the foreground browser tab to url via Ctrl+L / paste / Enter."""
    try:
        import win32api
        import win32clipboard
        import win32con
    except ImportError:
        minimize_window(hwnd)
        return

    try:
        old_clip = None
        try:
            win32clipboard.OpenClipboard()
            try:
                old_clip = win32clipboard.GetClipboardData(win32con.CF_UNICODETEXT)
            except Exception:
                pass
            win32clipboard.CloseClipboard()
        except Exception:
            pass

        win32clipboard.OpenClipboard()
        win32clipboard.EmptyClipboard()
        win32clipboard.SetClipboardData(win32con.CF_UNICODETEXT, url)
        win32clipboard.CloseClipboard()

        time.sleep(0.05)

        # Ctrl+L - focus browser address bar
        win32api.keybd_event(win32con.VK_CONTROL, 0, 0, 0)
        win32api.keybd_event(ord("L"), 0, 0, 0)
        time.sleep(0.06)
        win32api.keybd_event(ord("L"), 0, win32con.KEYEVENTF_KEYUP, 0)
        win32api.keybd_event(win32con.VK_CONTROL, 0, win32con.KEYEVENTF_KEYUP, 0)
        time.sleep(0.12)

        # Ctrl+V - paste URL
        win32api.keybd_event(win32con.VK_CONTROL, 0, 0, 0)
        win32api.keybd_event(ord("V"), 0, 0, 0)
        time.sleep(0.04)
        win32api.keybd_event(ord("V"), 0, win32con.KEYEVENTF_KEYUP, 0)
        win32api.keybd_event(win32con.VK_CONTROL, 0, win32con.KEYEVENTF_KEYUP, 0)
        time.sleep(0.06)

        # Enter
        win32api.keybd_event(win32con.VK_RETURN, 0, 0, 0)
        win32api.keybd_event(win32con.VK_RETURN, 0, win32con.KEYEVENTF_KEYUP, 0)

        def _restore():
            time.sleep(0.4)
            if old_clip is not None:
                try:
                    win32clipboard.OpenClipboard()
                    win32clipboard.EmptyClipboard()
                    win32clipboard.SetClipboardData(win32con.CF_UNICODETEXT, old_clip)
                    win32clipboard.CloseClipboard()
                except Exception:
                    pass

        threading.Thread(target=_restore, daemon=True).start()

    except Exception as e:
        ai_log(f"[REDIRECT_ERROR] {e}")
        minimize_window(hwnd)


class WindowMonitor(threading.Thread):
    """
    Monitors foreground window every second.
    Uses AiClassifier with the original proven Jev questions.
    """

    def __init__(
        self,
        session_id: int,
        mode: str,
        goal: str,
        category_name: str,
        api_key: str,
        interstitial_base_url: str,
        is_break_fn,
        event_callback=None,
    ):
        super().__init__(daemon=True, name="WindowMonitor")
        self.session_id = session_id
        self.mode = mode
        self.goal = goal
        self.category_name = category_name
        self.interstitial_base_url = interstitial_base_url
        self.is_break_fn = is_break_fn
        self.event_callback = event_callback

        self._cache = {}
        self._cache_lock = threading.Lock()

        self._classifier = AiClassifier(
            goal=self.goal,
            api_key=api_key,
            cache=self._cache,
            cache_lock=self._cache_lock,
        )

        self._stop_event = threading.Event()
        self.blocks_count = 0
        self._last_event_key = ""
        self._redirect_cooldown = {}

    @property
    def api_call_count(self) -> int:
        return self._classifier.api_call_count

    def stop(self) -> None:
        self._stop_event.set()
        self._classifier.stop()

    def start(self) -> None:
        self._classifier.start()
        super().start()

    def _is_safe(self, title: str) -> bool:
        lower = title.lower()
        return any(p in lower for p in SAFE_PATTERNS)

    def _on_cooldown(self, title: str) -> bool:
        last = self._redirect_cooldown.get(title, 0.0)
        return (time.time() - last) < REDIRECT_COOLDOWN_SECS

    def _handle_distraction(self, hwnd: int, pname: str, title: str) -> str:
        if self.mode != "block":
            return "observed"

        self.blocks_count += 1
        url = f"{self.interstitial_base_url}&title={quote(title, safe='')}"
        self._redirect_cooldown[title] = time.time()

        if pname.lower() in BROWSER_PROCESSES:
            redirect_browser(hwnd, url)
            ai_log(f"[REDIRECT] {title}")
            return "redirected"
        else:
            minimize_window(hwnd)
            ai_log(f"[MINIMIZED] {title}")
            return "minimized"

    def run(self) -> None:
        while not self._stop_event.is_set():
            try:
                hwnd, pname, title = get_foreground_window()

                if not title or len(title) < 2:
                    time.sleep(1)
                    continue

                if self._is_safe(title):
                    time.sleep(1)
                    continue

                # Check cache
                with self._cache_lock:
                    cached = self._cache.get(title)

                if cached is None:
                    # Submit to AI (non-blocking)
                    self._classifier.submit(title, pname)
                    time.sleep(1)
                    continue

                choice, allowed, conf = cached

                action = "allowed"
                if not allowed and not self.is_break_fn() and not self._on_cooldown(title):
                    current_hwnd = user32.GetForegroundWindow()
                    if current_hwnd == hwnd:
                        action = self._handle_distraction(hwnd, pname, title)

                event_key = f"{title}|{action}"
                if event_key != self._last_event_key:
                    self._last_event_key = event_key
                    # Log to SQLite DB
                    assigned_cat = self.category_name if choice == "on_task" else ("navigating" if choice == "transitioning" else "Entertainment/Other")
                    db.log_event(self.session_id, title, pname, assigned_cat, choice, action, conf)
                    if self.event_callback:
                        self.event_callback({
                            "type": "log",
                            "title": title,
                            "pname": pname,
                            "category": assigned_cat,
                            "classification": choice,
                            "action": action,
                            "confidence": round(conf, 2),
                            "timestamp": datetime.now().isoformat(),
                        })

            except Exception as e:
                ai_log(f"[MONITOR_ERROR] {e}")

            time.sleep(1)