"""Navigateur des agents (Playwright/Chromium) : captures d'écran, navigation, vidéos."""
import asyncio
import base64
import os
import re
import shutil
import subprocess
import tempfile
import time
import urllib.parse
from pathlib import Path

from .config import WORKSPACE

_pw = None
_browser = None
_loop = None
_lock: asyncio.Lock | None = None
CAPTURES = WORKSPACE / "captures"

FORMATS = {"vertical": (1080, 1920), "horizontal": (1920, 1080), "carré": (1080, 1080)}


async def _get_browser():
    global _pw, _browser, _loop, _lock
    loop = asyncio.get_running_loop()
    if _loop is not loop:  # nouvelle boucle d'événements : l'ancien navigateur n'est plus utilisable
        _pw = _browser = None
        _loop, _lock = loop, asyncio.Lock()
    async with _lock:
        if _browser is None or not _browser.is_connected():
            from playwright.async_api import async_playwright
            _pw = await async_playwright().start()
            exe = os.getenv("PLAYWRIGHT_CHROMIUM_PATH") or None
            _browser = await _pw.chromium.launch(executable_path=exe)
        return _browser


async def _no_tracking(obj) -> None:
    """Les visites du navigateur des agents (captures, audits, vidéos) ne comptent pas dans les statistiques."""
    await obj.route("**/public/t", lambda route: route.fulfill(status=204))


def _target(target: str) -> str:
    """URL web telle quelle ; sinon fichier du workspace (servi en file://)."""
    if re.match(r"^https?://", target):
        return target
    p = (WORKSPACE / target.lstrip("/")).resolve()
    if WORKSPACE.resolve() not in p.parents:
        raise ValueError("chemin hors du workspace")
    if p.is_dir():
        p = p / "index.html"
    if not p.is_file():
        raise ValueError(f"fichier introuvable : {target}")
    return p.as_uri()


def _out(name: str, ext: str) -> Path:
    CAPTURES.mkdir(parents=True, exist_ok=True)
    slug = re.sub(r"[^\w-]+", "-", name).strip("-")[:60] or "capture"
    return CAPTURES / f"{time.strftime('%Y%m%d-%H%M%S')}-{slug}.{ext}"


async def screenshot(target: str, name: str, mobile: bool = False, full_page: bool = True) -> str:
    b = await _get_browser()
    vp = {"width": 390, "height": 844} if mobile else {"width": 1366, "height": 850}
    page = await b.new_page(viewport=vp, device_scale_factor=2 if mobile else 1)
    await _no_tracking(page)
    try:
        await page.goto(_target(target), wait_until="networkidle", timeout=45000)
        await page.wait_for_timeout(800)
        out = _out(name, "png")
        await page.screenshot(path=str(out), full_page=full_page)
        return str(out.relative_to(WORKSPACE))
    finally:
        await page.close()


async def browse(url: str) -> dict:
    """Ouvre une page web (lecture seule) : texte, liens et capture d'écran."""
    if not re.match(r"^https?://", url):
        raise ValueError("URL http(s) attendue")
    b = await _get_browser()
    page = await b.new_page(viewport={"width": 1366, "height": 850})
    await _no_tracking(page)
    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=45000)
        await page.wait_for_timeout(1500)
        text = await page.inner_text("body")
        links = await page.eval_on_selector_all(
            "a[href]", "els => els.slice(0, 60).map(e => (e.innerText.trim().slice(0, 60) + ' -> ' + e.href))")
        out = _out(re.sub(r"^https?://", "", url), "png")
        await page.screenshot(path=str(out))
        return {"title": await page.title(), "url": page.url, "text": text[:15000], "links": links,
                "screenshot": str(out.relative_to(WORKSPACE))}
    finally:
        await page.close()


def _ffmpeg() -> str | None:
    exe = shutil.which("ffmpeg")
    if exe:
        return exe
    try:
        import imageio_ffmpeg  # ffmpeg embarqué, marche aussi sous Windows
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:  # noqa: BLE001
        return None


async def record_video(target: str, name: str, seconds: float, fmt: str) -> str:
    """Filme une page HTML animée (pub, démo…) et renvoie une vidéo MP4.

    Les images sont capturées directement par Chromium (screencast) puis assemblées par ffmpeg."""
    ffmpeg = _ffmpeg()
    if not ffmpeg:
        raise RuntimeError("ffmpeg introuvable (pip install imageio-ffmpeg)")
    w, h = FORMATS.get(fmt, FORMATS["vertical"])
    b = await _get_browser()
    ctx = await b.new_context(viewport={"width": w, "height": h})
    await _no_tracking(ctx)
    page = await ctx.new_page()
    frames: list[tuple[float, bytes]] = []
    try:
        cdp = await ctx.new_cdp_session(page)

        async def on_frame(p):
            frames.append((time.time(), base64.b64decode(p["data"])))
            try:
                await cdp.send("Page.screencastFrameAck", {"sessionId": p["sessionId"]})
            except Exception:  # noqa: BLE001
                pass

        cdp.on("Page.screencastFrame", lambda p: asyncio.ensure_future(on_frame(p)))
        await cdp.send("Page.startScreencast", {"format": "jpeg", "quality": 85, "maxWidth": w, "maxHeight": h})
        await page.goto(_target(target), wait_until="load", timeout=45000)
        start = time.time()
        await page.wait_for_timeout(int(min(seconds, 90) * 1000))
        end = time.time()
        await cdp.send("Page.stopScreencast")
    finally:
        await ctx.close()
    frames = [f for f in frames if f[0] >= start - 0.05] or frames[-1:]
    if not frames:
        raise RuntimeError("aucune image capturée")
    out = _out(name, "mp4")
    with tempfile.TemporaryDirectory() as tmp:
        lines = []
        for i, (ts, data) in enumerate(frames):
            f = Path(tmp) / f"f{i:05d}.jpg"
            f.write_bytes(data)
            nxt = frames[i + 1][0] if i + 1 < len(frames) else end
            lines += [f"file '{f.as_posix()}'", f"duration {max(nxt - max(ts, start), 0.001):.4f}"]
        lines.append(f"file '{(Path(tmp) / f'f{len(frames) - 1:05d}.jpg').as_posix()}'")
        (Path(tmp) / "list.txt").write_text("\n".join(lines))
        proc = await asyncio.to_thread(subprocess.run, [
            ffmpeg, "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(Path(tmp) / "list.txt"),
            "-vf", f"scale={w}:{h}:force_original_aspect_ratio=decrease,pad={w}:{h}:(ow-iw)/2:(oh-ih)/2,fps=30",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(out)],
            capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg : {proc.stderr[-500:]}")
    return str(out.relative_to(WORKSPACE))


# --- audit qualité d'un site ---------------------------------------------------
_AUDIT_JS = """() => {
  const q = s => document.querySelector(s), qa = s => [...document.querySelectorAll(s)];
  const text = (document.body ? document.body.innerText : "").toLowerCase().normalize("NFD").replace(/[\\u0300-\\u036f]/g, "");
  const html = document.documentElement.outerHTML;
  const links = qa("a[href]").map(a => a.getAttribute("href"));
  return {
    title: document.title || "", lang: document.documentElement.lang || "",
    charset: !!q("meta[charset]") || !!q('meta[http-equiv="Content-Type" i]'),
    description: (q('meta[name="description"]') || {}).content || "",
    viewport: !!q('meta[name="viewport"]'), ogTitle: !!q('meta[property="og:title"]'), ogImage: !!q('meta[property="og:image"]'),
    favicon: !!q('link[rel~="icon"]'), h1: qa("h1").length,
    imgNoAlt: qa("img").filter(i => !i.hasAttribute("alt")).length, images: qa("img").length,
    internalLinks: links.filter(h => h && !/^(https?:|mailto:|tel:|#|javascript:)/i.test(h)),
    emptyLinks: links.filter(h => !h || h === "#").length,
    legal: /mentions legales|mentions-legales|cgv|conditions generales/.test(text + " " + links.join(" ").toLowerCase()),
    contact: /\\/public\\/chat\\.js/.test(html) || links.some(h => /^mailto:|^tel:/i.test(h || "")) || !!q("form"),
    buy: links.some(h => /buy\\.stripe\\.com|checkout\\.stripe\\.com/.test(h || "")) || !!q("[data-buy]"),
    price: /\\d\\s?(€|eur)|€\\s?\\d/.test(text),
    analytics: /\\/public\\/(a|chat)\\.js/.test(html),
    words: text.split(/\\s+/).filter(Boolean).length,
    overflow: document.documentElement.scrollWidth > window.innerWidth + 2,
  };
}"""


async def audit(folder: str, base_url: str = "", password: str = "", kind: str = "site") -> dict:
    """Audit d'un site du workspace : chargement, erreurs, mobile, SEO, contact, mentions légales, liens."""
    path = (WORKSPACE / folder.strip("/")).resolve()
    if WORKSPACE.resolve() not in path.parents or not (path / "index.html").is_file():
        raise ValueError("dossier invalide (il faut un index.html dans le workspace)")
    rel = str(path.relative_to(WORKSPACE))
    url = f"{base_url.rstrip('/')}/w/{rel}/" if base_url else (path / "index.html").as_uri()
    b = await _get_browser()
    issues: list[dict] = []
    shots, metrics = {}, {}

    def add(level: str, msg: str) -> None:
        issues.append({"niveau": level, "probleme": msg})

    for device, vp in (("ordi", {"width": 1366, "height": 850}), ("mobile", {"width": 390, "height": 844})):
        ctx = await b.new_context(viewport=vp, is_mobile=device == "mobile",
                                  http_credentials={"username": "fusee", "password": password} if password else None)
        await _no_tracking(ctx)
        page = await ctx.new_page()
        errors, failed = [], []
        page.on("pageerror", lambda e: errors.append(str(e)[:200]))
        page.on("console", lambda m: errors.append(f"{m.text[:200]} @{(m.location or {}).get('url', '')}")
                if m.type == "error" else None)
        page.on("requestfailed", lambda r: failed.append(r.url[:150]))
        page.on("response", lambda r: failed.append(f"{r.status} {r.url[:150]}") if r.status >= 400 else None)
        try:
            t0 = time.time()
            resp = await page.goto(url, wait_until="load", timeout=30000)
            load_ms = int((time.time() - t0) * 1000)
            await page.wait_for_timeout(700)
            if resp is not None and resp.status >= 400:
                add("bloquant", f"la page ne se charge pas (HTTP {resp.status})")
            info = await page.evaluate(_AUDIT_JS)
            out = _out(f"audit-{path.name}-{device}", "png")
            await page.screenshot(path=str(out), full_page=device == "mobile")
            shots[device] = str(out.relative_to(WORKSPACE))
            if device == "ordi":
                metrics = {"temps_chargement_ms": load_ms, "mots": info["words"], "images": info["images"]}
                broken = []
                for href in info["internalLinks"][:40]:
                    target = href.split("#")[0].split("?")[0]
                    if not target:
                        continue
                    if base_url:
                        r = await page.request.get(urllib.parse.urljoin(page.url, target))
                        ok = r.status < 400
                    else:
                        p = (path / target).resolve()
                        ok = p.exists() and (p.is_file() or (p / "index.html").is_file())
                    if not ok:
                        broken.append(href)
                if broken:
                    add("erreur", f"liens internes cassés : {', '.join(broken[:6])}")
                if not info["title"]:
                    add("bloquant", "pas de <title>")
                elif not 10 <= len(info["title"]) <= 70:
                    add("avertissement", f"titre de {len(info['title'])} caractères (idéal 10-70)")
                if not info["description"]:
                    add("erreur", "pas de meta description (référencement Google)")
                if not info["charset"]:
                    add("erreur", "pas de <meta charset=\"utf-8\"> : accents et € peuvent s'afficher en caractères bizarres")
                if not info["lang"]:
                    add("avertissement", "attribut lang manquant sur <html>")
                if not info["viewport"]:
                    add("bloquant", "pas de meta viewport : illisible sur mobile")
                if info["h1"] != 1:
                    add("avertissement", f"{info['h1']} titre(s) <h1> (idéal : 1)")
                if not info["ogTitle"] or not info["ogImage"]:
                    add("avertissement", "balises og:title / og:image manquantes (aperçu des partages)")
                if not info["favicon"]:
                    add("avertissement", "pas de favicon")
                if info["imgNoAlt"]:
                    add("avertissement", f"{info['imgNoAlt']} image(s) sans texte alternatif (alt)")
                if info["emptyLinks"]:
                    add("avertissement", f"{info['emptyLinks']} lien(s) vide(s) ou « # »")
                if not info["contact"]:
                    add("bloquant", "aucun moyen de contact (widget de chat, e-mail ou formulaire)")
                if not info["legal"]:
                    add("bloquant" if kind == "site" else "avertissement", "pas de mentions légales / CGV")
                if info["buy"] and not info["price"]:
                    add("erreur", "bouton d'achat sans prix affiché")
                if not info["analytics"]:
                    add("avertissement", "pas de statistiques (script /public/a.js ou widget de chat)")
                if info["words"] < 60:
                    add("avertissement", f"très peu de texte ({info['words']} mots) : difficile à convaincre et à référencer")
                if load_ms > 4000:
                    add("erreur", f"chargement lent ({load_ms} ms)")
            elif info["overflow"]:
                add("bloquant", "la page déborde horizontalement sur mobile (défilement de côté)")
        except Exception as e:  # noqa: BLE001
            add("bloquant", f"chargement impossible sur {device} : {str(e)[:200]}")
        finally:
            await ctx.close()
        real_errors = [e.split(" @")[0] for e in errors if "/public/" not in e and "favicon" not in e]
        real_failed = [f for f in failed if "/public/" not in f and "favicon" not in f]
        if real_errors:
            add("bloquant", f"erreurs JavaScript ({device}) : {' | '.join(dict.fromkeys(real_errors))[:300]}")
        if real_failed:
            add("erreur", f"ressources introuvables ({device}) : {', '.join(dict.fromkeys(real_failed))[:300]}")

    weight = sum(f.stat().st_size for f in path.rglob("*") if f.is_file() and f.suffix not in (".mp4", ".webm"))
    metrics["poids_ko"] = round(weight / 1024)
    if weight > 3 * 1024 * 1024:
        add("erreur", f"site lourd ({weight // 1024} Ko) : compresse les images")
    penalty = {"bloquant": 20, "erreur": 10, "avertissement": 3}
    score = max(0, 100 - sum(penalty[i["niveau"]] for i in issues))
    blocking = [i for i in issues if i["niveau"] == "bloquant"]
    return {"site": rel, "score": score, "ok_pour_publier": score >= 70 and not blocking,
            "problemes": issues, "mesures": metrics, "captures": shots}


async def render_html(html: str, width: int, height: int, out: Path) -> None:
    """Rend un bout de HTML en image PNG (ex. image d'aperçu pour les partages sur les réseaux)."""
    b = await _get_browser()
    page = await b.new_page(viewport={"width": width, "height": height})
    try:
        await page.set_content(html, wait_until="load")
        await page.screenshot(path=str(out))
    finally:
        await page.close()


TEST_ACTIONS = ("click", "fill", "press", "wait", "expect_text", "expect_visible", "expect_title")


async def run_test(target: str, steps: list[dict], mobile: bool = False) -> dict:
    """Test automatique d'un site, d'une appli ou d'un jeu : rejoue des actions et vérifie le résultat."""
    b = await _get_browser()
    ctx = await b.new_context(viewport={"width": 390, "height": 844} if mobile else {"width": 1366, "height": 850},
                              is_mobile=mobile, has_touch=mobile)
    await _no_tracking(ctx)
    page = await ctx.new_page()
    errors: list[str] = []
    page.on("pageerror", lambda e: errors.append(str(e)[:200]))
    page.on("console", lambda m: errors.append(m.text[:200]) if m.type == "error" and "/public/" not in
            str((m.location or {}).get("url", "")) else None)
    results, ok = [], True
    try:
        await page.goto(_target(target), wait_until="load", timeout=30000)
        for i, st in enumerate(steps[:40], 1):
            action, sel, val = st.get("action"), st.get("selector", ""), st.get("value", "")
            try:
                if action == "click":
                    await page.click(sel, timeout=5000)
                elif action == "fill":
                    await page.fill(sel, val, timeout=5000)
                elif action == "press":
                    await (page.press(sel, val, timeout=5000) if sel else page.keyboard.press(val))
                elif action == "wait":
                    await page.wait_for_timeout(min(int(float(val or 500)), 10000))
                elif action == "expect_text":
                    scope = page.locator(sel) if sel else page.locator("body")
                    txt = await scope.first.inner_text(timeout=5000)
                    if val.lower() not in txt.lower():
                        raise AssertionError(f"texte « {val} » absent (trouvé : « {txt[:120]} »)")
                elif action == "expect_visible":
                    await page.wait_for_selector(sel, state="visible", timeout=5000)
                elif action == "expect_title":
                    title = await page.title()
                    if val.lower() not in title.lower():
                        raise AssertionError(f"titre « {title} »")
                else:
                    raise ValueError(f"action inconnue {action}")
                results.append({"etape": i, "action": action, "ok": True})
            except Exception as e:  # noqa: BLE001
                ok = False
                results.append({"etape": i, "action": action, "ok": False, "erreur": str(e).split("\n")[0][:200]})
                break
        out = _out("test-" + Path(target).name, "png")
        await page.screenshot(path=str(out))
    finally:
        await ctx.close()
    if errors:
        ok = False
    return {"reussi": ok, "etapes": results, "erreurs_javascript": list(dict.fromkeys(errors))[:10],
            "capture": str(out.relative_to(WORKSPACE))}
