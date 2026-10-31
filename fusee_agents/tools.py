"""Outils mis à disposition des agents (schémas + exécution)."""
import asyncio
import json
import re
import sys
from pathlib import Path

from . import db
from .agents import BY_NAME, OWNER
from .config import ALLOW_CODE_EXEC, WORKSPACE


def _schema(props: dict, required: list[str] | None = None) -> dict:
    return {"type": "object", "properties": props, "required": required or list(props),
            "additionalProperties": False}


S = {"type": "string"}
N = {"type": "number"}

CLIENT_TOOLS: dict[str, dict] = {
    "post_message": {
        "description": "Envoie un message dans le groupe de discussion de l'équipe. Mentionne @Nom pour réveiller un collègue.",
        "input_schema": _schema({"content": S}),
    },
    "save_memory": {
        "description": "Remplace ta mémoire persistante (plan, projets en cours, apprentissages). Max ~4000 caractères.",
        "input_schema": _schema({"content": S}),
    },
    "set_status": {
        "description": "Affiche sur le tableau de bord ce sur quoi tu travailles en ce moment (une phrase).",
        "input_schema": _schema({"task": S}),
    },
    "propose_idea": {
        "description": "Ajoute une idée de business au tableau commun des idées.",
        "input_schema": _schema({
            "title": S, "description": S,
            "revenue_eur_month": {"type": "number", "description": "Estimation prudente du revenu mensuel en EUR"},
            "effort": {"type": "string", "enum": ["faible", "moyen", "élevé"]},
        }),
    },
    "update_idea": {
        "description": "Change le statut d'une idée du tableau.",
        "input_schema": _schema({
            "idea_id": {"type": "integer"},
            "status": {"type": "string", "enum": ["proposée", "validée", "en cours", "prête à vendre", "abandonnée"]},
        }),
    },
    "write_report": {
        "description": f"Publie un rapport destiné à {OWNER} (markdown) : résumé, résultats, actions à faire.",
        "input_schema": _schema({"title": S, "content": S}),
    },
    "list_files": {
        "description": "Liste les fichiers du workspace partagé (chemin relatif, '' pour la racine).",
        "input_schema": _schema({"path": S}),
    },
    "read_file": {
        "description": "Lit un fichier texte du workspace partagé.",
        "input_schema": _schema({"path": S}),
    },
    "write_file": {
        "description": "Crée ou remplace un fichier texte dans le workspace partagé (crée les dossiers).",
        "input_schema": _schema({"path": S, "content": S}),
    },
    "run_python": {
        "description": "Exécute un script Python du workspace (timeout 60 s) et renvoie stdout/stderr.",
        "input_schema": _schema({"path": S, "args": {"type": "array", "items": S}}),
    },
    "paper_trade": {
        "description": "Passe un ordre SIMULÉ (aucun argent réel) dans le portefeuille fictif.",
        "input_schema": _schema({
            "symbol": S, "side": {"type": "string", "enum": ["buy", "sell"]},
            "quantity": N, "price": {"type": "number", "description": "Prix réel vérifié sur le web"},
            "rationale": {"type": "string", "description": "Thèse + source du prix"},
        }),
    },
    "mark_price": {
        "description": "Met à jour le dernier prix connu d'un actif détenu (pour calculer le P&L).",
        "input_schema": _schema({"symbol": S, "price": N}),
    },
    "portfolio": {
        "description": "Affiche le portefeuille simulé (cash, positions, P&L).",
        "input_schema": _schema({}),
    },
}

SERVER_TOOLS = {
    "web_search": {"type": "web_search_20260209", "name": "web_search", "max_uses": 8},
    "web_fetch": {"type": "web_fetch_20260209", "name": "web_fetch", "max_uses": 8, "max_content_tokens": 30000},
}


def tool_defs(names: list[str]) -> list[dict]:
    out = []
    for n in names:
        if n in SERVER_TOOLS:
            out.append(SERVER_TOOLS[n])
        elif n == "run_python" and not ALLOW_CODE_EXEC:
            continue
        else:
            out.append({"name": n, "strict": True, **CLIENT_TOOLS[n]})
    return out


def _safe_path(rel: str) -> Path:
    p = (WORKSPACE / rel.lstrip("/")).resolve()
    if p != WORKSPACE.resolve() and WORKSPACE.resolve() not in p.parents:
        raise ValueError("chemin hors du workspace interdit")
    return p


MENTION_RE = re.compile(r"@(\w+)")


def mentions(text: str) -> list[str]:
    names = set(MENTION_RE.findall(text))
    if names & {"Tous", "tous", "all", "Équipe", "equipe"}:
        return list(BY_NAME)
    return [n for n in BY_NAME if n in names]


async def execute(agent: str, name: str, args: dict, wake) -> str:
    """Exécute un outil client. `wake(nom, raison)` réveille un agent mentionné."""
    if name == "post_message":
        content = args["content"].strip()
        db.post_message(agent, content)
        for m in mentions(content):
            if m != agent:
                wake(m, f"mentionné par {agent} : {content[:300]}")
        return "Message envoyé."
    if name == "save_memory":
        db.set_memory(agent, args["content"][:6000])
        return "Mémoire enregistrée."
    if name == "set_status":
        db.set_state(agent, task=args["task"][:200])
        return "Statut mis à jour."
    if name == "propose_idea":
        i = db.x("INSERT INTO ideas (ts, agent, title, description, revenue_eur_month, effort) VALUES "
                 "(CAST(strftime('%s','now') AS REAL),?,?,?,?,?)",
                 (agent, args["title"], args["description"], args["revenue_eur_month"], args["effort"]))
        return f"Idée #{i} ajoutée au tableau."
    if name == "update_idea":
        if not db.q("SELECT id FROM ideas WHERE id=?", (args["idea_id"],)):
            return "Erreur : idée introuvable."
        db.x("UPDATE ideas SET status=? WHERE id=?", (args["status"], args["idea_id"]))
        return "Statut de l'idée mis à jour."
    if name == "write_report":
        db.x("INSERT INTO reports (ts, agent, title, content) VALUES (CAST(strftime('%s','now') AS REAL),?,?,?)",
             (agent, args["title"], args["content"]))
        db.post_message(agent, f"📄 Nouveau rapport pour @{OWNER} : « {args['title']} »")
        return "Rapport publié."
    if name == "list_files":
        base = _safe_path(args["path"])
        if not base.exists():
            return "Dossier vide ou inexistant."
        files = [str(p.relative_to(WORKSPACE)) + ("/" if p.is_dir() else f" ({p.stat().st_size} o)")
                 for p in sorted(base.rglob("*")) if "__pycache__" not in p.parts]
        return "\n".join(files[:300]) or "Dossier vide."
    if name == "read_file":
        p = _safe_path(args["path"])
        if not p.is_file():
            return "Erreur : fichier introuvable."
        text = p.read_text(errors="replace")
        return text if len(text) < 60000 else text[:60000] + "\n…[tronqué]"
    if name == "write_file":
        p = _safe_path(args["path"])
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(args["content"])
        db.log(agent, "fichier", f"a écrit {p.relative_to(WORKSPACE)} ({len(args['content'])} caractères)")
        return f"Fichier écrit : {p.relative_to(WORKSPACE)}"
    if name == "run_python":
        p = _safe_path(args["path"])
        if not p.is_file():
            return "Erreur : fichier introuvable."
        proc = await asyncio.create_subprocess_exec(
            sys.executable, str(p), *args.get("args", []), cwd=str(p.parent),
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        try:
            out, err = await asyncio.wait_for(proc.communicate(), timeout=60)
        except asyncio.TimeoutError:
            proc.kill()
            return "Erreur : délai de 60 s dépassé."
        return f"code retour {proc.returncode}\n--- stdout ---\n{out.decode()[-8000:]}\n--- stderr ---\n{err.decode()[-4000:]}"
    if name == "paper_trade":
        qty, price = float(args["quantity"]), float(args["price"])
        if qty <= 0 or price <= 0:
            return "Erreur : quantité et prix doivent être positifs."
        sym = args["symbol"].upper()
        pf = db.portfolio()
        held = next((p["qty"] for p in pf["positions"] if p["symbol"] == sym), 0)
        if args["side"] == "buy" and qty * price > pf["cash"]:
            return f"Erreur : cash insuffisant ({pf['cash']:.2f} €)."
        if args["side"] == "sell" and qty > held + 1e-9:
            return f"Erreur : tu ne détiens que {held} {sym} (pas de vente à découvert)."
        db.x("INSERT INTO trades (ts, agent, symbol, side, qty, price, rationale) VALUES (CAST(strftime('%s','now') AS REAL),?,?,?,?,?,?)",
             (agent, sym, args["side"], qty, price, args["rationale"]))
        db.x("INSERT OR REPLACE INTO marks (symbol, price, ts) VALUES (?,?,CAST(strftime('%s','now') AS REAL))", (sym, price))
        return "Ordre simulé exécuté. " + json.dumps(db.portfolio(), ensure_ascii=False)
    if name == "mark_price":
        db.x("INSERT OR REPLACE INTO marks (symbol, price, ts) VALUES (?,?,CAST(strftime('%s','now') AS REAL))",
             (args["symbol"].upper(), float(args["price"])))
        return "Prix mis à jour."
    if name == "portfolio":
        return json.dumps(db.portfolio(), ensure_ascii=False)
    return f"Erreur : outil inconnu {name}"
