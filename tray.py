"""
tray.py - System tray icon for Study Guard v2.
Keeps the app alive even when the browser tab is closed.
"""

import threading
import webbrowser


def _create_icon_image():
    """Generate a simple purple circle icon for the tray."""
    from PIL import Image, ImageDraw, ImageFont
    size = 64
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    # Purple filled circle
    draw.ellipse([2, 2, size - 2, size - 2], fill="#6c63ff")
    # White "SG" text
    try:
        draw.text((14, 18), "SG", fill="white")
    except Exception:
        pass
    return img


def start_tray(port: int = 7432):
    """Start the system tray icon (blocks calling thread until quit)."""
    import pystray

    def open_dashboard(_icon=None, _item=None):
        webbrowser.open(f"http://localhost:{port}")

    def stop_session(_icon=None, _item=None):
        try:
            import requests
            requests.post(f"http://localhost:{port}/api/session/stop", timeout=3)
        except Exception:
            pass

    def send_report(_icon=None, _item=None):
        try:
            import requests
            requests.post(
                f"http://localhost:{port}/api/report/send",
                json={"period_days": 7},
                timeout=10,
            )
        except Exception:
            pass

    def quit_app(icon, _item=None):
        try:
            import requests
            requests.post(f"http://localhost:{port}/api/session/stop", timeout=2)
        except Exception:
            pass
        icon.stop()
        import os
        os._exit(0)

    menu = pystray.Menu(
        pystray.MenuItem("Open Dashboard", open_dashboard, default=True),
        pystray.MenuItem("Stop Session", stop_session),
        pystray.MenuItem("Send Guardian Report", send_report),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Quit Study Guard", quit_app),
    )

    icon = pystray.Icon(
        "StudyGuard",
        _create_icon_image(),
        "Study Guard — AI Focus",
        menu,
    )
    icon.run()