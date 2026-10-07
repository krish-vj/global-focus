"""
reporter.py - Guardian report generator and SMTP sender for Study Guard v2.
Guardian reporting is optional; SMTP settings are configured in config.json.
"""

import smtplib
import ssl
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import db


def generate_report_html(period_days: int = 7):
    """
    Build a self-contained HTML email report.
    Returns (html_string, stats_dict).
    """
    stats = db.get_overview(period_days)
    integrity = db.verify_integrity()

    # Category bar rows
    cat_rows = ""
    cats = stats.get("categories_breakdown", [])
    max_mins = max((c["mins"] for c in cats), default=1) or 1
    for cat in cats:
        pct = round(cat["mins"] / max_mins * 100)
        cat_rows += f"""
        <tr>
          <td style="padding:8px 16px;color:#e2e8f0;white-space:nowrap">{cat['name']}</td>
          <td style="padding:8px 8px;width:100%">
            <div style="background:#0d0d1a;border-radius:4px;overflow:hidden">
              <div style="width:{pct}%;background:{cat.get('color','#6c63ff')};height:22px;min-width:4px;border-radius:4px"></div>
            </div>
          </td>
          <td style="padding:8px 16px;color:#6c63ff;font-weight:700;text-align:right;white-space:nowrap">{cat['mins']} min</td>
        </tr>"""

    # Daily bar rows (last 7 days of period)
    daily_rows = ""
    daily = stats.get("daily_activity", [])[-7:]
    max_daily = max((d["mins"] for d in daily), default=1) or 1
    for day in daily:
        pct = round(day["mins"] / max_daily * 100)
        daily_rows += f"""
        <tr>
          <td style="padding:6px 16px;color:#94a3b8;font-size:13px;white-space:nowrap">{day['date']}</td>
          <td style="padding:6px 8px;width:100%">
            <div style="background:#0d0d1a;border-radius:4px;overflow:hidden">
              <div style="width:{pct}%;background:#6c63ff;height:18px;min-width:4px;border-radius:4px"></div>
            </div>
          </td>
          <td style="padding:6px 16px;color:#e2e8f0;font-size:13px;text-align:right;white-space:nowrap">{day['mins']} min</td>
        </tr>"""

    int_color = "#00d2a0" if integrity["ok"] else "#ff6b6b"
    int_icon = "OK" if integrity["ok"] else "TAMPERED"
    int_msg = (
        f"Records verified - chain intact ({integrity['events_checked']} events, "
        f"{integrity['sessions_checked']} sessions)"
        if integrity["ok"]
        else (
            f"Tampering detected - "
            f"session #{integrity.get('first_tampered_session')} or "
            f"event #{integrity.get('first_tampered_event')} was modified after recording"
        )
    )

    no_cats = "<tr><td colspan='3' style='padding:16px;color:#64748b'>No sessions in this period.</td></tr>"
    no_daily = "<tr><td colspan='3' style='padding:16px;color:#64748b'>No activity in this period.</td></tr>"

    html = f"""<!DOCTYPE html>
<html lang="en">
<head><meta charset="UTF-8"><title>Study Guard Report</title></head>
<body style="margin:0;padding:0;background:#0a0a0f;font-family:'Segoe UI',Arial,sans-serif;color:#e2e8f0">
<div style="max-width:620px;margin:0 auto;padding:32px 16px">

  <div style="background:linear-gradient(135deg,#6c63ff,#3d7df5);border-radius:20px;padding:36px;text-align:center;margin-bottom:28px">
    <div style="font-size:40px;margin-bottom:12px">📚</div>
    <h1 style="color:#fff;font-size:26px;margin:0 0 8px;font-weight:800">Study Guard Report</h1>
    <p style="color:rgba(255,255,255,0.75);margin:0;font-size:14px">Last {period_days} days &nbsp;·&nbsp; Generated {datetime.now().strftime('%d %b %Y')}</p>
  </div>

  <table style="width:100%;border-collapse:separate;border-spacing:12px;margin-bottom:16px">
    <tr>
      <td style="background:#1a1a2e;border-radius:14px;padding:22px;text-align:center;border-top:3px solid #6c63ff;width:33%">
        <div style="font-size:34px;font-weight:800;color:#6c63ff">{stats['total_study_mins']}</div>
        <div style="font-size:12px;color:#64748b;margin-top:6px">Total Minutes</div>
      </td>
      <td style="background:#1a1a2e;border-radius:14px;padding:22px;text-align:center;border-top:3px solid #00d2a0;width:33%">
        <div style="font-size:34px;font-weight:800;color:#00d2a0">{stats['sessions_count']}</div>
        <div style="font-size:12px;color:#64748b;margin-top:6px">Sessions</div>
      </td>
      <td style="background:#1a1a2e;border-radius:14px;padding:22px;text-align:center;border-top:3px solid #ff6b6b;width:33%">
        <div style="font-size:34px;font-weight:800;color:#ff6b6b">{stats['total_blocks']}</div>
        <div style="font-size:12px;color:#64748b;margin-top:6px">Distractions Blocked</div>
      </td>
    </tr>
  </table>

  <div style="background:#1a1a2e;border-radius:14px;padding:24px;margin-bottom:20px">
    <h3 style="color:#e2e8f0;margin:0 0 18px;font-size:15px;font-weight:700">Study by Category</h3>
    <table style="width:100%;border-collapse:collapse">{cat_rows if cat_rows else no_cats}</table>
  </div>

  <div style="background:#1a1a2e;border-radius:14px;padding:24px;margin-bottom:20px">
    <h3 style="color:#e2e8f0;margin:0 0 18px;font-size:15px;font-weight:700">Daily Activity</h3>
    <table style="width:100%;border-collapse:collapse">{daily_rows if daily_rows else no_daily}</table>
  </div>

  <div style="background:#1a1a2e;border-radius:14px;padding:22px;margin-bottom:28px;border-left:4px solid {int_color}">
    <h3 style="color:#e2e8f0;margin:0 0 8px;font-size:15px;font-weight:700">
      Data Integrity
      <span style="font-size:11px;font-weight:700;color:{int_color};background:rgba(108,99,255,0.15);padding:3px 10px;border-radius:20px;margin-left:8px">{int_icon}</span>
    </h3>
    <p style="color:{int_color};margin:0;font-size:13px;line-height:1.5">{int_msg}</p>
  </div>

  <p style="text-align:center;color:#334155;font-size:12px;margin:0">
    Generated by Study Guard v2 &nbsp;·&nbsp; Powered by Jev AI (TypeSafe / OpenRouter)
  </p>
</div>
</body>
</html>"""

    return html, stats


def send_report(guardian_cfg: dict, period_days: int = 7) -> None:
    """
    Send an HTML guardian report via SMTP.

    guardian_cfg keys:
        email, student_name, smtp_host, smtp_port, smtp_user, smtp_pass
    """
    html, stats = generate_report_html(period_days)

    to_email = guardian_cfg["email"]
    student_name = guardian_cfg.get("student_name", "Student")
    smtp_host = guardian_cfg.get("smtp_host", "smtp.gmail.com")
    smtp_port = int(guardian_cfg.get("smtp_port", 587))
    smtp_user = guardian_cfg["smtp_user"]
    smtp_pass = guardian_cfg["smtp_pass"]

    msg = MIMEMultipart("alternative")
    msg["Subject"] = (
        f"[Study Guard] {period_days}-Day Report - {student_name} - "
        f"{datetime.now().strftime('%d %b %Y')}"
    )
    msg["From"] = smtp_user
    msg["To"] = to_email

    plain = (
        f"Study Guard Report for {student_name}\n\n"
        f"Period: Last {period_days} days\n"
        f"Total study time: {stats['total_study_mins']} minutes\n"
        f"Sessions completed: {stats['sessions_count']}\n"
        f"Distractions blocked: {stats['total_blocks']}\n\n"
        "Please view this email in an HTML-capable mail client for the full report."
    )
    msg.attach(MIMEText(plain, "plain"))
    msg.attach(MIMEText(html, "html"))

    ctx = ssl.create_default_context()
    with smtplib.SMTP(smtp_host, smtp_port) as smtp_conn:
        smtp_conn.ehlo()
        smtp_conn.starttls(context=ctx)
        smtp_conn.login(smtp_user, smtp_pass)
        smtp_conn.sendmail(smtp_user, [to_email], msg.as_string())