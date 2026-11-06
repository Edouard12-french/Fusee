"""Tests de Fusée : python -m pytest -q   (aucun appel réel à l'IA, à Stripe, à Netlify ou à Apple)."""
import asyncio
import json
import os
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


def test_qr_code_for_iphone(monkeypatch):
    from fastapi.testclient import TestClient
    from fusee_agents import web
    c = TestClient(web.app)
    monkeypatch.setattr(web.setup_mod, "_read", lambda: {"DASHBOARD_URL": ""})
    assert c.get("/api/qr").status_code == 404  # pas encore d'adresse privée
    assert c.get("/api/qr?for=tailscale").status_code == 200  # mais le QR pour installer Tailscale, oui
    monkeypatch.setattr(web.setup_mod, "_read", lambda: {"DASHBOARD_URL": "https://mac.tail1.ts.net"})
    r = c.get("/api/qr")
    assert r.status_code == 200 and r.headers["content-type"].startswith("image/svg+xml") and b"<svg" in r.content
    assert c.get("/api/device_url").json() == {"url": "https://mac.tail1.ts.net"}
    assert TestClient(web.public_app).get("/api/qr").status_code == 404  # jamais sur le serveur public


def test_site_chat_voice_message_is_marked_for_iris():
    from fastapi.testclient import TestClient
    from fusee_agents import web
    from fusee_agents.agents import BY_NAME as A
    c = TestClient(web.public_app)
    woke = []
    web.scheduler.wake, old = (lambda n, r: woke.append((n, r))), web.scheduler.wake
    try:
        sess = "voix-" + "x" * 20
        assert c.post("/public/chat/send", content=json.dumps(
            {"session": sess, "message": "Bonjour, c'est combien ?", "site": "demo", "voice": True})).status_code == 200
        assert c.post("/public/chat/send", content=json.dumps(
            {"session": sess, "message": "Et le délai ?", "site": "demo", "voice": "oui"})).status_code == 200
    finally:
        web.scheduler.wake = old
    cid = db.q("SELECT id FROM contacts WHERE session=?", (sess,))[0]["id"]
    msgs = [r["content"] for r in db.q("SELECT content FROM conv WHERE contact_id=? ORDER BY id", (cid,))]
    assert msgs == ["🎤 Bonjour, c'est combien ?", "Et le délai ?"]  # seul voice=true compte
    assert woke[0][0] == "Iris" and "VOCAL" in woke[0][1] and "VOCAL" not in woke[1][1]
    assert "LUE À VOIX HAUTE" in A["Iris"].prompt and "assistant virtuel (IA)" in system_prompt(A["Iris"])


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


def test_grammar_too_large_retries_without_strict():
    """Si l'API refuse les schémas stricts (« compiled grammar is too large »), l'agent réessaie sans et continue."""
    import anthropic
    try:
        import httpx2 as httpx
    except ImportError:
        import httpx
    from fusee_agents import runner
    calls = []

    def handler(req):
        body = json.loads(req.content)
        strict = any(t.get("strict") for t in body.get("tools", []))
        calls.append(strict)
        if strict:
            return httpx.Response(400, json={"type": "error", "error": {"type": "invalid_request_error",
                                  "message": "The compiled grammar is too large. Reduce the number of strict tools."}})
        return httpx.Response(200, json={"id": "m", "type": "message", "role": "assistant", "model": body["model"],
                              "content": [{"type": "text", "text": "OK"}], "stop_reason": "end_turn", "stop_sequence": None,
                              "usage": {"input_tokens": 1, "output_tokens": 1}})

    old = runner.client
    runner.client = anthropic.AsyncAnthropic(api_key="sk-ant-test", max_retries=0,
                                             http_client=anthropic.DefaultAsyncHttpxClient(transport=httpx.MockTransport(handler)))
    os.environ["ANTHROPIC_API_KEY"] = "sk-ant-test"
    try:
        runner.NO_STRICT.discard("Victor")
        asyncio.run(runner.run_cycle(BY_NAME["Victor"], "test", lambda *a: None))
        assert calls[:2] == [True, False] and "Victor" in runner.NO_STRICT
        assert db.get_states()["Victor"]["status"] == "en attente"
    finally:
        runner.client = old


# --- sauvegarde sur clé USB ---------------------------------------------------------------------------------

def test_usb_backup_copies_work_but_never_secrets(tmp_path):
    import sauvegarde_usb as sv
    db.kb_add("test", "Sauvegarde", "contenu à retrouver dans la copie")  # la base est ouverte (Fusée « allumé »)
    (sv.WORKSPACE / "sites" / "demo").mkdir(parents=True, exist_ok=True)
    (sv.WORKSPACE / "sites" / "demo" / "index.html").write_text("<h1>Démo</h1>")
    (sv.WORKSPACE / "node_modules").mkdir(exist_ok=True)
    (sv.WORKSPACE / "node_modules" / "gros.js").write_text("x")
    (sv.DATA / "vapid_private.pem").write_text("CLE PRIVEE")
    env = tmp_path / "test.env"
    env.write_text("ANTHROPIC_API_KEY=sk-ant-SECRET\nEMAIL_PASSWORD=motdepasse\nNTFY_TOPIC=sujet-secret\n"
                   "FUSEE_PLAN=eco\nAPI_BUDGET_EUR=18\n")
    clean = sv._env_without_secrets(env)
    assert "SECRET" not in clean and "motdepasse" not in clean and "sujet-secret" not in clean
    assert "FUSEE_PLAN=eco" in clean and "API_BUDGET_EUR=18" in clean and "ANTHROPIC_API_KEY=\n" in clean

    usb = tmp_path / "CLE USB"
    usb.mkdir()
    assert sv.main(str(usb)) == 0
    [dest] = list((usb / "Fusee-sauvegardes").iterdir())
    import sqlite3
    rows = sqlite3.connect(dest / "donnees" / "fusee.db").execute("SELECT content FROM kb WHERE topic='Sauvegarde'").fetchall()
    assert rows and "retrouver" in rows[0][0]
    assert (dest / "workspace" / "sites" / "demo" / "index.html").read_text() == "<h1>Démo</h1>"
    assert not (dest / "workspace" / "node_modules").exists()
    assert not list(dest.rglob("*.pem")) and not list(dest.rglob(".env"))
    assert (dest / "code" / "fusee_agents" / "web.py").exists() and (dest / "LISEZ-MOI.txt").exists()
    assert not (dest / "code" / ".git").exists() and not (dest / "code" / "data").exists()


# --- économies : petit modèle, recherches web plafonnées, nuit des agents ---------------------------------------

def test_eco_plan_uses_the_small_model_for_everyone():
    from fusee_agents import config
    assert {m for m, _ in config.PLANS["eco"].values()} == {"claude-haiku-5-5"}


def test_web_searches_are_capped_and_counted(monkeypatch):
    from fusee_agents import runner
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    monkeypatch.setattr(budget, "today_exhausted", lambda: False)
    monkeypatch.setattr(budget, "api_exhausted", lambda: False)
    seen = []

    async def fake(**kw):
        seen.append(([t["name"] for t in kw["tools"]], kw["messages"][0]["content"]))
        return NS(usage=NS(input_tokens=10, output_tokens=5, cache_read_input_tokens=0, cache_creation_input_tokens=0,
                           server_tool_use=NS(web_search_requests=2)), stop_reason="end_turn", model=kw["model"],
                  content=[NS(type="text", text="ok")])

    monkeypatch.setattr(runner, "client", NS(beta=NS(messages=NS(create=fake))))
    scout = BY_NAME["Scout"]
    assert "web_search" in scout.tools
    before = db.searches_today()
    monkeypatch.setattr(budget, "web_search_limit", lambda: before + 100)
    asyncio.run(runner.run_cycle(scout, "test", lambda *a: None))
    assert "web_search" in seen[-1][0] and db.searches_today() == before + 2  # comptées
    assert any(r["agent"] == "Scout" and r["searches"] >= 2 and r["cycles"] >= 1 for r in db.usage_today())
    monkeypatch.setattr(budget, "web_search_limit", lambda: before + 2)  # quota atteint
    asyncio.run(runner.run_cycle(scout, "test", lambda *a: None))
    assert "web_search" not in seen[-1][0] and "quota de recherches web du jour est atteint" in seen[-1][1]
    monkeypatch.undo()
    assert 5 <= budget.web_search_limit() <= int(budget.daily_cap_usd() * 0.4 / 0.01) + 5


def test_agents_wait_for_the_owner_unless_allowed_to_work_alone(monkeypatch):
    from datetime import datetime
    from fusee_agents.scheduler import Scheduler, why_may_work
    budget.stop_work(); db.set_setting("owner_active_until", "0")
    # par défaut : ils attendent que Patron parle
    assert why_may_work("Neo", "cycle régulier") is None and why_may_work("Atlas", "démarrage") is None
    assert why_may_work("Neo", "mentionné par Atlas : on lance un site") is None  # pas de bavardage entre agents
    assert why_may_work("Neo", "cycle régulier | message de Patron : tu es là ?") == "patron"
    assert why_may_work("Wolf", "Patron a répondu à ta question #3") == "patron"
    assert why_may_work("Iris", "message chat du contact #4 sur le site demo") == "client"  # les clients, toujours
    assert why_may_work("Victor", "2 nouvelle(s) vente(s) : remercie") == "client"
    # quand Patron vient de parler, l'équipe peut s'organiser 30 min pour lui répondre
    s = Scheduler()
    s.wake("Atlas", "message de Patron : faites-moi un jeu")
    assert budget.owner_active() and why_may_work("Pixel", "mentionné par Atlas : fais le jeu") == "patron"
    assert why_may_work("Pixel", "cycle régulier") is None  # mais pas de cycles réguliers pour autant
    db.set_setting("owner_active_until", "0")
    # Patron les autorise à travailler seuls (la nuit, 2 jours…)
    label = s.authorize(time.time() + 2 * 86400)
    assert budget.work_authorized() and label and why_may_work("Neo", "cycle régulier") == "autonome"
    assert any(r.startswith("autorisation") for r in s.reasons["Neo"]) and not s.reasons["Nexus"]  # à la demande
    # ... mais ils gardent 40 % du budget du jour pour Patron
    monkeypatch.setattr(db, "cost_today", lambda: 0.7 * budget.daily_cap_usd())
    assert budget.autonomous_budget_used()
    budget.stop_work()
    assert not budget.work_authorized() and why_may_work("Neo", "cycle régulier") is None
    # « cette nuit » = jusqu'à 7 h
    assert budget.next_morning(7, datetime(2026, 11, 3, 22, 0)) == datetime(2026, 11, 4, 7, 0)
    assert budget.next_morning(7, datetime(2026, 11, 3, 2, 0)) == datetime(2026, 11, 3, 7, 0)
    now = datetime(2026, 11, 3, 22, 0)
    assert budget.when_label(datetime(2026, 11, 4, 7, 0).timestamp(), now) == "demain 7 h"
    assert budget.when_label(datetime(2026, 11, 5, 22, 30).timestamp(), now) == "jeudi 5 à 22 h30"


def test_agents_are_told_how_they_work():
    from fusee_agents import runner
    budget.stop_work()
    assert "QUAND Patron VOUS PARLE" in runner.build_context(BY_NAME["Neo"], "message de Patron : salut")
    budget.authorize_work(time.time() + 3600)
    assert "travailler SEULS jusqu'à" in runner.build_context(BY_NAME["Neo"], "cycle régulier")
    budget.stop_work()


def test_costs_page_data():
    from fastapi.testclient import TestClient
    from fusee_agents import web
    db.add_cost("Neo", 0.01)
    r = TestClient(web.app).get("/api/costs").json()
    assert r["plan"] and r["search_limit"] >= 5 and any(a["agent"] == "Neo" and a["cost_eur"] > 0 for a in r["agents"])
    c = TestClient(web.app)
    assert c.post("/api/work", json={"choice": "nuit"}).json()["authorized"] is True
    assert c.get("/api/state").json()["work"]["authorized"] is True
    assert c.post("/api/work", json={"choice": "stop"}).json()["authorized"] is False
    assert c.post("/api/work", json={"choice": "toujours"}).status_code == 400


def test_netlify_token_applies_without_restart(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from fusee_agents import integrations, setup, web
    monkeypatch.setattr(setup, "ENV", tmp_path / ".env")
    monkeypatch.setattr(setup, "EXAMPLE", tmp_path / "absent")
    monkeypatch.setattr(integrations, "NETLIFY_TOKEN", "")
    monkeypatch.delenv("NETLIFY_TOKEN", raising=False)
    r = TestClient(web.app, client=("127.0.0.1", 50000)).post("/api/setup/save", json={"NETLIFY_TOKEN": "nfp_test_1234567890"}).json()
    assert r["applied"] and integrations.NETLIFY_TOKEN == "nfp_test_1234567890"
    assert TestClient(web.app).get("/api/state").json()["capabilities"]["netlify"] is True
    monkeypatch.delenv("NETLIFY_TOKEN", raising=False)


def test_owner_can_still_talk_after_the_daily_budget(monkeypatch):
    """Budget du jour fini : le travail en solo s'arrête, mais Patron peut encore parler (rallonge limitée)."""
    from fastapi.testclient import TestClient
    from fusee_agents import runner, web
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    monkeypatch.setattr(budget, "api_exhausted", lambda: False)
    cap = budget.daily_cap_usd()
    calls = []

    async def fake(**kw):
        calls.append(kw["messages"][0]["content"])
        return NS(usage=NS(input_tokens=1, output_tokens=1, cache_read_input_tokens=0, cache_creation_input_tokens=0,
                           server_tool_use=None), stop_reason="end_turn", model=kw["model"], content=[NS(type="text", text="ok")])

    monkeypatch.setattr(runner, "client", NS(beta=NS(messages=NS(create=fake))))
    monkeypatch.setattr(db, "cost_today", lambda: 1.5 * cap)  # budget du jour dépassé, rallonge pas encore finie
    asyncio.run(runner.run_cycle(BY_NAME["Neo"], "cycle régulier", lambda *a: None))
    assert not calls and db.get_states()["Neo"]["status"] == "budget du jour atteint"
    asyncio.run(runner.run_cycle(BY_NAME["Neo"], "message de Patron : tu es là ?", lambda *a: None, for_owner=True))
    assert len(calls) == 1 and "RALLONGE" in calls[0]
    assert TestClient(web.app).post("/api/dm/Neo", json={"content": "Salut"}).status_code == 200
    monkeypatch.setattr(db, "cost_today", lambda: 2.1 * cap)  # même la rallonge est utilisée
    r = TestClient(web.app).post("/api/dm/Neo", json={"content": "Salut"})
    assert r.status_code == 400 and "rallonge" in r.json()["detail"]


def test_schedule_work_for_tomorrow_and_keep_half_for_the_owner():
    from datetime import datetime
    from fastapi.testclient import TestClient
    from fusee_agents import web
    from fusee_agents.scheduler import Scheduler, why_may_work
    now = datetime(2026, 11, 3, 20, 0)
    s, e = budget.planned_window("demain", 8, 17, now)
    assert (datetime.fromtimestamp(s), datetime.fromtimestamp(e)) == (datetime(2026, 11, 4, 8), datetime(2026, 11, 4, 17))
    s, e = budget.planned_window("aujourdhui", 22, 7, now)  # la nuit : fin le lendemain
    assert datetime.fromtimestamp(e) == datetime(2026, 11, 4, 7)
    c = TestClient(web.app)
    # « garder 50 % pour moi »
    assert c.post("/api/work", json={"reserve": 50}).json()["reserve_pct"] == 50
    assert budget.autonomous_share() == 0.5 and c.post("/api/work", json={"reserve": 95}).status_code == 400
    # programmé pour demain : pas encore autorisé, mais affiché
    w = c.post("/api/work", json={"choice": "plan", "day": "demain", "h_from": 8, "h_to": 17}).json()
    assert w["scheduled"] and not w["authorized"] and w["range_label"] == "demain 8 h → 17 h"
    assert why_may_work("Neo", "cycle régulier") is None
    # quand l'heure arrive, ils peuvent travailler, et la surveillance réveille l'équipe une seule fois
    start = budget.work_from()
    assert budget.work_authorized(start + 60) and not budget.work_authorized(budget.work_until() + 1)
    sch = Scheduler()
    budget.authorize_work(time.time() + 3600, time.time() - 1)  # la période vient de commencer
    assert budget.work_authorized() and db.get_setting("work_kicked", "") != str(budget.work_from())
    sch._kick()
    assert any(r.startswith("autorisation") for r in sch.reasons["Neo"])
    assert db.get_setting("work_kicked") == str(budget.work_from())
    budget.stop_work(); db.set_setting("owner_reserve_pct", "40")


def test_mac_uses_certifi_certificates():
    """Sur Mac : sans ça, « Tester » Netlify/Stripe échouait avec CERTIFICATE_VERIFY_FAILED."""
    import certifi
    from fusee_agents import use_certifi_on_mac
    env = {}
    assert use_certifi_on_mac("darwin", env) and env["SSL_CERT_FILE"] == certifi.where()
    env = {"SSL_CERT_FILE": "/mon/certificat.pem"}
    assert not use_certifi_on_mac("darwin", env) and env["SSL_CERT_FILE"] == "/mon/certificat.pem"  # on ne touche à rien
    assert not use_certifi_on_mac("linux", {})


def test_connected_key_closes_old_requests_and_tells_the_team(tmp_path, monkeypatch):
    """Patron a branché Stripe : les agents ne doivent plus le lui redemander."""
    from fastapi.testclient import TestClient
    from fusee_agents import integrations, runner, setup, web
    monkeypatch.setattr(setup, "ENV", tmp_path / ".env")
    monkeypatch.setattr(setup, "EXAMPLE", tmp_path / "absent")
    monkeypatch.setattr(integrations, "STRIPE_KEY", "")
    monkeypatch.delenv("STRIPE_SECRET_KEY", raising=False)
    nid = db.x("INSERT INTO needs (ts, agent, need, why, urgency, status) VALUES (?,?,?,?,?,?)",
               (time.time(), "Victor", "Ajouter la clé API Stripe dans Démarrage", "liens de paiement", "haute", "nouveau"))
    other = db.x("INSERT INTO needs (ts, agent, need, why, urgency, status) VALUES (?,?,?,?,?,?)",
                 (time.time(), "Neo", "Choisir les couleurs du site", "", "basse", "nouveau"))
    tid = db.x("INSERT INTO owner_tasks (ts, agent, title, steps, priority) VALUES (?,?,?,?,?)",
               (time.time(), "Clara", "Créer le compte Stripe avec un parent", "", "haute"))
    c = TestClient(web.app, client=("127.0.0.1", 50000))
    assert c.post("/api/setup/save", json={"STRIPE_SECRET_KEY": "sk_test_1234567890abcdef"}).json()["applied"]
    status = {r["id"]: r["status"] for r in db.q("SELECT id, status FROM needs")}
    assert status[nid] == "résolu" and status[other] == "nouveau"
    assert db.q("SELECT done FROM owner_tasks WHERE id=?", (tid,))[0]["done"] == 1
    last = db.recent_messages(1)[0]
    assert last["sender"] == "Fusée" and "Stripe" in last["content"] and "Ne lui redemandez plus" in last["content"]
    assert "Stripe déjà branché" in runner.build_context(BY_NAME["Victor"], "test")
    # au redémarrage, rien à clore : pas de nouveau message
    n = db.q("SELECT COUNT(*) n FROM messages")[0]["n"]
    assert web.close_connected_requests(web.CONNECTED, announce=False) == 0
    assert db.q("SELECT COUNT(*) n FROM messages")[0]["n"] == n
    monkeypatch.delenv("STRIPE_SECRET_KEY", raising=False)


# --- chasse au meilleur business : classement + briefing garanti --------------------------------------------

def test_ranking_board_and_guaranteed_briefing(monkeypatch):
    from fastapi.testclient import TestClient
    from fusee_agents import briefing, runner, web
    from fusee_agents.scheduler import Scheduler, why_may_work
    db.x("DELETE FROM ideas")
    run = lambda name, args: asyncio.run(tools.execute("Scout", name, args, lambda *a: None))  # noqa: E731
    r1 = run("propose_idea", {"title": "Aide numérique aux seniors", "problem": "Les seniors galèrent avec les démarches en ligne",
                              "solution": "Guides vidéo + site d'aide", "future": "Population âgée en hausse jusqu'en 2035",
                              "score": 82, "sources": ["https://www.insee.fr/exemple"], "start_cost_eur": 0,
                              "revenue_eur_month": 150, "effort": "moyen"})
    r2 = run("propose_idea", {"title": "Idée sans preuve", "problem": "?", "solution": "?", "future": "?", "score": 95,
                              "sources": [], "start_cost_eur": 0, "revenue_eur_month": 1000, "effort": "faible"})
    assert "rang n°1" in r1 and "plafonnée à 50" in r2  # pas de source = pas de grosse note
    assert "déjà dans le classement" in run("propose_idea", {"title": "aide numérique aux seniors", "problem": "", "solution": "",
                                            "future": "", "score": 10, "sources": [], "start_cost_eur": 0,
                                            "revenue_eur_month": 0, "effort": "faible"})
    ranked = briefing.ranked()
    assert [i["title"] for i in ranked] == ["Aide numérique aux seniors", "Idée sans preuve"]
    assert ranked[0]["sources"] == ["https://www.insee.fr/exemple"] and ranked[1]["score"] == 50
    run("update_idea", {"idea_id": ranked[1]["id"], "status": "", "score": 90, "reason": "sources trouvées"})
    assert briefing.ranked()[0]["title"] == "Idée sans preuve"
    # tout le monde voit le classement et la mission
    ctx = runner.build_context(BY_NAME["Neo"], "test")
    assert "Mission permanente" in ctx and "🥇" in ctx and "Aide numérique aux seniors" in ctx
    assert "| Rang |" in briefing.table_md() and "[1](https://www.insee.fr/exemple)" in briefing.table_md()
    # le briefing réveille Atlas comme si Patron parlait (donc même avec le budget du soir)
    s = Scheduler()
    reason = briefing.BRIEFING_REASON.format(day="04/11")
    assert why_may_work("Atlas", reason) == "patron" and "ask_owner" in BY_NAME["Atlas"].tools
    # Atlas n'a rien rendu : Fusée publie quand même le classement, une seule fois
    since = time.time() - 1
    assert briefing.fallback_report(since) and not briefing.fallback_report(since)
    rep = db.q("SELECT * FROM reports ORDER BY id DESC LIMIT 1")[0]
    assert "Briefing" in rep["title"] and "Aide numérique aux seniors" in rep["content"]
    # appli : classement, réglage de l'heure
    c = TestClient(web.app)
    d = c.get("/api/ideas").json()
    assert d["ranked"][0]["score"] == 90 and d["last_briefing"]["title"] == rep["title"]
    assert c.post("/api/briefing_settings", json={"hour": 18, "enabled": True}).json() == {"enabled": True, "hour": 18}
    db.set_setting("briefing_hour", "17")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    web.scheduler.reasons["Atlas"].clear()
    r = c.post("/api/briefing")
    assert r.status_code == 200 and any("BRIEFING" in x for x in web.scheduler.reasons["Atlas"])
    del s


# --- accord d'un parent : code secret ---------------------------------------------------------------------

def test_parent_code_for_approvals_and_messages(monkeypatch):
    from fastapi.testclient import TestClient
    from fusee_agents import parent, web
    from fusee_agents.scheduler import why_may_work
    for k in ("parent_pin_hash", "parent_salt", "parent_name"):
        db.set_setting(k, "")
    parent._fails.clear()
    c = TestClient(web.app)
    # une demande qui a besoin d'un parent
    out = asyncio.run(tools.execute("Victor", "request_approval", {
        "kind": "business", "title": "Ouvrir le compte Stripe au nom de Muriel", "details": "pour encaisser",
        "amount_eur": 0, "attachments": [], "links": [], "parent": True}, lambda *a: None))
    aid = db.q("SELECT id FROM approvals ORDER BY id DESC LIMIT 1")[0]["id"]
    assert "Demande" in out and db.q("SELECT needs_parent FROM approvals WHERE id=?", (aid,))[0]["needs_parent"] == 1
    r = c.post(f"/api/approvals/{aid}", json={"approve": True})
    assert r.status_code == 403 and "créer son code parent" in r.json()["detail"]
    # le parent crée son code (jamais stocké en clair)
    assert c.post("/api/parent/setup", json={"name": "Muriel", "pin": "12"}).status_code == 400
    assert c.post("/api/parent/setup", json={"name": "Muriel", "pin": "2468"}).json()["set"] is True
    assert "2468" not in db.get_setting("parent_pin_hash")
    assert c.post("/api/parent/setup", json={"name": "X", "pin": "1111", "old_pin": "0000"}).status_code == 400
    # mauvais code : refusé ; bon code : accepté au nom du parent
    assert c.post(f"/api/approvals/{aid}", json={"approve": True, "parent_pin": "9999"}).json()["detail"] == "Code parent incorrect."
    assert c.post(f"/api/approvals/{aid}", json={"approve": True, "parent_pin": "2468"}).status_code == 200
    row = db.q("SELECT status, decided_by FROM approvals WHERE id=?", (aid,))[0]
    assert row["status"] == "acceptée" and row["decided_by"] == "👪 Muriel (parent)"
    assert any("ACCORD PARENT de Muriel vérifié" in x for x in web.scheduler.reasons["Victor"])
    # une demande normale : Patron seul suffit
    asyncio.run(tools.execute("Neo", "request_approval", {"kind": "publication", "title": "Publier le site démo",
                "details": "", "amount_eur": 0, "attachments": [], "links": [], "parent": False}, lambda *a: None))
    aid2 = db.q("SELECT id FROM approvals ORDER BY id DESC LIMIT 1")[0]["id"]
    assert c.post(f"/api/approvals/{aid2}", json={"approve": True}).status_code == 200
    # le parent écrit à l'équipe avec son badge, et ça réveille Atlas comme un message de Patron
    assert c.post("/api/parent/message", json={"pin": "0000", "content": "coucou"}).status_code == 403
    r = c.post("/api/parent/message", json={"pin": "2468", "content": "J'autorise le compte Stripe à mon nom."})
    assert r.status_code == 200 and db.recent_messages(1)[0]["sender"] == "👪 Muriel (parent)"
    reason = [x for x in web.scheduler.reasons["Atlas"] if x.startswith("message du parent")][-1]
    assert why_may_work("Atlas", reason) == "patron"
    # 5 erreurs : bloqué 15 min, même avec le bon code
    parent._fails.clear()
    for _ in range(5):
        parent.check("0000")
    assert parent.locked() and not parent.check("2468")
    parent._fails.clear()


def test_vice_patron_leads_when_the_owner_is_away():
    from fusee_agents import runner
    v = BY_NAME["Vice"]
    assert v.interval_min and "resolve_need" in v.tools and "adjust_agent" in v.tools
    for forbidden in ("request_approval", "publish_site", "create_payment_link", "send_prospect_email",
                      "reply_to_contact", "start_campaign"):
        assert forbidden not in v.tools  # il ne peut ni publier, ni dépenser, ni contacter
    db.x("INSERT INTO dms (ts, agent, sender, content, read) VALUES (?,?,?,?,1)",
         (time.time(), "Vice", "Patron", "Cette nuit : tout le monde sur l'agence d'automatisation IA."))
    ctx = runner.build_context(v, "cycle régulier")
    assert "agence d'automatisation IA" in ctx  # ses consignes privées sont dans son contexte
    assert "Vice (vice-patron)" in system_prompt(BY_NAME["Neo"])  # les autres savent qui il est


# --- images et fichiers envoyés par Patron ---------------------------------------------------------------

def test_owner_can_send_images_and_files_that_agents_can_see(monkeypatch):
    import base64
    from fastapi.testclient import TestClient
    from fusee_agents import runner, web
    c = TestClient(web.app)
    png = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==")
    r = c.post("/api/upload", json={"name": "Photo écran.PNG", "data": "data:image/png;base64," + base64.b64encode(png).decode()})
    assert r.status_code == 200 and r.json()["path"].startswith("de-patron/") and r.json()["path"].endswith("Photo-ecran.png")
    path = r.json()["path"]
    assert c.post("/api/upload", json={"name": "virus.exe", "data": "AAAA"}).status_code == 400
    assert c.post("/api/upload", json={"name": "x.png", "data": "pas du base64 !!"}).status_code == 400
    # dans le groupe : la pièce jointe est gardée et l'agent sait où la regarder
    web.scheduler.reasons["Nexus"].clear()
    assert c.post("/api/message", json={"content": "", "attachments": [path, "../../etc/passwd", "sites/x.html"]}).status_code == 200
    m = db.recent_messages(1)[0]
    assert json.loads(m["attachments"])["files"] == [path]  # seulement ses fichiers à lui
    assert any("view_file" in x and path in x for x in web.scheduler.reasons["Nexus"])
    # l'agent VOIT l'image
    blocks = asyncio.run(tools.execute("Neo", "view_file", {"path": path}, lambda *a: None))
    assert isinstance(blocks, list) and blocks[1]["type"] == "image" and blocks[1]["source"]["media_type"] == "image/png"
    assert "view_file" in BY_NAME["Neo"].tools and "view_file" in BY_NAME["Vice"].tools
    # en privé : l'image est mise directement sous les yeux de l'agent
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    seen = []

    async def fake(**kw):
        seen.append(kw["messages"][-1]["content"])
        return NS(usage=NS(input_tokens=1, output_tokens=1, cache_read_input_tokens=0, cache_creation_input_tokens=0,
                           server_tool_use=None), stop_reason="end_turn", model=kw["model"], content=[NS(type="text", text="Jolie photo !")])

    monkeypatch.setattr(runner, "client", NS(beta=NS(messages=NS(create=fake))))
    assert c.post("/api/dm/Pixel", json={"content": "Regarde mon dessin", "attachments": [path]}).status_code == 200
    asyncio.run(runner.dm_reply(BY_NAME["Pixel"], lambda *a: None))
    last = seen[-1]
    assert isinstance(last, list) and any(b.get("type") == "image" for b in last) and "Regarde mon dessin" in last[0]["text"]


def test_morning_recap_tells_what_happened_overnight():
    from fastapi.testclient import TestClient
    from fusee_agents import briefing, web
    from fusee_agents.scheduler import Scheduler, why_may_work
    db.set_setting("recap_last_ts", str(time.time()))  # les autres tests ne comptent pas
    time.sleep(0.02)
    db.log("Neo", "cycle", "début du cycle (autorisation)")
    db.log("Neo", "outil", "write_file", {})
    db.log("Neo", "outil", "write_file", {})
    db.log("Neo", "outil", "screenshot", {})
    db.log("Neo", "cycle", "fin du cycle — coût 0.020 $")
    db.log("Scout", "cycle", "début du cycle (autorisation)")
    db.log("Scout", "web", "web_search: automatisation IA restaurants")
    db.log("Scout", "erreur", "erreur réseau")
    db.x("INSERT INTO owner_questions (ts, agent, question, context, options) VALUES (?,?,?,?,?)",
         (time.time(), "Victor", "Quel prix pour la formule Pro ?", "", "[]"))
    content = briefing.morning_recap(briefing.recap_since())
    assert "**Neo** : 1 cycle(s)" in content and "2 fichiers" in content and "1 captures" in content
    assert "1 recherche(s) web" in content and "Quel prix pour la formule Pro ?" in content and "erreur" in content
    assert "0.02 €" in content or "0,02" in content or "0.01 €" in content  # ~0,02 $ convertis en €
    s = Scheduler()
    who = s.morning()
    rep = db.q("SELECT * FROM reports ORDER BY id DESC LIMIT 1")[0]
    assert rep["title"].startswith("☀️ Récap du matin") and "Neo" in rep["content"]
    reason = s.reasons[who][-1]
    assert who == "Vice" and why_may_work("Vice", reason) == "patron" and "5 lignes" in reason
    # le récap suivant repart de maintenant
    assert "Personne n'a travaillé" in briefing.morning_recap(briefing.recap_since())
    c = TestClient(web.app)
    assert c.post("/api/recap_settings", json={"enabled": True, "hour": 6, "ai_word": False}).json() == \
        {"enabled": True, "hour": 6, "ai_word": False}
    assert c.post("/api/recap").json()["word_by"] == ""  # sans le mot de Vice : 0 centime
    db.set_setting("recap_hour", "7"); db.set_setting("recap_ai", "1")
