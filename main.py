"""Lance l'équipe d'agents Fusée et son tableau de bord : python main.py"""
import os
import sys
import threading
import webbrowser

import uvicorn

from fusee_agents.config import PORT

if __name__ == "__main__":
    if not os.getenv("ANTHROPIC_API_KEY") and not os.getenv("ANTHROPIC_AUTH_TOKEN"):
        print("⚠️  ANTHROPIC_API_KEY manquante : copie .env.example en .env et mets ta clé.", file=sys.stderr)
    print(f"🚀 Fusée démarre — application sur http://localhost:{PORT}")
    if os.getenv("OPEN_BROWSER", "true").lower() in ("1", "true", "oui", "yes"):
        threading.Timer(2.5, lambda: webbrowser.open(f"http://localhost:{PORT}")).start()
    uvicorn.run("fusee_agents.web:app", host="0.0.0.0", port=PORT, log_level="warning")
