"""Sends the report over SMTP. Credentials come from env vars only."""
from __future__ import annotations

import os
import smtplib
from email.message import EmailMessage


def send(html_body: str, subject: str, cfg: dict) -> bool:
    host = os.getenv("SMTP_HOST", "smtp.gmail.com")
    port = int(os.getenv("SMTP_PORT", "587"))
    user = os.getenv("SMTP_USER")
    password = os.getenv("SMTP_PASS")
    to = os.getenv("REPORT_TO") or cfg["email"]["to"]

    if not (user and password):
        print("[email] SMTP_USER / SMTP_PASS not set - skipping send")
        return False

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = f"PoloFinder <{user}>"
    msg["To"] = to
    msg.set_content("This report is best viewed as HTML.")
    msg.add_alternative(html_body, subtype="html")

    with smtplib.SMTP(host, port, timeout=60) as s:
        s.starttls()
        s.login(user, password)
        s.send_message(msg)
    print(f"[email] sent to {to}")
    return True
