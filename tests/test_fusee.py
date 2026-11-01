"""Tests de Fusée : python -m pytest -q   (aucun appel réel à l'IA, à Stripe, à Netlify ou à Apple)."""
import asyncio
import json
import time
from types import SimpleNamespace as NS

import pytest

from fusee_agents import budget, db, markets, notify, outreach, sales, tools, webpush, workflow
from fusee_agents.agents import BY_NAME, TEAM, system_prompt

WOKEN: list = []


def ex(agent, name, args):
    return asyncio.run(tools.execute(agent, name, args, lambda who, why: WOKEN.append((who, why))))


# --- notifications iPhone : chiffrement et signature conformes aux normes ------------------------------
def test_webpush_rfc8291_official_vector():
    from cryptography.hazmat.primitives.asymmetric import ec
    as_priv = ec.derive_private_key(int.from_bytes(webpush.unb64u("yfWPiYE-n46HLnH0KqZOF1fJJU3MYrct3AELtAQ-oRw"), "big"),
                                    ec.SECP256R1())
    out = webpush.encrypt(b"When I grow up, I want to be a watermelon",
                          "BCVxsr7N_eNgVRqvHtD0zTZsEc6-VV-JvLexhqUzORcxaOzi6-AYWXvTBHm4bjyPjs7Vd8pZGH6SRpkNtoIAiw4",
                          "BTBZMqHH6r4Tts7J_aSIgg", salt=webpush.unb64u("DGv6ra1nlYgDCS1FRnbzlw"), server_key=as_priv)
    assert webpush.b64u(out) == ("DGv6ra1nlYgDCS1FRnbzlwAAEABBBP4z9KsN6nGRTbVYI_c7VJSPQTBtkgcy27mlmlMoZIIgDll6e3vCYLocInmYWAmS"
                                 "6TlzAC8wEqKK6PBru3jl7A_yl95bQpu6cVPTpK4Mqgkf1CXztLVBSt2Ks3oZwbuwXPXLWyouBWLVWGNWQexSgSxsj_"
                                 "Qulcy4a-fN")


def test_webpush_vapid_signature_valid():
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.hazmat.primitives.asymmetric.utils import encode_dss_signature
    h = webpush.vapid_header("https://web.push.apple.com/abc")
    t, k = h.split("t=")[1].split(",")[0], h.split("k=")[1]
    head, claims, sig = t.split(".")
    raw = webpush.unb64u(sig)
    pub = ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), webpush.unb64u(k))
    pub.verify(encode_dss_signature(int.from_bytes(raw[:32], "big"), int.from_bytes(raw[32:], "big")),
               f"{head}.{claims}".encode(), ec.ECDSA(hashes.SHA256()))
    assert json.loads(webpush.unb64u(claims))["aud"] == "https://web.push.apple.com"


# --- outils : limites de l'API, robustesse ------------------------------------------------------------
def test_every_agent_tool_exists_and_strict_limit():
    for a in TEAM:
        assert all(n in tools.CLIENT_TOOLS or n in tools.SERVER_TOOLS for n in a.tools), a.name
        assert sum(1 for t in tools.tool_defs(a.tools, "claude-sonnet-5-5") if t.get("strict")) <= tools.MAX_STRICT_TOOLS


def test_missing_arguments_are_filled():
    assert tools.normalize_args("post_message", {"content": "x"}) == {"content": "x", "attachments": [], "links": []}


def test_mentions():
    assert tools.mentions("salut @Neo et @Wolf") == ["Neo", "Wolf"] or set(tools.mentions("salut @Neo et @Wolf")) == {"Neo", "Wolf"}
    assert len(tools.mentions("@Tous réunion")) == len(BY_NAME)
    assert tools.mentions("écris à contact@exemple.fr") == []


def test_agents_know_owner_profile_and_identity():
    db.set_setting("owner_profile", json.dumps({"prenom": "Édouard", "appel": "Ed", "ville": "Lyon"}))
    p = system_prompt(BY_NAME["Wolf"])
    assert "« Ed »" in p and "Lyon" in p and "Ne te présente pas comme « Claude »" in p


# --- sécurité de l'argent et des publications -------------------------------------------------------------
def test_expense_over_budget_is_refused():
    r = ex("Mercure", "request_approval", {"kind": "dépense", "title": "Grosse pub", "details": "x", "amount_eur": 10_000,
                                         "attachments": [], "links": []})
    assert r.startswith("Refusé")


def test_publish_requires_owner_approval():
    ex("Neo", "write_file", {"path": "sites/test-pub/index.html", "content": "<html><title>x</title></html>"})
    assert ex("Neo", "publish_site", {"folder": "sites/test-pub", "approval_id": 0}).startswith("Refusé")


def test_agent_code_cannot_read_secrets(monkeypatch):
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_live_SECRET")
    ex("Forge", "write_file", {"path": "outils/espion.py", "content": "import os\nprint([k for k in os.environ if 'SECRET' in k])"})
    assert "SECRET_KEY" not in ex("Forge", "run_tool", {"name": "espion", "args": []}).split("--- stderr")[0]


def test_paths_outside_workspace_refused():
    with pytest.raises(ValueError):
        tools._safe_path("../../etc/passwd")


# --- coordination -------------------------------------------------------------------------------------------
def test_sequence_passes_results_along():
    WOKEN.clear()
    jid = workflow.start("Relais", "séquence", "Test séquence", [{"agent": "Scout", "instruction": "étudie"},
                                                              {"agent": "Victor", "instruction": "fixe le prix"}],
                         lambda w, r: WOKEN.append(w))
    t1, t2 = [t["id"] for t in db.q("SELECT id FROM tasks WHERE job_id=? ORDER BY idx", (jid,))]
    assert WOKEN == ["Scout"]
    assert "pas à toi" in workflow.complete("Victor", t1, "x", True, lambda *a: None)
    workflow.complete("Scout", t1, "3 concurrents à 15 €", True, lambda w, r: WOKEN.append(w))
    assert "3 concurrents" in workflow.agent_context("Victor")
    workflow.complete("Victor", t2, "9 €", True, lambda w, r: WOKEN.append(w))
    assert WOKEN[-1] == "Relais" and db.q("SELECT status FROM jobs WHERE id=?", (jid,))[0]["status"] == "terminé"


def test_needs_go_through_clara():
    WOKEN.clear()
    r = ex("Wolf", "submit_need", {"need": "Ton horizon de placement ?", "why": "stratégie", "urgency": "important", "options": []})
    assert "Clara" in r and WOKEN[-1][0] == "Clara"
    assert "déjà" in ex("Wolf", "submit_need", {"need": "Ton horizon de placement ?", "why": "x", "urgency": "normal", "options": []})


# --- prospection : règles légales appliquées par le code ------------------------------------------------
def test_outreach_guardrails(monkeypatch):
    assert outreach.validate_prospect("contact@boulangerie.fr", "Boulangerie", "") is not None  # source obligatoire
    cid = db.x("INSERT INTO campaigns (ts, agent, name, sender_name, followup, daily_limit, status) VALUES (?,?,?,?,?,?,?)",
               (time.time(), "Victor", "Test", "L'équipe", "Relance pour {entreprise}", 1, "en attente de validation"))
    pid = db.x("INSERT INTO prospects (ts, agent, campaign_id, company, email, source_url) VALUES (?,?,?,?,?,?)",
               (time.time(), "Victor", cid, "Boulangerie", "contact@boulangerie-test.fr", "https://x.fr"))
    p = db.q("SELECT * FROM prospects WHERE id=?", (pid,))[0]
    with pytest.raises(ValueError, match="pas active"):
        outreach.send(p, "Objet", "Bonjour", "Victor")
    db.x("UPDATE campaigns SET status='active' WHERE id=?", (cid,))
    sent = []
    monkeypatch.setattr(outreach.mailbox, "ENABLED", True)
    monkeypatch.setattr(outreach, "business_hours", lambda now=None: True)
    monkeypatch.setattr(outreach, "_send_smtp", lambda to, s, b: sent.append((to, b)) or "<id>")
    assert outreach.send(p, "Objet", "Bonjour", "Victor") == "envoyé"
    assert "ne plus recevoir" in sent[-1][1]  # désinscription toujours présente
    outreach.on_reply("contact@boulangerie-test.fr", "Stop merci")
    assert outreach.is_suppressed("contact@boulangerie-test.fr")
    assert outreach.validate_prospect("contact@boulangerie-test.fr", "Boulangerie", "https://x.fr") is not None


def test_unsubscribe_token():
    tok = outreach.stop_token("a@b.fr")
    assert outreach.check_stop_token("A@B.fr", tok) and not outreach.check_stop_token("a@b.fr", "faux")


# --- ventes, budget, mémoire ------------------------------------------------------------------------------
def test_sales_attributed_to_product_and_first_import_silent():
    prod = db.x("INSERT INTO products (ts, agent, name, kind, price_eur) VALUES (?,?,?,?,?)", (time.time(), "Neo", "TestProd", "appli", 9))
    db.x("INSERT INTO payment_links (ts, agent, name, price_eur, url, stripe_id, product_id) VALUES (?,?,?,?,?,?,?)",
         (time.time(), "Victor", "TestProd", 9, "https://buy.stripe.com/x", "plink_test", prod))
    c = {"id": "cs_test_1", "ts": time.time(), "amount": 9.0, "currency": "eur", "email": "client@ex.fr", "name": "Client",
         "payment_link": "plink_test"}
    woken = []
    assert sales.ingest([c], lambda w, r: woken.append(w), silent=True) and woken == []
    assert sales.ingest([c], lambda *a: None) == []  # pas de doublon
    assert db.q("SELECT product_id FROM sales WHERE id='cs_test_1'")[0]["product_id"] == prod


def test_budget_daily_cap():
    s = budget.settings()
    assert abs(budget.daily_cap_usd() * 0.92 - s["api_budget_eur"] / s["api_days"]) < 0.01


def test_collective_memory_search():
    db.kb_add("Victor", "Prix artisans", "Les artisans acceptent 9 €/mois")
    assert any("artisans" in h["content"] for h in db.kb_search("quel prix pour un artisan ?"))


def test_quiet_hours():
    from datetime import datetime
    db.set_setting("notif_quiet", "1"); db.set_setting("notif_quiet_from", "22"); db.set_setting("notif_quiet_to", "8")
    assert notify.is_quiet(datetime(2026, 1, 1, 23)) and not notify.is_quiet(datetime(2026, 1, 1, 12))


# --- bourse : calculs ----------------------------------------------------------------------------------------
def test_market_indicators_and_backtest(monkeypatch):
    assert markets.sma([1, 2, 3, 4], 2) == [None, 1.5, 2.5, 3.5]
    assert abs(markets.max_drawdown([100, 120, 60, 130]) + 0.5) < 1e-9
    px = [100 * (1.001 ** i) for i in range(400)]
    monkeypatch.setattr(markets, "_yahoo", lambda s, d: {"symbol": s, "currency": "EUR", "name": "", "source": "test",
                                                        "dates": [str(i) for i in range(400)], "closes": px, "last_price": px[-1]})
    markets._cache.clear()
    b = markets.backtest("TEST", "achat_conservation", days=400, fee_pct=0)
    assert abs(b["rendement_total_pct"] - b["comparaison_achat_conservation_pct"]) < 0.01


# --- serveur : la partie publique n'expose QUE le chat ---------------------------------------------------
def test_public_server_exposes_only_public_routes():
    from fastapi.testclient import TestClient
    from fusee_agents.web import public_app
    c = TestClient(public_app)
    for path in ("/", "/api/state", "/api/setup", "/api/owner", "/w/"):
        assert c.get(path).status_code == 404, path
    assert c.get("/public/a.js").status_code == 200


def test_setup_never_returns_secrets(tmp_path, monkeypatch):
    from fusee_agents import setup
    monkeypatch.setattr(setup, "ENV", tmp_path / ".env")
    monkeypatch.setattr(setup, "EXAMPLE", tmp_path / "absent")
    setup.save({"ANTHROPIC_API_KEY": "sk-ant-secret-1234567890wxyz", "NTFY_TOPIC": "fusee-abcdefghij"})
    cur = setup.current()
    assert "secret" not in cur["ANTHROPIC_API_KEY"]["value"] and cur["ANTHROPIC_API_KEY"]["value"].endswith("wxyz")
    setup.save({"ANTHROPIC_API_KEY": ""})  # vide = on garde l'ancienne clé
    assert "sk-ant-secret" in (tmp_path / ".env").read_text()


# --- réunion et discussion privée (IA simulée) ----------------------------------------------------------
def test_meeting_and_private_chat(monkeypatch):
    from fusee_agents import runner

    async def fake(**kw):
        if "Discussion privée" in kw["system"][0]["text"]:
            txt = "Salut Ed !\nACTION: je prépare un plan"
        else:
            txt = "Présent !"
        return NS(usage=NS(input_tokens=10, output_tokens=5, cache_read_input_tokens=0, cache_creation_input_tokens=0,
                           server_tool_use=None), stop_reason="end_turn", model=kw["model"], content=[NS(type="text", text=txt)])

    monkeypatch.setattr(runner, "client", NS(beta=NS(messages=NS(create=fake))))
    woken = []
    before = db.q("SELECT COUNT(*) n FROM messages")[0]["n"]
    asyncio.run(runner.run_meeting([BY_NAME["Neo"], BY_NAME["Wolf"]], "Bonjour", lambda w, r: woken.append(w)))
    assert db.q("SELECT COUNT(*) n FROM messages")[0]["n"] == before + 2
    db.x("INSERT INTO dms (ts, agent, sender, content, read) VALUES (?,?,?,?,1)", (time.time(), "Wolf", "Patron", "Salut"))
    asyncio.run(runner.dm_reply(BY_NAME["Wolf"], lambda w, r: woken.append(w)))
    last = runner.dm_thread("Wolf")[-1]
    assert last["sender"] == "Wolf" and "Je m'en occupe" in last["content"] and woken == ["Wolf"]


def test_full_context_builds_for_every_agent():
    from fusee_agents import runner
    for a in TEAM:
        ctx = runner.build_context(a, "test")
        assert "## Budget" in ctx and "## Derniers messages du groupe" in ctx, a.name
        assert len(system_prompt(a)) > 1000
