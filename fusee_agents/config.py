"""Configuration globale, lue depuis l'environnement (fichier .env)."""
import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")


def _bool(name: str, default: bool) -> bool:
    return os.getenv(name, str(default)).strip().lower() in ("1", "true", "yes", "oui")


# --- Modèles : un « plan » choisit le modèle et l'effort de chaque niveau d'agent -----------------
# Niveaux : lead (orchestrateur), worker (agents qui produisent), coord (agents de coordination).
PLANS = {
    "max":       {"lead": ("claude-opus-5-5", "high"), "worker": ("claude-opus-5-5", "medium"),
                  "coord": ("claude-opus-5-5", "low")},
    "equilibre": {"lead": ("claude-opus-5-5", "medium"), "worker": ("claude-sonnet-5-5", "medium"),
                  "coord": ("claude-haiku-5-5", "low")},
    "eco":       {"lead": ("claude-sonnet-5-5", "medium"), "worker": ("claude-haiku-5-5", "medium"),
                  "coord": ("claude-haiku-5-5", "low")},
}
PLAN = os.getenv("FUSEE_PLAN", "eco").strip().lower()
if PLAN not in PLANS:
    PLAN = "eco"
FORCE_MODEL = os.getenv("FUSEE_MODEL", "").strip()     # si défini : ce modèle pour tous les agents
FORCE_EFFORT = os.getenv("FUSEE_EFFORT", "").strip()   # si défini : cet effort pour tous les agents


def model_for(tier: str) -> tuple[str, str]:
    model, effort = PLANS[PLAN].get(tier, PLANS[PLAN]["worker"])
    return FORCE_MODEL or model, FORCE_EFFORT or effort


# --- Budget réel de Patron (modifiable ensuite dans l'appli, onglet Argent) ----------------------
BUDGET_INITIAL_EUR = float(os.getenv("BUDGET_INITIAL_EUR", "100"))
API_BUDGET_EUR = float(os.getenv("API_BUDGET_EUR", "60"))      # part du budget réservée à l'IA
API_BUDGET_DAYS = float(os.getenv("API_BUDGET_DAYS", "30"))    # étalée sur ce nombre de jours
USD_EUR = float(os.getenv("USD_EUR", "0.92"))                  # taux de conversion approximatif
DAILY_BUDGET_USD = float(os.getenv("DAILY_BUDGET_USD", "0") or 0)  # plafond dur optionnel (0 = aucun)
# Patron a moins de 18 ans : comptes, paiements et contrats passent par un parent
OWNER_MINOR = _bool("OWNER_MINOR", False)
INTERVAL_MULTIPLIER = float(os.getenv("INTERVAL_MULTIPLIER", "1"))
ALLOW_CODE_EXEC = _bool("ALLOW_CODE_EXEC", True)
MAX_PARALLEL_AGENTS = int(os.getenv("MAX_PARALLEL_AGENTS", "2"))
PORT = int(os.getenv("PORT", "8000"))
# Adresse publique du tableau de bord (Tailscale Funnel, Cloudflare Tunnel…) : sert au chat des sites en ligne
PUBLIC_URL = os.getenv("PUBLIC_URL", "").strip().rstrip("/")

DATA_DIR = Path(os.getenv("FUSEE_DATA_DIR", ROOT / "data"))        # réglables pour les tests
WORKSPACE = Path(os.getenv("FUSEE_WORKSPACE", ROOT / "workspace"))
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
