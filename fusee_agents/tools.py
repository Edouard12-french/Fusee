"""Outils mis à disposition des agents (schémas + exécution)."""
import asyncio
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

from . import analytics, browser, budget, db, integrations, mailbox, workflow
from .agents import BY_NAME, OWNER
from .config import ALLOW_CODE_EXEC, PORT, WORKSPACE
from .notify import notify


def _schema(props: dict, required: list[str] | None = None) -> dict:
    return {"type": "object", "properties": props, "required": list(props) if required is None else required,
            "additionalProperties": False}


S = {"type": "string"}
N = {"type": "number"}
I = {"type": "integer"}
LIST = {"type": "array", "items": S}
AGENT = {"type": "string", "enum": list(BY_NAME)}
STEPS = {"type": "array", "items": {"type": "object", "properties": {"agent": AGENT, "instruction": S},
                                    "required": ["agent", "instruction"], "additionalProperties": False}}

CLIENT_TOOLS: dict[str, dict] = {
    # --- équipe ---------------------------------------------------------------
    "post_message": {
        "description": ("Envoie un message dans le groupe. Mentionne @Nom pour réveiller un collègue. "
                        "attachments : chemins workspace d'images (.png/.jpg) ou vidéos (.mp4/.webm) à afficher ; "
                        "links : URLs à montrer (sites en ligne, liens de paiement…). Listes vides si rien."),
        "input_schema": _schema({"content": S, "attachments": LIST, "links": LIST}),
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
            "idea_id": I,
            "status": {"type": "string", "enum": ["proposée", "validée", "en cours", "prête à vendre", "en ligne", "abandonnée"]},
        }),
    },
    "write_report": {
        "description": f"Publie un rapport destiné à {OWNER} (markdown) : résumé, résultats, prospects, actions à faire.",
        "input_schema": _schema({"title": S, "content": S}),
    },
    "request_approval": {
        "description": (f"Demande l'accord de {OWNER} AVANT de lancer un business, une mise en ligne, un investissement, "
                        "une dépense ou toute action engageante. Il reçoit une notification et répond Accepter/Refuser ; "
                        "tu seras réveillé avec sa décision. Dossier précis : quoi, pourquoi, coût, risques, gains estimés "
                        "sourcés, étapes. attachments : captures/vidéos qui montrent le travail ; links : liens utiles."),
        "input_schema": _schema({
            "kind": {"type": "string", "enum": ["business", "investissement", "publication", "dépense", "autre"]},
            "title": S, "details": S,
            "amount_eur": {"type": "number", "description": "Argent réel engagé (0 si aucun)"},
            "attachments": LIST, "links": LIST,
        }),
    },
    "notify_owner": {
        "description": f"Envoie une notification sur le téléphone de {OWNER}. Uniquement pour une info importante ou urgente.",
        "input_schema": _schema({"title": S, "body": S}),
    },
    # --- fichiers & code ----------------------------------------------------
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
        "input_schema": _schema({"path": S, "args": LIST}),
    },
    # --- navigateur, captures, vidéos ---------------------------------------
    "screenshot": {
        "description": ("Prend une capture d'écran d'une page du workspace (ex. 'sites/mon-site' ou 'jeux/x/index.html') "
                        "ou d'une URL web, pour montrer le résultat. Renvoie le chemin de l'image (à joindre à "
                        "post_message). mobile=true pour un rendu téléphone."),
        "input_schema": _schema({"target": S, "name": S, "mobile": {"type": "boolean"}}),
    },
    "browse": {
        "description": ("Ouvre une page web dans un vrai navigateur (lecture seule) : texte, liens, capture d'écran. "
                        f"Disponible seulement si {OWNER} a autorisé la navigation."),
        "input_schema": _schema({"url": S}),
    },
    "record_video": {
        "description": ("Filme une page HTML animée du workspace (pub, démo produit, teaser de jeu) et produit une vidéo "
                        "MP4. Crée d'abord une page HTML/CSS/JS animée qui se joue toute seule (texte, couleurs, "
                        "transitions, captures du produit), puis filme-la. Format vertical = TikTok/Reels/Shorts."),
        "input_schema": _schema({"target": S, "name": S, "seconds": {"type": "number", "description": "3 à 60"},
                                 "format": {"type": "string", "enum": ["vertical", "horizontal", "carré"]}}),
    },
    # --- mise en ligne & ventes ---------------------------------------------
    "publish_site": {
        "description": ("Met en ligne (Netlify) un site/app statique du workspace (dossier avec index.html) et renvoie "
                        "son URL publique. Exige l'id d'une demande de validation ACCEPTÉE par "
                        f"{OWNER} pour ce site. Republier le même dossier met à jour le site."),
        "input_schema": _schema({"folder": S, "approval_id": I}),
    },
    "create_payment_link": {
        "description": ("Crée un lien de paiement Stripe (le client paie par carte, l'argent arrive sur le compte de "
                        f"{OWNER}). Exige l'id d'une demande de validation ACCEPTÉE mentionnant ce produit et ce prix."),
        "input_schema": _schema({"name": S, "price_eur": N, "description": S, "approval_id": I,
                                 "product_id": {"type": "integer", "description": "Produit du catalogue (0 si aucun)"}}),
    },
    "sales_summary": {
        "description": "Ventes réelles encaissées sur Stripe + liens de paiement et sites en ligne.",
        "input_schema": _schema({}),
    },
    # --- catalogue, statistiques, qualité -----------------------------------
    "register_product": {
        "description": ("Ajoute un produit au catalogue de l'équipe (à faire dès qu'un produit est en création). "
                        "site_folder : dossier du site dans le workspace (ex. 'sites/devis-eclair'), '' si aucun."),
        "input_schema": _schema({"name": S, "kind": {"type": "string", "enum": ["site", "appli", "jeu", "logiciel",
                                 "template", "service", "contenu", "autre"]},
                                 "description": S, "target": {"type": "string", "enum": ["particuliers", "entreprises", "les deux"]},
                                 "site_folder": S, "price_eur": N}),
    },
    "update_product": {
        "description": "Met à jour un produit du catalogue (statut, prix, description, dossier du site).",
        "input_schema": _schema({"product_id": I, "status": {"type": "string", "enum": ["en création", "prêt",
                                 "en ligne", "en vente", "en pause", "abandonné"]}, "price_eur": N, "description": S,
                                 "site_folder": S}),
    },
    "list_products": {
        "description": "Catalogue : chaque produit avec statut, prix, liens, visites (7 j), ventes et chiffre d'affaires.",
        "input_schema": _schema({}),
    },
    "site_stats": {
        "description": ("Statistiques d'un site (nom du dossier, ex. 'devis-eclair') : visiteurs, sources, pages, "
                        "appareils, clics « acheter », chats, ventes, taux de conversion. site='' = tous les sites."),
        "input_schema": _schema({"site": S, "days": I}),
    },
    "audit_site": {
        "description": ("Audit qualité d'un site du workspace (ex. 'sites/devis-eclair') comme un vrai visiteur, sur "
                        "ordinateur et mobile : erreurs, liens cassés, débordement mobile, SEO, contact, mentions "
                        "légales, prix, poids, vitesse. Score /100. publish_site exige un audit réussi."),
        "input_schema": _schema({"folder": S}),
    },
    # --- mémoire collective -------------------------------------------------
    "remember": {
        "description": ("Enregistre un apprentissage durable dans la mémoire collective de l'équipe (ce qui marche, "
                        "ce qui rate, chiffres, décisions, contacts utiles). Une idée par entrée, avec un sujet clair."),
        "input_schema": _schema({"topic": S, "content": S}),
    },
    "recall": {
        "description": "Cherche dans la mémoire collective de l'équipe (recherche plein texte) avant de refaire un travail.",
        "input_schema": _schema({"query": S}),
    },
    # --- prospects & clients ------------------------------------------------
    "list_contacts": {
        "description": "Liste les prospects/clients (id, nom, segment, intérêt, sentiment, score, statut, en attente de réponse).",
        "input_schema": _schema({"only_waiting": {"type": "boolean", "description": "Seulement ceux qui attendent une réponse"}}),
    },
    "read_conversation": {
        "description": "Lit toute la conversation avec un contact (e-mails et chat du site) et sa fiche.",
        "input_schema": _schema({"contact_id": I}),
    },
    "reply_to_contact": {
        "description": ("Répond à un contact, sur le canal de son dernier message (chat du site ou e-mail). Selon le "
                        f"réglage de {OWNER}, part directement (et il est notifié) ou attend sa validation."),
        "input_schema": _schema({"contact_id": I, "message": S}),
    },
    "update_contact": {
        "description": ("Met à jour la fiche d'un prospect après chaque échange : ce qui l'intéresse, son ressenti, un "
                        "score d'intérêt 0-100, et pourquoi il pourrait être intéressant pour le futur."),
        "input_schema": _schema({
            "contact_id": I, "name": S, "company": S,
            "segment": {"type": "string", "enum": ["particulier", "entreprise", "inconnu"]},
            "interest": {"type": "string", "description": "Ce qui l'intéresse, précisément"},
            "sentiment": {"type": "string", "enum": ["très positif", "positif", "neutre", "hésitant", "négatif"]},
            "score": {"type": "integer", "description": "0-100 : probabilité qu'il achète / valeur future"},
            "potential": {"type": "string", "description": "Pourquoi il est (ou non) intéressant pour le futur"},
            "status": {"type": "string", "enum": ["nouveau", "en discussion", "intéressé", "client", "perdu"]},
        }),
    },
    # --- coordination : routage, workflows ----------------------------------
    "route_to": {
        "description": "Confie une demande à un agent (il est réveillé avec ta consigne). Consigne claire et autonome.",
        "input_schema": _schema({"agent": AGENT, "instruction": S}),
    },
    "start_sequence": {
        "description": ("Lance un workflow SÉQUENTIEL : chaque étape est confiée à un agent, qui reçoit les résultats "
                        "des étapes précédentes. Tu es réveillé à la fin pour la synthèse."),
        "input_schema": _schema({"title": S, "steps": STEPS}),
    },
    "start_parallel": {
        "description": ("Lance un workflow PARALLÈLE : toutes les tâches partent en même temps vers leurs agents. "
                        "Tu es réveillé quand tout est revenu, pour fusionner les résultats."),
        "input_schema": _schema({"title": S, "tasks": STEPS}),
    },
    "complete_task": {
        "description": "Termine une tâche de workflow qui t'est confiée, avec un résultat complet et autonome.",
        "input_schema": _schema({"task_id": I, "result": S, "success": {"type": "boolean"}}),
    },
    "list_jobs": {
        "description": "Liste les workflows (séquentiels et parallèles) avec l'état et le résultat de chaque tâche.",
        "input_schema": _schema({"only_active": {"type": "boolean"}}),
    },
    "cancel_job": {
        "description": "Annule un workflow en cours.",
        "input_schema": _schema({"job_id": I}),
    },
    # --- boîte à outils & compétences ---------------------------------------
    "list_toolbox": {
        "description": "Liste les outils de la boîte à outils de l'équipe (workspace/outils/), avec leur description.",
        "input_schema": _schema({}),
    },
    "run_tool": {
        "description": "Lance un outil de la boîte à outils (nom sans .py) avec ses arguments ; renvoie sa sortie.",
        "input_schema": _schema({"name": S, "args": LIST}),
    },
    "list_skills": {
        "description": "Liste les fiches de savoir-faire de l'équipe (workspace/competences/).",
        "input_schema": _schema({}),
    },
    "read_skill": {
        "description": "Lit une fiche de savoir-faire (nom sans .md).",
        "input_schema": _schema({"name": S}),
    },
    # --- lien avec Patron (agent humain) ------------------------------------
    "ask_owner": {
        "description": (f"Pose une question à {OWNER} (notification + réponse dans l'appli). options : réponses "
                        "proposées en boutons (liste vide = réponse libre)."),
        "input_schema": _schema({"question": S, "context": S, "options": LIST}),
    },
    "add_owner_task": {
        "description": f"Ajoute une tâche à la liste « À faire » de {OWNER}, avec des étapes numérotées très concrètes.",
        "input_schema": _schema({"title": S, "steps": S,
                                 "priority": {"type": "string", "enum": ["haute", "normale", "basse"]}}),
    },
    "list_owner_items": {
        "description": f"Questions et tâches en attente chez {OWNER} (et réponses récentes).",
        "input_schema": _schema({}),
    },
    # --- budget & stratégie -------------------------------------------------
    "budget_status": {
        "description": f"Budget réel de {OWNER} : départ, dépenses IA, autres dépenses, revenus, reste disponible.",
        "input_schema": _schema({}),
    },
    "write_strategy": {
        "description": f"Enregistre la stratégie d'investissement personnalisée de {OWNER} (markdown, remplace l'ancienne).",
        "input_schema": _schema({"content": S}),
    },
    # --- trading simulé -----------------------------------------------------
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
# Les versions « 20260209 » (filtrage dynamique) existent sur Opus/Sonnet récents ; les autres modèles ont les basiques.
BASIC_SERVER_TOOLS = {
    "web_search": {"type": "web_search_20250305", "name": "web_search", "max_uses": 5},
    "web_fetch": {"type": "web_fetch_20250910", "name": "web_fetch", "max_uses": 5, "max_content_tokens": 20000},
}


def tool_defs(names: list[str], model: str = "") -> list[dict]:
    server = SERVER_TOOLS if ("opus" in model or "sonnet" in model or not model) else BASIC_SERVER_TOOLS
    out = []
    for n in names:
        if n in SERVER_TOOLS:
            out.append(server[n])
        elif n in ("run_python", "run_tool") and not ALLOW_CODE_EXEC:
            continue
        else:
            out.append({"name": n, "strict": True, **CLIENT_TOOLS[n]})
    return out


SECRET_HINTS = ("KEY", "TOKEN", "SECRET", "PASSWORD", "PASS", "AUTH", "CREDENTIAL", "NTFY", "EMAIL", "SMTP", "IMAP")


def _safe_env() -> dict:
    """Environnement du code écrit par les agents : sans aucune clé ni mot de passe de Patron."""
    return {k: v for k, v in os.environ.items() if not any(h in k.upper() for h in SECRET_HINTS)}


def _safe_path(rel: str) -> Path:
    p = (WORKSPACE / rel.lstrip("/")).resolve()
    if p != WORKSPACE.resolve() and WORKSPACE.resolve() not in p.parents:
        raise ValueError("chemin hors du workspace interdit")
    return p


def _clean_attachments(paths: list[str]) -> list[str]:
    out = []
    for a in paths[:8]:
        try:
            p = _safe_path(a)
        except ValueError:
            continue
        if p.is_file():
            out.append(str(p.relative_to(WORKSPACE)))
    return out


def _attach_json(attachments: list[str], links: list[str]) -> str:
    links = [l for l in links[:8] if re.match(r"^https?://", l)]
    return json.dumps({"files": _clean_attachments(attachments), "links": links}, ensure_ascii=False)


def _describe(p: Path) -> str:
    for line in p.read_text(errors="replace").splitlines():
        line = line.strip().strip('#"\' ').strip()
        if line and not line.startswith(("!", "-*-", "coding")):
            return line[:160]
    return ""


def toolbox() -> list[tuple[str, str]]:
    d = WORKSPACE / "outils"
    return [(p.stem, _describe(p)) for p in sorted(d.glob("*.py"))] if d.exists() else []


def skills() -> list[tuple[str, str]]:
    d = WORKSPACE / "competences"
    return [(p.stem, _describe(p)) for p in sorted(d.glob("*.md"))] if d.exists() else []


MENTION_RE = re.compile(r"(?:^|\s)@(\w+)")


def mentions(text: str) -> list[str]:
    names = set(MENTION_RE.findall(text))
    if names & {"Tous", "tous", "all", "Équipe", "equipe"}:
        return list(BY_NAME)
    return [n for n in BY_NAME if n in names]


async def run_audit(folder: str) -> dict:
    """Audit d'un site via le serveur local (comme en ligne), ou en fichier si le serveur ne répond pas."""
    folder = folder.strip().strip("/")
    kind = "jeu" if folder.startswith("jeux/") else "site"
    if await asyncio.to_thread(_server_up):
        return await browser.audit(folder, f"http://127.0.0.1:{PORT}", os.getenv("DASHBOARD_PASSWORD", ""), kind)
    return await browser.audit(folder, "", "", kind)


def _server_up() -> bool:
    try:
        urllib.request.urlopen(f"http://127.0.0.1:{PORT}/manifest.webmanifest", timeout=2)
        return True
    except urllib.error.HTTPError:
        return True  # répond (ex. 401 avec mot de passe)
    except Exception:  # noqa: BLE001
        return False


def products_overview() -> list[dict]:
    out = []
    for p in db.q("SELECT * FROM products WHERE status!='abandonné' ORDER BY id DESC LIMIT 40"):
        site = Path(p["site_folder"]).name if p["site_folder"] else ""
        st = analytics.site_stats(site, 7) if site else {}
        sales = db.q("SELECT COUNT(*) n, COALESCE(SUM(amount_eur), 0) t FROM sales WHERE product_id=?", (p["id"],))[0]
        dep = db.q("SELECT url FROM deployments WHERE site=? ORDER BY id DESC LIMIT 1", (p["site_folder"],))
        links = db.q("SELECT url, price_eur FROM payment_links WHERE product_id=?", (p["id"],))
        out.append({"id": p["id"], "nom": p["name"], "type": p["kind"], "cible": p["target"], "statut": p["status"],
                    "prix_eur": p["price_eur"], "site": p["site_folder"], "en_ligne": dep[0]["url"] if dep else "",
                    "liens_paiement": [x["url"] for x in links], "visiteurs_7j": st.get("visiteurs", 0),
                    "clics_achat_7j": st.get("clics_achat", 0), "ventes": sales["n"], "ca_eur": round(sales["t"], 2),
                    "par": p["agent"]})
    return out


def _accepted(approval_id: int, kinds: tuple[str, ...]) -> dict | None:
    rows = db.q("SELECT * FROM approvals WHERE id=? AND status='acceptée'", (approval_id,))
    return rows[0] if rows and rows[0]["kind"] in kinds else None


async def deliver_reply(contact_id: int, message: str, agent: str) -> str:
    """Envoie réellement une réponse à un contact sur son dernier canal. Renvoie le canal utilisé."""
    last_in = db.q("SELECT channel FROM conv WHERE contact_id=? AND direction='in' ORDER BY id DESC LIMIT 1",
                   (contact_id,))
    channel = last_in[0]["channel"] if last_in else "email"
    if channel == "email":
        if not mailbox.ENABLED:
            raise RuntimeError("la boîte mail n'est pas configurée (.env)")
        await asyncio.to_thread(mailbox.send, contact_id, message, agent)
    else:
        db.add_conv(contact_id, "chat", "out", message, agent=agent)
    return channel


async def execute(agent: str, name: str, args: dict, wake) -> str:
    """Exécute un outil client. `wake(nom, raison)` réveille un agent mentionné."""
    # --- équipe -------------------------------------------------------------
    if name == "post_message":
        content = args["content"].strip()
        db.post_message(agent, content, _attach_json(args["attachments"], args["links"]))
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
        notify("rapport", f"Nouveau rapport : {args['title']}", args["content"][:1500])
        return "Rapport publié."
    if name == "request_approval":
        pending = db.q("SELECT id FROM approvals WHERE status='en attente' AND title=?", (args["title"],))
        if pending:
            return f"Une demande identique (#{pending[0]['id']}) attend déjà la réponse de {OWNER}."
        if args["amount_eur"] > 0:
            free = budget.summary()["free_to_spend_eur"]
            if args["amount_eur"] > free:
                return (f"Refusé : {args['amount_eur']:.2f} € dépasse l'argent disponible hors IA ({free:.2f} €). "
                        "Trouve une option moins chère ou gratuite.")
        att = _attach_json(args["attachments"], args["links"])
        i = db.x("INSERT INTO approvals (ts, agent, kind, title, details, amount_eur, payload) "
                 "VALUES (CAST(strftime('%s','now') AS REAL),?,?,?,?,?,?)",
                 (agent, args["kind"], args["title"], args["details"], args["amount_eur"], att))
        money = f" — {args['amount_eur']:.0f} € engagés" if args["amount_eur"] else ""
        db.post_message(agent, f"🙋 Demande de validation #{i} pour @{OWNER} ({args['kind']}) : {args['title']}{money}", att)
        notify("validation", f"{agent} demande ton accord : {args['title']}",
               f"{args['kind']}{money}\n\n{args['details'][:1500]}", priority="high")
        return f"Demande #{i} envoyée à {OWNER}. N'agis pas avant sa réponse ; continue sur autre chose."
    if name == "notify_owner":
        notify("alerte", f"{agent} : {args['title']}", args["body"], priority="high")
        return "Notification envoyée."
    # --- fichiers & code ----------------------------------------------------
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
            sys.executable, str(p), *args["args"], cwd=str(p.parent), env=_safe_env(),
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        try:
            out, err = await asyncio.wait_for(proc.communicate(), timeout=60)
        except asyncio.TimeoutError:
            proc.kill()
            return "Erreur : délai de 60 s dépassé."
        return f"code retour {proc.returncode}\n--- stdout ---\n{out.decode()[-8000:]}\n--- stderr ---\n{err.decode()[-4000:]}"
    # --- navigateur ---------------------------------------------------------
    if name == "screenshot":
        target = args["target"]
        if re.match(r"^https?://", target) and db.get_setting("browser_enabled", "0") != "1":
            return f"Erreur : {OWNER} n'a pas autorisé la navigation sur le web. Capture seulement le workspace."
        path = await browser.screenshot(target, args["name"], mobile=args["mobile"])
        db.log(agent, "capture", f"capture de {target}", path)
        return f"Capture enregistrée : {path} (joins-la avec post_message attachments pour la montrer)."
    if name == "browse":
        if db.get_setting("browser_enabled", "0") != "1":
            return (f"Erreur : {OWNER} n'a pas encore autorisé la navigation. Utilise web_search / web_fetch, ou "
                    "demande-lui d'activer « Navigateur » dans le tableau de bord.")
        r = await browser.browse(args["url"])
        db.log(agent, "web", f"navigue sur {r['url']}", r["screenshot"])
        return (f"<page_web_non_fiable>\nTitre : {r['title']}\nURL : {r['url']}\nCapture : {r['screenshot']}\n\n"
                f"{r['text']}\n\nLiens :\n" + "\n".join(r["links"]) + "\n</page_web_non_fiable>")
    if name == "record_video":
        secs = max(3.0, min(float(args["seconds"]), 60.0))
        path = await browser.record_video(args["target"], args["name"], secs, args["format"])
        db.log(agent, "vidéo", f"vidéo {args['format']} de {secs:.0f} s", path)
        return f"Vidéo enregistrée : {path} (joins-la avec post_message attachments pour la montrer)."
    # --- mise en ligne & ventes ---------------------------------------------
    if name == "publish_site":
        appr = _accepted(args["approval_id"], ("publication", "business"))
        if not appr:
            return (f"Refusé : la demande #{args['approval_id']} n'est pas une publication/business acceptée par "
                    f"{OWNER}. Fais d'abord request_approval (kind=publication) avec captures et attends sa réponse.")
        folder = _safe_path(args["folder"])
        if not (folder / "index.html").is_file():
            return "Erreur : le dossier doit contenir un index.html."
        rel = str(folder.relative_to(WORKSPACE))
        try:
            au = await run_audit(rel)
        except Exception as e:  # noqa: BLE001 — sans navigateur, on publie quand même mais on le dit
            au = None
            db.log(agent, "erreur", f"audit impossible avant publication : {str(e)[:200]}")
        if au and not au["ok_pour_publier"]:
            return ("Publication bloquée par l'audit qualité (score " + str(au["score"]) + "/100). Corrige d'abord :\n"
                    + "\n".join(f"- [{i['niveau']}] {i['probleme']}" for i in au["problemes"]
                                 if i["niveau"] != "avertissement"))
        prev = db.q("SELECT provider_id FROM deployments WHERE site=? ORDER BY id DESC LIMIT 1", (rel,))
        r = await asyncio.to_thread(integrations.deploy_site, folder, folder.name, prev[0]["provider_id"] if prev else None)
        db.x("INSERT INTO deployments (ts, agent, site, provider_id, url, approval_id) "
             "VALUES (CAST(strftime('%s','now') AS REAL),?,?,?,?,?)", (agent, rel, r["site_id"], r["url"], appr["id"]))
        notify("alerte", f"🌐 Site en ligne : {folder.name}", f"{r['url']}\n(validé par toi, demande #{appr['id']})")
        db.x("UPDATE products SET status='en ligne' WHERE site_folder=? AND status IN ('en création','prêt')", (rel,))
        db.post_message(agent, f"🌐 {folder.name} est en ligne !" + (f" (audit {au['score']}/100)" if au else ""),
                        _attach_json(list((au or {}).get("captures", {}).values()), [r["url"]]))
        return f"Site en ligne : {r['url']}"
    if name == "create_payment_link":
        appr = _accepted(args["approval_id"], ("business", "publication"))
        if not appr:
            return (f"Refusé : la demande #{args['approval_id']} n'est pas acceptée. Demande d'abord l'accord de "
                    f"{OWNER} (produit, prix, plateforme) avec request_approval.")
        if args["price_eur"] <= 0:
            return "Erreur : prix invalide."
        r = await asyncio.to_thread(integrations.create_payment_link, args["name"], args["price_eur"], args["description"])
        pid = args["product_id"] if db.q("SELECT id FROM products WHERE id=?", (args["product_id"],)) else None
        db.x("INSERT INTO payment_links (ts, agent, name, price_eur, url, stripe_id, approval_id, product_id) "
             "VALUES (CAST(strftime('%s','now') AS REAL),?,?,?,?,?,?,?)",
             (agent, args["name"], args["price_eur"], r["url"], r["id"], appr["id"], pid))
        if pid:
            db.x("UPDATE products SET price_eur=? WHERE id=?", (args["price_eur"], pid))
        notify("alerte", f"💳 Lien de paiement créé : {args['name']} ({args['price_eur']} €)", r["url"])
        return f"Lien de paiement : {r['url']} (à mettre sur le site / la page de vente)."
    if name == "sales_summary":
        out = {"liens_de_paiement": db.q("SELECT name, price_eur, url FROM payment_links"),
               "sites_en_ligne": db.q("SELECT site, url, max(ts) ts FROM deployments GROUP BY site")}
        if integrations.STRIPE_KEY:
            out["ventes_stripe"] = await asyncio.to_thread(integrations.sales_summary)
        return json.dumps(out, ensure_ascii=False)
    # --- catalogue, statistiques, qualité -----------------------------------
    if name == "register_product":
        if db.q("SELECT id FROM products WHERE lower(name)=lower(?) AND status!='abandonné'", (args["name"],)):
            return "Un produit de ce nom existe déjà : utilise update_product."
        folder = args["site_folder"].strip().strip("/")
        if folder:
            _safe_path(folder)
        i = db.x("INSERT INTO products (ts, agent, name, kind, description, target, site_folder, price_eur) "
                 "VALUES (?,?,?,?,?,?,?,?)", (time.time(), agent, args["name"], args["kind"], args["description"],
                                              args["target"], folder, args["price_eur"]))
        db.post_message(agent, f"📦 Nouveau produit au catalogue : #{i} {args['name']} ({args['kind']}, "
                               f"{args['price_eur']:.2f} €, pour {args['target']})")
        return f"Produit #{i} ajouté au catalogue."
    if name == "update_product":
        if not db.q("SELECT id FROM products WHERE id=?", (args["product_id"],)):
            return "Erreur : produit introuvable."
        db.x("UPDATE products SET status=?, price_eur=?, description=COALESCE(NULLIF(?, ''), description), "
             "site_folder=COALESCE(NULLIF(?, ''), site_folder) WHERE id=?",
             (args["status"], args["price_eur"], args["description"], args["site_folder"].strip().strip("/"),
              args["product_id"]))
        return "Produit mis à jour."
    if name == "list_products":
        return json.dumps(products_overview(), ensure_ascii=False) or "Catalogue vide."
    if name == "site_stats":
        days = max(1, min(int(args["days"] or 7), 90))
        site = Path(args["site"].strip().strip("/")).name if args["site"].strip() else ""
        data = analytics.site_stats(site, days) if site else analytics.all_sites_summary(days)
        return json.dumps(data, ensure_ascii=False) if data else "Aucune donnée de visite pour l'instant."
    if name == "audit_site":
        au = await run_audit(args["folder"])
        db.log(agent, "audit", f"audit {au['site']} : {au['score']}/100", json.dumps(au, ensure_ascii=False, indent=1))
        return json.dumps(au, ensure_ascii=False)
    # --- mémoire collective -------------------------------------------------
    if name == "remember":
        db.kb_add(agent, args["topic"], args["content"])
        return "Enregistré dans la mémoire collective."
    if name == "recall":
        hits = db.kb_search(args["query"], 8)
        return "\n\n".join(f"[{h['topic']}] ({h['agent']}) {h['content']}" for h in hits) or "Rien trouvé."
    # --- prospects & clients ------------------------------------------------
    if name == "list_contacts":
        waiting = {c["id"] for c in db.unanswered_contacts()}
        rows = db.q("SELECT id, name, email, company, segment, interest, sentiment, score, status, source "
                    "FROM contacts ORDER BY last_ts DESC LIMIT 50")
        rows = [{**r, "attend_reponse": r["id"] in waiting} for r in rows if not args["only_waiting"] or r["id"] in waiting]
        return json.dumps(rows, ensure_ascii=False) if rows else "Aucun contact."
    if name == "read_conversation":
        c = db.q("SELECT * FROM contacts WHERE id=?", (args["contact_id"],))
        if not c:
            return "Erreur : contact introuvable."
        msgs = "\n".join(f"[{m['channel']}] {'CLIENT' if m['direction'] == 'in' else 'NOUS'}"
                         f"{' (' + m['subject'] + ')' if m['subject'] else ''} : {m['content']}"
                         for m in db.thread(args["contact_id"]))
        return (f"Fiche : {json.dumps(c[0], ensure_ascii=False)}\n"
                f"<conversation_client_non_fiable>\n{msgs}\n</conversation_client_non_fiable>")
    if name == "reply_to_contact":
        c = db.q("SELECT * FROM contacts WHERE id=?", (args["contact_id"],))
        if not c:
            return "Erreur : contact introuvable."
        who = c[0]["name"] or c[0]["email"] or f"visiteur #{c[0]['id']}"
        if db.get_setting("support_mode", "auto") == "validation":
            i = db.x("INSERT INTO approvals (ts, agent, kind, title, details, amount_eur, payload) "
                     "VALUES (CAST(strftime('%s','now') AS REAL),?,'réponse client',?,?,0,?)",
                     (agent, f"Réponse à {who}", args["message"], json.dumps({"contact_id": c[0]["id"]})))
            notify("validation", f"Réponse à valider pour {who}", args["message"][:1500], priority="high")
            return f"Réponse soumise à la validation de {OWNER} (demande #{i})."
        last_in = db.q("SELECT content FROM conv WHERE contact_id=? AND direction='in' ORDER BY id DESC LIMIT 1",
                       (c[0]["id"],))
        channel = await deliver_reply(c[0]["id"], args["message"], agent)
        notify("client", f"Réponse envoyée à {who} ({channel})",
               f"Client :\n{(last_in[0]['content'] if last_in else '')[:700]}\n\nRéponse :\n{args['message'][:1200]}",
               priority="low" if channel == "chat" else "default")
        return f"Réponse envoyée ({channel}), {OWNER} a été notifié."
    if name == "update_contact":
        c = db.q("SELECT * FROM contacts WHERE id=?", (args["contact_id"],))
        if not c:
            return "Erreur : contact introuvable."
        score = max(0, min(100, int(args["score"])))
        db.x("UPDATE contacts SET name=COALESCE(NULLIF(?, ''), name), company=COALESCE(NULLIF(?, ''), company), "
             "segment=?, interest=?, sentiment=?, score=?, potential=?, status=? WHERE id=?",
             (args["name"], args["company"], args["segment"], args["interest"], args["sentiment"], score,
              args["potential"], args["status"], args["contact_id"]))
        if score >= 70 > (c[0]["score"] or 0):
            who = args["name"] or c[0]["email"] or f"visiteur #{c[0]['id']}"
            notify("client", f"🔥 Prospect chaud : {who} ({score}/100)",
                   f"Intéressé par : {args['interest']}\nRessenti : {args['sentiment']}\n{args['potential']}", priority="high")
        return "Fiche mise à jour."
    # --- coordination -------------------------------------------------------
    if name == "route_to":
        if args["agent"] == agent:
            return "Erreur : tu ne peux pas te router une demande à toi-même."
        db.post_message(agent, f"➡️ @{args['agent']} : {args['instruction']}")
        wake(args["agent"], f"demande routée par {agent} : {args['instruction'][:1500]}")
        return f"Demande confiée à {args['agent']}."
    if name in ("start_sequence", "start_parallel"):
        steps = args["steps"] if name == "start_sequence" else args["tasks"]
        if not 1 <= len(steps) <= 8:
            return "Erreur : entre 1 et 8 étapes."
        job_id = workflow.start(agent, "séquence" if name == "start_sequence" else "parallèle",
                                args["title"], steps, wake)
        return f"Workflow #{job_id} lancé. Tu seras réveillé à la fin pour la synthèse."
    if name == "complete_task":
        return workflow.complete(agent, args["task_id"], args["result"], args["success"], wake)
    if name == "list_jobs":
        where = "WHERE status='en cours'" if args["only_active"] else ""
        jobs = db.q(f"SELECT * FROM jobs {where} ORDER BY id DESC LIMIT 10")
        return "\n\n".join(workflow.describe(j) for j in jobs) or "Aucun workflow."
    if name == "cancel_job":
        return workflow.cancel(args["job_id"], agent)
    # --- boîte à outils & compétences ---------------------------------------
    if name == "list_toolbox":
        return "\n".join(f"- {n} : {d}" for n, d in toolbox()) or "Boîte à outils vide (demande à @Forge)."
    if name == "run_tool":
        p = (WORKSPACE / "outils" / f"{Path(args['name']).stem}.py")
        if not p.is_file():
            return "Erreur : outil inconnu. Vois list_toolbox."
        return await execute(agent, "run_python", {"path": f"outils/{p.name}", "args": args["args"]}, wake)
    if name == "list_skills":
        return "\n".join(f"- {n} : {d}" for n, d in skills()) or "Aucune fiche pour l'instant (demande à @Sage)."
    if name == "read_skill":
        p = WORKSPACE / "competences" / f"{Path(args['name']).stem}.md"
        return p.read_text(errors="replace")[:30000] if p.is_file() else "Erreur : fiche inconnue. Vois list_skills."
    # --- lien avec Patron ---------------------------------------------------
    if name == "ask_owner":
        dup = db.q("SELECT id FROM owner_questions WHERE answer IS NULL AND question=?", (args["question"],))
        if dup:
            return f"Cette question (#{dup[0]['id']}) attend déjà la réponse de {OWNER}."
        i = db.x("INSERT INTO owner_questions (ts, agent, question, context, options) VALUES (?,?,?,?,?)",
                 (time.time(), agent, args["question"], args["context"], json.dumps(args["options"][:6], ensure_ascii=False)))
        db.post_message(agent, f"❓ Question #{i} pour @{OWNER} : {args['question']}")
        notify("validation", f"Question de {agent}", args["question"], priority="default")
        return f"Question #{i} posée. Tu seras réveillé avec la réponse."
    if name == "add_owner_task":
        i = db.x("INSERT INTO owner_tasks (ts, agent, title, steps, priority) VALUES (?,?,?,?,?)",
                 (time.time(), agent, args["title"], args["steps"], args["priority"]))
        db.post_message(agent, f"📝 Nouvelle tâche pour @{OWNER} : {args['title']}")
        if args["priority"] == "haute":
            notify("alerte", f"À faire : {args['title']}", args["steps"][:1500], priority="high")
        return f"Tâche #{i} ajoutée à la liste de {OWNER}."
    if name == "list_owner_items":
        qs = db.q("SELECT id, agent, question, answer FROM owner_questions WHERE answer IS NULL OR answered_ts > ? "
                  "ORDER BY id DESC LIMIT 20", (time.time() - 3 * 86400,))
        ts = db.q("SELECT id, agent, title, priority, done, ts FROM owner_tasks WHERE done=0 OR done_ts > ? "
                  "ORDER BY id DESC LIMIT 20", (time.time() - 3 * 86400,))
        return json.dumps({"questions": qs, "taches": ts}, ensure_ascii=False)
    # --- budget & stratégie -------------------------------------------------
    if name == "budget_status":
        s = budget.summary()
        return json.dumps({k: round(v, 2) if isinstance(v, float) else v for k, v in s.items()}, ensure_ascii=False)
    if name == "write_strategy":
        db.set_setting("strategy", args["content"][:30000])
        db.set_setting("strategy_ts", str(time.time()))
        db.post_message(agent, f"📈 Stratégie d'investissement de @{OWNER} mise à jour (onglet Argent).")
        notify("rapport", "Ta stratégie d'investissement est à jour", args["content"][:800])
        return "Stratégie enregistrée."
    # --- trading simulé -----------------------------------------------------
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
        db.x("INSERT INTO trades (ts, agent, symbol, side, qty, price, rationale) "
             "VALUES (CAST(strftime('%s','now') AS REAL),?,?,?,?,?,?)",
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
