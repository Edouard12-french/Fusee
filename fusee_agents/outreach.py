"""Prospection d'entreprises par e-mail, dans le cadre légal français (RGPD / recommandations CNIL).

Règles appliquées par le code (les agents ne peuvent pas les contourner) :
- uniquement des ENTREPRISES, à une adresse professionnelle trouvée publiquement (URL source conservée) ;
- campagne validée par Patron avant tout envoi (cible, message, volume) ;
- identité de l'expéditeur, raison du contact et moyen simple de refuser dans chaque e-mail ;
- liste « ne plus contacter » respectée pour toujours (STOP, désinscription, refus) ;
- 1 premier e-mail + 1 seule relance au maximum, arrêt dès qu'il y a une réponse ;
- plafond d'envois par jour, envois en semaine de 9 h à 18 h."""
import hashlib
import hmac
import os
import re
import secrets
import smtplib
import time
import urllib.parse
from datetime import datetime
from email.message import EmailMessage
from email.utils import make_msgid

from . import db, mailbox
from .config import PUBLIC_URL

DAILY_LIMIT = int(os.getenv("OUTREACH_DAILY_LIMIT", "20"))
FOLLOWUP_DAYS = 5
EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
STOP_RE = re.compile(r"\b(stop|désinscri|desinscri|unsubscribe|ne (plus|pas) (me )?(contacter|écrire|ecrire)|"
                     r"pas intéressé|pas interesse|retirez|supprimez)", re.I)


def norm(email: str) -> str:
    return email.strip().lower()


def is_suppressed(email: str) -> bool:
    e = norm(email)
    domain = e.split("@")[-1]
    return bool(db.q("SELECT 1 FROM suppression WHERE email=? OR email=?", (e, "@" + domain)))


def suppress(email: str, reason: str) -> None:
    db.x("INSERT OR IGNORE INTO suppression (email, ts, reason) VALUES (?,?,?)", (norm(email), time.time(), reason))
    db.x("UPDATE prospects SET status='ne plus contacter' WHERE lower(email)=?", (norm(email),))


def _secret() -> bytes:
    s = db.get_setting("outreach_secret", "")
    if not s:
        s = secrets.token_hex(16)
        db.set_setting("outreach_secret", s)
    return s.encode()


def stop_token(email: str) -> str:
    return hmac.new(_secret(), norm(email).encode(), hashlib.sha256).hexdigest()[:24]


def check_stop_token(email: str, token: str) -> bool:
    return hmac.compare_digest(stop_token(email), token or "")


def sent_today() -> int:
    start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
    return db.q("SELECT COUNT(*) n FROM conv WHERE channel='email' AND direction='out' AND agent LIKE 'prospection%' "
                "AND ts>=?", (start,))[0]["n"]


def business_hours(now: datetime | None = None) -> bool:
    now = now or datetime.now()
    return now.weekday() < 5 and 9 <= now.hour < 18


def footer(campaign: dict, to: str) -> str:
    sender = campaign["sender_name"]
    if PUBLIC_URL:
        link = f"{PUBLIC_URL}/public/stop?e={urllib.parse.quote(norm(to))}&t={stop_token(to)}"
        stop = f"Pour ne plus recevoir de message : {link} (ou répondez STOP)."
    else:
        stop = "Pour ne plus recevoir de message, répondez simplement STOP."
    ident = f"{sender} — {mailbox.EMAIL_USER}" if mailbox.EMAIL_USER else sender
    return (f"\n\n--\n{ident}\n"
            f"Vous recevez ce message car votre adresse professionnelle est publiée sur votre site ou une fiche "
            f"professionnelle. {stop}")


def validate_prospect(email: str, company: str, source_url: str) -> str | None:
    if not EMAIL_RE.fullmatch(email.strip()):
        return "adresse e-mail invalide"
    if not company.strip():
        return "il faut le nom de l'entreprise (prospection réservée aux professionnels)"
    if not re.match(r"^https?://", source_url.strip()):
        return "il faut l'URL publique où l'adresse a été trouvée (site de l'entreprise, fiche pro)"
    if is_suppressed(email):
        return "cette adresse a demandé à ne plus être contactée"
    return None


def _send_smtp(to: str, subject: str, body: str) -> str:
    msg = EmailMessage()
    msg["From"], msg["To"], msg["Subject"] = mailbox.EMAIL_USER, to, subject
    msg["Message-ID"] = make_msgid(domain=mailbox.EMAIL_USER.split("@")[-1] or None)
    msg["List-Unsubscribe"] = f"<mailto:{mailbox.EMAIL_USER}?subject=STOP>"
    msg.set_content(body)
    with smtplib.SMTP_SSL(mailbox.SMTP_HOST, mailbox.SMTP_PORT) as s:
        s.login(mailbox.EMAIL_USER, mailbox.EMAIL_PASSWORD)
        s.send_message(msg)
    return msg["Message-ID"]


def send(prospect: dict, subject: str, message: str, agent: str, followup: bool = False) -> str:
    """Envoie (ou prépare, sans boîte mail) un e-mail de prospection. Lève ValueError si une règle l'interdit."""
    camp = db.q("SELECT * FROM campaigns WHERE id=?", (prospect["campaign_id"],))
    if not camp or camp[0]["status"] != "active":
        raise ValueError("la campagne n'est pas active (elle doit être validée par Patron)")
    camp = camp[0]
    if is_suppressed(prospect["email"]):
        raise ValueError("cette adresse a demandé à ne plus être contactée")
    if prospect["status"] in ("a répondu", "intéressé", "client", "ne plus contacter", "sans réponse"):
        raise ValueError(f"prospect « {prospect['status']} » : on ne le relance plus")
    if prospect["sends"] >= (2 if followup else 1):
        raise ValueError("déjà contacté (1 e-mail + 1 relance maximum)")
    limit = min(camp["daily_limit"] or DAILY_LIMIT, DAILY_LIMIT)
    if sent_today() >= limit:
        raise ValueError(f"plafond du jour atteint ({limit} e-mails) : reprends demain")
    if mailbox.ENABLED and not business_hours():
        raise ValueError("envois seulement en semaine de 9 h à 18 h (respect des professionnels et meilleurs résultats)")
    body = message.strip() + footer(camp, prospect["email"])
    cid = prospect["contact_id"] or db.upsert_contact(email=prospect["email"], name=prospect["company"],
                                                      source=f"prospection : {camp['name']}")
    db.x("UPDATE contacts SET company=?, segment='entreprise' WHERE id=?", (prospect["company"], cid))
    if mailbox.ENABLED:
        mid = _send_smtp(prospect["email"], subject, body)
        db.add_conv(cid, "email", "out", body, subject=subject, message_id=mid, agent=f"prospection ({agent})")
        status = "relancé" if followup else "contacté"
        result = "envoyé"
    else:  # sans boîte mail : brouillon que Patron envoie lui-même depuis l'onglet Prospection
        status, result = "à envoyer par Patron", "préparé (boîte mail non configurée : Patron l'enverra)"
    db.x("UPDATE prospects SET status=?, contact_id=?, sends=sends+?, last_sent_ts=?, subject=?, message=? WHERE id=?",
         (status, cid, 1 if mailbox.ENABLED else 0, time.time() if mailbox.ENABLED else prospect["last_sent_ts"],
          subject, body, prospect["id"]))
    return result


def on_reply(email: str, text: str) -> str | None:
    """Appelé pour chaque e-mail reçu : arrête la séquence, gère les STOP. Renvoie le nouveau statut."""
    rows = db.q("SELECT * FROM prospects WHERE lower(email)=? ORDER BY id DESC LIMIT 1", (norm(email),))
    if STOP_RE.search(text[:600]):
        suppress(email, "réponse STOP / refus")
        return "ne plus contacter"
    if rows:
        db.x("UPDATE prospects SET status='a répondu' WHERE id=?", (rows[0]["id"],))
        return "a répondu"
    return None


def due_followups() -> list[dict]:
    limit_ts = time.time() - FOLLOWUP_DAYS * 86400
    return db.q("""SELECT p.* FROM prospects p JOIN campaigns c ON c.id=p.campaign_id
                   WHERE c.status='active' AND p.status='contacté' AND p.sends=1 AND p.last_sent_ts<=?
                   AND COALESCE(c.followup, '')!='' ORDER BY p.last_sent_ts LIMIT 50""", (limit_ts,))


def run_followups() -> int:
    """Relances automatiques (texte de relance validé avec la campagne). Les sans-réponse sont clôturés."""
    done = 0
    for p in due_followups():
        camp = db.q("SELECT * FROM campaigns WHERE id=?", (p["campaign_id"],))[0]
        subject = p["subject"] if (p["subject"] or "").lower().startswith("re:") else f"Re: {p['subject'] or camp['name']}"
        msg = camp["followup"].replace("{entreprise}", p["company"])
        try:
            send(p, subject, msg, "relance auto", followup=True)
            done += 1
        except ValueError:
            break  # plafond du jour, heures de bureau…
    old = time.time() - (FOLLOWUP_DAYS + 7) * 86400
    db.x("UPDATE prospects SET status='sans réponse' WHERE status='relancé' AND last_sent_ts<=?", (old,))
    return done


def stats(campaign_id: int) -> dict:
    rows = db.q("SELECT status, COUNT(*) n FROM prospects WHERE campaign_id=? GROUP BY status", (campaign_id,))
    by = {r["status"]: r["n"] for r in rows}
    total = sum(by.values())
    contacted = sum(by.get(k, 0) for k in ("contacté", "relancé", "a répondu", "intéressé", "client", "sans réponse",
                                            "ne plus contacter"))
    replied = sum(by.get(k, 0) for k in ("a répondu", "intéressé", "client"))
    return {"prospects": total, "contactes": contacted, "reponses": replied, "par_statut": by,
            "taux_reponse_pct": round(100 * replied / contacted, 1) if contacted else 0.0}


# --- trouver l'adresse publique d'une entreprise sur son site -----------------------------------------
_PAGES = ("", "contact", "contact.html", "nous-contacter", "contactez-nous", "mentions-legales", "mentions-legales.html",
          "a-propos", "about", "impressum")
_JUNK = re.compile(r"\.(png|jpe?g|gif|webp|svg|css|js)$|example\.|sentry|wixpress|domain\.|votre|your|email@|nom@|"
                   r"@2x|noreply|no-reply", re.I)


def find_emails(url: str) -> dict:
    """Parcourt la page d'accueil et les pages contact / mentions légales d'un site d'entreprise."""
    import urllib.parse
    import urllib.request
    if not re.match(r"^https?://", url):
        url = "https://" + url
    base = "{0.scheme}://{0.netloc}/".format(urllib.parse.urlparse(url))
    found: dict[str, str] = {}
    visited = []
    for page in _PAGES:
        u = urllib.parse.urljoin(base, page) if page else url
        try:
            req = urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0 (compatible; FuseeBot/1.0)"})
            with urllib.request.urlopen(req, timeout=12) as r:
                if "html" not in (r.headers.get("Content-Type") or "html"):
                    continue
                html = r.read(800_000).decode(errors="replace")
        except Exception:  # noqa: BLE001 — page absente : on passe à la suivante
            continue
        visited.append(u)
        text = re.sub(r"\s*(\[at\]|\(at\)|\s+arobase\s+|\s+at\s+)\s*", "@", html, flags=re.I)
        text = re.sub(r"\s*(\[dot\]|\(dot\)|\s+point\s+)\s*", ".", text, flags=re.I)
        for e in set(re.findall(r"mailto:([^\"'?>\s]+)", html, re.I)) | set(EMAIL_RE.findall(text)):
            e = urllib.parse.unquote(e).strip().strip(".").lower()
            if EMAIL_RE.fullmatch(e) and not _JUNK.search(e):
                found.setdefault(e, u)
        if len(found) >= 5 or (page == "" and found and len(visited) > 2):
            break
    domain = urllib.parse.urlparse(base).netloc.removeprefix("www.")
    emails = sorted(found.items(), key=lambda kv: (not kv[0].endswith(domain),
                                                   not kv[0].split("@")[0] in ("contact", "info", "bonjour", "hello")))
    return {"site": base, "pages_lues": visited,
            "emails": [{"email": e, "trouve_sur": src, "suppression": is_suppressed(e)} for e, src in emails]}
