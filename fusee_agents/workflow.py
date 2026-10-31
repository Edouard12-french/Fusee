"""Moteur de workflows : chaînes séquentielles (étape après étape) et tâches parallèles (tous en même temps).

Un workflow appartient à l'agent qui l'a lancé. Chaque tâche est confiée à un agent, qui la termine avec
l'outil complete_task. Quand tout est fini, le propriétaire est réveillé avec tous les résultats."""
import time

from . import db


def _activate(task: dict, wake, previous: list[dict] | None = None) -> None:
    db.x("UPDATE tasks SET status='en cours', started_ts=? WHERE id=?", (time.time(), task["id"]))
    job = db.q("SELECT * FROM jobs WHERE id=?", (task["job_id"],))[0]
    reason = f"tâche #{task['id']} du workflow {job['mode']} « {job['title']} » (lancé par {job['owner']})"
    if previous:
        reason += " — les résultats des étapes précédentes sont dans « Tes tâches en cours »"
    wake(task["agent"], reason)


def start(owner: str, mode: str, title: str, steps: list[dict], wake) -> int:
    job_id = db.x("INSERT INTO jobs (ts, owner, mode, title) VALUES (?,?,?,?)", (time.time(), owner, mode, title))
    for i, st in enumerate(steps):
        db.x("INSERT INTO tasks (job_id, idx, agent, instruction) VALUES (?,?,?,?)",
             (job_id, i, st["agent"], st["instruction"]))
    tasks = db.q("SELECT * FROM tasks WHERE job_id=? ORDER BY idx", (job_id,))
    for t in (tasks[:1] if mode == "séquence" else tasks):
        _activate(t, wake)
    icon = "⛓️" if mode == "séquence" else "🐙"
    plan = (" → " if mode == "séquence" else " + ").join(f"@{t['agent']}" for t in tasks)
    db.post_message(owner, f"{icon} Workflow #{job_id} « {title} » lancé : {plan}")
    return job_id


def complete(agent: str, task_id: int, output: str, success: bool, wake) -> str:
    rows = db.q("SELECT * FROM tasks WHERE id=?", (task_id,))
    if not rows:
        return "Erreur : tâche introuvable."
    t = rows[0]
    if t["agent"] != agent:
        return f"Erreur : cette tâche est confiée à {t['agent']}, pas à toi."
    if t["status"] != "en cours":
        return f"Erreur : cette tâche est « {t['status']} »."
    db.x("UPDATE tasks SET status=?, output=?, ended_ts=? WHERE id=?",
         ("terminée" if success else "échouée", output[:12000], time.time(), task_id))
    job = db.q("SELECT * FROM jobs WHERE id=?", (t["job_id"],))[0]
    tasks = db.q("SELECT * FROM tasks WHERE job_id=? ORDER BY idx", (job["id"],))

    if job["mode"] == "séquence":
        nxt = next((x for x in tasks if x["status"] == "en attente"), None)
        if success and nxt:
            _activate(nxt, wake, previous=[x for x in tasks if x["status"] == "terminée"])
            return f"Tâche terminée. Étape suivante confiée à {nxt['agent']}."
        if not success:
            for x in tasks:
                if x["status"] == "en attente":
                    db.x("UPDATE tasks SET status='annulée' WHERE id=?", (x["id"],))
    elif any(x["status"] in ("en attente", "en cours") for x in tasks):
        left = sum(x["status"] in ("en attente", "en cours") for x in tasks)
        return f"Tâche terminée. {left} tâche(s) parallèle(s) encore en cours."

    status = "terminé" if all(x["status"] == "terminée" for x in db.q(
        "SELECT status FROM tasks WHERE job_id=?", (job["id"],))) else "échoué"
    db.x("UPDATE jobs SET status=?, ended_ts=? WHERE id=?", (status, time.time(), job["id"]))
    db.post_message(agent, f"🏁 Workflow #{job['id']} « {job['title']} » {status}.")
    wake(job["owner"], f"ton workflow #{job['id']} « {job['title']} » est {status} : fais la synthèse "
                       f"(résultats dans « Tes tâches en cours » / list_jobs)")
    return f"Tâche terminée. Workflow {status} ; {job['owner']} va faire la synthèse."


def cancel(job_id: int, by: str) -> str:
    if not db.q("SELECT id FROM jobs WHERE id=? AND status='en cours'", (job_id,)):
        return "Erreur : workflow introuvable ou déjà fini."
    db.x("UPDATE tasks SET status='annulée' WHERE job_id=? AND status IN ('en attente','en cours')", (job_id,))
    db.x("UPDATE jobs SET status='annulé', ended_ts=? WHERE id=?", (time.time(), job_id))
    db.post_message(by, f"🛑 Workflow #{job_id} annulé.")
    return "Workflow annulé."


def describe(job: dict) -> str:
    tasks = db.q("SELECT * FROM tasks WHERE job_id=? ORDER BY idx", (job["id"],))
    lines = [f"Workflow #{job['id']} ({job['mode']}, {job['status']}, par {job['owner']}) « {job['title']} »"]
    for t in tasks:
        lines.append(f"  - tâche #{t['id']} [{t['status']}] {t['agent']} : {t['instruction'][:300]}")
        if t["output"]:
            lines.append(f"    résultat : {t['output'][:1500]}")
    return "\n".join(lines)


def agent_context(agent: str) -> str:
    """Tâches en cours confiées à cet agent (+ résultats précédents pour les séquences) et ses workflows."""
    out = []
    for t in db.q("SELECT * FROM tasks WHERE agent=? AND status='en cours' ORDER BY id", (agent,)):
        job = db.q("SELECT * FROM jobs WHERE id=?", (t["job_id"],))[0]
        out.append(f"### Tâche #{t['id']} — workflow {job['mode']} « {job['title']} » (par {job['owner']})\n"
                   f"Consigne : {t['instruction']}")
        if job["mode"] == "séquence":
            for p in db.q("SELECT * FROM tasks WHERE job_id=? AND idx<? AND status='terminée' ORDER BY idx",
                          (job["id"], t["idx"])):
                out.append(f"Résultat de l'étape {p['idx'] + 1} ({p['agent']}) : {p['output'][:2500]}")
        out.append(f"→ Quand c'est fait : complete_task(task_id={t['id']}, result=…, success=true/false).")
    for j in db.q("SELECT * FROM jobs WHERE owner=? AND (status='en cours' OR ended_ts>?) ORDER BY id DESC LIMIT 5",
                  (agent, time.time() - 86400)):
        out.append(describe(j))
    return "\n".join(out)
