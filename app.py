"""
app.py - Main Entry Point for Study Guard v2.
Initializes the SQLite database, starts the local Flask server on port 7432,
launches the browser dashboard, and runs the system tray process.
"""

import os
import sys
import threading
import time
import webbrowser
from pathlib import Path

import config
import db
from server import create_app
from tray import start_tray

PORT = 7432

DEFAULT_CATEGORIES = [
    {
        "name": "DBMS",
        "description": "Database Management Systems: relational models, SQL queries, indexes, transactions, normalization, database design lectures.",
        "color": "#6c63ff",
        "is_productive": True,
    },
    {
        "name": "OS",
        "description": "Operating Systems: processes, threads, virtual memory, scheduling, paging, file systems, Linux kernel concepts.",
        "color": "#38bdf8",
        "is_productive": True,
    },
    {
        "name": "CAO",
        "description": "Computer Architecture & Organization: pipelining, cache memory, CPU registers, instruction sets, microarchitecture.",
        "color": "#00d2a0",
        "is_productive": True,
    },
    {
        "name": "Coding & Dev",
        "description": "Software development: IDEs (VS Code, Cursor), GitHub, programming language docs, coding problems (LeetCode), terminal/cmd.",
        "color": "#f59e0b",
        "is_productive": True,
    },
    {
        "name": "Entertainment",
        "description": "Gaming, non-academic YouTube videos, memes, streaming series/movies, social media feeds, comedy, gossip.",
        "color": "#ff6b6b",
        "is_productive": False,
    },
    {
        "name": "General Study",
        "description": "General academic study, math, research papers, note-taking apps, Notion, textbooks, university portals.",
        "color": "#a855f7",
        "is_productive": True,
    },
]


def ensure_defaults():
    cats = db.get_categories()
    if not cats:
        for cat in DEFAULT_CATEGORIES:
            try:
                db.add_category(cat["name"], cat["description"], cat["color"], cat["is_productive"])
            except Exception:
                pass


def main():
    print("=" * 60)
    print("  Study Guard v2 — AI Focus & Long-Term Analytics")
    print("=" * 60)

    cfg = config.load_config()
    api_key = cfg.get("ApiKey", "")

    # Initialize SQLite database
    db.init_db()
    db.set_integrity_key(api_key if api_key else "default_key_fallback")
    ensure_defaults()

    # Create Flask App
    flask_app = create_app(api_key)

    # Start Flask Server in background thread
    def run_flask():
        # Running with werkzeug in production thread
        import logging
        log = logging.getLogger("werkzeug")
        log.setLevel(logging.ERROR)
        flask_app.run(host="127.0.0.1", port=PORT, debug=False, use_reloader=False)

    server_thread = threading.Thread(target=run_flask, daemon=True, name="FlaskServer")
    server_thread.start()

    time.sleep(1.0)
    url = f"http://127.0.0.1:{PORT}"
    print(f"\n[+] Local Server started at: {url}")
    print("[+] Opening Study Guard Dashboard in default browser...")
    webbrowser.open(url)

    # Run system tray (blocks main thread until exit)
    print("[+] Starting system tray icon. Check system tray for quick options.\n")
    try:
        start_tray(PORT)
    except Exception as e:
        print(f"[-] Tray error or head-less mode ({e}). Running in terminal wait mode...")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\nShutting down Study Guard...")
            sys.exit(0)


if __name__ == "__main__":
    main()