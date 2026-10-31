"""Navigateur des agents (Playwright/Chromium) : captures d'écran, navigation, vidéos."""
import asyncio
import base64
import os
import re
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

from .config import WORKSPACE

_pw = None
_browser = None
_lock = asyncio.Lock()
CAPTURES = WORKSPACE / "captures"

FORMATS = {"vertical": (1080, 1920), "horizontal": (1920, 1080), "carré": (1080, 1080)}


async def _get_browser():
    global _pw, _browser
    async with _lock:
        if _browser is None or not _browser.is_connected():
            from playwright.async_api import async_playwright
            _pw = await async_playwright().start()
            exe = os.getenv("PLAYWRIGHT_CHROMIUM_PATH") or None
            _browser = await _pw.chromium.launch(executable_path=exe)
        return _browser


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
