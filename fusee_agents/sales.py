"""Détection des ventes Stripe en temps réel : enregistrement, attribution au produit, notification."""
import asyncio

from . import db, integrations
from .config import USD_EUR
from .notify import notify

POLL_SECONDS = 180


def ingest(checkouts: list[dict], wake, silent: bool = False) -> list[dict]:
    """Enregistre les nouvelles ventes ; renvoie celles qui sont nouvelles (silent : import de l'historique)."""
    new = []
    for c in sorted(checkouts, key=lambda c: c["ts"]):
        if db.q("SELECT id FROM sales WHERE id=?", (c["id"],)):
            continue
        link = db.q("SELECT * FROM payment_links WHERE stripe_id=?", (c["payment_link"],)) if c["payment_link"] else []
        product_id = link[0]["product_id"] if link else None
        product = db.q("SELECT * FROM products WHERE id=?", (product_id,)) if product_id else []
        name = product[0]["name"] if product else (link[0]["name"] if link else "vente Stripe")
        amount = c["amount"] if c["currency"] == "eur" else c["amount"] * (USD_EUR if c["currency"] == "usd" else 1)
        db.x("INSERT INTO sales (id, ts, amount_eur, currency, email, name, payment_link, product_id, description) "
             "VALUES (?,?,?,?,?,?,?,?,?)", (c["id"], c["ts"], amount, c["currency"], c["email"], c["name"],
                                            c["payment_link"], product_id, name))
        if c["email"]:
            cid = db.upsert_contact(email=c["email"], name=c["name"], source="achat Stripe")
            db.x("UPDATE contacts SET status='client', score=MAX(score, 90) WHERE id=?", (cid,))
        if product and product[0]["status"] != "en vente":
            db.x("UPDATE products SET status='en vente' WHERE id=?", (product_id,))
        new.append({**c, "product": name, "amount_eur": amount})
    if silent:
        return new
    for s in new:
        who = s["name"] or s["email"] or "un client"
        db.post_message("Victor", f"💶 NOUVELLE VENTE : {s['product']} — {s['amount_eur']:.2f} € ({who}) 🎉")
        notify("client", f"💶 Vente ! {s['product']} — {s['amount_eur']:.2f} €", f"Client : {who}", priority="high")
        db.log("Victor", "vente", f"{s['product']} — {s['amount_eur']:.2f} € par {who}")
    if new:
        wake("Victor", f"{len(new)} nouvelle(s) vente(s) : remercie, propose la suite (upsell honnête), note ce qui a marché")
        wake("Atlas", f"{len(new)} nouvelle(s) vente(s) — total : {sum(s['amount_eur'] for s in new):.2f} €")
    return new


async def poll_forever(wake) -> None:
    if not integrations.STRIPE_KEY:
        return
    while True:
        try:
            checkouts = await asyncio.to_thread(integrations.completed_checkouts)
            first = db.get_setting("sales_initialized", "0") != "1"
            ingest(checkouts, wake, silent=first)
            if first:
                db.set_setting("sales_initialized", "1")
        except Exception as e:  # noqa: BLE001
            db.log("système", "erreur", f"lecture des ventes Stripe : {str(e)[:300]}")
        await asyncio.sleep(POLL_SECONDS)
