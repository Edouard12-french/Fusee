"""🔐 Autorisations : ce que 🎖️ Vice peut accepter à la place de Patron (réglé avec le code parent).

Patron coche ce qu'il délègue : mises en ligne de sites, lancements sans argent, prospection d'entreprises ; et quand :
seulement pendant qu'il laisse l'équipe travailler seule, ou tout le temps. Jamais délégable : argent, compte, accord d'un
parent, réponse à un client, recrutement d'agent. Tout ce que Vice accepte est noté « 🎖️ Vice (à ta place) », apparaît
dans le récap du matin et peut être annulé (un site est retiré d'internet ; une campagne est stoppée — mais un e-mail
déjà envoyé ne peut pas être repris).
"""
from . import budget, db

VICE = "🎖️ Vice (à ta place)"
# type de demande → autorisation qui permet à Vice de la décider
KINDS = {"publication": "publish", "business": "business", "prospection": "outreach"}
NEVER = ("dépense", "investissement", "équipe", "réponse client")
LABELS = {"publish": "mettre des sites en ligne", "business": "lancer un business sans argent",
          "outreach": "contacter des entreprises (prospection)"}


def settings() -> dict:
    g = lambda k: db.get_setting(k, "0") == "1"  # noqa: E731
    return {"publish": g("delegate_publish"), "business": g("delegate_business"), "outreach": g("delegate_outreach"),
            "always": g("delegate_always"), "unlimited": budget.unlimited()}


def save(**changes) -> dict:
    for k in ("publish", "business", "outreach", "always"):
        if changes.get(k) is not None:
            db.set_setting(f"delegate_{k}", "1" if changes[k] else "0")
    if changes.get("unlimited") is not None:
        db.set_setting("budget_unlimited", "1" if changes["unlimited"] else "0")
    return settings()


def active() -> bool:
    """Vice peut-il décider en ce moment ? (quelque chose est délégué, et c'est le bon moment)"""
    s = settings()
    return (s["publish"] or s["business"] or s["outreach"]) and (s["always"] or budget.work_authorized())


def can_decide(appr: dict) -> tuple[bool, str]:
    """Vice peut-il décider cette demande à la place de Patron ? (oui/non, pourquoi)"""
    s = settings()
    if appr["status"] != "en attente":
        return False, "cette demande est déjà décidée"
    if not (s["always"] or budget.work_authorized()):
        return False, "Patron ne délègue que pendant qu'il laisse l'équipe travailler seule"
    if appr.get("needs_parent"):
        return False, "elle a besoin de l'accord d'un parent (code parent) : seul le parent peut l'accepter"
    if (appr.get("amount_eur") or 0) > 0 or appr["kind"] in NEVER:
        return False, "argent, recrutement ou réponse à un client : toujours Patron lui-même"
    need = KINDS.get(appr["kind"])
    if not need:
        return False, f"le type « {appr['kind']} » n'est pas délégable"
    if not s[need]:
        return False, f"Patron n'a pas autorisé Vice à {LABELS[need]}"
    return True, ""


def context_text() -> str:
    s = settings()
    if not active():
        return "Aucune délégation en ce moment : toutes les validations attendent Patron."
    allowed = [LABELS[k] for k in ("publish", "business", "outreach") if s[k]]
    when = "tout le temps" if s["always"] else "pendant la période de travail en solo"
    return (f"DÉLÉGATION ACTIVE ({when}) : tu peux décider à la place de Patron, avec list_approvals puis "
            f"decide_approval, les demandes pour : {' ; '.join(allowed)}. Jamais argent, compte, accord parent ni "
            "réponse à un client. Patron verra tout dans le récap et pourra annuler.")
