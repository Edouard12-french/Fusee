"""Outils mis à disposition des agents (schémas + exécution)."""
import asyncio
import json
import re
import sys
from pathlib import Path

from . import browser, db, integrations, mailbox
from .agents import BY_NAME, OWNER
from .config import ALLOW_CODE_EXEC, WORKSPACE
from .notify import notify


def _schema(props: dict, required: list[str] | None = None) -> dict:
    return {"type": "object", "properties": props, "required": list(props) if required is None else required,
            "additionalProperties": False}


S = {"type": "string"}
N = {"type": "number"}
I = {"type": "integer"}
LIST = {"type": "array", "items": S}

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
        "input_schema": _schema({"name": S, "price_eur": N, "description": S, "approval_id": I}),
    },
    "sales_summary": {
        "description": "Ventes réelles encaissées sur Stripe + liens de paiement et sites en ligne.",
        "input_schema": _schema({}),
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


MENTION_RE = re.compile(r"(?:^|\s)@(\w+)")


def mentions(text: str) -> list[str]:
    names = set(MENTION_RE.findall(text))
    if names & {"Tous", "tous", "all", "Équipe", "equipe"}:
        return list(BY_NAME)
    return [n for n in BY_NAME if n in names]


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
            sys.executable, str(p), *args["args"], cwd=str(p.parent),
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
        prev = db.q("SELECT provider_id FROM deployments WHERE site=? ORDER BY id DESC LIMIT 1", (rel,))
        r = await asyncio.to_thread(integrations.deploy_site, folder, folder.name, prev[0]["provider_id"] if prev else None)
        db.x("INSERT INTO deployments (ts, agent, site, provider_id, url, approval_id) "
             "VALUES (CAST(strftime('%s','now') AS REAL),?,?,?,?,?)", (agent, rel, r["site_id"], r["url"], appr["id"]))
        notify("alerte", f"🌐 Site en ligne : {folder.name}", f"{r['url']}\n(validé par toi, demande #{appr['id']})")
        db.post_message(agent, f"🌐 {folder.name} est en ligne !", _attach_json([], [r["url"]]))
        return f"Site en ligne : {r['url']}"
    if name == "create_payment_link":
        appr = _accepted(args["approval_id"], ("business", "publication"))
        if not appr:
            return (f"Refusé : la demande #{args['approval_id']} n'est pas acceptée. Demande d'abord l'accord de "
                    f"{OWNER} (produit, prix, plateforme) avec request_approval.")
        if args["price_eur"] <= 0:
            return "Erreur : prix invalide."
        r = await asyncio.to_thread(integrations.create_payment_link, args["name"], args["price_eur"], args["description"])
        db.x("INSERT INTO payment_links (ts, agent, name, price_eur, url, stripe_id, approval_id) "
             "VALUES (CAST(strftime('%s','now') AS REAL),?,?,?,?,?,?)",
             (agent, args["name"], args["price_eur"], r["url"], r["id"], appr["id"]))
        notify("alerte", f"💳 Lien de paiement créé : {args['name']} ({args['price_eur']} €)", r["url"])
        return f"Lien de paiement : {r['url']} (à mettre sur le site / la page de vente)."
    if name == "sales_summary":
        out = {"liens_de_paiement": db.q("SELECT name, price_eur, url FROM payment_links"),
               "sites_en_ligne": db.q("SELECT site, url, max(ts) ts FROM deployments GROUP BY site")}
        if integrations.STRIPE_KEY:
            out["ventes_stripe"] = await asyncio.to_thread(integrations.sales_summary)
        return json.dumps(out, ensure_ascii=False)
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
