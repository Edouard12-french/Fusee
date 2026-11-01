#!/usr/bin/env bash
# Crée l'application « Fusée » : une icône à double-cliquer (Finder, Dock, Launchpad) qui démarre Fusée si besoin
# et ouvre l'interface dans sa propre fenêtre. Tout reste sur ton Mac : rien n'est mis sur internet.
set -e
cd "$(dirname "$0")"
DIR="$(pwd)"
[ "$(uname)" = "Darwin" ] || { echo "Ce script est pour Mac."; exit 1; }
APP="$HOME/Applications/Fusée.app"
mkdir -p "$HOME/Applications"
rm -rf "$APP"
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"
cp fusee_agents/static/AppIcon.icns "$APP/Contents/Resources/AppIcon.icns"

cat > "$APP/Contents/Info.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleName</key><string>Fusée</string>
  <key>CFBundleDisplayName</key><string>Fusée</string>
  <key>CFBundleIdentifier</key><string>fr.fusee.app</string>
  <key>CFBundleVersion</key><string>1.0</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>CFBundleExecutable</key><string>Fusee</string>
  <key>CFBundleIconFile</key><string>AppIcon</string>
  <key>LSMinimumSystemVersion</key><string>11.0</string>
  <key>NSHighResolutionCapable</key><true/>
</dict>
</plist>
PLIST

cat > "$APP/Contents/MacOS/Fusee" <<LAUNCHER
#!/bin/bash
# Lanceur de Fusée (créé par creer-app-mac.sh)
DIR="$DIR"
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
PORT=\$(grep -E '^PORT=' "\$DIR/.env" 2>/dev/null | cut -d= -f2 | tr -d '" ')
URL="http://localhost:\${PORT:-8000}"
up() { curl -s -m 2 -o /dev/null "\$URL/manifest.webmanifest"; }
say() { osascript -e "display notification \"\$1\" with title \"🚀 Fusée\"" >/dev/null 2>&1; }

if ! up; then
  if launchctl print "gui/\$(id -u)/fr.fusee.agents" >/dev/null 2>&1; then
    launchctl kickstart "gui/\$(id -u)/fr.fusee.agents"
  else
    mkdir -p "\$DIR/logs"
    OPEN_BROWSER=false nohup /bin/bash "\$DIR/start.sh" >> "\$DIR/logs/fusee.log" 2>&1 &
  fi
  [ -x "\$DIR/.venv/bin/python" ] && say "Démarrage de l'équipe…" || say "Première installation : 2 à 5 minutes, patience…"
  for i in \$(seq 1 400); do up && break; sleep 1; done
  if ! up; then
    osascript -e 'display dialog "Fusée n'"'"'a pas pu démarrer. Ouvre le fichier logs/fusee.log dans le dossier Fusee pour voir pourquoi (souvent : Python 3.11+ à installer depuis python.org)." buttons {"OK"} with icon caution with title "Fusée"' >/dev/null 2>&1
    open "\$DIR/logs"
    exit 1
  fi
fi

# Une fenêtre à part, comme une vraie application (Chrome, Edge, Brave ou Arc), sinon le navigateur par défaut
for b in "Google Chrome" "Microsoft Edge" "Brave Browser" "Arc" "Chromium"; do
  if [ -d "/Applications/\$b.app" ] || [ -d "\$HOME/Applications/\$b.app" ]; then
    open -na "\$b" --args --app="\$URL" --window-size=1400,900
    exit 0
  fi
done
open "\$URL"
LAUNCHER
chmod +x "$APP/Contents/MacOS/Fusee" start.sh
touch "$APP"   # rafraîchit l'icône dans le Finder
ln -sfn "$APP" "$HOME/Desktop/Fusée.app" 2>/dev/null || true   # raccourci sur le Bureau
echo "✅ Application créée : $APP"
echo "   👉 Double-clique sur « Fusée » sur ton Bureau (ou glisse-la dans le Dock)."
open -R "$APP" 2>/dev/null || true
