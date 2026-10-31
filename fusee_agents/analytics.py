"""Statistiques des sites : visites, provenance, clics « acheter », ouvertures du chat. Sans cookies."""
import time
from datetime import date, timedelta

from . import db

EVENTS = {"vue", "clic_achat", "chat_ouvert", "chat_message", "clic_contact"}


def record(site: str, path: str, event: str, visitor: str, ref: str, utm: str, device: str) -> None:
    if event not in EVENTS:
        return
    db.x("INSERT INTO events (ts, day, site, path, event, visitor, ref, utm, device) VALUES (?,?,?,?,?,?,?,?,?)",
         (time.time(), date.today().isoformat(), site[:60], path[:200], event, visitor[:40], ref[:120], utm[:80],
          device[:10]))


def _since(days: int) -> str:
    return (date.today() - timedelta(days=days - 1)).isoformat()


def site_stats(site: str, days: int = 7) -> dict:
    since = _since(days)
    rows = db.q("SELECT event, COUNT(*) n, COUNT(DISTINCT visitor) u FROM events WHERE site=? AND day>=? GROUP BY event",
                (site, since))
    by = {r["event"]: r for r in rows}
    visitors = by.get("vue", {}).get("u", 0)
    per_day = db.q("SELECT day, COUNT(DISTINCT visitor) u FROM events WHERE site=? AND day>=? AND event='vue' "
                   "GROUP BY day ORDER BY day", (site, since))
    refs = db.q("SELECT CASE WHEN utm!='' THEN utm WHEN ref!='' THEN ref ELSE 'direct' END src, "
                "COUNT(DISTINCT visitor) u FROM events WHERE site=? AND day>=? AND event='vue' "
                "GROUP BY src ORDER BY u DESC LIMIT 8", (site, since))
    pages = db.q("SELECT path, COUNT(*) n FROM events WHERE site=? AND day>=? AND event='vue' "
                 "GROUP BY path ORDER BY n DESC LIMIT 8", (site, since))
    devices = db.q("SELECT device, COUNT(DISTINCT visitor) u FROM events WHERE site=? AND day>=? AND event='vue' "
                   "GROUP BY device", (site, since))
    prod = db.q("SELECT id FROM products WHERE site_folder LIKE ?", (f"%{site}",))
    sales = db.q("SELECT COUNT(*) n, COALESCE(SUM(amount_eur), 0) t FROM sales WHERE product_id=? AND ts>=?",
                 (prod[0]["id"], time.time() - days * 86400))[0] if prod else {"n": 0, "t": 0}
    buy = by.get("clic_achat", {}).get("u", 0)
    return {
        "site": site, "jours": days, "visiteurs": visitors, "pages_vues": by.get("vue", {}).get("n", 0),
        "clics_achat": buy, "chats_ouverts": by.get("chat_ouvert", {}).get("u", 0),
        "messages_chat": by.get("chat_message", {}).get("n", 0), "ventes": sales["n"], "ca_eur": round(sales["t"], 2),
        "taux_clic_achat": round(100 * buy / visitors, 1) if visitors else 0.0,
        "taux_conversion": round(100 * sales["n"] / visitors, 2) if visitors else 0.0,
        "par_jour": per_day, "sources": refs, "pages": pages, "appareils": devices,
    }


def all_sites_summary(days: int = 7) -> list[dict]:
    sites = [r["site"] for r in db.q("SELECT DISTINCT site FROM events WHERE day>=?", (_since(days),))]
    out = []
    for s in sites:
        st = site_stats(s, days)
        out.append({k: st[k] for k in ("site", "visiteurs", "clics_achat", "chats_ouverts", "ventes", "ca_eur",
                                       "taux_conversion")})
    return sorted(out, key=lambda r: -r["visiteurs"])
