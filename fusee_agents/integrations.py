"""Mise en ligne (Netlify) et paiements (Stripe), via les clés API de Patron."""
import io
import json
import os
import re
import unicodedata
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path

NETLIFY_TOKEN = os.getenv("NETLIFY_TOKEN", "").strip()
STRIPE_KEY = os.getenv("STRIPE_SECRET_KEY", "").strip()


def _req(url: str, *, data: bytes | None = None, headers: dict, method: str = "GET") -> dict:
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            return json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"HTTP {e.code} : {e.read()[:500].decode(errors='replace')}") from None


# --- Netlify -----------------------------------------------------------------
def deploy_site(folder: Path, site_name: str, site_id: str | None) -> dict:
    """Publie un dossier statique sur Netlify. Crée le site au premier déploiement."""
    if not NETLIFY_TOKEN:
        raise RuntimeError("NETLIFY_TOKEN manquant dans .env")
    auth = {"Authorization": f"Bearer {NETLIFY_TOKEN}"}
    if not site_id:
        plain = unicodedata.normalize("NFKD", site_name).encode("ascii", "ignore").decode()
        name = re.sub(r"[^a-z0-9-]+", "-", plain.lower()).strip("-")[:50]
        try:
            site = _req("https://api.netlify.com/api/v1/sites", data=json.dumps({"name": name}).encode(),
                        headers={**auth, "Content-Type": "application/json"}, method="POST")
        except RuntimeError:  # nom déjà pris : Netlify en génère un
            site = _req("https://api.netlify.com/api/v1/sites", data=b"{}",
                        headers={**auth, "Content-Type": "application/json"}, method="POST")
        site_id = site["id"]
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for f in folder.rglob("*"):
            if f.is_file() and "__pycache__" not in f.parts:
                z.write(f, f.relative_to(folder))
    dep = _req(f"https://api.netlify.com/api/v1/sites/{site_id}/deploys", data=buf.getvalue(),
               headers={**auth, "Content-Type": "application/zip"}, method="POST")
    url = dep.get("ssl_url") or dep.get("url") or ""
    return {"site_id": site_id, "url": url}


# --- Stripe ------------------------------------------------------------------
def _stripe(path: str, params: dict | None = None, method: str = "POST") -> dict:
    if not STRIPE_KEY:
        raise RuntimeError("STRIPE_SECRET_KEY manquante dans .env")
    data = urllib.parse.urlencode(params or {}).encode() if method == "POST" else None
    url = f"https://api.stripe.com/v1/{path}" + ("" if method == "POST" or not params else "?" + urllib.parse.urlencode(params))
    return _req(url, data=data, method=method, headers={"Authorization": f"Bearer {STRIPE_KEY}"})


def create_payment_link(name: str, price_eur: float, description: str) -> dict:
    prod = _stripe("products", {"name": name[:250], "description": description[:500]})
    price = _stripe("prices", {"product": prod["id"], "currency": "eur", "unit_amount": int(round(price_eur * 100))})
    link = _stripe("payment_links", {"line_items[0][price]": price["id"], "line_items[0][quantity]": 1})
    return {"url": link["url"], "id": link["id"]}


def sales_summary() -> dict:
    """Ventes réelles encaissées sur Stripe (100 dernières)."""
    charges = _stripe("charges", {"limit": 100}, method="GET")["data"]
    paid = [c for c in charges if c.get("paid") and not c.get("refunded")]
    return {"count": len(paid), "total_eur": sum(c["amount"] for c in paid if c["currency"] == "eur") / 100,
            "recent": [{"ts": c["created"], "amount": c["amount"] / 100, "currency": c["currency"],
                        "description": c.get("description") or "", "email": (c.get("billing_details") or {}).get("email")}
                       for c in paid[:20]]}


def completed_checkouts(limit: int = 100) -> list[dict]:
    """Paiements terminés (sessions Checkout, y compris via liens de paiement), du plus récent au plus ancien."""
    data = _stripe("checkout/sessions", {"limit": limit, "status": "complete"}, method="GET")["data"]
    out = []
    for c in data:
        if c.get("payment_status") not in ("paid", "no_payment_required"):
            continue
        cd = c.get("customer_details") or {}
        out.append({"id": c["id"], "ts": c["created"], "amount": (c.get("amount_total") or 0) / 100,
                    "currency": c.get("currency") or "eur", "email": cd.get("email") or "", "name": cd.get("name") or "",
                    "payment_link": c.get("payment_link") or ""})
    return out
