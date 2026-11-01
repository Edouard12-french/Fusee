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
    """Récupère les mails non lus, les range dans la fiche du contact, renvoie les ids des contacts concernés."""
    contacts = []
    with imaplib.IMAP4_SSL(IMAP_HOST) as m:
        m.login(EMAIL_USER, EMAIL_PASSWORD)
        m.select("INBOX")
        _, data = m.search(None, "UNSEEN")
        for num in data[0].split():
            _, parts = m.fetch(num, "(RFC822)")
            msg = email.message_from_bytes(parts[0][1])
            mid = msg.get("Message-ID", "")
            if mid and db.q("SELECT id FROM conv WHERE message_id=?", (mid,)):
                continue
            name, addr = parseaddr(msg.get("From", ""))
            cid = db.upsert_contact(email=addr, name=str(make_header(decode_header(name))) if name else "",
                                    source="e-mail")
            db.add_conv(cid, "email", "in", _text(msg)[:20000],
                        subject=str(make_header(decode_header(msg.get("Subject", "")))), message_id=mid)
            from . import outreach  # import local : évite une boucle d'imports
            if outreach.on_reply(addr, _text(msg)) == "ne plus contacter":
                db.x("UPDATE contacts SET status='perdu' WHERE id=?", (cid,))
            contacts.append(cid)
    return sorted(set(contacts))


def send(contact_id: int, body: str, agent: str = "") -> None:
    """Répond par e-mail au contact, dans le fil de son dernier message."""
    c = db.q("SELECT * FROM contacts WHERE id=?", (contact_id,))[0]
    last = db.q("SELECT * FROM conv WHERE contact_id=? AND channel='email' AND direction='in' ORDER BY id DESC LIMIT 1",
                (contact_id,))
    subj = last[0]["subject"] if last else ""
    msg = EmailMessage()
    msg["From"], msg["To"] = EMAIL_USER, c["email"]
    msg["Subject"] = subj if subj.lower().startswith("re:") else (f"Re: {subj}" if subj else "Votre demande")
    if last and last[0]["message_id"]:
        msg["In-Reply-To"] = msg["References"] = last[0]["message_id"]
    msg.set_content(body + (f"\n\n{SIGNATURE}" if SIGNATURE else ""))
    with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT) as s:
        s.login(EMAIL_USER, EMAIL_PASSWORD)
        s.send_message(msg)
    db.add_conv(contact_id, "email", "out", body, subject=msg["Subject"], agent=agent)


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
