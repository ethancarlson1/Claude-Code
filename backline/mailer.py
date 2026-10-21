"""Sending email from the platform: gig offers and updates to crew, and a
note to the office when someone answers an offer.

It goes out through any email account that allows SMTP, set up with the
BACKLINE_SMTP_* variables: the company's Google Workspace or Microsoft 365
mailbox, or an email service such as Postmark or SendGrid. Until it's set
up, the office sends the same messages from its own email or texting app
with one click."""

import os
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formataddr, parseaddr

from . import db, demo


class MailError(Exception):
    """Email couldn't be sent. The message says why, in plain words."""


def config():
    username = os.environ.get("BACKLINE_SMTP_USERNAME", "").strip()
    return {
        "host": os.environ.get("BACKLINE_SMTP_HOST", "").strip(),
        "port": int(os.environ.get("BACKLINE_SMTP_PORT", "").strip() or 587),
        "username": username,
        "password": os.environ.get("BACKLINE_SMTP_PASSWORD", ""),
        "sender": os.environ.get("BACKLINE_MAIL_FROM", "").strip() or username,
    }


def configured():
    """Email is set up (and never from the public demo)."""
    c = config()
    return bool(c["host"] and "@" in c["sender"]) and not demo.enabled()


def sender():
    name, address = parseaddr(config()["sender"])
    return formataddr((name or db.get_setting("company_name") or "", address))


def send(to, subject, body, reply_to=None):
    if not configured():
        raise MailError("Email isn't set up on this server yet.")
    msg = EmailMessage()
    msg["From"] = sender()
    msg["To"] = to
    msg["Subject"] = subject
    reply_to = reply_to or db.get_setting("company_email")
    if reply_to:
        msg["Reply-To"] = reply_to
    msg.set_content(body)
    try:
        _deliver(msg, config())
    except smtplib.SMTPAuthenticationError as exc:
        raise MailError("The email server didn't accept the username or password (BACKLINE_SMTP_USERNAME and "
                        "BACKLINE_SMTP_PASSWORD). Gmail and Microsoft 365 need an app password here, not your "
                        "normal one.") from exc
    except smtplib.SMTPRecipientsRefused as exc:
        raise MailError(f"The email server wouldn't send to {to}. Check the address.") from exc
    except (smtplib.SMTPException, OSError) as exc:
        raise MailError(f"Couldn't send email through {config()['host']}: {exc}") from exc


def _deliver(msg, c):
    """Hand the message to the mail server. (Tests swap this out.)"""
    context = ssl.create_default_context()
    if c["port"] == 465:
        server = smtplib.SMTP_SSL(c["host"], c["port"], context=context, timeout=20)
    else:
        server = smtplib.SMTP(c["host"], c["port"], timeout=20)
    with server:
        if c["port"] != 465:
            server.starttls(context=context)
        if c["username"]:
            server.login(c["username"], c["password"])
        server.send_message(msg)
