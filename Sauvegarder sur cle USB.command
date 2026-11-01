#!/bin/bash
# 💾 Branche ta clé USB, puis double-clique sur ce fichier : Fusée et tout le travail des agents y sont copiés.
#    Tes clés et mots de passe ne sont PAS copiés (si la clé est perdue, personne ne peut s'en servir).
cd "$(dirname "$0")" || exit 1
export PATH="$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
clear
echo "💾 Sauvegarde de Fusée sur clé USB"
echo ""
fin() { echo ""; read -r -p "Appuie sur Entrée pour fermer cette fenêtre…" _; exit "${1:-0}"; }

# Les clés USB / disques externes branchés (pas le disque du Mac, pas les images disque)
VOLS=()
for v in /Volumes/*; do
  [ -d "$v" ] && [ -w "$v" ] || continue
  info="$(diskutil info "$v" 2>/dev/null)" || continue
  echo "$info" | grep -qE "Protocol: +Disk Image" && continue
  echo "$info" | grep -qE "Protocol: +USB|Device Location: +External|Removable Media: +Removable" || continue
  VOLS+=("$v")
done

if [ ${#VOLS[@]} -eq 0 ]; then
  echo "🔌 Je ne trouve aucune clé USB."
  echo "   Branche-la, attends qu'elle apparaisse dans le Finder (à gauche), puis double-clique à nouveau sur ce fichier."
  fin 1
elif [ ${#VOLS[@]} -eq 1 ]; then
  VOL="${VOLS[0]}"
else
  NAMES=(); for v in "${VOLS[@]}"; do NAMES+=("$(basename "$v")"); done
  CHOIX="$(osascript - "${NAMES[@]}" <<'OSA'
on run argv
  set c to choose from list argv with prompt "Sur quelle clé USB sauvegarder Fusée ?" with title "Fusée"
  if c is false then return ""
  return item 1 of c
end run
OSA
)"
  [ -z "$CHOIX" ] && { echo "Annulé."; fin 1; }
  VOL="/Volumes/$CHOIX"
fi
echo "🔌 Clé USB : $(basename "$VOL")"
echo ""

PY=.venv/bin/python; [ -x "$PY" ] || PY=python3
if ! "$PY" sauvegarde_usb.py "$VOL"; then
  echo ""
  echo "❌ La sauvegarde n'a pas pu se faire (voir le message ci-dessus)."
  fin 1
fi

echo ""
echo "⏏️  Éjection de la clé…"
if diskutil eject "$VOL" >/dev/null 2>&1; then
  echo "✅ Tu peux retirer la clé USB."
else
  echo "👉 Avant de la retirer : dans le Finder, clique sur ⏏️ à côté du nom de la clé."
fi
fin 0
