"""Création de sites à partir des modèles pro (qui passent l'audit qualité dès le départ)."""
import html
import re
import unicodedata
from datetime import date
from pathlib import Path

from . import browser, mailbox
from .config import PUBLIC_URL, WORKSPACE

TEMPLATES = Path(__file__).parent / "templates"
EDITEUR_DEFAUT = ("[À compléter : nom, e-mail et téléphone du responsable de publication — un parent si le créateur "
                  "est mineur]")


def _price(v: float) -> str:
    return "" if not v else (f"{v:.2f}".replace(".00", "").replace(".", ",") + " €")


def slugify(text: str) -> str:
    plain = unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9-]+", "-", plain.lower()).strip("-")[:50]


async def create(template: str, folder: str, name: str, emoji: str, color: str, tagline: str, description: str,
                 points: list[dict], price_eur: float, price_detail: str, button_text: str, payment_link: str,
                 contact_email: str, address: str, hours: str, editor: str) -> dict:
    if template not in ("produit", "vitrine"):
        raise ValueError("modèle inconnu (produit ou vitrine)")
    plain = unicodedata.normalize("NFKD", folder).encode("ascii", "ignore").decode()
    slug = re.sub(r"[^a-z0-9-]+", "-", plain.lower()).strip("-")[:50]
    if not slug:
        raise ValueError("nom de dossier invalide")
    if not re.fullmatch(r"#[0-9a-fA-F]{6}", color or ""):
        color = "#4f46e5"
    if payment_link and not payment_link.startswith("https://"):
        raise ValueError("le lien de paiement doit commencer par https://")
    email = contact_email.strip() or (mailbox.EMAIL_USER if mailbox.ENABLED else "")
    e = lambda s: html.escape(str(s or ""), quote=True)  # noqa: E731
    pts = (points + [{"title": "", "text": ""}] * 3)[:3]
    contact_html = []
    if PUBLIC_URL:
        contact_html.append("<p>💬 Écrivez-nous dans le chat en bas à droite : on vous répond vite.</p>")
    if email:
        contact_html.append(f'<a class="btn ghost" href="mailto:{e(email)}">✉️ {e(email)}</a>')
    script = (f'<script src="{PUBLIC_URL}/public/chat.js" data-site="{slug}" data-color="{color}"></script>'
              if PUBLIC_URL else "")
    values = {
        "NOM": e(name), "EMOJI": e(emoji or "✨"), "COULEUR": color, "ACCROCHE": e(tagline),
        "ACCROCHE_COURTE": e(tagline if len(tagline) <= 55 else tagline[:52].rsplit(" ", 1)[0] + "…"),
        "DESCRIPTION": e(description), "PRIX": _price(price_eur), "PRIX_DETAIL": e(price_detail),
        "TEXTE_BOUTON": e(button_text or ("Acheter" if payment_link else "Nous contacter")),
        "LIEN_ACHAT": e(payment_link or "#contact"), "DATA_BUY": "data-buy" if payment_link else "",
        "CONTACT_HTML": "\n    ".join(contact_html) or "<p>Contact : [à compléter]</p>",
        "CONTACT_FOOTER": f' · <a href="mailto:{e(email)}">Contact</a>' if email else "",
        "CONTACT_TEXTE": f" à {e(email)}" if email else (" via le chat du site" if PUBLIC_URL else ""),
        "SCRIPT_FUSEE": script, "ANNEE": str(date.today().year), "EDITEUR": e(editor or EDITEUR_DEFAUT),
        "ADRESSE": e(address or "[Adresse à compléter]"), "HORAIRES": e(hours or "[Horaires à compléter]"),
    }
    for i, p in enumerate(pts, 1):
        values[f"POINT_{i}_TITRE"], values[f"POINT_{i}"] = e(p.get("title")), e(p.get("text"))
    values["CSS"] = (TEMPLATES / "_base.css").read_text().replace("{{COULEUR}}", color)
    dest = WORKSPACE / "sites" / slug
    if (dest / "index.html").exists():
        raise ValueError(f"le site sites/{slug} existe déjà : modifie-le avec write_file")
    dest.mkdir(parents=True, exist_ok=True)
    for f in (TEMPLATES / template).glob("*.html"):
        txt = f.read_text()
        for k, v in values.items():
            txt = txt.replace("{{" + k + "}}", v)
        (dest / f.name).write_text(txt)
    og = f"""<html><body style="margin:0;width:1200px;height:630px;display:flex;flex-direction:column;justify-content:center;
      padding:0 90px;box-sizing:border-box;font-family:system-ui,sans-serif;color:#fff;
      background:linear-gradient(135deg,{color},color-mix(in srgb,{color} 55%,#000))">
      <div style="font-size:110px">{values['EMOJI']}</div><div style="font-size:86px;font-weight:800;line-height:1.05">{values['NOM']}</div>
      <div style="font-size:40px;opacity:.9;margin-top:18px">{values['ACCROCHE_COURTE']}</div></body></html>"""
    warnings = []
    try:
        await browser.render_html(og, 1200, 630, dest / "og.png")
    except Exception as ex:  # noqa: BLE001
        warnings.append(f"image d'aperçu non générée ({str(ex)[:80]})")
    if not PUBLIC_URL and not email:
        warnings.append("aucun moyen de contact : il faut un e-mail de contact ou l'adresse publique (PUBLIC_URL)")
    if not editor:
        warnings.append("mentions légales : l'éditeur est à compléter (demande à @Clara)")
    if template == "vitrine" and (not address or not hours):
        warnings.append("adresse/horaires à compléter")
    return {"dossier": f"sites/{slug}", "fichiers": sorted(p.name for p in dest.iterdir()), "a_faire": warnings}
