"""AniZone source — search, browse, and download from anizone.to.

Uses Laravel Livewire's component-update protocol (POST ``/livewire/update``)
for all dynamic data — search results, episode lists, and video server switching.
The initial CSRF token and component snapshot are extracted from the server-rendered
HTML, then the session is driven entirely through Livewire calls, exactly like the
browser does.

Video servers are revealed by calling ``setVideo(id)`` on the Livewire component,
which swaps the ``<media-player src="…">`` to a different HLS stream. Each server's
master playlist is then probed for available resolutions, and every (server × quality)
combination is emitted as a ``VideoVariant`` for the shared HLS download engine.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup
from curl_cffi import requests as cf_requests

from nekofetch.core.logging import get_logger
from nekofetch.domain.enums import AudioType
from nekofetch.sources._hls import (
    RECOMMENDED_LIMITS,
    RECOMMENDED_TIMEOUT,
    download_hls_ts,
    download_subtitles,
    find_ffmpeg,
    list_master_qualities,
    maybe_remux,
)
from nekofetch.sources._mux import (
    WANTED_AUDIO,
    assemble_final,
    audio_label,
    normalize_audio_lang,
)
from nekofetch.sources.base import (
    AnimeDetails,
    AnimeSource,
    AnimeStub,
    Episode,
    ProgressCallback,
    SourceCoverage,
    VideoVariant,
)

log = get_logger(__name__)

BASE_URL = "https://anizone.to"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/141.0.0.0 Safari/537.36"
)

# Regex to extract the numeric server ID from a Livewire button.
_SETVIDEO_RE = re.compile(r"setVideo\('(\d+)'\)")

# Episode selector for the episode list.
_EPISODE_SELECTOR = "ul > li"


class AnizoneSource(AnimeSource):
    name = "anizone"

    def __init__(
        self,
        base_url: str = BASE_URL,
        preferred_quality: str = "1080",
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.preferred_quality = preferred_quality
        self._http: httpx.AsyncClient | None = None
        self._cf: cf_requests.AsyncSession | None = None

        # Livewire session state: CSRF token + per-purpose snapshots.
        self._token: str = ""
        self._snapshots: dict[str, str] = {
            "anime": "",    # anime listing / search
            "episode": "",  # episode list for a specific anime
            "video": "",    # video server switching
        }
        self._load_count: int = 0

    @property
    def http(self) -> httpx.AsyncClient:
        if self._http is None:
            self._http = httpx.AsyncClient(
                timeout=RECOMMENDED_TIMEOUT,
                limits=RECOMMENDED_LIMITS,
                headers={
                    "User-Agent": USER_AGENT,
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                    "Accept-Language": "en-US,en;q=0.9",
                },
                follow_redirects=True,
            )
        return self._http

    @property
    def cf(self) -> cf_requests.AsyncSession:
        """curl_cffi client that impersonates Chrome's TLS fingerprint.

        Standard httpx clients are blocked by Cloudflare WAF because Python's TLS
        library exposes a detectable fingerprint.  curl_cffi wraps libcurl with
        browser-impersonation patches so the TLS handshake looks like a real
        browser (Chrome 131 as of mid-2025)."""
        if self._cf is None:
            self._cf = cf_requests.AsyncSession(
                impersonate="chrome",
                timeout=60.0,
                allow_redirects=True,
                headers={
                    "User-Agent": USER_AGENT,
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                    "Accept-Language": "en-US,en;q=0.9",
                },
            )
        return self._cf

    async def close(self) -> None:
        if self._http is not None:
            await self._http.aclose()
            self._http = None
        if self._cf is not None:
            # curl_cffi's AsyncSession.close() is an ASYNC coroutine in 0.15+
            # (not httpx's sync `.aclose()` from earlier docs). Must await it
            # — otherwise the runtime emits "coroutine was never awaited".
            try:
                await self._cf.close()
            except Exception:  # noqa: BLE001 - best-effort teardown
                pass
            self._cf = None

    # ------------------------------------------------------------------ #
    # Livewire helpers
    # ------------------------------------------------------------------ #

    async def _ensure_session(self, path: str, *, snapshot_key: str = "anime") -> BeautifulSoup | None:
        """GET ``path`` to initialise the CSRF token, component snapshot, and
        return the parsed HTML for immediate use.

        Called once at the start of any interaction flow (search, episodes,
        video). On subsequent Livewire calls the token and snapshot from
        the previous response are reused.
        """
        if self._token and self._snapshots.get(snapshot_key):
            return None
        resp = await self.cf.get(f"{self.base_url}{path}")
        resp.raise_for_status()
        text = resp.text

        # CSRF token from <script data-csrf="...">
        csrf = re.search(r'data-csrf="([^"]+)"', text)
        if csrf:
            self._token = csrf.group(1)
        else:
            log.warning("anizone.csrf.not_found", path=path)

        # Component snapshot from <main> <div wire:snapshot="...">
        snap = re.search(
            r'<main[^>]*>.*?<div[^>]*wire:snapshot="([^"]+)"',
            text, re.DOTALL,
        )
        if snap:
            self._snapshots[snapshot_key] = snap.group(1).replace("&quot;", '"')
        else:
            log.warning("anizone.snapshot.not_found", path=path)

        return BeautifulSoup(text, "html.parser")

    def _set_snapshot(self, snapshot_key: str, raw: str) -> None:
        """Store a snapshot after unescaping the response format."""
        # The server returns snapshots with \'\"' (escaped quotes in JSON
        # string values) that need to be unescaped before the next call.
        self._snapshots[snapshot_key] = raw.replace('\\"', '"')

    def _extract_html(self, raw: str) -> str:
        """Extract and clean Livewire effects HTML from the response.

        The server returns HTML with \'\"' (escaped quotes) and \\n (escaped
        newlines) that need to be cleaned before BeautifulSoup parsing.
        """
        return raw.replace('\\"', '"').replace("\\n", "\n")

    async def _livewire_call(
        self,
        snapshot_key: str,
        updates: dict | None = None,
        calls: list[dict] | None = None,
        path: str = "/anime",
    ) -> tuple[str, dict]:
        """POST to ``/livewire/update`` and return ``(html, new_snapshot)``.

        ``updates`` are property changes (e.g. ``{"search": "naruto"}``).
        ``calls`` are method invocations (e.g. ``{"method": "loadMore", "params": []}``).
        ``path`` is the URL path used for the initial session GET (only used if
        the session hasn't been initialised yet).
        """
        await self._ensure_session(path, snapshot_key=snapshot_key)

        body = {
            "_token": self._token,
            "components": [
                {
                    "calls": calls or [],
                    "snapshot": self._snapshots.get(snapshot_key, ""),
                    "updates": updates or {},
                }
            ],
        }

        lw_headers = {
            "User-Agent": USER_AGENT,
            "Content-Type": "application/json",
            "X-Livewire": "",
            "X-Requested-With": "XMLHttpRequest",
            "Accept": "application/json",
            "Referer": f"{self.base_url}{path}",
        }

        try:
            resp = await self.cf.post(
                f"{self.base_url}/livewire/update",
                headers=lw_headers,
                json=body,
            )
            resp.raise_for_status()
            data = resp.json()
        except (httpx.HTTPError, cf_requests.errors.RequestsError, json.JSONDecodeError, KeyError, IndexError) as exc:
            log.warning("anizone.livewire.failed", path=path, error=str(exc))
            return "", {}

        components = data.get("components", [])
        if not components:
            return "", {}

        comp = components[0]
        new_snapshot = comp.get("snapshot", "")
        if new_snapshot:
            self._set_snapshot(snapshot_key, new_snapshot)

        raw_html = comp.get("effects", {}).get("html", "")
        html = self._extract_html(raw_html)
        return html, comp

    # ------------------------------------------------------------------ #
    # Search
    # ------------------------------------------------------------------ #

    async def search(self, query: str) -> list[AnimeStub]:
        slug_match = re.match(r"slug:(.+)", query)
        if slug_match:
            slug = slug_match.group(1)
            stub = await self._search_by_slug(slug)
            return [stub] if stub else []

        self._load_count = 0
        self._snapshots["anime"] = ""
        html, _ = await self._livewire_call(
            "anime",
            updates={"search": query, "sort": "title-asc"},
            path="/anime",
        )
        if not html:
            return []
        soup = BeautifulSoup(html, "html.parser")
        results = self._parse_anime_grid(soup)
        return _rank_by_title(query, results)

    def _parse_anime_grid(self, soup: BeautifulSoup) -> list[AnimeStub]:
        """Parse anime cards from the grid.

        anizone.to renders titles client-side via Alpine.js (``x-data`` with
        ``anmTitles: JSON.parse(…)``) so ``get_text()`` on the link element
        returns an empty string. Instead we parse the title from the JSON blob
        inside the ``x-data`` attribute on each card's root ``<div>``.
        """
        results: list[AnimeStub] = []
        seen: set[str] = set()
        for item in soup.select("div.grid > div"):
            # Extract slug from the link's href.
            link = item.select_one("a[href*='/anime/']")
            if not link:
                continue
            href = link.get("href", "")
            m = re.search(r"/anime/([^/]+)", href)
            slug = m.group(1) if m else ""
            if not slug or slug in seen:
                continue
            seen.add(slug)

            # Extract title from Alpine.js x-data anmTitles JSON.
            title = self._extract_title_from_xdata(item)
            if not title:
                # Fallback: img alt (also Alpine-set, but check just in case)
                img = item.select_one("img")
                title = img.get("alt", "") if img else ""

            poster = None
            img = item.select_one("img")
            if img:
                poster = img.get("src")

            results.append(
                AnimeStub(
                    source_ref=slug,
                    title=str(title).strip(),
                    poster_url=_fix_url(poster) if poster else None,
                )
            )
        return results

    _XDATA_TITLE_RE = re.compile(r"JSON\.parse\s*\(\s*'([^']+)'\s*\)")
    _TITLE_KEY_PRIORITY = ["1", "5", "8", "2", "3"]

    def _extract_title_from_xdata(self, card: BeautifulSoup) -> str:
        """Extract the anime title from the Alpine.js ``x-data`` attribute.

        The card's root div has an ``x-data`` attribute containing:
        ::  anmTitles: JSON.parse('{"5":"English Title","8":"Romaji Title"}')

        We decode the JS Unicode escapes (``\\u0022`` → ``"``), parse the JSON,
        and return the first available title from our priority key list.
        """
        x_data = card.get("x-data", "")
        if not x_data:
            return ""
        m = self._XDATA_TITLE_RE.search(x_data.replace("\\n", "").replace("\\t", ""))
        if not m:
            return ""
        raw = m.group(1)
        # Decode JS Unicode escapes: \u0022 → "
        raw = re.sub(r"\\u0022", '"', raw)
        # Also decode \u0027 → '
        raw = re.sub(r"\\u0027", "'", raw)
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return ""
        if not isinstance(data, dict):
            return ""
        # Try priority keys first, then any key
        for key in self._TITLE_KEY_PRIORITY:
            val = data.get(key, "")
            if val:
                # Strip any extra surrounding quotes from the value
                val = val.strip('"')
                return val
        # Fallback: first non-empty value
        for val in data.values():
            if val:
                return val.strip('"')
        return ""

    # Make _search_by_slug also use the same extraction for consistency
    async def _search_by_slug(self, slug: str) -> AnimeStub | None:
        """Fetch a single anime's page by slug and return a stub."""
        url = f"{self.base_url}/anime/{slug}"
        try:
            resp = await self.cf.get(url)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "html.parser")
            title_el = soup.select_one("h1")
            # H1 might also be Alpine-rendered; check its text
            title = ""
            if title_el:
                title = title_el.get_text(strip=True)
            if not title:
                # Try Alpine x-data on the page for title
                main = soup.find("main")
                if main:
                    alpine_div = main.find("div", attrs={"x-data": lambda v: v and "anmTitles" in v if v else False})
                    if alpine_div:
                        title = self._extract_title_from_xdata(alpine_div)
            if not title:
                title = slug
            img = soup.select_one("div.flex.items-start img")
            poster = img.get("src") if img else None
            return AnimeStub(
                source_ref=slug,
                title=title,
                poster_url=_fix_url(poster) if poster else None,
            )
        except (httpx.HTTPError, cf_requests.errors.RequestsError):
            return None

    # ------------------------------------------------------------------ #
    # Details
    # ------------------------------------------------------------------ #

    async def get_details(self, source_ref: str) -> AnimeDetails:
        slug = source_ref.strip("/")
        url = f"{self.base_url}/anime/{slug}"
        resp = await self.cf.get(url)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        # Extract from the info layout: div.flex.items-start > div:nth-child(2)
        title_el = soup.select_one("h1")
        title = title_el.get_text(strip=True) if title_el else slug

        # Synopsis from the section after the <h3>Synopsis</h3> heading
        synopsis = None
        synopsis_h3 = soup.find("h3", string=lambda t: t and "Synopsis" in t)
        if synopsis_h3:
            synopsis_div = synopsis_h3.find_next("div")
            if synopsis_div:
                synopsis = synopsis_div.get_text(strip=True)

        # Genres from links in the info div
        genres: list[str] = []
        for g in soup.select("div.flex.items-start > div a[href*='/anime?']"):
            t = g.get_text(strip=True)
            if t and t not in genres:
                genres.append(t)

        # Status
        status = soup.select_one("span.flex")
        status_text = status.get_text(strip=True).lower() if status else ""

        img = soup.select_one("div.flex.items-start img")
        poster = img.get("src") if img else None

        return AnimeDetails(
            source_ref=slug,
            title=title,
            synopsis=synopsis,
            genres=genres,
            poster_url=_fix_url(poster) if poster else None,
            season_count=1,
        )

    # ------------------------------------------------------------------ #
    # Episodes
    # ------------------------------------------------------------------ #

    async def get_episodes(
        self, source_ref: str, *, ep_type: str | None = None,
    ) -> list[Episode]:
        slug = source_ref.strip("/")
        # Strip accidental /anime/ prefix — slugs come from various sources
        # (admin pastes full URLs, etc.) and may already contain the path prefix.
        slug = re.sub(r'^anime/', '', slug)
        path = f"/anime/{slug}"

        # Map friendly names to AniZone numeric type values.
        # 0 = all, 1 = regular episodes only, 2 = specials/OVAs.
        _TYPE_MAP = {None: "0", "all": "0", "regular": "1", "episode": "1", "special": "2", "ova": "2"}
        type_val = _TYPE_MAP.get(ep_type, "0")

        # Reset episode snapshot and fetch first page.
        self._snapshots["episode"] = ""
        html, _ = await self._livewire_call(
            "episode",
            updates={"sort": "release-desc", "type": type_val},
            path=path,
        )

        episodes: list[Episode] = []
        if html:
            soup = BeautifulSoup(html, "html.parser")
            episodes = self._parse_episodes(soup)
            self._load_count = len(episodes)

            # Paginate: keep calling loadMore until no more episodes.
            while True:
                if not self._has_more(soup):
                    break
                more_html, _ = await self._livewire_call(
                    "episode",
                    updates={},
                    calls=[{"path": "", "method": "loadMore", "params": []}],
                    path=path,
                )
                if not more_html:
                    break
                soup = BeautifulSoup(more_html, "html.parser")
                more_eps = self._parse_episodes(soup)
                # Skip already-loaded episodes (they repeat in subsequent pages)
                new_eps = more_eps[self._load_count:]
                if not new_eps:
                    break
                episodes.extend(new_eps)
                self._load_count = len(episodes)

        return episodes

    def _has_more(self, soup: BeautifulSoup) -> bool:
        """Check if a ``x-intersect~=loadMore`` element exists for pagination."""
        return bool(soup.select_one("[x-intersect~=loadMore]"))

    def _parse_episodes(self, soup: BeautifulSoup) -> list[Episode]:
        """Parse episode list items from ``ul > li`` elements."""
        result: list[Episode] = []
        seen: set[str] = set()
        for item in soup.select(_EPISODE_SELECTOR):
            link = item.select_one("a[href]")
            if not link:
                continue
            href = link.get("href", "")
            if not href or href in seen:
                continue
            seen.add(href)

            # Extract episode number from URL: /anime/{slug}/{number}
            ep_num = 0
            m = re.search(r"/anime/[^/]+/(\d+)", href)
            if m:
                ep_num = int(m.group(1))

            title_el = item.select_one("h3")
            name = title_el.get_text(strip=True) if title_el else f"Ep. {ep_num}"

            # Date from the second span in a flex-row
            date_str = None
            date_spans = item.select("div.flex-row > span")
            if len(date_spans) >= 2:
                date_str = date_spans[1].get_text(strip=True)

            result.append(
                Episode(
                    source_ref=href,
                    season=1,
                    number=ep_num,
                    title=name,
                )
            )
        return result

    # ------------------------------------------------------------------ #
    # Video variants (extract ALL servers' m3u8 URLs)
    # ------------------------------------------------------------------ #

    async def get_variants(self, episode_ref: str) -> list[VideoVariant]:
        """Fetch all available video servers and probe their qualities.

        The flow:
          1. GET the episode page to get the default server's m3u8 URL and
             identify all available server buttons (``wire:click="setVideo(N)"``).
          2. For each additional server, POST a ``setVideo(id)`` Livewire call
             to switch servers and read the new m3u8 URL.
          3. For each server's m3u8, probe the master playlist for qualities.
          4. Emit one ``VideoVariant`` per (server × quality) combination.
        """
        # Normalise to a relative path: strip scheme+host if present.
        parsed = urlparse(episode_ref)
        path = parsed.path if parsed.scheme else episode_ref
        if not path.startswith("/"):
            path = f"/{path}"
        slug = path.strip("/")

        # GET the episode page for initial state and parse it.
        self._snapshots["video"] = ""
        soup = await self._ensure_session(path, snapshot_key="video")

        # Collect ALL servers: (server_name, m3u8_url, subtitles)
        servers: list[dict] = []

        # First server: from <media-player src="...">
        player_el = soup.select_one("media-player") or soup.select_one("[src*='.m3u8']")
        first_url = player_el.get("src", "") if player_el else ""

        # Subtitle tracks from <track kind="subtitles">
        subtitles = self._extract_subtitles(soup)

        if first_url:
            servers.append({
                "name": "Server",
                "url": first_url,
                "subtitles": subtitles,
            })

        # Find ALL server buttons (wire:click="setVideo(N)")
        # Note: CSS selectors with colons in attribute names (wire:click) are
        # not supported by Soup Sieve's CSS parser, so we use iteration + filter.
        server_buttons = [
            btn for btn in soup.find_all("button")
            if btn.get("wire:click", "") and "setVideo" in btn["wire:click"]
        ]

        for i, btn in enumerate(server_buttons):
            name = btn.get_text(strip=True) or "Server"
            click_attr = btn.get("wire:click", "")
            m = _SETVIDEO_RE.search(click_attr)
            if not m:
                continue
            video_id = m.group(1)

            # Skip the first server button (index 0) — its video is already
            # captured from the default <media-player src> on the page.
            if i == 0 and first_url:
                continue

            # Livewire call to switch to this server
            html_text, _ = await self._livewire_call(
                "video",
                updates={},
                calls=[{"path": "", "method": "setVideo", "params": [int(video_id)]}],
                path=path,
            )
            if not html_text:
                continue

            srv_soup = BeautifulSoup(html_text, "html.parser")
            srv_player = srv_soup.select_one("media-player")
            srv_src = srv_player.get("src", "") if srv_player else ""
            # Also try direct src attribute
            if not srv_src:
                srv_el = srv_soup.select_one("[src*='.m3u8']")
                srv_src = srv_el.get("src", "") if srv_el else ""
            if not srv_src:
                continue

            srv_subs = self._extract_subtitles(srv_soup)
            servers.append({
                "name": name,
                "url": srv_src,
                "subtitles": srv_subs,
            })

        # Log enumerated servers for debugging.
        log.info(
            "anizone.servers.enumerated", episode=slug,
            count=len(servers),
            names=[s["name"] for s in servers],
            hosts=[_extract_host(s["url"]) for s in servers],
        )

        # Build variants: for each server, probe the master playlist ONCE to
        # discover available qualities AND whether the stream carries separate
        # #EXT-X-MEDIA:TYPE=AUDIO renditions (ja/en).  A dual-audio stream should
        # be reported as DUAL_AUDIO so the download service fetches it once and
        # lets download() handle the audio-track muxing internally, rather than
        # requesting SUB + DUB separately and downloading the same video twice.
        variants: list[VideoVariant] = []
        seen_combos: set[tuple[str, str]] = set()

        for srv in servers:
            url = srv["url"]
            qualities: list[str] = [self.preferred_quality]
            dual = False
            if ".m3u8" in url:
                try:
                    txt = (await self.http.get(
                        url,
                        headers={"referer": f"{self.base_url}/", "origin": self.base_url},
                    )).text
                    # Extract quality heights (same logic as list_master_qualities)
                    if "#EXTM3U" in txt[:64]:
                        heights = {
                            m.group(1)
                            for ln in txt.splitlines() if ln.startswith("#EXT-X-STREAM-INF")
                            for m in [re.search(r"RESOLUTION=\d+x(\d+)", ln)] if m
                        }
                        if heights:
                            qualities = sorted(heights, key=int, reverse=True)
                    # Count audio renditions
                    dual = sum(
                        1 for ln in txt.splitlines()
                        if ln.startswith("#EXT-X-MEDIA:TYPE=AUDIO")
                    ) >= 2
                except Exception:
                    pass  # fall back to preferred_quality + SUBBED
            audio_type = AudioType.DUAL_AUDIO if dual else AudioType.SUBBED
            for q in qualities:
                combo = (srv["name"], q)
                if combo in seen_combos:
                    continue
                seen_combos.add(combo)
                variants.append(
                    VideoVariant(
                        source_ref=json.dumps({
                            "video_url": url,
                            "server": srv["name"],
                            "quality": q,
                            "subtitles": srv["subtitles"],
                        }),
                        resolution=f"{q}p",
                        audio=audio_type,
                    )
                )

        return variants

    def _extract_subtitles(self, soup: BeautifulSoup) -> list[tuple[str, str]]:
        """Extract subtitle tracks from ``<track kind="subtitles">`` elements.

        Returns ``[(label, url), ...]`` tuples.
        """
        subs: list[tuple[str, str]] = []
        for track in soup.select('track[kind="subtitles"]'):
            src = track.get("src", "")
            label = track.get("label", "") or "Subtitle"
            if src:
                subs.append((label, src))
        return subs

    async def _probe_qualities(self, m3u8_url: str) -> list[str]:
        """Probe an HLS master playlist for available resolutions.

        Returns quality heights (e.g. ``["1080", "720", "480"]``) best-first.
        Falls back to the configured preferred quality if probing fails.
        """
        if ".m3u8" not in m3u8_url:
            return [self.preferred_quality]
        try:
            qs = await list_master_qualities(
                self.http, m3u8_url,
                {"referer": f"{self.base_url}/", "origin": self.base_url},
            )
            if qs:
                return qs
        except Exception as exc:  # noqa: BLE001
            log.debug("anizone.probe.failed", url=m3u8_url[:80], error=str(exc))
        return [self.preferred_quality]

    # ------------------------------------------------------------------ #
    # Coverage (for the website report card)
    # ------------------------------------------------------------------ #

    async def coverage(self, *titles: str) -> SourceCoverage | None:
        """Exact episode total + a sampled sub/dub estimate.

        AniZone serves one audio type per stream (sub or dub). We sample a
        handful of episodes spread across the run to estimate audio availability,
        marked as approximate.
        """
        from nekofetch.sources._match import find_verified_match

        stub = await find_verified_match(self, list(titles))
        if not stub:
            return SourceCoverage(
                source=self.name, matched_title=titles[0] if titles else "",
                source_ref="", available=False, note="no confident match",
            )
        try:
            eps = await self.get_episodes(stub.source_ref)
        except Exception:
            eps = []
        total = len(eps)
        if not total:
            return SourceCoverage(
                source=self.name, matched_title=stub.title,
                source_ref=stub.source_ref, available=False, note="no episodes",
            )

        # Sample a few episodes for audio availability.
        k = min(5, total)
        idxs = sorted({round(i * (total - 1) / (k - 1)) for i in range(k)}) if k > 1 else [0]
        sub_hits = dub_hits = sampled = 0
        for i in idxs:
            try:
                variants = await self.get_variants(eps[i].source_ref)
            except Exception:
                continue
            sampled += 1
            audios = {v.audio for v in variants}
            if AudioType.SUBBED in audios:
                sub_hits += 1
            if AudioType.DUBBED in audios:
                dub_hits += 1

        if sampled == 0:
            return SourceCoverage(
                source=self.name, matched_title=stub.title,
                source_ref=stub.source_ref, total_episodes=total,
                approximate=True, note="audio resolved per-server",
            )
        return SourceCoverage(
            source=self.name, matched_title=stub.title, source_ref=stub.source_ref,
            total_episodes=total, seasons=1,
            sub_episodes=round(total * sub_hits / sampled),
            dub_episodes=round(total * dub_hits / sampled),
            approximate=True, available=True,
        )

    # ------------------------------------------------------------------ #
    # Download
    # ------------------------------------------------------------------ #

    async def download(
        self,
        variant: VideoVariant,
        dest: Path,
        *,
        on_progress: ProgressCallback | None = None,
        resume_state: dict | None = None,
    ) -> dict:
        """Download an HLS stream, handling dual audio (ja + en) from the master
        playlist + external subtitle tracks, then mux into a single MKV.

        AniZone's master playlists carry two ``#EXT-X-MEDIA:TYPE=AUDIO`` renditions:
        Japanese (default) and English. The video stream itself is silent; audio
        is delivered as separate HLS streams. We download the video + both audio
        renditions and mux them together with proper language metadata, exactly
        like kickassanime's ``_download_hls()``.
        """
        from nekofetch.sources._diagnostics import classify

        info = json.loads(variant.source_ref)
        manifest_url = info["video_url"]
        quality = info.get("quality", variant.resolution).rstrip("p")
        sub_list = info.get("subtitles", [])
        server_name = info.get("server", "server")

        dest.parent.mkdir(parents=True, exist_ok=True)
        stem = dest.stem
        if on_progress:
            await on_progress(0, 1)

        headers = {
            "Accept": "*/*",
            "Origin": self.base_url,
            "Referer": f"{self.base_url}/",
            "User-Agent": USER_AGENT,
        }

        if ".m3u8" not in manifest_url:
            # Progressive download (non-HLS) — rare edge case.
            try:
                out = await self._download_direct(manifest_url, dest, headers, on_progress)
            except Exception as exc:
                kind, reason = classify(exc)
                raise RuntimeError(
                    f"anizone direct download failed ({server_name}): {kind.value} — {reason}"
                ) from exc
            total = out.stat().st_size
            if on_progress:
                await on_progress(total, total)
            return {
                "checksum": hashlib.sha256(out.read_bytes()).hexdigest(),
                "bytes": total, "complete": True,
                "container": out.suffix.lstrip("."), "server": server_name,
                "label": "SUBBED", "subtitles": [],
            }

        # ---- HLS: fetch master playlist and parse audio renditions ----
        try:
            master_txt = (await self.http.get(manifest_url, headers=headers)).text
        except Exception as exc:
            kind, reason = classify(exc)
            raise RuntimeError(
                f"anizone master playlist failed ({server_name}): {kind.value} — {reason}"
            ) from exc

        if "#EXTM3U" not in master_txt[:64]:
            raise RuntimeError(f"not an HLS playlist: {master_txt[:60]!r}")

        # Parse audio renditions: #EXT-X-MEDIA:TYPE=AUDIO
        warnings: list[str] = []
        tagged: dict[str, tuple[str, str]] = {}  # canon lang -> (name, uri)
        for line in master_txt.splitlines():
            if not line.startswith("#EXT-X-MEDIA:TYPE=AUDIO"):
                continue
            uri_m = re.search(r'URI="([^"]+)"', line)
            if not uri_m:
                continue
            au_url = urljoin(manifest_url, uri_m.group(1))
            name_m = re.search(r'NAME="([^"]+)"', line)
            lang_m = re.search(r'LANGUAGE="([^"]+)"', line)
            canon = normalize_audio_lang(lang_m.group(1) if lang_m else "")
            if canon and canon not in tagged:
                tagged[canon] = (name_m.group(1) if name_m else canon.upper(), au_url)

        stats: dict = {}

        # ---- Download video stream ----
        try:
            video_ts = await download_hls_ts(
                self.http, manifest_url, headers, quality,
                dest.with_name(f".{stem}.video"), on_progress, stats=stats,
            )
        except Exception as exc:
            kind, reason = classify(exc)
            raise RuntimeError(
                f"anizone video download failed ({server_name}): {kind.value} — {reason}"
            ) from exc

        # ---- Download audio renditions ----
        names = {"ja": "Japanese", "en": "English", "hi": "Hindi"}
        audio_files: list[tuple[Path, str, str]] = []
        embedded_audio: tuple[str, str] | None = None
        covered: set[str] = set()

        if len(tagged) >= 2:
            # Dual/Multi audio — download each language-track separately.
            for canon in (c for c in WANTED_AUDIO if c in tagged):
                name, au_url = tagged[canon]
                try:
                    ap = await download_hls_ts(
                        self.http, au_url, headers, quality,
                        dest.with_name(f".{stem}.audio.{canon}"),
                    )
                    audio_files.append((ap, name, canon))
                    covered.add(canon)
                except Exception as exc:  # noqa: BLE001
                    warnings.append(f"audio '{name}' failed: {exc}")
        elif len(tagged) == 1:
            # Single language-tagged rendition.
            canon, (name, au_url) = next(iter(tagged.items()))
            ap = await download_hls_ts(
                self.http, au_url, headers, quality,
                dest.with_name(f".{stem}.audio.{canon}"),
            )
            audio_files.append((ap, name, canon))
            covered.add(canon)
        else:
            # No separate audio groups — audio is embedded in the video stream.
            embedded_audio = ("Japanese", "ja")
            covered.add("ja")

        label = audio_label(covered)

        # ---- Download subtitle tracks ----
        sub_info: list[dict] = []
        sub_tracks: list[tuple[str, str, Path]] = []
        if sub_list:
            pairs = [(s[0], s[1]) for s in sub_list if isinstance(s, (list, tuple)) and len(s) >= 2]
            sub_info = await download_subtitles(self.http, pairs, headers, dest)
            for s in sub_info:
                if s.get("saved"):
                    lang_m = re.search(r"\((\w[\w-]*)\)", s.get("label", ""))
                    lang = lang_m.group(1) if lang_m else "und"
                    sub_tracks.append((s["label"], lang, Path(s["saved"])))

        # ---- Mux into MKV ----
        container = "ts"
        if not find_ffmpeg():
            out = maybe_remux(video_ts, dest)
            warnings.append("ffmpeg not found — video-only .ts (no mux)")
            if on_progress:
                await on_progress(out.stat().st_size, out.stat().st_size)
            total = out.stat().st_size
            sha = hashlib.sha256(out.read_bytes())
            return {
                "checksum": sha.hexdigest(), "bytes": total, "complete": True,
                "container": out.suffix.lstrip("."), "server": server_name,
                "label": label, "subtitles": sub_info, "warnings": warnings,
            }

        try:
            mkv, sub_meta = await assemble_final(
                video_ts, audio_files, sub_tracks, dest,
                title=f"{stem} [{label}]",
                embedded_audio=embedded_audio,
            )
            container = "mkv"
            sub_info = sub_meta or sub_info
        except Exception as exc:  # noqa: BLE001 - keep the playable .ts
            log.warning("anizone.mux.failed", error=str(exc))
            mkv = maybe_remux(video_ts, dest)

        total_bytes = mkv.stat().st_size
        if on_progress:
            await on_progress(total_bytes, total_bytes)
        sha = hashlib.sha256()
        sha.update(mkv.read_bytes())

        log.info("anizone.download.ok", server=server_name, bytes=total_bytes,
                 label=label, audios=len(audio_files), subs=len(sub_tracks))
        return {
            "checksum": sha.hexdigest(),
            "bytes": total_bytes,
            "complete": True,
            "container": container,
            "server": server_name,
            "label": label,
            "subtitles": sub_info,
            "stats": stats,
            "warnings": warnings,
        }

    async def _download_direct(
        self, url: str, dest: Path, headers: dict,
        on_progress: ProgressCallback | None,
    ) -> Path:
        """Stream a plain progressive file (mp4 etc.) straight to disk."""
        out = dest.with_suffix(Path(url.split("?")[0]).suffix or ".mp4")
        total = 0
        async with self.http.stream("GET", url, headers=headers) as resp:
            resp.raise_for_status()
            expected = int(resp.headers.get("content-length", 0))
            with out.open("wb") as fh:
                async for chunk in resp.aiter_bytes(1 << 16):
                    fh.write(chunk)
                    total += len(chunk)
                    if on_progress and expected:
                        await on_progress(total, expected)
        if total == 0:
            raise RuntimeError("direct download produced an empty file")
        return out


def _rank_by_title(query: str, results: list[AnimeStub]) -> list[AnimeStub]:
    """Re-order site results by title relevance, not raw site order.

    The site may sort by title alphabetically, but that puts "Naruto" after
    "Naruto: Shippuden" which is the wrong season. We prefer an exact title
    match, then word overlap, keeping the site's order as a stable tiebreak.
    """
    from nekofetch.sources.telegram.matching import normalize_words

    q = normalize_words(query)
    nq = query.strip().lower()

    def key(stub: AnimeStub) -> tuple[int, float]:
        c = normalize_words(stub.title)
        exact = stub.title.strip().lower() == nq
        overlap = (len(q & c) / len(q)) if q else 0.0
        return (1 if exact else 0, overlap)

    return sorted(results, key=key, reverse=True)


def _fix_url(raw: str) -> str:
    """Normalise protocol-relative and root-relative URLs."""
    raw = raw.strip()
    if raw.startswith("//"):
        return f"https:{raw}"
    if raw.startswith("/"):
        return f"{BASE_URL}{raw}"
    return raw


def _extract_host(url: str) -> str:
    """Extract the hostname from a URL for logging."""
    m = re.match(r"https?://([^/]+)", url or "")
    return m.group(1) if m else "?"
