"""Fusée : l'équipe d'agents IA de Patron."""
import os
import sys


def use_certifi_on_mac(platform: str = sys.platform, env=os.environ) -> bool:
    """Sur Mac, le Python installé pour Fusée ne trouve pas toujours les certificats du système : chaque connexion
    sécurisée (Netlify, Stripe, notifications, cours de bourse…) échoue avec « CERTIFICATE_VERIFY_FAILED ».
    On lui donne la liste de certificats de « certifi » (celle qu'utilise déjà le module de Claude)."""
    if platform != "darwin" or env.get("SSL_CERT_FILE"):
        return False
    try:
        import certifi
    except ImportError:
        return False
    env["SSL_CERT_FILE"] = certifi.where()
    return True


use_certifi_on_mac()
