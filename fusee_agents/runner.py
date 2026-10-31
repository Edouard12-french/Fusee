"""Un « cycle » de travail d'un agent : boucle d'appels Claude + exécution des outils."""
import json
import time
from datetime import datetime

import anthropic

from . import budget, db, integrations, mailbox, workflow
from .agents import OWNER, Agent, system_prompt
from .config import MAX_STEPS_PER_CYCLE, OWNER_MINOR, PRICING, PUBLIC_URL, WEB_SEARCH_COST, model_for
from .tools import execute, skills, tool_defs, toolbox

client = anthropic.AsyncAnthropic(max_retries=4)
MINOR_TXT = f"""

## ⚠️ {OWNER} a moins de 18 ans
- Tout compte (Stripe, plateformes de vente, pub, hébergement payant), paiement, encaissement, contrat ou devis
  signé passe par un PARENT, titulaire du compte. Les tâches pour {OWNER} le prévoient (« avec un parent : … »).
- Pas de bourse réelle, pas de crypto, pas de régie publicitaire à son nom. Pas de démarchage téléphonique.
- Business adaptés : produits numériques, jeux, sites et outils, petits services en ligne — encaissés via le
  compte d'un parent. Contenus et communication adaptés à son âge.
- Ne collecte que le strict nécessaire sur les clients (RGPD) et ne donne jamais ses informations personnelles."""
JOURS = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]


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
        f"- Navigateur web (browse, captures d'URL) : {'AUTORISÉ' if db.get_setting('browser_enabled', '0') == '1' else f'non autorisé par {OWNER} pour le moment'}",
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
{owner_directive or "(aucune — objectif général : faire gagner de l'argent légalement)"}

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
    extra = ({"betas": ["server-side-fallback-2026-07-01"], "fallbacks": "default"}
             if ("opus" in model or "sonnet-5-5" in model or "fable" in model) else {})
    system = [{"type": "text", "text": system_prompt(agent), "cache_control": {"type": "ephemeral"}}]
    messages: list = [{"role": "user", "content": build_context(agent, reason)}]
    cycle_cost = 0.0

    try:
        for _ in range(MAX_STEPS_PER_CYCLE):
            resp = await client.beta.messages.create(
                model=model,
                max_tokens=16000,
                system=system,
                tools=tools,
                messages=messages,
                thinking={"type": "adaptive", "display": "summarized"},
                output_config={"effort": effort},
                cache_control={"type": "ephemeral"},
                **extra,
            )
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
        db.set_state(agent.name, status=f"erreur API {e.status_code}")
        db.log(agent.name, "erreur", f"API {e.status_code}: {e.message[:300]}")
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
