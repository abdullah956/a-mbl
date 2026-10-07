"""Optional email alerts for flagged cases (functional requirement FR5).

Feature-flagged like OCR: configured entirely through environment variables so
whoever runs the server plugs in their own mailbox; with nothing configured,
nothing is sent and the in-app alerts remain the only channel. Alert emails
carry the same fields as alert rows — severity, category, subject name — and
never any message content (roadmap §14.1).

    A_MBL_SMTP_HOST      e.g. smtp.gmail.com (required)
    A_MBL_SMTP_FROM      sender address (required)
    A_MBL_SMTP_PORT      default 587
    A_MBL_SMTP_USER      login user, if the server needs one
    A_MBL_SMTP_PASSWORD  login password (for Gmail: an app password)
    A_MBL_SMTP_STARTTLS  default 1; set 0 only for a local test relay
"""

import os
import smtplib
import threading
from email.message import EmailMessage


def _config() -> dict | None:
    host = os.environ.get("A_MBL_SMTP_HOST", "").strip()
    sender = os.environ.get("A_MBL_SMTP_FROM", "").strip()
    if not host or not sender:
        return None
    return {
        "host": host,
        "port": int(os.environ.get("A_MBL_SMTP_PORT", "587")),
        "user": os.environ.get("A_MBL_SMTP_USER", "").strip(),
        "password": os.environ.get("A_MBL_SMTP_PASSWORD", ""),
        "sender": sender,
        "starttls": os.environ.get("A_MBL_SMTP_STARTTLS", "1") != "0",
    }


def available() -> bool:
    return _config() is not None


def send_case_alerts(recipients: list[dict], severity: str,
                     primary_label: str, subject_name: str) -> None:
    """Email each recipient about a newly flagged case. Fire-and-forget: runs
    on a daemon thread and never blocks or fails the request that raised the
    alert. ``recipients`` items need ``email`` and ``displayName``."""
    config = _config()
    if config is None or not recipients:
        return
    _spawn(config, recipients, severity, primary_label, subject_name)


def _spawn(config: dict, recipients: list[dict], severity: str,
           primary_label: str, subject_name: str) -> None:
    threading.Thread(
        target=_deliver,
        args=(config, recipients, severity, primary_label, subject_name),
        daemon=True,
    ).start()


def _deliver(config: dict, recipients: list[dict], severity: str,
             primary_label: str, subject_name: str) -> None:
    label = primary_label.replace("_", " ")
    for recipient in recipients:
        message = EmailMessage()
        message["From"] = config["sender"]
        message["To"] = recipient["email"]
        message["Subject"] = f"a-mbl alert: {severity}-severity case involving {subject_name}"
        message.set_content(
            f"Hello {recipient['displayName']},\n"
            "\n"
            f"a-mbl flagged a possible {label} case ({severity} severity) involving "
            f"{subject_name}.\n"
            "\n"
            "For privacy, this email contains no message content. Open the a-mbl app "
            "to review the case.\n"
            "\n"
            "Classifications are automated estimates, not judgments about a person or "
            "incident."
        )
        try:
            _send_one(config, message)
        except Exception as exc:  # a mail failure must never break the API
            print(f"[emailer] could not send alert to {recipient['email']}: {exc}")


def _send_one(config: dict, message: EmailMessage) -> None:
    with smtplib.SMTP(config["host"], config["port"], timeout=15) as smtp:
        if config["starttls"]:
            smtp.starttls()
        if config["user"]:
            smtp.login(config["user"], config["password"])
        smtp.send_message(message)
