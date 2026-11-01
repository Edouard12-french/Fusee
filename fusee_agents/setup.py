"""Assistant de démarrage : lecture/écriture du fichier .env et tests de chaque connexion."""
import imaplib
import json
import os
import re
import shutil
import sys
import urllib.error
import urllib.request

from .config import ROOT

ENV = ROOT / ".env"
EXAMPLE = ROOT / ".env.example"

# Champs réglables depuis l'appli. secret=True : jamais renvoyé en clair au navigateur.
FIELDS = {
    "ANTHROPIC_API_KEY": {"secret": True}, "NTFY_TOPIC": {"secret": False}, "DASHBOARD_PASSWORD": {"secret": True},
    "NETLIFY_TOKEN": {"secret": True}, "STRIPE_SECRET_KEY": {"secret": True}, "PUBLIC_URL": {"secret": False},
    "DASHBOARD_URL": {"secret": False}, "IMAP_HOST": {"secret": False}, "SMTP_HOST": {"secret": False},
    "SMTP_PORT": {"secret": False}, "EMAIL_USER": {"secret": False}, "EMAIL_PASSWORD": {"secret": True},
    "EMAIL_SIGNATURE": {"secret": False}, "FUSEE_PLAN": {"secret": False}, "OWNER_MINOR": {"secret": False},
    "HOST": {"secret": False},
}


def _read() -> dict:
    if not ENV.exists():
        return {}
    out = {}
    for line in ENV.read_text().splitlines():
        m = re.match(r"^\s*([A-Z_][A-Z0-9_]*)\s*=\s*(.*)$", line)
        if m:
            v = m.group(2).strip()
            if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
                v = v[1:-1]
            out[m.group(1)] = v
    return out


def _mask(v: str) -> str:
    return "" if not v else ("•" * 6 + v[-4:] if len(v) > 8 else "••••")


def current() -> dict:
    """Valeurs actuelles (fichier .env, sinon environnement), secrets masqués."""
    env = _read()
    out = {}
    for k, meta in FIELDS.items():
        v = env.get(k, os.getenv(k, ""))
        if v in ("sk-ant-...",):
            v = ""
        out[k] = {"set": bool(v), "value": _mask(v) if meta["secret"] else v}
    return out


def _quote(v: str) -> str:
    return f'"{v}"' if re.search(r"[\s#\"']", v) else v


def save(values: dict) -> list[str]:
    """Écrit les valeurs dans .env (en conservant le reste du fichier). Les secrets vides ne sont pas effacés."""
    if not ENV.exists():
        shutil.copy(EXAMPLE, ENV) if EXAMPLE.exists() else ENV.write_text("")
    lines = ENV.read_text().splitlines()
    changed = []
    for k, v in values.items():
        if k not in FIELDS:
            continue
        v = str(v).strip().replace("\n", " ")
        if FIELDS[k]["secret"] and (not v or v.startswith("••")):
            continue  # champ secret laissé vide ou masqué : on garde l'ancienne valeur
        new = f"{k}={_quote(v)}"
        for i, line in enumerate(lines):
            if re.match(rf"^\s*{k}\s*=", line):
                lines[i] = new
                break
        else:
            lines.append(new)
        os.environ[k] = v
        changed.append(k)
    ENV.write_text("\n".join(lines) + "\n")
    try:
        os.chmod(ENV, 0o600)  # fichier lisible seulement par toi
    except OSError:
        pass
    return changed


def _value(k: str, given: str) -> str:
    """La valeur à tester : celle saisie, sinon celle déjà enregistrée."""
    if given and not given.startswith("••"):
        return given.strip()
    return _read().get(k, os.getenv(k, "")).strip()


def _get(url: str, headers: dict, timeout: int = 15) -> tuple[int, str]:
    req = urllib.request.Request(url, headers={"User-Agent": "Fusee/1.0", **headers})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read(4000).decode(errors="replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read(500).decode(errors="replace")


def test(service: str, given: dict) -> dict:
    """Teste une connexion. Renvoie {ok, message}."""
    try:
        if service == "anthropic":
            key = _value("ANTHROPIC_API_KEY", given.get("ANTHROPIC_API_KEY", ""))
            if not key:
                return {"ok": False, "message": "Colle d'abord la clé."}
            import anthropic
            models = anthropic.Anthropic(api_key=key, max_retries=0, timeout=20).models.list(limit=5)
            return {"ok": True, "message": f"Clé valide ✅ ({len(models.data)} modèles accessibles)."}
        if service == "ntfy":
            topic = _value("NTFY_TOPIC", given.get("NTFY_TOPIC", ""))
            if len(topic) < 12:
                return {"ok": False, "message": "Choisis un nom de sujet long et secret (au moins 12 caractères)."}
            server = os.getenv("NTFY_SERVER", "https://ntfy.sh").rstrip("/")
            body = json.dumps({"topic": topic, "title": "Fusée 🚀", "message": "Les notifications marchent !",
                               "tags": ["rocket"]}).encode()
            req = urllib.request.Request(server, data=body, headers={"Content-Type": "application/json"}, method="POST")
            urllib.request.urlopen(req, timeout=15).read()
            return {"ok": True, "message": "Notification envoyée : regarde ton téléphone 📱"}
        if service == "netlify":
            tok = _value("NETLIFY_TOKEN", given.get("NETLIFY_TOKEN", ""))
            code, body = _get("https://api.netlify.com/api/v1/user", {"Authorization": f"Bearer {tok}"})
            if code == 200:
                return {"ok": True, "message": f"Connecté à Netlify ✅ ({json.loads(body).get('email', '')})"}
            return {"ok": False, "message": f"Netlify refuse le jeton (HTTP {code})."}
        if service == "stripe":
            key = _value("STRIPE_SECRET_KEY", given.get("STRIPE_SECRET_KEY", ""))
            if not key.startswith(("sk_test_", "sk_live_", "rk_")):
                return {"ok": False, "message": "Une clé secrète Stripe commence par sk_test_ ou sk_live_."}
            code, body = _get("https://api.stripe.com/v1/balance", {"Authorization": f"Bearer {key}"})
            if code == 200:
                live = json.loads(body).get("livemode")
                return {"ok": True, "message": "Stripe connecté ✅ — " + ("mode RÉEL (vrais paiements)" if live else
                                                                      "mode TEST (aucun vrai paiement)")}
            return {"ok": False, "message": f"Stripe refuse la clé (HTTP {code})."}
        if service == "email":
            host = _value("IMAP_HOST", given.get("IMAP_HOST", ""))
            user = _value("EMAIL_USER", given.get("EMAIL_USER", ""))
            pwd = _value("EMAIL_PASSWORD", given.get("EMAIL_PASSWORD", ""))
            with imaplib.IMAP4_SSL(host, timeout=20) as m:
                m.login(user, pwd)
            return {"ok": True, "message": f"Boîte mail connectée ✅ ({user})"}
        if service == "public_url":
            url = _value("PUBLIC_URL", given.get("PUBLIC_URL", "")).rstrip("/")
            if not url.startswith("https://"):
                return {"ok": False, "message": "L'adresse publique doit commencer par https://"}
            code, body = _get(f"{url}/public/a.js", {})
            if code == 200 and "Fusée" in body:
                return {"ok": True, "message": "Adresse publique joignable ✅ : le chat marchera sur les sites en ligne."}
            return {"ok": False, "message": f"Fusée n'est pas joignable à cette adresse (HTTP {code})."}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "message": f"Échec : {str(e)[:200]}"}
    return {"ok": False, "message": "Service inconnu."}


def restart() -> None:
    """Redémarre Fusée pour appliquer les nouveaux réglages (sans rouvrir le navigateur)."""
    os.environ["OPEN_BROWSER"] = "false"
    os.execv(sys.executable, [sys.executable] + sys.argv)
