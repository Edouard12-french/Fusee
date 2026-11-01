#!/usr/bin/env bash
# Rend Fusée accessible depuis TON iPhone, de façon privée, grâce à Tailscale (gratuit).
#   ./activer-iphone.sh          → adresse privée https://…ts.net (seuls tes appareils Tailscale y ont accès)
#   ./activer-iphone.sh --chat   → en plus, ouvre au public UNIQUEMENT le chat des sites (serveur séparé)
#   ./activer-iphone.sh --off    → coupe tout
cd "$(dirname "$0")"
TS="$(command -v tailscale || true)"
[ -z "$TS" ] && [ -x "/Applications/Tailscale.app/Contents/MacOS/Tailscale" ] && TS="/Applications/Tailscale.app/Contents/MacOS/Tailscale"
if [ -z "$TS" ]; then
  echo "❌ Tailscale n'est pas installé. Installe-le (gratuit) : https://tailscale.com/download/mac"
  echo "   puis connecte-toi, et installe aussi l'app Tailscale sur ton iPhone avec le même compte."
  [ "$(uname)" = "Darwin" ] && open "https://tailscale.com/download/mac"
  exit 1
fi
PY=python3; [ -x .venv/bin/python ] && PY=.venv/bin/python
env_get() { grep -E "^$1=" .env 2>/dev/null | tail -1 | cut -d= -f2- | tr -d '"'; }
env_set() {  # remplace ou ajoute une ligne CLE=valeur dans .env
  [ -f .env ] || { cp .env.example .env; chmod 600 .env; }
  "$PY" - "$1" "$2" <<'PYEOF'
import re, sys, pathlib
k, v = sys.argv[1], sys.argv[2]
p = pathlib.Path(".env"); lines = p.read_text().splitlines()
for i, l in enumerate(lines):
    if re.match(rf"^\s*{k}\s*=", l):
        lines[i] = f"{k}={v}"; break
else:
    lines.append(f"{k}={v}")
p.write_text("\n".join(lines) + "\n")
PYEOF
}
APP_PORT="$(env_get PORT)"; APP_PORT="${APP_PORT:-8000}"
PUB_PORT="$(env_get PUBLIC_PORT)"; PUB_PORT="${PUB_PORT:-8001}"

if [ "$1" = "--off" ]; then
  "$TS" serve reset && echo "🛑 Fusée n'est plus accessible depuis tes autres appareils (ni le chat public)."
  exit 0
fi

DNS="$("$TS" status --json 2>/dev/null | "$PY" -c 'import json,sys; d=json.load(sys.stdin); print((d.get("Self") or {}).get("DNSName","").rstrip(".")) if d.get("BackendState")=="Running" else print("")' 2>/dev/null)"
if [ -z "$DNS" ]; then
  echo "❌ Tailscale n'est pas connecté : ouvre l'app Tailscale sur le Mac et connecte-toi, puis relance ce script."
  exit 1
fi

echo "🔒 Accès privé à Fusée (seulement tes appareils Tailscale)…"
if ! "$TS" serve --bg "$APP_PORT"; then
  echo "⚠️  Si Tailscale affiche un lien pour activer HTTPS, ouvre-le, accepte, puis relance ce script."
  exit 1
fi
URL="https://$DNS"
env_set DASHBOARD_URL "$URL"
echo ""
echo "✅ Adresse privée de Fusée : $URL"
echo "   📱 Sur ton iPhone (Tailscale allumé) : ouvre-la dans Safari → Partager → « Sur l'écran d'accueil »,"
echo "      puis ouvre Fusée depuis l'icône → ⚙️ Réglages → « Activer les notifications sur cet iPhone »."

if [ "$1" = "--chat" ]; then
  echo ""
  echo "🌍 Chat des sites : ouverture au public du SEUL serveur « chat et statistiques » (port $PUB_PORT)…"
  if "$TS" funnel --bg --https=8443 "$PUB_PORT"; then
    env_set PUBLIC_URL "https://$DNS:8443"
    echo "✅ Adresse publique du chat : https://$DNS:8443 (l'application, elle, reste privée)"
  else
    echo "⚠️  Si Tailscale affiche un lien pour activer « Funnel », ouvre-le, accepte, puis relance avec --chat."
  fi
fi

# Redémarre Fusée pour appliquer (si installé comme service)
if [ "$(uname)" = "Darwin" ] && launchctl print "gui/$(id -u)/fr.fusee.agents" >/dev/null 2>&1; then
  launchctl kickstart -k "gui/$(id -u)/fr.fusee.agents" && echo "♻️  Fusée redémarré avec la nouvelle adresse."
else
  echo "♻️  Redémarre Fusée (bouton « Redémarrer » dans 🚀 Démarrage) pour appliquer."
fi
