"""Thumbnail renderer — uses Playwright to render the HTML template to an image.

Takes ``thumbnail/index.html`` as the base template and substitutes actual images
and text data at render time. Uses headless Chromium for faithful rendering of
CSS, fonts, SVGs, gradients, and custom typography.

The output is a high-quality ``.webp`` image that matches the reference card
design exactly.
"""

from __future__ import annotations

import html as html_module
from pathlib import Path
from typing import Any

import httpx

from nekofetch.core.logging import get_logger

log = get_logger(__name__)

_TEMPLATE_DIR = Path(__file__).resolve().parents[3] / "thumbnail"
_DEFAULT_TEMPLATE = _TEMPLATE_DIR / "index.html"
_OUTPUT_DIR = Path(__file__).resolve().parents[3] / "data" / "thumbnails"

# The template layout is viewport-relative (poster is 12vw×40vh; panels use
# vw/vh/%), tuned for a wide ~2.13:1 banner — the exact ratio the design was
# authored at. Rendering at any other aspect ratio reflows and crops it, so we
# render at the native ratio and scale ×2 for a crisp output.
_THUMBNAIL_WIDTH = 1366
_THUMBNAIL_HEIGHT = 641
_SYNOPSIS_MAX_CHARS = 230

# Genre pill styling, verbatim from the template, so code-generated pills match.
_PILL_CLS = ("border border-white/30 bg-black/10 px-[1.1rem] py-1.5 rounded-full "
             "text-md font-medium tracking-wider text-zinc-100 backdrop-blur-xs")
# The SVG ring's stroke-dasharray (2·π·42 ≈ 263.89); offset encodes the percent.
_RING_CIRCUMFERENCE = 263.89


def _truncate(text: str, max_chars: int = _SYNOPSIS_MAX_CHARS) -> str:
    """Truncate text and append ``...`` if too long."""
    text = text.strip()
    if len(text) <= max_chars:
        return text
    return text[:max_chars - 3].rstrip() + "..."


def _fmt_runtime(minutes: int | None) -> str:
    """Minutes → '2h 1m' / '1h' / '24m' (empty when unknown)."""
    if not minutes or minutes <= 0:
        return ""
    h, m = divmod(int(minutes), 60)
    if h and m:
        return f"{h}h {m}m"
    return f"{h}h" if h else f"{m}m"


async def _download_image(url: str, dest: Path) -> Path | None:
    try:
        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as cli:
            resp = await cli.get(url)
            resp.raise_for_status()
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(resp.content)
            return dest
    except Exception as exc:
        log.warning("thumbnail.download.failed", url=url[:80], error=str(exc))
        return None


_HTML_TEMPLATE: str | None = None


def _load_template() -> str:
    global _HTML_TEMPLATE
    if _HTML_TEMPLATE is None:
        if _DEFAULT_TEMPLATE.exists():
            _HTML_TEMPLATE = _DEFAULT_TEMPLATE.read_text(encoding="utf-8")
        else:
            log.warning("thumbnail.template.not_found", path=str(_DEFAULT_TEMPLATE))
            _HTML_TEMPLATE = "<html><body><h1>No template</h1></body></html>"
    return _HTML_TEMPLATE


class ThumbnailRenderService:
    """Renders the HTML template to a thumbnail image using Playwright."""

    def __init__(self) -> None:
        self._playwright: Any = None
        self._browser: Any = None
        self._init_done = False

    async def _ensure_browser(self) -> Any:
        if self._init_done and self._browser:
            return self._browser
        try:
            import playwright.async_api as pw
            self._playwright = await pw.async_playwright().start()
            self._browser = await self._playwright.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-setuid-sandbox",
                       "--disable-dev-shm-usage", "--disable-gpu"],
            )
            self._init_done = True
            log.info("thumbnail.playwright.started")
            return self._browser
        except ImportError:
            log.warning("thumbnail.playwright.not_installed")
            raise
        except Exception as exc:
            log.warning("thumbnail.playwright.launch_failed", error=str(exc))
            raise

    async def close(self) -> None:
        if self._browser:
            await self._browser.close()
            self._browser = None
        if self._playwright:
            await self._playwright.stop()
            self._playwright = None
        self._init_done = False
        log.info("thumbnail.playwright.stopped")

    async def render_thumbnail(
        self,
        *,
        title: str,
        native_title: str = "",
        romaji: str = "",
        synopsis: str = "",
        year: str | int | None = None,
        cert: str = "",
        runtime_minutes: int | None = None,
        language: str = "",
        genres: list[str] | None = None,
        director: str = "",
        imdb: float | str | None = None,
        anilist_pct: int | None = None,
        brand: str = "AniMovie Weebs",
        logo_url: str | None = None,
        poster_url: str | None = None,
        bg_url: str | None = None,
        entry_label: str = "",          # deprecated/back-compat; no longer used
        output_dir: str | Path | None = None,
    ) -> Path | None:
        """Fill the template's ``{{tokens}}`` with real data and render to WebP.

        Returns the output path, or ``None`` on failure.
        """
        esc = html_module.escape
        genres = genres or []

        work_dir = Path(output_dir or _OUTPUT_DIR)
        work_dir.mkdir(parents=True, exist_ok=True)
        safe_name = "".join(c if c.isalnum() or c in " -_" else "_" for c in title)[:40]
        images_dir = work_dir / f"assets_{safe_name}"
        images_dir.mkdir(parents=True, exist_ok=True)

        # Download art; when a URL is missing/fails, fall back to the bundled
        # template asset so a card never renders with a broken image (the html
        # lives in images_dir, so defaults are copied in next to it).
        import shutil

        def _with_default(local: Path | None, asset: str) -> Path | None:
            if local is not None:
                return local
            src = _TEMPLATE_DIR / asset
            if src.exists():
                dest = images_dir / asset
                shutil.copyfile(src, dest)
                return dest
            return None

        bg_local = await _download_image(bg_url, images_dir / "background.webp") if bg_url else None
        logo_local = await _download_image(logo_url, images_dir / "logo.png") if logo_url else None
        poster_local = await _download_image(poster_url, images_dir / "poster.webp") if poster_url else None
        bg_local = _with_default(bg_local, "background.webp")
        logo_local = _with_default(logo_local, "logo.png")
        poster_local = _with_default(poster_local, "poster.webp")

        html = _load_template()
        # Assets are saved under the html's own dir with the template's names, so
        # the relative refs already resolve; this keeps them correct regardless.
        html = html.replace("background.webp", bg_local.name if bg_local else "background.webp")
        html = html.replace("logo.png", logo_local.name if logo_local else "logo.png")
        html = html.replace("poster.webp", poster_local.name if poster_local else "poster.webp")

        # Build genre pills (verbatim styling) and the Anilist ring offset.
        pills = "\n".join(f'<span class="{_PILL_CLS}">{esc(g)}</span>'
                          for g in genres[:4]) or f'<span class="{_PILL_CLS}">Anime</span>'
        pct = max(0, min(100, int(anilist_pct))) if anilist_pct is not None else 0
        dash = round(_RING_CIRCUMFERENCE * (1 - pct / 100), 2)
        imdb_txt = (f"{imdb:.1f}" if isinstance(imdb, (int, float))
                    else esc(str(imdb))) if imdb not in (None, "") else "—"

        tokens = {
            "{{BRAND}}": esc(brand or "AniMovie Weebs"),
            "{{TITLE}}": esc(title),
            "{{TITLE_NATIVE}}": esc(native_title or title),
            "{{TITLE_ROMAJI}}": f"({esc(romaji)})" if romaji else "",
            "{{YEAR}}": esc(str(year)) if year else "—",
            "{{CERT}}": esc(cert) if cert else "NR",
            "{{RUNTIME}}": esc(_fmt_runtime(runtime_minutes)) or "—",
            "{{LANGUAGE}}": esc(language) if language else "Japanese",
            "{{SYNOPSIS}}": esc(_truncate(synopsis)) if synopsis else "",
            "{{GENRE_PILLS}}": pills,
            "{{DIRECTOR}}": esc(director) if director else "—",
            "{{IMDB}}": imdb_txt,
            "{{ANILIST_PCT}}": str(pct),
            "{{ANILIST_DASH}}": str(dash),
        }
        for k, v in tokens.items():
            html = html.replace(k, v)
        html = html.replace("Suzume Movie Presentation Layout", esc(title))  # <title>

        output_html = images_dir / "thumbnail.html"
        output_html.write_text(html, encoding="utf-8")

        browser = await self._ensure_browser()
        context = page = None
        try:
            context = await browser.new_context(
                viewport={"width": _THUMBNAIL_WIDTH, "height": _THUMBNAIL_HEIGHT},
                device_scale_factor=2,
            )
            page = await context.new_page()
            page.set_default_timeout(30000)
            file_url = output_html.absolute().as_uri()
            # 'domcontentloaded' returns fast; the explicit Tailwind + fonts waits
            # below gate the screenshot. ('load'/'networkidle' can block for the
            # full timeout waiting on slow CDN font/script requests.)
            await page.goto(file_url, wait_until="domcontentloaded")
            # The Tailwind v4 browser build compiles classes AFTER load; wait until
            # it has actually applied (body's `flex` class → computed display:flex)
            # so we never screenshot a half-styled page, then wait for the webfonts
            # (Cinzel/Inter) so the title isn't rendered in a fallback face.
            try:
                await page.wait_for_function(
                    "() => getComputedStyle(document.body).display === 'flex'",
                    timeout=15000,
                )
            except Exception:
                pass
            try:
                await page.evaluate("async () => { await document.fonts.ready; }")
            except Exception:
                pass
            await page.wait_for_timeout(1200)

            output_path = work_dir / f"thumb_{safe_name}.webp"
            # Playwright's screenshot only emits png|jpeg; grab lossless PNG and
            # transcode to the .webp the rest of the pipeline expects.
            png_bytes = await page.screenshot(type="png", full_page=False)
            from io import BytesIO

            from PIL import Image

            with Image.open(BytesIO(png_bytes)) as im:
                im.save(output_path, format="WEBP", quality=92, method=6)
            log.info("thumbnail.rendered", path=str(output_path), title=title)
            return output_path
        except Exception as exc:
            log.warning("thumbnail.render.failed", title=title, error=str(exc))
            return None
        finally:
            if page:
                await page.close()
            if context:
                await context.close()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        await self.close()
