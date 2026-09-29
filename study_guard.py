"""
Study Guard — AI-Powered Focus App
Uses Jev (TypeSafe AI) via OpenRouter to classify window titles and minimize distractions.
"""

import ctypes
import ctypes.wintypes
import json
import os
import sys
import threading
import time
import queue
import webbrowser
from datetime import datetime, timedelta
from pathlib import Path

import tkinter as tk
from tkinter import ttk, messagebox, simpledialog

# ─── Windows API ─────────────────────────────────────────────────────────────

user32 = ctypes.windll.user32

SW_FORCEMINIMIZE = 11

def get_foreground_window():
    """Return (hwnd, process_name, title) of the active window."""
    hwnd = user32.GetForegroundWindow()
    if not hwnd:
        return None, "", ""
    
    length = user32.GetWindowTextLengthW(hwnd)
    buf = ctypes.create_unicode_buffer(length + 1)
    user32.GetWindowTextW(hwnd, buf, length + 1)
    title = buf.value.strip()
    
    pid = ctypes.wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    
    pname = ""
    try:
        import subprocess
        result = subprocess.run(
            ["tasklist", "/FI", f"PID eq {pid.value}", "/FO", "CSV", "/NH"],
            capture_output=True, text=True, timeout=2
        )
        if result.stdout.strip():
            pname = result.stdout.strip().split(",")[0].strip('"')
    except Exception:
        pass
    
    return hwnd, pname, title

def minimize_window(hwnd):
    """Forcefully minimize a window by its handle."""
    user32.ShowWindow(hwnd, SW_FORCEMINIMIZE)

# ─── Configuration ───────────────────────────────────────────────────────────

SCRIPT_DIR = Path(os.path.dirname(os.path.abspath(sys.argv[0])))
CONFIG_PATH = SCRIPT_DIR / "config.json"
AI_LOG_PATH = SCRIPT_DIR / "ai_log.txt"

def load_config():
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH, "r", encoding="utf-8-sig") as f:
            return json.load(f)
    return {}

def save_config(cfg):
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)

def ai_log(msg):
    try:
        with open(AI_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}\n")
    except Exception:
        pass

# ─── Jev API (TypeSafe AI via OpenRouter) ───────────────────────────────────

def make_jev_client(api_key):
    """Create and return a TypeSafeClient configured for OpenRouter."""
    try:
        from typesafe_sdk import TypeSafeClient
    except ImportError:
        import subprocess, sys
        subprocess.check_call([sys.executable, "-m", "pip", "install", "typesafe-sdk"])
        from typesafe_sdk import TypeSafeClient
    return TypeSafeClient(
        api_key=api_key,
        base_url="https://openrouter.ai/api",
    )

_jev_client = None

def get_jev_client(api_key):
    global _jev_client
    if _jev_client is None:
        _jev_client = make_jev_client(api_key)
    return _jev_client

def classify_title(title, goal, api_key):
    """Ask Jev to classify a window title into one of three states.
    
    Returns True (allow) for 'on_task' and 'transitioning'.
    Returns False (block) only for 'distracted'.
    """
    from typesafe_sdk import Choice
    try:
        client = get_jev_client(api_key)
        r = client.system_one(
            state={"window_title": title, "study_goal": goal},
            questions={
                "activity": Choice(
                    instructions=(
                        f"The user's study goal is: '{goal}'. "
                        f"Classify what the window titled '{title}' represents."
                    ),
                    criteria={
                        "on_task": (
                            "The window title clearly shows content that is directly "
                            "related to the study goal — e.g. a relevant video, article, "
                            "documentation page, IDE, code editor, or study tool."
                        ),
                        "transitioning": (
                            "The window is a neutral navigation point with no specific "
                            "content yet — e.g. a browser homepage, new tab, empty search "
                            "bar, YouTube homepage, Google homepage, app loading screen, "
                            "or any system/utility window (File Explorer, Settings, "
                            "Task Manager, Terminal, Notepad). The user is likely about "
                            "to navigate to something useful."
                        ),
                        "distracted": (
                            "The window title clearly shows content unrelated to the "
                            "study goal — e.g. an entertainment video, social media feed, "
                            "news article, game, or any other obvious distraction."
                        ),
                    },
                ),
            },
        )
        ans = r.answers["activity"]
        choice = ans.choice          # "on_task" | "transitioning" | "distracted"
        conf  = ans.confidence
        allowed = choice != "distracted"
        tag = {"on_task": "ON_TASK", "transitioning": "TRANSIT", "distracted": "NO"}[choice]
        ai_log(f"[{tag}] (conf={conf:.2f}) {title}")
        return allowed
    except Exception as e:
        ai_log(f"[ERROR] {e} — {title}")
        return True  # Fail open — never block on API errors


# ─── AI Classifier Thread ───────────────────────────────────────────────────

class AiClassifier(threading.Thread):
    """Background thread that processes window titles through the Jev API."""
    
    def __init__(self, goal, api_key, cache, cache_lock):
        super().__init__(daemon=True)
        self.goal = goal
        self.api_key = api_key
        self.cache = cache        # shared dict: title -> bool (True=allowed)
        self.cache_lock = cache_lock
        self.queue = queue.Queue()
        self._stop_event = threading.Event()
        self.api_call_count = 0   # number of Jev API calls made
    
    def submit(self, title):
        """Add a title to the classification queue (non-blocking)."""
        self.queue.put(title)
    
    def stop(self):
        self._stop_event.set()
    
    def run(self):
        while not self._stop_event.is_set():
            try:
                title = self.queue.get(timeout=0.5)
            except queue.Empty:
                continue
            
            # Double-check cache (another submission may have been processed)
            with self.cache_lock:
                if title in self.cache:
                    continue
            
            allowed = classify_title(title, self.goal, self.api_key)
            self.api_call_count += 1
            
            with self.cache_lock:
                self.cache[title] = allowed


# ─── Window Monitor Thread ───────────────────────────────────────────────────

class WindowMonitor(threading.Thread):
    """Monitors the foreground window every second and triggers blocking."""
    
    SAFE_PATTERNS = [
        "study guard", "study mode", "task switching", "task manager",
        "file explorer", "settings", "control panel",
    ]
    
    def __init__(self, classifier, cache, cache_lock, tracker, is_break_fn):
        super().__init__(daemon=True)
        self.classifier = classifier
        self.cache = cache
        self.cache_lock = cache_lock
        self.tracker = tracker  # shared dict: title -> seconds
        self.tracker_lock = threading.Lock()
        self.is_break_fn = is_break_fn
        self._stop_event = threading.Event()
        self.blocked_count = 0
    
    def stop(self):
        self._stop_event.set()
    
    def _is_safe(self, title):
        lower = title.lower()
        for pat in self.SAFE_PATTERNS:
            if pat in lower:
                return True
        return False
    
    def run(self):
        while not self._stop_event.is_set():
            try:
                hwnd, pname, title = get_foreground_window()
                
                if not title or len(title) < 2:
                    time.sleep(1)
                    continue
                
                # Track time
                with self.tracker_lock:
                    key = f"{pname} | {title}" if pname else title
                    self.tracker[key] = self.tracker.get(key, 0) + 1
                
                # Skip safe patterns
                if self._is_safe(title):
                    time.sleep(1)
                    continue
                
                # Check cache
                with self.cache_lock:
                    cached = self.cache.get(title)
                
                if cached is None:
                    # Unknown — submit to AI (non-blocking!)
                    self.classifier.submit(title)
                    time.sleep(1)
                    continue
                
                if cached is False and not self.is_break_fn():
                    # It's a distraction — verify window hasn't changed, then minimize
                    current_hwnd = user32.GetForegroundWindow()
                    if current_hwnd == hwnd:
                        minimize_window(hwnd)
                        self.blocked_count += 1
                        ai_log(f"[BLOCKED] {title}")
                
            except Exception as e:
                ai_log(f"[MONITOR ERROR] {e}")
            
            time.sleep(1)

# ─── Analytics ───────────────────────────────────────────────────────────────

def generate_analytics_html(tracker, goal, jev_calls):
    """Generate an HTML analytics report showing the activity log."""
    sorted_items = sorted(tracker.items(), key=lambda x: x[1], reverse=True)[:25]
    max_val = max((v for _, v in sorted_items), default=1)
    total_secs = sum(tracker.values())
    total_mins = round(total_secs / 60, 1)

    rows = ""
    for name, secs in sorted_items:
        mins = round(secs / 60, 1)
        pct = round(secs / max_val * 100, 1)
        share = round(secs / total_secs * 100, 1) if total_secs else 0
        rows += (
            f"<div class='item'>"
            f"<div class='lbl'>{name} &nbsp;<span class='share'>{share}%</span></div>"
            f"<div class='bar-wrap'><div class='bar' style='width:{pct}%'>{mins} min</div></div>"
            f"</div>\n"
        )

    safe_goal = goal.replace("<", "&lt;").replace(">", "&gt;")
    now_str = datetime.now().strftime("%d %b %Y, %H:%M")

    html = f"""<!DOCTYPE html><html><head><meta charset="utf-8"><title>Study Session Analytics</title>
<style>
body{{font-family:'Segoe UI',sans-serif;background:#111;color:#eee;padding:40px}}
h1{{text-align:center;color:#4CAF50;margin-bottom:4px}}
h3{{text-align:center;color:#aaa;margin-bottom:8px}}
.meta{{text-align:center;color:#666;font-size:13px;margin-bottom:36px}}
.wrap{{max-width:820px;margin:0 auto}}
.stats{{display:flex;gap:20px;margin-bottom:30px;justify-content:center}}
.stat-box{{background:#1e1e2d;padding:18px 32px;border-radius:8px;text-align:center;border-top:3px solid #4CAF50}}
.stat-box .val{{font-size:28px;font-weight:bold;color:#4CAF50}}
.stat-box .lbl-s{{font-size:12px;color:#888;margin-top:4px}}
.item{{margin-bottom:16px}}
.lbl{{font-size:13px;margin-bottom:4px;color:#ccc;display:flex;justify-content:space-between}}
.share{{color:#888;font-size:12px}}
.bar-wrap{{background:#2a2a2a;border-radius:4px;overflow:hidden}}
.bar{{height:28px;background:linear-gradient(90deg,#4CAF50,#81C784);display:flex;align-items:center;padding-left:10px;color:#fff;font-weight:bold;white-space:nowrap;min-width:48px}}
h4{{color:#888;margin:0 0 16px;border-bottom:1px solid #333;padding-bottom:8px}}
</style></head><body>
<h1>Study Session Complete!</h1>
<h3>Goal: {safe_goal}</h3>
<p class='meta'>Session ended {now_str}</p>
<div class='wrap'>
<div class='stats'>
  <div class='stat-box'><div class='val'>{total_mins}</div><div class='lbl-s'>Total Minutes</div></div>
  <div class='stat-box'><div class='val'>{len(sorted_items)}</div><div class='lbl-s'>Windows Visited</div></div>
  <div class='stat-box'><div class='val'>{jev_calls}</div><div class='lbl-s'>Jev API Calls</div></div>
</div>
<h4>Time Breakdown</h4>
{rows}
</div></body></html>"""

    filename = SCRIPT_DIR / f"StudyMode_Analytics_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
    with open(filename, "w", encoding="utf-8") as f:
        f.write(html)
    webbrowser.open(str(filename))



# ─── Overlay Widget ──────────────────────────────────────────────────────────

class OverlayWidget(tk.Toplevel):
    """Always-on-top draggable timer widget."""
    
    def __init__(self, master, goal, end_time, pomodoro, pomo_study, pomo_break):
        super().__init__(master)
        self.goal = goal
        self.end_time = end_time
        self.pomodoro = pomodoro
        self.pomo_study = pomo_study
        self.pomo_break = pomo_break
        
        self.is_break = False
        self.phase_end = datetime.now() + timedelta(minutes=pomo_study) if pomodoro else end_time
        
        # Window setup
        self.title("Study Mode")
        self.overrideredirect(True)
        self.attributes("-topmost", True)
        self.attributes("-alpha", 0.93)
        self.configure(bg="#12121c")
        
        # Position top-right
        screen_w = self.winfo_screenwidth()
        self.geometry(f"290x120+{screen_w - 310}+10")
        
        # Title bar
        title_frame = tk.Frame(self, bg="#08080f", height=24)
        title_frame.pack(fill="x")
        title_frame.pack_propagate(False)
        
        title_lbl = tk.Label(title_frame, text="  Study Guard", bg="#08080f",
                            fg="#9696aa", font=("Segoe UI", 8), anchor="w")
        title_lbl.pack(side="left", fill="both", expand=True)
        
        min_btn = tk.Label(title_frame, text=" _ ", bg="#08080f", fg="#9696aa",
                          font=("Segoe UI", 8, "bold"), cursor="hand2")
        min_btn.pack(side="right")
        min_btn.bind("<Button-1>", lambda e: self.iconify())
        
        # Content
        self.goal_lbl = tk.Label(self, text=f"Goal: {goal}", bg="#12121c",
                                fg="#ffd250", font=("Segoe UI", 8, "bold"), anchor="w")
        self.goal_lbl.pack(fill="x", padx=10, pady=(4, 0))
        
        phase_frame = tk.Frame(self, bg="#12121c")
        phase_frame.pack(fill="x", padx=10)
        
        self.phase_lbl = tk.Label(phase_frame, text="FOCUS", bg="#12121c",
                                 fg="#5ad278", font=("Segoe UI", 10, "bold"))
        self.phase_lbl.pack(side="left")
        
        self.cd_lbl = tk.Label(phase_frame, text="--:--", bg="#12121c",
                              fg="#ffffff", font=("Consolas", 19, "bold"))
        self.cd_lbl.pack(side="left", padx=(10, 0))
        
        self.next_lbl = tk.Label(self, text="", bg="#12121c", fg="#aaaaaa",
                                font=("Segoe UI", 8))
        self.next_lbl.pack()
        
        self.end_lbl = tk.Label(self, text="", bg="#12121c", fg="#6e6e82",
                               font=("Segoe UI", 8))
        self.end_lbl.pack()
        
        # Drag support
        self._drag_data = {"x": 0, "y": 0}
        for w in [title_frame, title_lbl, self.goal_lbl, phase_frame,
                  self.phase_lbl, self.cd_lbl, self.next_lbl, self.end_lbl]:
            w.bind("<ButtonPress-1>", self._on_drag_start)
            w.bind("<B1-Motion>", self._on_drag)
        
        self._tick()
    
    def _on_drag_start(self, event):
        self._drag_data["x"] = event.x_root - self.winfo_x()
        self._drag_data["y"] = event.y_root - self.winfo_y()
    
    def _on_drag(self, event):
        x = event.x_root - self._drag_data["x"]
        y = event.y_root - self._drag_data["y"]
        self.geometry(f"+{x}+{y}")
    
    def _tick(self):
        now = datetime.now()
        
        if now >= self.end_time:
            self.destroy()
            return
        
        # Pomodoro phase switching
        if self.pomodoro and now >= self.phase_end:
            self.is_break = not self.is_break
            if self.is_break:
                self.phase_end = now + timedelta(minutes=self.pomo_break)
            else:
                self.phase_end = now + timedelta(minutes=self.pomo_study)
        
        total_left = self.end_time - now
        self.end_lbl.config(text=f"Ends {self.end_time.strftime('%H:%M')}  —  {str(total_left).split('.')[0]} left")
        
        if self.pomodoro:
            phase_left = max(self.phase_end - now, timedelta(0))
            cd_str = f"{int(phase_left.total_seconds()) // 60:02d}:{int(phase_left.total_seconds()) % 60:02d}"
            self.cd_lbl.config(text=cd_str)
            if self.is_break:
                self.phase_lbl.config(text="BREAK", fg="#50a0ff")
                self.next_lbl.config(text=f"Study resumes in {cd_str}")
            else:
                self.phase_lbl.config(text="STUDY", fg="#5ad278")
                self.next_lbl.config(text=f"Next break in {cd_str}")
        else:
            secs = int(total_left.total_seconds())
            self.cd_lbl.config(text=f"{secs // 3600:02d}:{(secs % 3600) // 60:02d}:{secs % 60:02d}")
            self.phase_lbl.config(text="FOCUS", fg="#5ad278")
            self.next_lbl.config(text="Keep going!")
        
        self.after(1000, self._tick)

# ─── Main Application ────────────────────────────────────────────────────────

class StudyGuardApp:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Study Guard — AI Focus App")
        self.root.geometry("700x440")
        self.root.resizable(False, False)
        self.root.configure(bg="#f8f6f0")
        
        self.api_key = self._get_api_key()
        if not self.api_key:
            sys.exit(1)
        
        self._build_ui()
        self.root.mainloop()
    
    def _get_api_key(self):
        cfg = load_config()
        key = cfg.get("ApiKey", "")
        if key:
            return key
        
        # Ask for key
        temp = tk.Tk()
        temp.withdraw()
        key = simpledialog.askstring(
            "Setup Study Guard",
            "Enter your OpenRouter API Key\n(Get one free at openrouter.ai/keys):",
            parent=temp
        )
        temp.destroy()
        
        if not key or not key.strip():
            messagebox.showerror("Error", "API key is required.")
            return None
        
        key = key.strip()
        save_config({"ApiKey": key})
        return key
    
    def _build_ui(self):
        r = self.root
        
        # Header
        header = tk.Frame(r, bg="white", height=90)
        header.pack(fill="x")
        header.pack_propagate(False)
        
        tk.Label(header, text="Study Guard", bg="white", fg="#2c3e50",
                font=("Segoe UI", 22, "bold")).place(x=20, y=14)
        tk.Label(header, text="Jev AI evaluates your windows in real-time.",
                bg="white", fg="#7f8c8d", font=("Segoe UI", 10)).place(x=24, y=54)
        
        # Minutes
        tk.Label(r, text="Minutes", bg="#f8f6f0", font=("Segoe UI", 10)).place(x=28, y=110)
        self.minutes_var = tk.IntVar(value=30)
        ttk.Spinbox(r, from_=1, to=1440, textvariable=self.minutes_var, width=6).place(x=28, y=136)
        
        # Goal
        tk.Label(r, text="Your Goal", bg="#f8f6f0", font=("Segoe UI", 10)).place(x=140, y=110)
        self.goal_var = tk.StringVar()
        tk.Entry(r, textvariable=self.goal_var, font=("Segoe UI", 10), width=48).place(x=140, y=136)
        
        # Pomodoro
        self.pomo_var = tk.BooleanVar(value=False)
        tk.Checkbutton(r, text="Pomodoro Timer", variable=self.pomo_var,
                      bg="#f8f6f0", font=("Segoe UI", 10)).place(x=28, y=180)
        
        tk.Label(r, text="Study (m)", bg="#f8f6f0", font=("Segoe UI", 9)).place(x=200, y=182)
        self.pomo_study_var = tk.IntVar(value=25)
        ttk.Spinbox(r, from_=1, to=120, textvariable=self.pomo_study_var, width=4).place(x=270, y=182)
        
        tk.Label(r, text="Break (m)", bg="#f8f6f0", font=("Segoe UI", 9)).place(x=340, y=182)
        self.pomo_break_var = tk.IntVar(value=5)
        ttk.Spinbox(r, from_=1, to=60, textvariable=self.pomo_break_var, width=4).place(x=410, y=182)
        
        # Buttons
        analytics_btn = tk.Button(r, text="View Last Analytics", bg="#d6e0e2",
                                 font=("Segoe UI", 10), command=self._view_analytics)
        analytics_btn.place(x=28, y=240, width=166, height=38)
        
        start_btn = tk.Button(r, text="Start AI Guard", bg="#e3b45d",
                             font=("Segoe UI", 11, "bold"), command=self._start_session)
        start_btn.place(x=510, y=236, width=166, height=44)
        
        # Log
        tk.Label(r, text="Activity Log", bg="#f8f6f0", font=("Segoe UI", 10)).place(x=28, y=300)
        self.log_box = tk.Text(r, height=6, width=82, font=("Consolas", 9),
                              bg="#fdfbf6", state="disabled")
        self.log_box.place(x=28, y=326)
    
    def _log(self, msg):
        ts = datetime.now().strftime("[%H:%M:%S]")
        self.log_box.config(state="normal")
        self.log_box.insert("end", f"{ts} {msg}\n")
        self.log_box.see("end")
        self.log_box.config(state="disabled")
    
    def _view_analytics(self):
        files = sorted(SCRIPT_DIR.glob("StudyMode_Analytics_*.html"), reverse=True)
        if files:
            webbrowser.open(str(files[0]))
        else:
            messagebox.showinfo("Study Guard", "No analytics found. Complete a session first.")
    
    def _start_session(self):
        goal = self.goal_var.get().strip()
        if not goal:
            messagebox.showwarning("Study Guard", "Please enter a goal.")
            return
        
        minutes = self.minutes_var.get()
        pomodoro = self.pomo_var.get()
        pomo_study = self.pomo_study_var.get()
        pomo_break = self.pomo_break_var.get()
        
        end_time = datetime.now() + timedelta(minutes=minutes)
        
        self._log(f"Starting AI Guard for {minutes} minutes.")
        self._log(f"Goal: {goal}")
        self._log(f"Session ends at {end_time.strftime('%H:%M:%S')}")
        
        # Shared state
        cache = {}
        cache_lock = threading.Lock()
        tracker = {}
        
        # Create overlay widget
        widget = OverlayWidget(self.root, goal, end_time, pomodoro, pomo_study, pomo_break)
        
        # Start AI classifier thread
        classifier = AiClassifier(goal, self.api_key, cache, cache_lock)
        classifier.start()
        
        # Start window monitor thread
        monitor = WindowMonitor(
            classifier, cache, cache_lock, tracker,
            is_break_fn=lambda: widget.is_break if widget.winfo_exists() else False
        )
        monitor.start()
        
        self._log("AI Guard is active. Monitoring windows...")
        
        # Session end watcher
        def watch_session():
            while datetime.now() < end_time:
                time.sleep(2)
            
            # Stop threads
            monitor.stop()
            classifier.stop()
            monitor.join(timeout=3)
            classifier.join(timeout=3)
            
            self._log(f"Session complete! Blocked {monitor.blocked_count} distractions.")
            self._log(f"Jev API calls made: {classifier.api_call_count}")
            
            # Generate analytics
            generate_analytics_html(tracker, goal, classifier.api_call_count)
        
        threading.Thread(target=watch_session, daemon=True).start()


if __name__ == "__main__":
    StudyGuardApp()
