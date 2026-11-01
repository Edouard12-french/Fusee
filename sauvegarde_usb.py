"""Sauvegarde complète de Fusée vers une clé USB (ou n'importe quel dossier).

    python sauvegarde_usb.py /Volumes/MA_CLE

Crée MA_CLE/Fusee-sauvegardes/AAAA-MM-JJ_HHhMM/ avec :
  donnees/   la base (conversations, clients, ventes, mémoire des agents…) copiée proprement, même Fusée allumé
  workspace/ tout le travail des agents (sites, code, vidéos, documents…)
  code/      Fusée lui-même
  reglages.env  tes réglages SANS les clés ni mots de passe (si la clé USB est perdue, personne ne peut s'en servir)
  LISEZ-MOI.txt comment remettre la sauvegarde
Rien n'est jamais effacé sur la clé. N'utilise que la bibliothèque standard de Python.
"""
import os
import re
import shutil
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA = Path(os.getenv("FUSEE_DATA_DIR", ROOT / "data"))
WORKSPACE = Path(os.getenv("FUSEE_WORKSPACE", ROOT / "workspace"))
SKIP_DIRS = {".git", ".venv", "venv", "__pycache__", "node_modules", ".pytest_cache", "logs", "sauvegardes"}
SKIP_CODE = SKIP_DIRS | {"data", "workspace"}
SECRET_RE = re.compile(r"KEY|PASS|SECRET|TOKEN|TOPIC", re.I)  # tout ce qui ressemble à un secret


def _size(path: Path, skip: set[str]) -> int:
    total = 0
    for dirpath, dirnames, filenames in os.walk(path):
        dirnames[:] = [d for d in dirnames if d not in skip]
        for f in filenames:
            try:
                total += (Path(dirpath) / f).stat().st_size
            except OSError:
                pass
    return total


def _copy_tree(src: Path, dst: Path, skip: set[str], skip_files=lambda p: False) -> tuple[int, list[str]]:
    """Copie fichier par fichier : une erreur (fichier trop gros pour la clé, nom refusé…) n'arrête pas tout."""
    n, errors = 0, []
    if not src.is_dir():
        return n, errors
    for dirpath, dirnames, filenames in os.walk(src):
        dirnames[:] = [d for d in dirnames if d not in skip]
        rel = Path(dirpath).relative_to(src)
        for f in filenames:
            s = Path(dirpath) / f
            if s.is_symlink() or skip_files(s):
                continue
            d = dst / rel / f
            try:
                d.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(s, d)
                try:
                    shutil.copystat(s, d)  # les clés USB (FAT/exFAT) refusent parfois : pas grave
                except OSError:
                    pass
                n += 1
            except OSError as e:
                errors.append(f"{rel / f} ({e.strerror or e})")
    return n, errors


def _env_without_secrets(src: Path) -> str:
    secret_keys = set()
    try:
        sys.path.insert(0, str(ROOT))
        from fusee_agents.setup import FIELDS  # liste officielle des champs secrets
        secret_keys = {k for k, v in FIELDS.items() if v.get("secret")}
    except Exception:  # noqa: BLE001 — sans le module, la règle par nom suffit
        pass
    out = ["# Réglages de Fusée SANS les clés ni mots de passe (à recoller dans 🚀 Démarrage après restauration)"]
    for line in src.read_text(encoding="utf-8", errors="replace").splitlines():
        m = re.match(r"\s*([A-Za-z_][A-Za-z0-9_]*)\s*=", line)
        if m and (m.group(1) in secret_keys or SECRET_RE.search(m.group(1))):
            out.append(f"{m.group(1)}=")
        else:
            out.append(line)
    return "\n".join(out) + "\n"


README = """💾 SAUVEGARDE DE FUSÉE — {date}

Ce dossier contient :
  donnees/      la base de Fusée : conversations, clients, ventes, idées, mémoire des agents…
  workspace/    tout le travail des agents : sites, code, vidéos, documents
  code/         Fusée lui-même
  reglages.env  tes réglages, SANS ta clé API ni tes mots de passe (exprès : si la clé USB est perdue,
                personne ne peut dépenser ton argent)

⚠️ Garde cette clé USB dans un endroit sûr : elle contient les conversations avec tes clients.

POUR REMETTRE CETTE SAUVEGARDE (par exemple sur un nouveau Mac)
  1. Installe Fusée normalement (fichier « Fusee » à double-cliquer), puis ferme la fenêtre Fusée.
  2. Copie le dossier « donnees » de cette sauvegarde à la place du dossier « data » dans le dossier Fusee
     (renomme-le « data »), et le dossier « workspace » à la place de « workspace ».
  3. Ouvre Fusée → 🚀 Démarrage → recolle ta clé API (et tes autres mots de passe s'il y en avait).
  En cas de doute, demande de l'aide avant de remplacer quoi que ce soit.
"""


def main(target: str) -> int:
    base = Path(target)
    if not base.is_dir():
        print(f"❌ Je ne trouve pas « {target} ». Branche la clé USB et réessaie.")
        return 1
    estimate = _size(DATA, SKIP_DIRS) + _size(WORKSPACE, SKIP_DIRS) + _size(ROOT, SKIP_CODE)
    free = shutil.disk_usage(base).free
    print(f"📦 Taille à copier : environ {estimate / 1e6:.1f} Mo — place libre sur la clé : {free / 1e9:.1f} Go")
    if estimate * 1.1 > free:
        print("❌ Pas assez de place sur la clé USB. Libère de la place ou prends une autre clé.")
        return 1
    stamp = datetime.now().strftime("%Y-%m-%d_%Hh%M")
    dest = base / "Fusee-sauvegardes" / stamp
    dest.mkdir(parents=True, exist_ok=True)
    errors: list[str] = []

    print("🗄️  Base de données…")
    db = DATA / "fusee.db"
    (dest / "donnees").mkdir(exist_ok=True)
    if db.exists():
        tmp = dest / "donnees" / "fusee.db"
        src = sqlite3.connect(db)
        out = sqlite3.connect(tmp)
        try:
            src.backup(out)  # copie cohérente, même si les agents travaillent en ce moment
        finally:
            out.close()
            src.close()
    n_data, e = _copy_tree(DATA, dest / "donnees", SKIP_DIRS,
                           skip_files=lambda p: p.name.startswith("fusee.db") or p.suffix == ".pem")
    errors += e

    print("🧰 Travail des agents…")
    n_ws, e = _copy_tree(WORKSPACE, dest / "workspace", SKIP_DIRS)
    errors += e

    print("🚀 Code de Fusée…")
    n_code, e = _copy_tree(ROOT, dest / "code", SKIP_CODE,
                           skip_files=lambda p: p.name == ".env" or p.suffix == ".pyc")
    errors += e

    env = ROOT / ".env"
    if env.exists():
        (dest / "reglages.env").write_text(_env_without_secrets(env), encoding="utf-8")
    (dest / "LISEZ-MOI.txt").write_text(README.format(date=stamp.replace("_", " à ")), encoding="utf-8")

    print("")
    print(f"✅ Sauvegarde terminée : {dest}")
    print(f"   {n_ws} fichiers de travail, {n_data + (1 if db.exists() else 0)} fichiers de données, {n_code} fichiers de code.")
    print("   🔒 Ta clé API et tes mots de passe ne sont PAS sur la clé (exprès).")
    if errors:
        print(f"⚠️  {len(errors)} fichier(s) n'ont pas pu être copiés :")
        for line in errors[:10]:
            print("   -", line)
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Utilisation : python sauvegarde_usb.py /Volumes/MA_CLE")
        sys.exit(2)
    sys.exit(main(sys.argv[1]))
