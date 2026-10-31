"""Configuration globale, lue depuis l'environnement (fichier .env)."""
import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")


def _bool(name: str, default: bool) -> bool:
    return os.getenv(name, str(default)).strip().lower() in ("1", "true", "yes", "oui")


MODEL = os.getenv("FUSEE_MODEL", "claude-opus-5-5")
EFFORT = os.getenv("FUSEE_EFFORT", "medium")
DAILY_BUDGET_USD = float(os.getenv("DAILY_BUDGET_USD", "10"))
INTERVAL_MULTIPLIER = float(os.getenv("INTERVAL_MULTIPLIER", "1"))
ALLOW_CODE_EXEC = _bool("ALLOW_CODE_EXEC", True)
MAX_PARALLEL_AGENTS = int(os.getenv("MAX_PARALLEL_AGENTS", "2"))
PORT = int(os.getenv("PORT", "8000"))
# Adresse publique du tableau de bord (Tailscale Funnel, Cloudflare Tunnel…) : sert au chat des sites en ligne
PUBLIC_URL = os.getenv("PUBLIC_URL", "").strip().rstrip("/")

DATA_DIR = ROOT / "data"
WORKSPACE = ROOT / "workspace"
DB_PATH = DATA_DIR / "fusee.db"
DATA_DIR.mkdir(exist_ok=True)
WORKSPACE.mkdir(exist_ok=True)

MAX_STEPS_PER_CYCLE = 25          # appels API max par cycle d'un agent
PAPER_START_CASH = 10_000.0       # capital fictif du portefeuille simulé (EUR)

# Tarifs USD par million de tokens : (entrée, sortie, lecture cache, écriture cache)
PRICING = {
    "claude-opus-5-5": (4.0, 20.0, 0.20, 5.0),
    "claude-sonnet-5-5": (2.0, 10.0, 0.20, 2.5),
    "claude-haiku-5-5": (0.10, 0.50, 0.01, 0.125),
    "claude-fable-5-1": (10.0, 50.0, 0.25, 12.5),
}
WEB_SEARCH_COST = 0.01  # USD par recherche web
