"""Notifications « Web Push » vers l'app Fusée installée sur l'iPhone (ou un autre appareil).

Implémentation autonome des standards (pas de dépendance difficile à installer) :
- RFC 8291 / RFC 8188 : chiffrement du message (aes128gcm) — personne d'autre que l'appareil ne peut le lire,
  pas même le service de push d'Apple ;
- RFC 8292 : identification du serveur (VAPID, jeton signé ES256)."""
import base64
import json
import os
import struct
import time
import urllib.error
import urllib.parse
import urllib.request

from cryptography.hazmat.primitives import hashes, hmac, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF, HKDFExpand

from . import db
from .config import DATA_DIR

KEY_FILE = DATA_DIR / "vapid_private.pem"


def b64u(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def unb64u(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def _raw_public(key: ec.EllipticCurvePrivateKey) -> bytes:
    return key.public_key().public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)


def vapid_key() -> ec.EllipticCurvePrivateKey:
    """Clé du serveur, créée au premier usage et gardée dans data/ (jamais envoyée sur GitHub)."""
    if KEY_FILE.exists():
        return serialization.load_pem_private_key(KEY_FILE.read_bytes(), password=None)
    key = ec.generate_private_key(ec.SECP256R1())
    KEY_FILE.write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                           serialization.NoEncryption()))
    try:
        os.chmod(KEY_FILE, 0o600)
    except OSError:
        pass
    return key


def public_key_b64() -> str:
    """Clé publique à donner au navigateur (applicationServerKey)."""
    return b64u(_raw_public(vapid_key()))


def _subject() -> str:
    custom = os.getenv("VAPID_SUBJECT", "").strip()
    if custom:
        return custom
    email = os.getenv("EMAIL_USER", "").strip()
    if email:
        return f"mailto:{email}"
    url = os.getenv("DASHBOARD_URL", "").strip()
    return url if url.startswith("https://") else "mailto:fusee@example.org"


def vapid_header(endpoint: str) -> str:
    """En-tête Authorization VAPID (RFC 8292) pour le service de push de cet abonnement."""
    u = urllib.parse.urlparse(endpoint)
    head = b64u(json.dumps({"typ": "JWT", "alg": "ES256"}, separators=(",", ":")).encode())
    claims = b64u(json.dumps({"aud": f"{u.scheme}://{u.netloc}", "exp": int(time.time()) + 12 * 3600,
                              "sub": _subject()}, separators=(",", ":")).encode())
    key = vapid_key()
    der = key.sign(f"{head}.{claims}".encode(), ec.ECDSA(hashes.SHA256()))
    r, s = decode_dss_signature(der)
    sig = b64u(r.to_bytes(32, "big") + s.to_bytes(32, "big"))
    return f"vapid t={head}.{claims}.{sig}, k={b64u(_raw_public(key))}"


def encrypt(payload: bytes, p256dh: str, auth: str, salt: bytes | None = None,
            server_key: ec.EllipticCurvePrivateKey | None = None) -> bytes:
    """Chiffre le message pour l'appareil (RFC 8291, codage aes128gcm, un seul enregistrement)."""
    ua_public = unb64u(p256dh)
    auth_secret = unb64u(auth)
    as_key = server_key or ec.generate_private_key(ec.SECP256R1())
    as_public = _raw_public(as_key)
    ua_key = ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), ua_public)
    ecdh_secret = as_key.exchange(ec.ECDH(), ua_key)
    ikm = HKDF(algorithm=hashes.SHA256(), length=32, salt=auth_secret,
               info=b"WebPush: info\x00" + ua_public + as_public).derive(ecdh_secret)
    salt = salt or os.urandom(16)
    h = hmac.HMAC(salt, hashes.SHA256())  # HKDF-Extract (RFC 8188) : PRK = HMAC-SHA256(salt, IKM)
    h.update(ikm)
    prk_bytes = h.finalize()
    cek = HKDFExpand(algorithm=hashes.SHA256(), length=16, info=b"Content-Encoding: aes128gcm\x00").derive(prk_bytes)
    nonce = HKDFExpand(algorithm=hashes.SHA256(), length=12, info=b"Content-Encoding: nonce\x00").derive(prk_bytes)
    record = payload + b"\x02"  # délimiteur du dernier enregistrement
    cipher = AESGCM(cek).encrypt(nonce, record, None)
    rs = 4096
    header = salt + struct.pack(">I", rs) + bytes([len(as_public)]) + as_public
    return header + cipher


def send(sub: dict, title: str, body: str, url: str = "/", urgency: str = "normal") -> int:
    """Envoie une notification à un abonnement. Renvoie le code HTTP du service de push."""
    payload = json.dumps({"title": title[:120], "body": body[:300], "url": url}, ensure_ascii=False).encode()
    data = encrypt(payload, sub["keys"]["p256dh"], sub["keys"]["auth"])
    req = urllib.request.Request(sub["endpoint"], data=data, method="POST", headers={
        "Content-Encoding": "aes128gcm", "Content-Type": "application/octet-stream", "TTL": "86400",
        "Urgency": urgency, "Authorization": vapid_header(sub["endpoint"])})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.status
    except urllib.error.HTTPError as e:
        return e.code


def subscriptions() -> list[dict]:
    return db.q("SELECT * FROM push_subs ORDER BY ts DESC")


def add_subscription(sub: dict, device: str) -> None:
    if not (isinstance(sub, dict) and str(sub.get("endpoint", "")).startswith("https://")
            and sub.get("keys", {}).get("p256dh") and sub.get("keys", {}).get("auth")):
        raise ValueError("abonnement invalide")
    db.x("INSERT OR REPLACE INTO push_subs (endpoint, data, device, ts) VALUES (?,?,?,?)",
         (sub["endpoint"], json.dumps(sub), device[:80], time.time()))


def broadcast(title: str, body: str, url: str = "/", urgency: str = "normal") -> int:
    """Envoie à tous les appareils abonnés ; supprime ceux qui ne sont plus valides. Renvoie le nombre d'envois réussis."""
    ok = 0
    for row in subscriptions():
        try:
            code = send(json.loads(row["data"]), title, body, url, urgency)
        except Exception as e:  # noqa: BLE001
            db.log("système", "erreur", f"notification iPhone : {str(e)[:150]}")
            continue
        if code in (404, 410):
            db.x("DELETE FROM push_subs WHERE endpoint=?", (row["endpoint"],))
        elif 200 <= code < 300:
            ok += 1
        else:
            db.log("système", "erreur", f"notification iPhone refusée (HTTP {code})")
    return ok
