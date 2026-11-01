"""Savoir de départ de l'équipe : fiches d'expert installées dans workspace/competences et la mémoire collective."""
import shutil
from pathlib import Path

from . import db
from .config import WORKSPACE

SRC = Path(__file__).parent / "knowledge"
VERSION = "1"


def install() -> int:
    """Copie les fiches manquantes (sans écraser celles que Sage a améliorées) et les indexe une fois en mémoire."""
    dest = WORKSPACE / "competences"
    dest.mkdir(parents=True, exist_ok=True)
    copied = 0
    for f in sorted(SRC.glob("*.md")):
        if not (dest / f.name).exists():
            shutil.copy(f, dest / f.name)
            copied += 1
    if db.get_setting("knowledge_version", "") != VERSION:
        for f in sorted(SRC.glob("*.md")):
            text = f.read_text()
            db.kb_add("Fusée", text.splitlines()[0].lstrip("# ").strip(), text)
        db.set_setting("knowledge_version", VERSION)
    return copied
