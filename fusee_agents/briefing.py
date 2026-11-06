"""Chasse permanente au meilleur business : classement des idées et briefing quotidien garanti pour Patron."""
import json
import time
from datetime import date

from . import db
from .agents import OWNER

MEDALS = ["🥇", "🥈", "🥉"]

MISSION = f"""En permanence, l'équipe cherche LE MEILLEUR business possible : un vrai problème qui existe déjà \
(des gens paient déjà pour le résoudre) ET qui va grandir dans les 5 à 10 prochaines années, avec une solution que \
l'équipe peut lancer vite et presque sans argent.
- Chaque piste va dans le CLASSEMENT avec propose_idea : problème, solution, pourquoi ça grandit sur 5-10 ans, \
note sur 100, coût de départ, revenu prudent, et des SOURCES (liens). Pas de source = pas de note au-dessus de 50.
- Avant d'ajouter, regarde le classement ci-dessous : améliore ou re-note une idée existante (update_idea) plutôt \
que de créer un doublon. Une idée plus forte qu'une autre doit avoir une meilleure note.
- Note sur 100 = avenir 5-10 ans (25) + argent possible (25) + facilité pour l'équipe (20) + rapidité du premier euro \
(15) + faible risque (15). Sois honnête : les notes servent à {OWNER} pour choisir.
- Chaque jour, Atlas présente le BRIEFING à {OWNER} : le classement, le meilleur business en détail et le choix en QCM."""

BRIEFING_REASON = (f"{OWNER} a demandé le BRIEFING : écris-le MAINTENANT avec write_report, titre « 📋 Briefing du "
                   "{day} », en markdown : 1) le TABLEAU CLASSÉ des meilleures idées (rang, problème, solution, note "
                   "/100, coût de départ, temps pour lancer, gains possibles 1 mois / 1 an / 5 ans, sources) ; 2) LE "
                   "MEILLEUR business en détail (pourquoi, ce qu'on fait en premier, qui fait quoi, ce que "
                   f"{OWNER} doit faire) ; 3) ce que chaque agent a fait depuis le dernier briefing. Puis ask_owner : "
                   "QCM « Quels business lancer ? » avec les 3 premiers. Mets d'abord à jour les notes "
                   "(update_idea) si besoin. Réponds court ailleurs : le briefing passe avant tout.")
FALLBACK_AFTER_S = 20 * 60  # si Atlas n'a rien rendu après 20 min, Fusée publie elle-même le classement


def ranked(limit: int = 50) -> list[dict]:
    rows = db.q("SELECT * FROM ideas WHERE status != 'abandonnée' "
                "ORDER BY COALESCE(score, 0) DESC, revenue_eur_month DESC, id DESC LIMIT ?", (limit,))
    for r in rows:
        try:
            r["sources"] = json.loads(r.get("sources") or "[]")
        except ValueError:
            r["sources"] = [r["sources"]] if r.get("sources") else []
    return rows


def context_lines(limit: int = 15) -> str:
    lines = []
    for k, i in enumerate(ranked(limit)):
        medal = MEDALS[k] if k < 3 else f"{k + 1}."
        lines.append(f"{medal} #{i['id']} [{i['status']}] {i['title']} — note {i.get('score') or 0}/100, "
                     f"~{i['revenue_eur_month']:.0f} €/mois, effort {i['effort']}, départ "
                     f"{(i.get('start_cost_eur') or 0):.0f} € (par {i['agent']})"
                     + (f" — problème : {i['problem'][:120]}" if i.get("problem") else ""))
    return "\n".join(lines) or "(classement vide : à vous de le remplir)"


def table_md(limit: int = 10) -> str:
    rows = ranked(limit)
    if not rows:
        return "_Le classement est encore vide._"
    out = ["| Rang | Business | Problème | Solution | Note | Départ | Revenu prudent | Sources |",
           "|---|---|---|---|---|---|---|---|"]
    for k, i in enumerate(rows):
        cell = lambda s: str(s or "—").replace("|", "/").replace("\n", " ")[:160]  # noqa: E731
        src = " ".join(f"[{n + 1}]({u})" for n, u in enumerate(i["sources"][:3]) if str(u).startswith("http")) or "—"
        out.append(f"| {MEDALS[k] if k < 3 else k + 1} | {cell(i['title'])} | {cell(i.get('problem'))} | "
                   f"{cell(i.get('solution') or i.get('description'))} | {i.get('score') or 0}/100 | "
                   f"{(i.get('start_cost_eur') or 0):.0f} € | ~{i['revenue_eur_month']:.0f} €/mois | {src} |")
    return "\n".join(out)


def fallback_report(since_ts: float) -> bool:
    """Atlas n'a pas rendu le briefing à temps : Fusée publie le classement tel quel, pour que Patron ait toujours
    quelque chose. Renvoie True si un rapport a été publié."""
    if db.q("SELECT id FROM reports WHERE ts >= ? AND title LIKE '%Briefing%'", (since_ts,)):
        return False
    from .notify import notify
    day = date.today().strftime("%d/%m")
    content = (f"Atlas n'a pas eu le temps (ou le budget) de rédiger le briefing : voici le **classement actuel** "
               f"des idées de l'équipe, du meilleur au moins bon.\n\n{table_md()}\n\n"
               "Pour choisir un business : onglet 💡 Idées, ou écris dans le groupe « @Atlas on lance le n°1 ».")
    db.x("INSERT INTO reports (ts, agent, title, content) VALUES (?,?,?,?)",
         (time.time(), "Fusée", f"📋 Briefing du {day} (classement automatique)", content))
    db.post_message("Fusée", f"📋 Briefing du {day} : le classement des idées est dans 📄 Rapports.")
    notify("rapport", f"📋 Briefing du {day}", "Le classement des meilleurs business est dans 📄 Rapports.")
    return True


def settings() -> dict:
    return {"enabled": db.get_setting("briefing_enabled", "1") == "1",
            "hour": int(db.get_setting("briefing_hour", "17"))}


# --- ☀️ récap du matin : tout ce qui s'est passé depuis le dernier récap (sans IA, donc gratuit) ---------------
TOOL_LABELS = {"propose_idea": "idées", "write_report": "rapports", "request_approval": "demandes d'accord",
               "write_file": "fichiers", "create_site_from_template": "sites", "publish_site": "mises en ligne",
               "screenshot": "captures", "post_message": "messages", "update_idea": "notes d'idées",
               "resolve_need": "besoins réglés", "ask_owner": "questions", "complete_task": "tâches finies",
               "send_prospect_email": "e-mails", "register_product": "produits"}


def recap_settings() -> dict:
    return {"enabled": db.get_setting("recap_enabled", "1") == "1", "hour": int(db.get_setting("recap_hour", "7")),
            "ai_word": db.get_setting("recap_ai", "1") == "1"}


def recap_since() -> float:
    """Depuis le dernier récap (au plus 36 h en arrière)."""
    try:
        last = float(db.get_setting("recap_last_ts", "0") or 0)
    except ValueError:
        last = 0.0
    return max(last, time.time() - 36 * 3600)


def morning_recap(since_ts: float) -> str:
    import re
    from collections import Counter, defaultdict
    acts = db.q("SELECT agent, kind, summary FROM activity WHERE ts >= ? ORDER BY id", (since_ts,))
    cycles, cost, tools, web = Counter(), defaultdict(float), defaultdict(Counter), Counter()
    errors = []
    for a in acts:
        if a["kind"] == "cycle" and a["summary"].startswith("début du cycle"):
            cycles[a["agent"]] += 1
        elif a["kind"] == "cycle":
            m = re.search(r"coût ([0-9.]+) \$", a["summary"])
            cost[a["agent"]] += float(m.group(1)) if m else 0
        elif a["kind"] == "outil":
            tools[a["agent"]][a["summary"]] += 1
        elif a["kind"] == "web":
            web[a["agent"]] += 1
        elif a["kind"] == "erreur":
            errors.append(f"{a['agent']} : {a['summary'][:120]}")
    states = db.get_states()
    lines = []
    for name in sorted(set(cycles) | set(tools), key=lambda n: -cycles[n]):
        done = ", ".join(f"{n} {TOOL_LABELS[t]}" for t, n in tools[name].most_common() if t in TOOL_LABELS)
        task = (states.get(name) or {}).get("task") or ""
        lines.append(f"- **{name}** : {cycles[name]} cycle(s)" + (f", {web[name]} recherche(s) web" if web[name] else "")
                     + (f" — {done}" if done else "") + (f" — en ce moment : « {task[:120]} »" if task else ""))
    new_ideas = db.q("SELECT title, score, agent FROM ideas WHERE ts >= ? ORDER BY COALESCE(score,0) DESC", (since_ts,))
    reports = db.q("SELECT title, agent FROM reports WHERE ts >= ? AND agent != 'Fusée' ORDER BY id", (since_ts,))
    approvals = db.q("SELECT id, title, agent, needs_parent FROM approvals WHERE status='en attente' ORDER BY id")
    questions = db.q("SELECT id, question, agent FROM owner_questions WHERE answer IS NULL ORDER BY id")
    tasks_open = db.q("SELECT COUNT(*) n FROM owner_tasks WHERE done=0")[0]["n"]
    talk = db.q("SELECT sender, content FROM messages WHERE ts >= ? AND sender NOT IN (?, 'Fusée') "
                "ORDER BY id DESC LIMIT 5", (since_ts, OWNER))[::-1]
    from .config import USD_EUR
    total = sum(cost.values()) * USD_EUR
    top = ranked(3)
    out = [f"Ce qui s'est passé depuis {time.strftime('%d/%m à %H h', time.localtime(since_ts))}.", ""]
    out += ["## 🤖 L'équipe"] + (lines or ["- Personne n'a travaillé (ils attendaient que tu leur parles)."])
    out += ["", f"💶 Dépensé par les agents : environ **{total:.2f} €**."]
    out += ["", "## 🏆 Classement"]
    out += ["- Nouvelles idées : " + ", ".join(f"{i['title']} ({i['score'] or 0}/100, {i['agent']})" for i in new_ideas[:6])
            if new_ideas else "- Pas de nouvelle idée."]
    out += ["- Top 3 : " + " · ".join(f"{MEDALS[k]} {i['title']} ({i['score'] or 0}/100)" for k, i in enumerate(top))
            if top else "- Classement encore vide."]
    if reports:
        out += ["", "## 📄 Rapports"] + [f"- {r['title']} ({r['agent']})" for r in reports[:6]]
    out += ["", "## ⏳ Ce qui t'attend"]
    out += ([f"- ✅ {len(approvals)} demande(s) d'accord : " + " ; ".join(
        f"#{a['id']} {a['title'][:60]}" + (" 👪" if a.get("needs_parent") else "") for a in approvals[:5])]
            if approvals else ["- Aucune demande d'accord."])
    out += ([f"- 📥 {len(questions)} question(s) : " + " ; ".join(f"{q['question'][:70]} ({q['agent']})" for q in questions[:4])]
            if questions else ["- Aucune question."])
    if tasks_open:
        out += [f"- 📋 {tasks_open} tâche(s) pour toi dans 📥 Demandes."]
    if talk:
        out += ["", "## 💬 Derniers messages de l'équipe"] + [f"- {m['sender']} : {m['content'][:150]}" for m in talk]
    if errors:
        out += ["", f"## ⚠️ {len(errors)} erreur(s)"] + [f"- {e}" for e in errors[-3:]]
    return "\n".join(out)


def publish_morning_recap() -> tuple[str, str]:
    """Publie le récap dans 📄 Rapports + le groupe + une notification. Renvoie (titre, contenu)."""
    from .notify import notify
    since = recap_since()
    content = morning_recap(since)
    title = f"☀️ Récap du matin du {date.today().strftime('%d/%m')}"
    db.x("INSERT INTO reports (ts, agent, title, content) VALUES (?,?,?,?)", (time.time(), "Fusée", title, content))
    db.set_setting("recap_last_ts", str(time.time()))
    db.post_message("Fusée", f"{title} : il est dans 📄 Rapports.")
    waiting = db.q("SELECT COUNT(*) n FROM approvals WHERE status='en attente'")[0]["n"]
    notify("rapport", title, f"Ce que l'équipe a fait. {waiting} demande(s) d'accord t'attendent." if waiting
           else "Ce que l'équipe a fait : regarde dans 📄 Rapports.")
    return title, content


def recap_reason(content: str) -> str:
    return (f"{OWNER} a demandé le récap du matin. Voici ce qui s'est passé :\n{content[:2500]}\n\nÉcris MAINTENANT "
            f"dans le groupe (post_message) un mot pour {OWNER}, 5 lignes maximum : le plus important, ce qui attend sa "
            "décision, et le plan de l'équipe pour aujourd'hui. Pas de recherche web, sois bref et clair.")
