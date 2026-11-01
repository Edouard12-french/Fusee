"""Un « cycle » de travail d'un agent : boucle d'appels Claude + exécution des outils."""
import asyncio
import json
import os
import time
from datetime import datetime

import anthropic

from . import budget, db, integrations, mailbox, workflow
from .agents import OWNER, Agent, system_prompt
from .config import MAX_STEPS_PER_CYCLE, OWNER_MINOR, PRICING, PUBLIC_URL, WEB_SEARCH_COST, model_for
from .tools import execute, products_overview, skills, tool_defs, toolbox

client = anthropic.AsyncAnthropic(max_retries=4)


def reload_client() -> None:
    """Applique une nouvelle clé API tout de suite, sans redémarrer Fusée."""
    global client
    client = anthropic.AsyncAnthropic(api_key=os.getenv("ANTHROPIC_API_KEY") or None, max_retries=4)
MINOR_TXT = f"""

## ⚠️ {OWNER} a moins de 18 ans
- Tout compte (Stripe, plateformes de vente, pub, hébergement payant), paiement, encaissement, contrat ou devis
  signé passe par un PARENT, titulaire du compte. Les tâches pour {OWNER} le prévoient (« avec un parent : … »).
- Pas de bourse réelle, pas de crypto, pas de régie publicitaire à son nom. Pas de démarchage téléphonique.
- Business adaptés : produits numériques, jeux, sites et outils, petits services en ligne — encaissés via le
  compte d'un parent. Contenus et communication adaptés à son âge.
- Ne collecte que le strict nécessaire sur les clients (RGPD) et ne donne jamais ses informations personnelles."""
DEFAULT_DIRECTIVE = f"""Phase 1 — choisir le premier business (aucune consigne précise de {OWNER} : l'équipe choisit).
- @Scout repère des pistes ; @Hydre lance une comparaison PARALLÈLE de 3 à 5 pistes (ex. jeux web, sites pour
  commerces et artisans locaux, outils ou templates numériques, autres trouvailles), chacune notée sur 10 pour :
  demande prouvée (sources), concurrence, prix possible, coût de départ (proche de 0 €), délai avant la première
  vente, faisabilité avec l'équipe, compatibilité avec la situation de {OWNER}.
- @Atlas choisit UNE piste avec les chiffres, demande la validation de {OWNER} (request_approval, kind=business),
  puis fait enchaîner la création par @Relais (étude → offre et prix → produit → page de vente → pub).
- Ensuite : un seul produit à la fois jusqu'à la première vente."""
JOURS = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]


def explain_api_error(e: "anthropic.APIStatusError") -> str:
    """Traduit une erreur de l'API en français, avec la solution."""
    msg = (getattr(e, "message", "") or str(e)).lower()
    code = getattr(e, "status_code", 0)
    if "credit balance" in msg or "billing" in msg or "purchase credits" in msg:
        return "erreur : crédit épuisé ou absent → achète du crédit (Billing) sur platform.claude.com"
    if "spend limit" in msg or "usage limit" in msg or "monthly" in msg and "limit" in msg:
        return "erreur : limite de dépense du mois atteinte (Limits sur platform.claude.com)"
    if code == 401 or "x-api-key" in msg or "authentication" in msg:
        return "erreur : clé API invalide → recrée une clé (API Keys) et colle-la dans 🚀 Démarrage"
    if code == 403 or "permission" in msg:
        return "erreur : ce compte n'a pas accès à ce modèle ou à cet outil"
    if code == 404 or "model" in msg and ("not found" in msg or "does not exist" in msg):
        return "erreur : modèle indisponible pour ce compte (essaie le plan « eco » dans 🚀 Démarrage)"
    if code == 429 or "rate limit" in msg:
        return "en pause : trop de demandes d'un coup, reprise automatique"
    if code >= 500 or code == 529 or "overloaded" in msg:
        return "en pause : le service est surchargé, reprise automatique"
    return f"erreur API {code} : {(getattr(e, 'message', '') or '')[:120]}"


NO_STRICT: set[str] = set()  # agents pour qui l'API a refusé le mode strict (grammaire trop grande)


def _strip_strict(tools: list[dict]) -> list[dict]:
    return [{k: v for k, v in t.items() if k != "strict"} for t in tools]


def _grammar_too_large(e: Exception) -> bool:
    m = (getattr(e, "message", "") or str(e)).lower()
    return "grammar" in m or "strict tools" in m


def _cost(usage, model: str) -> float:
    pin, pout, pread, pwrite = PRICING.get(model, PRICING["claude-opus-5-5"])
    c = (usage.input_tokens * pin + usage.output_tokens * pout
         + (usage.cache_read_input_tokens or 0) * pread
         + (usage.cache_creation_input_tokens or 0) * pwrite) / 1e6
    stu = getattr(usage, "server_tool_use", None)
    if stu and getattr(stu, "web_search_requests", None):
        c += stu.web_search_requests * WEB_SEARCH_COST
    return c


def _fmt_ts(ts: float) -> str:
    return datetime.fromtimestamp(float(ts)).strftime("%d/%m %H:%M")


def build_context(agent: Agent, reason: str) -> str:
    msgs = db.recent_messages(40)
    chat = "\n".join(f"[{_fmt_ts(m['ts'])}] {m['sender']}: {m['content']}" for m in msgs) or "(aucun message)"
    ideas = db.q("SELECT * FROM ideas WHERE status != 'abandonnée' ORDER BY id DESC LIMIT 25")
    ideas_txt = "\n".join(
        f"#{i['id']} [{i['status']}] {i['title']} — ~{i['revenue_eur_month']:.0f} €/mois, effort {i['effort']} (par {i['agent']})"
        for i in ideas) or "(tableau vide)"
    mine = db.activity(agent.name, 12)[::-1]
    mine_txt = "\n".join(f"[{_fmt_ts(a['ts'])}] {a['kind']}: {a['summary']}" for a in mine) or "(rien encore)"
    owner_directive = db.get_setting("directive", "")
    appr = db.q("SELECT * FROM approvals WHERE status='en attente' OR decided_ts > ? ORDER BY id DESC LIMIT 15",
                (time.time() - 3 * 86400,))
    appr_txt = "\n".join(
        f"#{a['id']} [{a['status']}] ({a['kind']}, par {a['agent']}) {a['title']}"
        + (f" — commentaire de {OWNER} : {a['response']}" if a["response"] else "") for a in appr) or "(aucune)"
    b = budget.summary()
    budget_txt = (f"Argent de {OWNER} : {b['remaining_eur']:.2f} € restants sur {b['initial_eur']:.0f} € de départ "
                  f"(revenus : {b['revenues_eur']:.2f} €, dépenses validées : {b['expenses_eur']:.2f} €). "
                  f"IA : {b['api_spent_eur']:.2f} € dépensés sur {b['api_budget_eur']:.0f} € prévus "
                  f"(aujourd'hui {b['api_today_eur']:.2f} / {b['api_daily_cap_eur']:.2f} €). "
                  f"Disponible pour de vraies dépenses (hors IA) : {b['free_to_spend_eur']:.2f} €.")
    my_tasks = workflow.agent_context(agent.name)
    private = dm_thread(agent.name, 8)
    private_txt = "\n".join(f"[{_fmt_ts(m['ts'])}] {m['sender']}: {m['content'][:500]}" for m in private) or "(aucune)"
    prods = products_overview()
    prods_txt = "\n".join(
        f"#{p['id']} {p['nom']} [{p['statut']}] {p['prix_eur']:.2f} € — {p['visiteurs_7j']} visiteurs/7 j, "
        f"{p['clics_achat_7j']} clics achat, {p['ventes']} ventes, {p['ca_eur']:.2f} € CA"
        + (f" — {p['en_ligne']}" if p["en_ligne"] else "") for p in prods[:15]) or "(catalogue vide)"
    memories = db.kb_search(f"{reason} {agent.title}", 4)
    mem_txt = "\n".join(f"- [{m['topic']}] ({m['agent']}) {m['content'][:400]}" for m in memories) or "(rien de lié)"
    tb = ", ".join(n for n, _ in toolbox()) or "(vide)"
    sk = ", ".join(n for n, _ in skills()) or "(aucune)"
    answers = db.q("SELECT id, agent, question, answer FROM owner_questions WHERE answered_ts > ? ORDER BY id DESC LIMIT 8",
                   (time.time() - 3 * 86400,))
    answers_txt = "\n".join(f"#{a['id']} ({a['agent']}) {a['question']} → {a['answer']}" for a in answers) or "(aucune)"
    profile = ""
    if agent.name in ("Wolf", "Atlas", "Clara"):
        prof = budget.investor_profile()
        profile = ("\n\n## Profil investisseur de " + OWNER + "\n"
                   + ("\n".join(f"- {k} : {v}" for k, v in prof.items()) if prof else
                      "(pas encore rempli — il peut le remplir dans l'onglet Argent, ou @Clara peut lui demander)"))
        if agent.name == "Wolf":
            strat = budget.strategy()
            profile += "\n\n## Stratégie actuelle\n" + (strat[:6000] if strat else "(aucune — à rédiger)")
    caps = "\n".join([
        f"- Navigateur web (browse, captures d'URL) : {'AUTORISÉ' if db.get_setting('browser_enabled', '1') == '1' else f'désactivé par {OWNER}'}",
        f"- Mise en ligne de sites (publish_site) : {'disponible' if integrations.NETLIFY_TOKEN else f'non configurée ({OWNER} doit ajouter NETLIFY_TOKEN) — prépare quand même les sites'}",
        f"- Liens de paiement (create_payment_link) : {'disponibles' if integrations.STRIPE_KEY else f'non configurés ({OWNER} doit ajouter STRIPE_SECRET_KEY)'}",
        f"- E-mail clients : {'connecté (' + mailbox.EMAIL_USER + ')' if mailbox.ENABLED else 'non configuré'}",
        (f"- Chat sur les sites : ajoute avant </body> : <script src=\"{PUBLIC_URL}/public/chat.js\" data-site=\"NOM-DU-SITE\"></script>"
         if PUBLIC_URL else "- Chat sur les sites : indisponible (pas d'adresse publique) — mets un lien e-mail de contact"
         + (f" vers {mailbox.EMAIL_USER}" if mailbox.ENABLED else "")),
    ])
    hot = db.q("SELECT id, name, email, segment, interest, sentiment, score, status FROM contacts "
               "ORDER BY score DESC, last_ts DESC LIMIT 10")
    waiting = len(db.unanswered_contacts())
    hot_txt = ("\n".join(f"#{c['id']} {c['name'] or c['email'] or 'visiteur'} — {c['segment']}, {c['status']}, "
                         f"score {c['score']}, {c['sentiment']} : {c['interest'][:120]}" for c in hot) or "(aucun)")
    hot_txt += f"\n{waiting} contact(s) attendent une réponse." if waiting else ""
    return f"""# Nouveau cycle — {JOURS[datetime.now().weekday()]} {datetime.now().strftime('%d/%m/%Y %H:%M')}
Raison du réveil : {reason}

## Budget
{budget_txt}{MINOR_TXT if OWNER_MINOR else ""}

## Consigne permanente de {OWNER}
{owner_directive or DEFAULT_DIRECTIVE}

## Catalogue produits (ventes réelles)
{prods_txt}

## Souvenirs utiles de la mémoire collective (recall pour chercher plus)
{mem_txt}

## Ta discussion privée récente avec {OWNER} (les autres ne la voient pas)
{private_txt}

## Tes tâches en cours (workflows)
{my_tasks or "(aucune)"}

## Capacités disponibles
{caps}
- Boîte à outils (run_tool) : {tb}
- Fiches de savoir-faire (read_skill) : {sk}

## Réponses récentes de {OWNER} à vos questions
{answers_txt}{profile}

## Ta mémoire
{db.get_memory(agent.name) or "(vide — premier cycle : présente-toi brièvement au groupe et établis ton plan)"}

## Tes dernières actions
{mine_txt}

## Demandes de validation à {OWNER} (en attente + décisions des 3 derniers jours)
{appr_txt}

## Prospects & clients (meilleurs scores)
{hot_txt}

## Tableau des idées
{ideas_txt}

## Derniers messages du groupe
{chat}

Travaille maintenant sur ton rôle. Agis avec les outils, puis termine en mettant à jour ta mémoire."""


async def run_cycle(agent: Agent, reason: str, wake) -> None:
    if not (os.getenv("ANTHROPIC_API_KEY") or os.getenv("ANTHROPIC_AUTH_TOKEN")):
        db.set_state(agent.name, status="en attente de la clé API (onglet 🚀 Démarrage)")
        return
    if budget.api_exhausted():
        db.set_state(agent.name, status="budget IA épuisé")
        return
    if budget.today_exhausted():
        db.set_state(agent.name, status="budget du jour atteint")
        return
    model, effort = model_for(agent.tier)
    db.set_state(agent.name, status="travaille", last_run=time.time())
    db.log(agent.name, "cycle", f"début du cycle ({reason[:200]})")

    tools = tool_defs(agent.tools, model)
    if agent.name in NO_STRICT:
        tools = _strip_strict(tools)
    extra = ({"betas": ["server-side-fallback-2026-07-01"], "fallbacks": "default"}
             if ("opus" in model or "sonnet-5-5" in model or "fable" in model) else {})
    system = [{"type": "text", "text": system_prompt(agent), "cache_control": {"type": "ephemeral"}}]
    messages: list = [{"role": "user", "content": build_context(agent, reason)}]
    cycle_cost = 0.0

    try:
        for _ in range(MAX_STEPS_PER_CYCLE):
            params = dict(model=model, max_tokens=16000, system=system, messages=messages,
                          thinking={"type": "adaptive", "display": "summarized"}, output_config={"effort": effort},
                          cache_control={"type": "ephemeral"}, **extra)
            try:
                resp = await client.beta.messages.create(tools=tools, **params)
            except anthropic.BadRequestError as e:
                if not _grammar_too_large(e) or not any(t.get("strict") for t in tools):
                    raise
                NO_STRICT.add(agent.name)  # l'API trouve les schémas stricts trop lourds : on réessaie sans
                tools = _strip_strict(tools)
                db.log(agent.name, "info", "mode strict désactivé pour cet agent (grammaire trop grande)")
                resp = await client.beta.messages.create(tools=tools, **params)
            c = _cost(resp.usage, getattr(resp, "model", None) or model)
            cycle_cost += c
            db.add_cost(agent.name, c)
            messages.append({"role": "assistant", "content": resp.content})

            tool_results = []
            for block in resp.content:
                if block.type == "thinking" and block.thinking:
                    db.log(agent.name, "réflexion", block.thinking[:200], block.thinking)
                elif block.type == "text" and block.text.strip():
                    db.log(agent.name, "texte", block.text[:200], block.text)
                elif block.type == "server_tool_use":
                    inp = block.input or {}
                    label = inp.get("query") or inp.get("url") or json.dumps(inp, ensure_ascii=False)
                    db.log(agent.name, "web", f"{block.name}: {label}")
                elif block.type == "tool_use":
                    db.log(agent.name, "outil", f"{block.name}", block.input)
                    try:
                        result = await execute(agent.name, block.name, block.input, wake)
                        tool_results.append({"type": "tool_result", "tool_use_id": block.id, "content": result})
                    except Exception as e:  # noqa: BLE001 — renvoyé au modèle
                        tool_results.append({"type": "tool_result", "tool_use_id": block.id,
                                             "content": f"Erreur : {e}", "is_error": True})

            if resp.stop_reason == "tool_use":
                messages.append({"role": "user", "content": tool_results})
            elif resp.stop_reason == "pause_turn":
                continue  # le serveur reprend la recherche web là où il s'est arrêté
            elif resp.stop_reason == "refusal":
                db.log(agent.name, "erreur", "requête refusée par le modèle",
                       str(getattr(resp, "stop_details", "")))
                break
            elif resp.stop_reason == "max_tokens":
                messages.append({"role": "user", "content": "Ta réponse a été coupée. Termine plus brièvement."})
            else:
                break
            if budget.today_exhausted() or budget.api_exhausted():
                db.log(agent.name, "budget", "budget IA atteint, arrêt du cycle")
                break
        db.set_state(agent.name, status="en attente")
    except anthropic.AuthenticationError:
        db.set_state(agent.name, status="erreur : clé API invalide")
        db.log(agent.name, "erreur", "clé API invalide ou manquante (ANTHROPIC_API_KEY)")
    except anthropic.APIStatusError as e:
        db.set_state(agent.name, status=explain_api_error(e))
        db.log(agent.name, "erreur", f"{explain_api_error(e)} — détail : API {e.status_code}: {e.message[:400]}")
    except anthropic.APIConnectionError as e:
        db.set_state(agent.name, status="erreur réseau")
        db.log(agent.name, "erreur", f"connexion : {e}")
    except Exception as e:  # noqa: BLE001 — un agent ne doit jamais faire tomber l'équipe
        db.set_state(agent.name, status="erreur")
        db.log(agent.name, "erreur", f"{type(e).__name__}: {str(e)[:300]}")
    finally:
        st = db.get_states().get(agent.name, {})
        db.set_state(agent.name, cycles=(st.get("cycles") or 0) + 1)
        db.log(agent.name, "cycle", f"fin du cycle — coût {cycle_cost:.3f} $")


# --- réunion : tous les agents répondent en même temps, en quelques secondes -----------------------------
MEETING_RULES = f"""
## Réunion d'équipe en direct
{OWNER} parle à toute l'équipe en même temps, comme dans une réunion. Réponds MAINTENANT, en ton nom, avec ta
personnalité et ton métier :
- 1 à 3 phrases, concrètes, en français, sans répéter ce que diraient les autres (reste dans ton rôle).
- Si la question ne concerne pas ton métier, une phrase suffit (ou « Rien à ajouter de mon côté 👍 »).
- Pas d'outils ici : tu réponds juste. Si une action de ta part est utile, termine par une ligne seule :
  ACTION: <ce que tu vas faire concrètement>
  et tu te mettras au travail juste après la réunion.
- Ne promets rien que tu ne peux pas faire ; rien n'est publié ni dépensé sans validation de {OWNER}."""


async def meeting_reply(agent: Agent, owner_text: str) -> tuple[str, str]:
    """Réponse courte d'un agent pendant une réunion. Renvoie (réponse, action éventuelle)."""
    model, _ = model_for(agent.tier)
    msgs = db.recent_messages(25)
    chat = "\n".join(f"{m['sender']}: {m['content'][:400]}" for m in msgs[:-1]) or "(aucun)"
    memory = db.get_memory(agent.name)[:1500] or "(vide)"
    context = (f"Ta mémoire :\n{memory}\n\nDerniers messages du groupe :\n{chat}\n\n"
               f"🎙️ {OWNER} dit à toute l'équipe : « {owner_text} »\n\nTa réponse :")
    extra = ({"betas": ["server-side-fallback-2026-07-01"], "fallbacks": "default"}
             if ("opus" in model or "sonnet-5-5" in model or "fable" in model) else {})
    resp = await client.beta.messages.create(
        model=model, max_tokens=1500,
        system=[{"type": "text", "text": system_prompt(agent) + MEETING_RULES, "cache_control": {"type": "ephemeral"}}],
        messages=[{"role": "user", "content": context}],
        output_config={"effort": "low"}, **extra)
    db.add_cost(agent.name, _cost(resp.usage, getattr(resp, "model", None) or model))
    text = "".join(b.text for b in resp.content if b.type == "text").strip()
    action = ""
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if line.strip().upper().startswith("ACTION:"):
            action = line.split(":", 1)[1].strip()
            text = "\n".join(lines[:i]).strip()
            break
    return text, action


async def run_meeting(agents: list[Agent], owner_text: str, wake, parallel: int = 14) -> None:
    """Tous les agents répondent en parallèle ; chaque réponse est postée dès qu'elle arrive."""
    sem = asyncio.Semaphore(parallel)

    async def one(agent: Agent) -> None:
        async with sem:
            db.set_state(agent.name, status="en réunion")
            try:
                text, action = await meeting_reply(agent, owner_text)
                if text or action:
                    db.post_message(agent.name, text + (f"\n➡️ Je m'en occupe : {action}" if action else ""))
                if action:
                    wake(agent.name, f"pendant la réunion, tu as annoncé : « {action} ». Fais-le maintenant "
                                     f"(message de {OWNER} : « {owner_text[:300]} »)")
            except Exception as e:  # noqa: BLE001
                db.log(agent.name, "erreur", f"réunion : {type(e).__name__}: {str(e)[:200]}")
            finally:
                db.set_state(agent.name, status="en attente")

    await asyncio.gather(*(one(a) for a in agents))
    db.log("système", "réunion", f"réunion terminée ({len(agents)} agents)")



# --- discussion privée avec un agent ------------------------------------------------------------------
DM_RULES = f"""
## Discussion privée
{OWNER} te parle EN PRIVÉ (les autres agents ne voient pas cette conversation). Réponds-lui directement, en ton nom,
de façon naturelle, utile et concrète (en général 1 à 6 phrases ; plus seulement s'il demande une explication).
Tu n'as pas d'outils dans cette discussion. Si une action de ta part est utile, termine par une ligne seule :
ACTION: <ce que tu vas faire concrètement>
et tu t'y mettras juste après (avec tes outils). Rien n'est publié ni dépensé sans validation de {OWNER}."""


def dm_thread(agent_name: str, limit: int = 30) -> list[dict]:
    return db.q("SELECT * FROM dms WHERE agent=? ORDER BY id DESC LIMIT ?", (agent_name, limit))[::-1]


async def dm_reply(agent: Agent, wake) -> None:
    """L'agent répond en privé au dernier message de Patron."""
    model, _ = model_for(agent.tier)
    history = dm_thread(agent.name, 30)
    messages: list[dict] = []
    for m in history:
        role = "user" if m["sender"] == OWNER else "assistant"
        if messages and messages[-1]["role"] == role:
            messages[-1]["content"] += "\n\n" + m["content"]
        else:
            messages.append({"role": role, "content": m["content"]})
    while messages and messages[0]["role"] != "user":
        messages.pop(0)
    if not messages or messages[-1]["role"] != "user":
        return
    memory = db.get_memory(agent.name)[:2000] or "(vide)"
    messages[0]["content"] = f"(Contexte — ta mémoire : {memory})\n\n" + messages[0]["content"]
    extra = ({"betas": ["server-side-fallback-2026-07-01"], "fallbacks": "default"}
             if ("opus" in model or "sonnet-5-5" in model or "fable" in model) else {})
    db.set_state(agent.name, status="en discussion privée")
    try:
        resp = await client.beta.messages.create(
            model=model, max_tokens=3000,
            system=[{"type": "text", "text": system_prompt(agent) + DM_RULES, "cache_control": {"type": "ephemeral"}}],
            messages=messages, output_config={"effort": "medium"}, **extra)
        db.add_cost(agent.name, _cost(resp.usage, getattr(resp, "model", None) or model))
        text = "".join(b.text for b in resp.content if b.type == "text").strip()
        action = ""
        lines = text.splitlines()
        for i, line in enumerate(lines):
            if line.strip().upper().startswith("ACTION:"):
                action, text = line.split(":", 1)[1].strip(), "\n".join(lines[:i]).strip()
                break
        db.x("INSERT INTO dms (ts, agent, sender, content, read) VALUES (?,?,?,?,1)",
             (time.time(), agent.name, agent.name, (text or "👍") + (f"\n➡️ Je m'en occupe : {action}" if action else "")))
        if action:
            wake(agent.name, f"en privé, {OWNER} t'a parlé et tu as annoncé : « {action} ». Fais-le maintenant "
                             "(la discussion privée est dans ton contexte)")
    except Exception as e:  # noqa: BLE001
        db.x("INSERT INTO dms (ts, agent, sender, content, read) VALUES (?,?,?,?,1)",
             (time.time(), agent.name, agent.name, f"(Je n'ai pas pu répondre : {type(e).__name__}. Réessaie dans un instant.)"))
    finally:
        db.set_state(agent.name, status="en attente")


# --- diagnostic : une mini-requête réelle par agent (modèle, instructions et outils exacts) -------------------
async def diagnose(agents: list[Agent]) -> list[dict]:
    async def one(agent: Agent) -> dict:
        model, _ = model_for(agent.tier)
        extra = ({"betas": ["server-side-fallback-2026-07-01"], "fallbacks": "default"}
                 if ("opus" in model or "sonnet-5-5" in model or "fable" in model) else {})
        t0 = time.time()
        try:
            params = dict(model=model, max_tokens=256,
                          system=[{"type": "text", "text": system_prompt(agent), "cache_control": {"type": "ephemeral"}}],
                          messages=[{"role": "user", "content": "Diagnostic technique : réponds seulement « OK », sans outil."}],
                          thinking={"type": "adaptive", "display": "summarized"}, output_config={"effort": "low"}, **extra)
            tools = tool_defs(agent.tools, model)
            if agent.name in NO_STRICT:
                tools = _strip_strict(tools)
            try:
                resp = await client.beta.messages.create(tools=tools, **params)
            except anthropic.BadRequestError as e:
                if not _grammar_too_large(e):
                    raise
                NO_STRICT.add(agent.name)
                resp = await client.beta.messages.create(tools=_strip_strict(tools), **params)
            cost = _cost(resp.usage, getattr(resp, "model", None) or model)
            db.add_cost(agent.name, cost)
            return {"agent": agent.name, "ok": True, "model": model, "secondes": round(time.time() - t0, 1),
                    "cout_eur": round(cost * 0.92, 4), "message": "OK"}
        except anthropic.APIStatusError as e:
            return {"agent": agent.name, "ok": False, "model": model,
                    "message": f"{explain_api_error(e)} (détail : API {e.status_code} : {e.message[:250]})"}
        except Exception as e:  # noqa: BLE001
            return {"agent": agent.name, "ok": False, "model": model, "message": f"{type(e).__name__} : {str(e)[:300]}"}

    return list(await asyncio.gather(*(one(a) for a in agents)))
