"""
server.py - Flask REST API + SSE + motivational interstitial for Study Guard v2.
"""

import json
import queue
import random
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import quote

from flask import Flask, Response, jsonify, render_template_string, request, send_from_directory

import db
from monitor import WindowMonitor

SCRIPT_DIR = Path(__file__).parent
WEB_DIR = SCRIPT_DIR / "web"
ASSETS_DIR = SCRIPT_DIR / "assets"

# Load motivational quotes
_quotes = []
_quotes_path = ASSETS_DIR / "quotes.json"
if _quotes_path.exists():
    with open(_quotes_path, encoding="utf-8-sig") as _f:
        _quotes = json.load(_f)

# ---------------------------------------------------------------------------
# Shared session state
# ---------------------------------------------------------------------------

class _SessionState:
    def __init__(self):
        self.lock = threading.Lock()
        self.session_id = None
        self.goal = ""
        self.category_name = ""
        self.mode = "block"
        self.started_at = None
        self.ends_at = None
        self.pomodoro_enabled = False
        self.pomo_study = 25
        self.pomo_break = 5
        self.is_break = False
        self.phase_end = None
        self.monitor = None
        self.event_queue = queue.Queue(maxsize=500)

    @property
    def is_running(self):
        return self.session_id is not None

    def to_dict(self):
        with self.lock:
            if not self.is_running:
                return {"running": False, "session": None}
            now = datetime.now()
            elapsed = int((now - self.started_at).total_seconds()) if self.started_at else 0
            remaining = max(0, int((self.ends_at - now).total_seconds())) if self.ends_at else 0
            pomo = None
            if self.pomodoro_enabled and self.phase_end:
                phase_left = max(0, int((self.phase_end - now).total_seconds()))
                pomo = {"enabled": True, "is_break": self.is_break, "phase_secs_left": phase_left}
            return {
                "running": True,
                "session": {
                    "id": self.session_id,
                    "goal": self.goal,
                    "category": self.category_name,
                    "mode": self.mode,
                    "started_at": self.started_at.isoformat() if self.started_at else None,
                    "ends_at": self.ends_at.isoformat() if self.ends_at else None,
                    "elapsed_secs": elapsed,
                    "remaining_secs": remaining,
                    "blocks_count": self.monitor.blocks_count if self.monitor else 0,
                    "jev_calls": self.monitor.api_call_count if self.monitor else 0,
                    "pomodoro": pomo,
                },
            }


_state = _SessionState()
_api_key = ""


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _push_event(evt: dict):
    try:
        _state.event_queue.put_nowait(evt)
    except queue.Full:
        pass


def _stop_session_internal(session_id: int):
    with _state.lock:
        if _state.session_id != session_id:
            return
        monitor = _state.monitor
        blocks = monitor.blocks_count if monitor else 0
        jev_calls = monitor.api_call_count if monitor else 0
        _state.session_id = None
        _state.monitor = None

    if monitor:
        monitor.stop()
        monitor.join(timeout=3)

    db.end_session(session_id, blocks, jev_calls)
    _push_event({"type": "session_end", "timestamp": datetime.now().isoformat()})


# ---------------------------------------------------------------------------
# Flask app factory
# ---------------------------------------------------------------------------

def _get_effective_api_key():
    global _api_key
    if _api_key:
        return _api_key
    from config import load_config
    cfg = load_config()
    _api_key = cfg.get("ApiKey", "")
    return _api_key

def create_app(api_key: str) -> Flask:
    global _api_key
    _api_key = api_key

    app = Flask(__name__, static_folder=str(WEB_DIR), static_url_path="")
    app.config["JSON_SORT_KEYS"] = False

    # --- SPA ---
    @app.route("/")
    def index():
        return send_from_directory(str(WEB_DIR), "index.html")

    # --- Motivational interstitial ---
    @app.route("/blocked")
    def blocked():
        goal = request.args.get("goal", "your goal")
        title = request.args.get("title", "")
        quote = random.choice(_quotes) if _quotes else {"text": "Stay focused.", "author": ""}
        return render_template_string(
            _INTERSTITIAL,
            goal=goal,
            blocked_title=title,
            quote_text=quote.get("text", ""),
            quote_author=quote.get("author", ""),
        )

    # --- Status ---
    @app.route("/api/status")
    def api_status():
        return jsonify(_state.to_dict())

    # --- Categories ---
    @app.route("/api/categories", methods=["GET"])
    def api_get_categories():
        return jsonify(db.get_categories())

    @app.route("/api/categories", methods=["POST"])
    def api_add_category():
        d = request.json or {}
        cat = db.add_category(
            d.get("name", ""), d.get("description", ""),
            d.get("color", "#6c63ff"), d.get("is_productive", True),
        )
        return jsonify(cat), 201

    @app.route("/api/categories/<int:cid>", methods=["PUT"])
    def api_update_category(cid):
        d = request.json or {}
        db.update_category(cid, d.get("name", ""), d.get("description", ""),
                           d.get("color", "#6c63ff"), d.get("is_productive", True))
        return jsonify({"ok": True})

    @app.route("/api/categories/<int:cid>", methods=["DELETE"])
    def api_delete_category(cid):
        db.delete_category(cid)
        return jsonify({"ok": True})

    # --- Session start/stop ---
    @app.route("/api/session/start", methods=["POST"])
    def api_start_session():
        if _state.is_running:
            return jsonify({"error": "Session already running"}), 400

        d = request.json or {}
        category_id = d.get("category_id")
        category_name = d.get("category_name", "General")
        goal = d.get("goal") or category_name
        mode = d.get("mode", "block")
        duration_mins = int(d.get("duration_mins", 30))
        pomodoro = bool(d.get("pomodoro", False))
        pomo_study = int(d.get("pomo_study", 25))
        pomo_break = int(d.get("pomo_break", 5))

        all_categories = db.get_categories()
        session_id = db.start_session(
            goal, category_id, category_name, mode, duration_mins,
            pomodoro, pomo_study, pomo_break,
        )

        now = datetime.now()
        end_time = now + timedelta(minutes=duration_mins)

        with _state.lock:
            _state.session_id = session_id
            _state.goal = goal
            _state.category_name = category_name
            _state.mode = mode
            _state.started_at = now
            _state.ends_at = end_time
            _state.pomodoro_enabled = pomodoro
            _state.pomo_study = pomo_study
            _state.pomo_break = pomo_break
            _state.is_break = False
            _state.phase_end = now + timedelta(minutes=pomo_study) if pomodoro else end_time

        base_url = f"http://localhost:7432/blocked?goal={quote(category_name, safe='')}"

        monitor = WindowMonitor(
            session_id=session_id,
            mode=mode,
            goal=goal,
            category_name=category_name,
            api_key=_get_effective_api_key(),
            interstitial_base_url=base_url,
            is_break_fn=lambda: _state.is_break,
            event_callback=_push_event,
        )
        _state.monitor = monitor
        monitor.start()

        # Session watcher: manages pomodoro phases + auto-stop
        def _watch():
            while datetime.now() < end_time and _state.session_id == session_id:
                if pomodoro:
                    with _state.lock:
                        if _state.phase_end and datetime.now() >= _state.phase_end:
                            _state.is_break = not _state.is_break
                            mins = pomo_break if _state.is_break else pomo_study
                            _state.phase_end = datetime.now() + timedelta(minutes=mins)
                            _push_event({
                                "type": "phase_change",
                                "is_break": _state.is_break,
                                "timestamp": datetime.now().isoformat(),
                            })
                time.sleep(1)
            if _state.session_id == session_id:
                _stop_session_internal(session_id)

        threading.Thread(target=_watch, daemon=True, name="SessionWatcher").start()
        return jsonify({"ok": True, "session_id": session_id})

    @app.route("/api/session/stop", methods=["POST"])
    def api_stop_session():
        sid = _state.session_id
        if not sid:
            return jsonify({"error": "No active session"}), 400
        _stop_session_internal(sid)
        return jsonify({"ok": True})

    # --- Analytics ---
    @app.route("/api/analytics/overview")
    def api_overview():
        days = int(request.args.get("days", 30))
        return jsonify(db.get_overview(days))

    @app.route("/api/analytics/sessions")
    def api_sessions():
        limit = int(request.args.get("limit", 20))
        offset = int(request.args.get("offset", 0))
        return jsonify(db.get_sessions(limit, offset))

    @app.route("/api/analytics/session/<int:sid>")
    def api_session_detail(sid):
        return jsonify(db.get_session_detail(sid))

    # --- Integrity ---
    @app.route("/api/integrity/verify")
    def api_verify():
        return jsonify(db.verify_integrity())

    # --- Settings ---
    @app.route("/api/settings", methods=["GET"])
    def api_get_settings():
        from config import load_config
        cfg = load_config()
        if not _api_key:
            _api_key = cfg.get("ApiKey", "")
        g = cfg.get("guardian", {})
        safe_g = {k: v for k, v in g.items() if k != "smtp_pass"}
        if g.get("smtp_pass"):
            safe_g["smtp_pass_set"] = True
        return jsonify({"api_key_set": bool(cfg.get("ApiKey")), "guardian": safe_g})

    @app.route("/api/settings", methods=["POST"])
    def api_save_settings():
        from config import load_config, save_config
        d = request.json or {}
        cfg = load_config()
        if "guardian" in d:
            old_pass = cfg.get("guardian", {}).get("smtp_pass", "")
            cfg["guardian"] = d["guardian"]
            if not cfg["guardian"].get("smtp_pass"):
                cfg["guardian"]["smtp_pass"] = old_pass
        if "api_key" in d and d["api_key"]:
            cfg["ApiKey"] = d["api_key"]
            global _api_key
            _api_key = d["api_key"]
        save_config(cfg)
        return jsonify({"ok": True})

    # --- Report ---
    @app.route("/api/report/send", methods=["POST"])
    def api_send_report():
        d = request.json or {}
        period_days = int(d.get("period_days", 7))
        try:
            from config import load_config
            from reporter import send_report
            cfg = load_config()
            g = cfg.get("guardian", {})
            if not g.get("email"):
                return jsonify({"ok": False, "error": "No guardian email configured"}), 400
            send_report(g, period_days)
            return jsonify({"ok": True, "message": f"Report sent to {g['email']}"})
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)}), 500

    # --- SSE live event stream ---
    @app.route("/api/live")
    def api_live():
        def generate():
            yield "data: {\"type\":\"connected\"}\n\n"
            while True:
                try:
                    evt = _state.event_queue.get(timeout=15)
                    yield f"data: {json.dumps(evt)}\n\n"
                except queue.Empty:
                    yield "data: {\"type\":\"ping\"}\n\n"

        return Response(
            generate(),
            mimetype="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    return app


# ---------------------------------------------------------------------------
# Motivational interstitial HTML template
# ---------------------------------------------------------------------------

_INTERSTITIAL = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Stay Focused - Study Guard</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{min-height:100vh;background:#0a0a0f;display:flex;flex-direction:column;
     align-items:center;justify-content:center;font-family:'Segoe UI',system-ui,sans-serif;
     color:#e2e8f0;overflow:hidden}
.orb{position:fixed;border-radius:50%;filter:blur(90px);opacity:.12;pointer-events:none;
     animation:float 9s ease-in-out infinite}
.orb1{width:450px;height:450px;background:#6c63ff;top:-120px;left:-120px}
.orb2{width:350px;height:350px;background:#00d2a0;bottom:-100px;right:-100px;animation-delay:-4.5s}
@keyframes float{0%,100%{transform:translate(0,0)}50%{transform:translate(24px,-24px)}}
.card{position:relative;z-index:1;text-align:center;padding:52px 48px;max-width:680px;width:90%;
      background:rgba(255,255,255,.04);border:1px solid rgba(255,255,255,.08);
      border-radius:28px;backdrop-filter:blur(24px)}
.icon{font-size:60px;margin-bottom:20px;display:block;animation:pulse 2s ease-in-out infinite}
@keyframes pulse{0%,100%{transform:scale(1)}50%{transform:scale(1.08)}}
h1{font-size:38px;font-weight:800;color:#6c63ff;letter-spacing:-1px;margin-bottom:8px}
.sub{font-size:15px;color:#64748b;margin-bottom:28px}
.goal-pill{display:inline-flex;align-items:center;gap:8px;background:rgba(0,210,160,.12);
           border:1px solid rgba(0,210,160,.25);color:#00d2a0;padding:8px 20px;
           border-radius:24px;font-size:14px;font-weight:600;margin-bottom:28px}
.blocked-label{font-size:12px;color:#475569;margin-bottom:6px;text-transform:uppercase;letter-spacing:1.5px}
.blocked-title{font-size:13px;color:#64748b;background:rgba(255,107,107,.08);
               border:1px solid rgba(255,107,107,.15);padding:8px 18px;border-radius:10px;
               max-width:400px;margin:0 auto 36px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.quote{font-size:21px;font-style:italic;color:#e2e8f0;line-height:1.65;
       margin-bottom:10px;font-weight:300;max-width:520px;margin-left:auto;margin-right:auto}
.author{font-size:14px;color:#6c63ff;font-weight:600;margin-bottom:44px}
.timer-wrap{margin-bottom:44px}
.timer-label{font-size:11px;color:#475569;text-transform:uppercase;letter-spacing:2px;margin-bottom:8px}
.timer{font-size:52px;font-weight:700;color:#00d2a0;font-variant-numeric:tabular-nums;
       font-family:Consolas,monospace;letter-spacing:2px}
.btns{display:flex;gap:14px;justify-content:center;flex-wrap:wrap}
.btn{padding:14px 32px;border-radius:14px;font-size:15px;font-weight:600;
     cursor:pointer;border:none;text-decoration:none;display:inline-block;
     transition:all .2s;line-height:1}
.btn-primary{background:#6c63ff;color:#fff}
.btn-primary:hover{background:#5a52e0;transform:translateY(-2px);box-shadow:0 8px 24px rgba(108,99,255,.35)}
.btn-ghost{background:rgba(255,255,255,.06);color:#94a3b8;border:1px solid rgba(255,255,255,.1)}
.btn-ghost:hover{background:rgba(255,255,255,.1);transform:translateY(-2px)}
</style>
</head>
<body>
<div class="orb orb1"></div>
<div class="orb orb2"></div>
<div class="card">
  <span class="icon">&#x1F3AF;</span>
  <h1>Stay Focused</h1>
  <p class="sub">This content doesn't align with your current goal</p>
  <div class="goal-pill">&#x1F4DA; Studying: {{ goal }}</div>
  {% if blocked_title %}
  <p class="blocked-label">Blocked</p>
  <div class="blocked-title">&#x1F6AB; {{ blocked_title }}</div>
  {% endif %}
  <p class="quote">"{{ quote_text }}"</p>
  <p class="author">&mdash; {{ quote_author }}</p>
  <div class="timer-wrap">
    <p class="timer-label">Session time remaining</p>
    <p class="timer" id="tmr">--:--</p>
  </div>
  <div class="btns">
    <a href="http://localhost:7432" class="btn btn-primary">&larr; Back to Dashboard</a>
    <button class="btn btn-ghost" onclick="history.back()">I'll stay on task</button>
  </div>
</div>
<script>
async function updateTimer(){
  try{
    const r=await fetch('/api/status');
    const d=await r.json();
    if(d.running&&d.session){
      const s=d.session.remaining_secs;
      document.getElementById('tmr').textContent=
        String(Math.floor(s/60)).padStart(2,'0')+':'+String(s%60).padStart(2,'0');
    }else{
      document.getElementById('tmr').textContent='Done';
    }
  }catch(e){document.getElementById('tmr').textContent='--:--';}
}
updateTimer();
setInterval(updateTimer,1000);
</script>
</body>
</html>"""