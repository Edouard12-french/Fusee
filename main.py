"""Lance l'équipe d'agents Fusée et son tableau de bord : python main.py"""
import os
import sys

import uvicorn

from fusee_agents.config import PORT

if __name__ == "__main__":
    if not os.getenv("ANTHROPIC_API_KEY") and not os.getenv("ANTHROPIC_AUTH_TOKEN"):
        print("⚠️  ANTHROPIC_API_KEY manquante : copie .env.example en .env et mets ta clé.", file=sys.stderr)
    print(f"🚀 Fusée démarre — tableau de bord sur http://localhost:{PORT}")
    uvicorn.run("fusee_agents.web:app", host="0.0.0.0", port=PORT, log_level="warning")
