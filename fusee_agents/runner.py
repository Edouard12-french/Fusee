"""Un « cycle » de travail d'un agent : boucle d'appels Claude + exécution des outils."""
import json
import time
from datetime import datetime

import anthropic

from . import db
from .agents import OWNER, Agent, system_prompt
from .config import (DAILY_BUDGET_USD, EFFORT, MAX_STEPS_PER_CYCLE, MODEL, PRICING,
                     WEB_SEARCH_COST)
from .tools import execute, tool_defs

client = anthropic.AsyncAnthropic(max_retries=4)
JOURS = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]


def _cost(usage) -> float:
    pin, pout, pread, pwrite = PRICING.get(MODEL, PRICING["claude-opus-5-5"])
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
    spent = db.cost_today()
    return f"""# Nouveau cycle — {JOURS[datetime.now().weekday()]} {datetime.now().strftime('%d/%m/%Y %H:%M')}
Raison du réveil : {reason}
Budget API du jour : {spent:.2f} $ utilisés sur {DAILY_BUDGET_USD:.2f} $ — sois efficace.

## Consigne permanente de {OWNER}
{owner_directive or "(aucune — objectif général : faire gagner de l'argent légalement)"}

## Ta mémoire
{db.get_memory(agent.name) or "(vide — premier cycle : présente-toi brièvement au groupe et établis ton plan)"}

## Tes dernières actions
{mine_txt}

## Tableau des idées
{ideas_txt}

## Derniers messages du groupe
{chat}

Travaille maintenant sur ton rôle. Agis avec les outils, puis termine en mettant à jour ta mémoire."""


async def run_cycle(agent: Agent, reason: str, wake) -> None:
    if db.cost_today() >= DAILY_BUDGET_USD:
        db.set_state(agent.name, status="budget atteint")
        return
    db.set_state(agent.name, status="travaille", last_run=time.time())
    db.log(agent.name, "cycle", f"début du cycle ({reason[:200]})")

    tools = tool_defs(agent.tools)
    system = [{"type": "text", "text": system_prompt(agent), "cache_control": {"type": "ephemeral"}}]
    messages: list = [{"role": "user", "content": build_context(agent, reason)}]
    cycle_cost = 0.0

    try:
        for _ in range(MAX_STEPS_PER_CYCLE):
            resp = await client.beta.messages.create(
                model=MODEL,
                max_tokens=16000,
                system=system,
                tools=tools,
                messages=messages,
                thinking={"type": "adaptive", "display": "summarized"},
                output_config={"effort": EFFORT},
                cache_control={"type": "ephemeral"},
                betas=["server-side-fallback-2026-07-01"],
                fallbacks="default",
            )
            c = _cost(resp.usage)
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
            if db.cost_today() >= DAILY_BUDGET_USD:
                db.log(agent.name, "budget", "budget du jour atteint, arrêt du cycle")
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
