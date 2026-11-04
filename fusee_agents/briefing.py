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
