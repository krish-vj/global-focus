"""
jev_classifier.py - Jev API integration for Study Guard v2.
Reverts EXACTLY to the proven, working prompt and logic from v1.
"""

import queue
import threading
from datetime import datetime
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
AI_LOG_PATH = SCRIPT_DIR / "ai_log.txt"


def ai_log(msg: str) -> None:
    try:
        with open(AI_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}\n")
    except Exception:
        pass


_jev_client = None
_jev_lock = threading.Lock()


def get_jev_client(api_key: str):
    global _jev_client
    with _jev_lock:
        if _jev_client is None:
            try:
                from typesafe_sdk import TypeSafeClient
            except ImportError:
                import subprocess, sys
                subprocess.check_call([sys.executable, "-m", "pip", "install", "typesafe-sdk"])
                from typesafe_sdk import TypeSafeClient
            _jev_client = TypeSafeClient(
                api_key=api_key,
                base_url="https://openrouter.ai/api",
            )
    return _jev_client


def classify_title(title: str, goal: str, api_key: str) -> tuple:
    """
    Original proven Jev classifier.
    Returns: (choice: str, allowed: bool, confidence: float)
    choice is 'on_task' | 'transitioning' | 'distracted'
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
        conf = float(ans.confidence)
        allowed = choice != "distracted"
        tag = {"on_task": "ON_TASK", "transitioning": "TRANSIT", "distracted": "NO"}.get(choice, choice)
        ai_log(f"[{tag}] (conf={conf:.2f}) {title}")
        return choice, allowed, conf
    except Exception as e:
        ai_log(f"[ERROR] {e} — {title}")
        return "transitioning", True, 0.0  # Fail open — never block on API errors


class AiClassifier(threading.Thread):
    """Background thread that processes window titles through the Jev API."""

    def __init__(self, goal: str, api_key: str, cache: dict, cache_lock: threading.Lock):
        super().__init__(daemon=True, name="AiClassifier")
        self.goal = goal
        self.api_key = api_key
        self.cache = cache
        self.cache_lock = cache_lock
        self._queue = queue.Queue()
        self._stop_event = threading.Event()
        self.api_call_count = 0

    def submit(self, title: str, process_name: str = "") -> None:
        self._queue.put((title, process_name))

    def stop(self) -> None:
        self._stop_event.set()

    def run(self) -> None:
        while not self._stop_event.is_set():
            try:
                title, pname = self._queue.get(timeout=0.5)
            except queue.Empty:
                continue

            with self.cache_lock:
                if title in self.cache:
                    continue

            choice, allowed, conf = classify_title(title, self.goal, self.api_key)
            self.api_call_count += 1

            with self.cache_lock:
                self.cache[title] = (choice, allowed, conf)