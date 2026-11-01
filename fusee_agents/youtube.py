"""Accès YouTube pour apprendre et faire de la veille : recherche, statistiques, transcription des vidéos.

Fonctionne sans clé (yt-dlp + youtube-transcript-api). La publication de vidéos reste faite par Patron
(calendrier de contenus) : pas de compte YouTube piloté par les agents."""
import re
from datetime import datetime

_ID = re.compile(r"(?:v=|youtu\.be/|shorts/|embed/|live/)([A-Za-z0-9_-]{11})")


def video_id(url_or_id: str) -> str:
    s = url_or_id.strip()
    if re.fullmatch(r"[A-Za-z0-9_-]{11}", s):
        return s
    m = _ID.search(s)
    if not m:
        raise ValueError("lien YouTube invalide")
    return m.group(1)


def _ydl(opts: dict):
    import yt_dlp
    return yt_dlp.YoutubeDL({"quiet": True, "no_warnings": True, "skip_download": True, **opts})


def search(query: str, limit: int = 10, sort: str = "pertinence") -> list[dict]:
    """Recherche de vidéos (titre, chaîne, vues, durée, lien). sort : pertinence | récentes."""
    limit = max(1, min(limit, 20))
    prefix = "ytsearchdate" if sort == "récentes" else "ytsearch"
    with _ydl({"extract_flat": True}) as ydl:
        info = ydl.extract_info(f"{prefix}{limit}:{query}", download=False)
    out = []
    for e in info.get("entries") or []:
        if not e:
            continue
        vid = e.get("id", "")
        out.append({"titre": e.get("title", ""), "chaine": e.get("channel") or e.get("uploader") or "",
                    "vues": e.get("view_count"), "duree_s": e.get("duration"),
                    "short": "/shorts/" in (e.get("url") or "") or (e.get("duration") or 999) <= 60,
                    "lien": f"https://www.youtube.com/watch?v={vid}"})
    return out


def transcript(vid: str, max_chars: int = 15000) -> tuple[str, str]:
    """Transcription (français, sinon anglais, sinon la première disponible). Renvoie (langue, texte)."""
    from youtube_transcript_api import YouTubeTranscriptApi
    api = YouTubeTranscriptApi()
    try:
        fetched = api.fetch(vid, languages=["fr", "en"])
    except Exception:  # noqa: BLE001 — autre langue disponible ?
        tl = next(iter(api.list(vid)))
        fetched = tl.fetch()
    text = " ".join(s.text.replace("\n", " ") for s in fetched.snippets)
    return fetched.language_code, (text[:max_chars] + " …[tronqué]") if len(text) > max_chars else text


def video(url_or_id: str, with_transcript: bool = True) -> dict:
    """Détails d'une vidéo (statistiques, description, tags) + transcription pour l'étudier."""
    vid = video_id(url_or_id)
    with _ydl({}) as ydl:
        i = ydl.extract_info(f"https://www.youtube.com/watch?v={vid}", download=False)
    views, likes = i.get("view_count") or 0, i.get("like_count") or 0
    up = i.get("upload_date") or ""
    days = (datetime.now() - datetime.strptime(up, "%Y%m%d")).days if up else None
    out = {
        "titre": i.get("title", ""), "chaine": i.get("channel", ""), "abonnes_chaine": i.get("channel_follower_count"),
        "vues": views, "likes": likes, "commentaires": i.get("comment_count"),
        "taux_like_pct": round(100 * likes / views, 2) if views else None,
        "vues_par_jour": round(views / max(days, 1)) if days is not None else None,
        "publiee_le": f"{up[6:8]}/{up[4:6]}/{up[:4]}" if up else "", "duree_s": i.get("duration"),
        "tags": (i.get("tags") or [])[:20], "description": (i.get("description") or "")[:1500],
        "lien": f"https://www.youtube.com/watch?v={vid}",
    }
    if with_transcript:
        try:
            out["langue_transcription"], out["transcription"] = transcript(vid)
        except Exception as e:  # noqa: BLE001
            out["transcription"] = f"(pas de transcription disponible : {str(e)[:120]})"
    return out
