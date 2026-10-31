"""Boîte mail du service client : lecture IMAP + envoi SMTP (bibliothèque standard Python)."""
import asyncio
import email
import imaplib
import os
import smtplib
from email.header import decode_header, make_header
from email.message import EmailMessage
from email.utils import parseaddr

from . import db

IMAP_HOST = os.getenv("IMAP_HOST", "")
SMTP_HOST = os.getenv("SMTP_HOST", "")
SMTP_PORT = int(os.getenv("SMTP_PORT", "465"))
EMAIL_USER = os.getenv("EMAIL_USER", "")
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD", "")
SIGNATURE = os.getenv("EMAIL_SIGNATURE", "")
POLL_SECONDS = int(os.getenv("EMAIL_POLL_SECONDS", "120"))

ENABLED = bool(IMAP_HOST and SMTP_HOST and EMAIL_USER and EMAIL_PASSWORD)


def _text(msg: email.message.Message) -> str:
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain" and "attachment" not in str(part.get("Content-Disposition")):
                return part.get_payload(decode=True).decode(part.get_content_charset() or "utf-8", "replace")
        for part in msg.walk():
            if part.get_content_type() == "text/html":
                import re
                html = part.get_payload(decode=True).decode(part.get_content_charset() or "utf-8", "replace")
                return re.sub(r"<[^>]+>", " ", html)
        return ""
    return msg.get_payload(decode=True).decode(msg.get_content_charset() or "utf-8", "replace")


def fetch_new() -> list[int]:
    """Récupère les mails non lus, les enregistre, renvoie les ids créés."""
    new_ids = []
    with imaplib.IMAP4_SSL(IMAP_HOST) as m:
        m.login(EMAIL_USER, EMAIL_PASSWORD)
        m.select("INBOX")
        _, data = m.search(None, "UNSEEN")
        for num in data[0].split():
            _, parts = m.fetch(num, "(RFC822)")
            msg = email.message_from_bytes(parts[0][1])
            mid = msg.get("Message-ID", "")
            if mid and db.q("SELECT id FROM inbox WHERE message_id=?", (mid,)):
                continue
            new_ids.append(db.x(
                "INSERT INTO inbox (ts, from_addr, subject, body, message_id, status) "
                "VALUES (CAST(strftime('%s','now') AS REAL),?,?,?,?, 'nouveau')",
                (parseaddr(msg.get("From", ""))[1], str(make_header(decode_header(msg.get("Subject", "")))),
                 _text(msg)[:20000], mid)))
    return new_ids


def send(inbox_id: int, body: str) -> None:
    row = db.q("SELECT * FROM inbox WHERE id=?", (inbox_id,))[0]
    msg = EmailMessage()
    msg["From"], msg["To"] = EMAIL_USER, row["from_addr"]
    subj = row["subject"] or ""
    msg["Subject"] = subj if subj.lower().startswith("re:") else f"Re: {subj}"
    if row["message_id"]:
        msg["In-Reply-To"] = msg["References"] = row["message_id"]
    msg.set_content(body + (f"\n\n{SIGNATURE}" if SIGNATURE else ""))
    with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT) as s:
        s.login(EMAIL_USER, EMAIL_PASSWORD)
        s.send_message(msg)
    db.x("UPDATE inbox SET status='répondu', reply=?, replied_ts=CAST(strftime('%s','now') AS REAL) WHERE id=?",
         (body, inbox_id))


async def poll_forever(on_new) -> None:
    if not ENABLED:
        return
    while True:
        try:
            ids = await asyncio.to_thread(fetch_new)
            if ids:
                on_new(ids)
        except Exception as e:  # noqa: BLE001
            db.log("système", "erreur", f"lecture des mails : {e}")
        await asyncio.sleep(POLL_SECONDS)
