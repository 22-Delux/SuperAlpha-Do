"""yt-dlp source adapter: options, URL sniffing, metadata, and error messages."""

from __future__ import annotations

import asyncio
import atexit
import base64
import json
import multiprocessing as mp
import os
import re
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from urllib.parse import parse_qs, quote_plus, urlsplit
import aiohttp
import yt_dlp

# Resolve cookies.txt against the repo root so it works regardless of cwd.
# Override with YTDL_COOKIES=/path/to/cookies.txt when the host mounts it elsewhere.
_DEFAULT_COOKIES = Path(__file__).resolve().parents[3] / "cookies.txt"
COOKIES_FILE = os.environ.get("YTDL_COOKIES") or str(_DEFAULT_COOKIES)

# Public Piped/Invidious mirrors used only when yt-dlp's ytsearch API returns
# an empty body (common on datacenter IPs such as Wispbyte). Tried in order;
# first mirror that returns video ids wins.
_SEARCH_FALLBACK_ENDPOINTS = (
    "https://api.piped.private.coffee/search?q={q}&filter=videos",
    "https://pipedapi.darkness.services/search?q={q}&filter=videos",
    "https://piped-api.privacyredirect.com/search?q={q}&filter=videos",
    "https://invidious.projectsegfau.lt/api/v1/search?q={q}&type=video",
    "https://inv.nadeko.net/api/v1/search?q={q}&type=video",
)

BASE_YTDL_OPTS = {
    "format": "bestaudio/best",
    "quiet": True,
    "no_warnings": True,
    "default_search": "ytsearch",
    "noplaylist": True,
    "extract_flat": False,
    "socket_timeout": 30,
    # Rotate through multiple YouTube players so a bot-checked web client
    # doesn't block playback (embedded/TV clients are usually allowed).
    "extractor_args": {
        "youtube": {
            "player_client": ["TV_EMBED", "WEB_EMBED", "TV", "MWEB", "IOS", "ANDROID"],
        },
    },
    "http_headers": {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
    },
    "js_runtimes": {"node": {"cmd": ["node"]}},
}

# Dedicated process pool so heavy yt-dlp work stays off the event-loop thread pool.
_ytdl_pool: ProcessPoolExecutor | None = None
_YTDL_POOL_WORKERS = 2


def _get_ytdl_pool() -> ProcessPoolExecutor:
    global _ytdl_pool
    if _ytdl_pool is None:
        _ytdl_pool = ProcessPoolExecutor(
            max_workers=_YTDL_POOL_WORKERS,
            mp_context=mp.get_context("spawn"),
        )
    return _ytdl_pool


def shutdown_ytdl_pool() -> None:
    """Shut down the shared yt-dlp process pool (idempotent)."""
    global _ytdl_pool
    if _ytdl_pool is not None:
        _ytdl_pool.shutdown(wait=False, cancel_futures=True)
        _ytdl_pool = None


atexit.register(shutdown_ytdl_pool)


def _ytdl_extract(query: str, opts: dict) -> dict | None:
    """Picklable worker: run yt-dlp extract_info in a child process."""
    try:
        with yt_dlp.YoutubeDL(opts) as ytdl:
            return ytdl.extract_info(query, download=False)
    except Exception as exc:
        # Strip the traceback/exc_info chain before it crosses the process
        # boundary — exceptions with tracebacks can't be pickled, which would
        # surface as "cannot pickle 'traceback' object" instead of the real
        # yt-dlp message.
        raise RuntimeError(str(exc)) from None


def get_ytdl_opts() -> dict:
    opts = BASE_YTDL_OPTS.copy()
    opts["extractor_args"] = {k: dict(v) for k, v in opts.get("extractor_args", {}).items()}
    use_cookies = os.path.exists(COOKIES_FILE) and os.path.getsize(COOKIES_FILE) > 0
    if use_cookies:
        opts["cookiefile"] = COOKIES_FILE
        # Prioritize embedded/TV clients when cookies are present to avoid "page needs to be reloaded"
        opts["extractor_args"]["youtube"]["player_client"] = [
            "TV_EMBED", "WEB_EMBED", "IOS", "ANDROID", "TV", "MWEB", "WEB_SAFARI", "WEB",
        ]
    else:
        print(f"Warning: cookies.txt is missing or empty — anonymous playback ({COOKIES_FILE})")
        opts["extractor_args"]["youtube"]["player_client"] = [
            "TV_EMBED", "WEB_EMBED", "ANDROID", "IOS", "TV", "MWEB", "WEB_SAFARI",
        ]
    # Optional remote PO-token (bgutil) support for hosts whose IP is flagged.
    # Either an HTTP server (POT_SERVER_URL) or a local node/deno script
    # (POT_SCRIPT_PATH) may be provided; yt-dlp auto-uses it when present.
    if pot_url := os.getenv("POT_SERVER_URL"):
        opts["extractor_args"]["youtubepot-bgutilhttp"] = {"base_url": pot_url}
    if pot_script := os.getenv("POT_SCRIPT_PATH"):
        opts["extractor_args"]["youtubepot-bgutilscript"] = {"script_path": pot_script}
    # Optional HTTP(S) proxy — needed on hosts whose egress IP is blocked by YouTube.
    # Prefer YTDL_PROXY; fall back to the standard HTTPS_PROXY / HTTP_PROXY envs.
    proxy = (
        os.getenv("YTDL_PROXY")
        or os.getenv("HTTPS_PROXY")
        or os.getenv("HTTP_PROXY")
        or os.getenv("https_proxy")
        or os.getenv("http_proxy")
    )
    if proxy:
        opts["proxy"] = proxy
    return opts


def _hostname(url: str) -> str:
    """The lowercased hostname of a URL, or ``""`` when unparseable."""
    try:
        return (urlsplit(url).hostname or "").lower()
    except ValueError:
        return ""


def _is_domain(host: str, domain: str) -> bool:
    return host == domain or host.endswith(f".{domain}")


def _host_part(url: str) -> str:
    """The host of a URL, tolerating a missing scheme and trailing junk."""
    text = url.strip().lower().split("://", 1)[-1]
    return text.split("/", 1)[0].split("?", 1)[0]


def is_spotify_url(url: str) -> bool:
    return _is_domain(_host_part(url), "spotify.com")


SPOTIFY_API = "https://api.spotify.com/v1"
SPOTIFY_TOKEN_URL = "https://accounts.spotify.com/api/token"
SPOTIFY_OEMBED = "https://open.spotify.com/oembed"
SPOTIFY_ID_RE = re.compile(r"[0-9A-Za-z]{22}")
SPOTIFY_INTL_RE = re.compile(r"intl[.-][a-z]{2}", re.IGNORECASE)
SPOTIFY_KINDS = ("track", "album", "playlist", "episode", "show")
_spotify_token: tuple[str, float] | None = None


def parse_spotify_url(url: str) -> tuple[str, str] | None:
    """Return ``(kind, spotify_id)`` for a Spotify track/album/playlist link.

    Handles both the ``https://open.spotify.com/track/<id>?si=...`` form and the
    ``spotify:track:<id>`` URI people paste out of the mobile app, plus the
    localised ``/intl-de/track/<id>`` path. ``None`` means "not a Spotify link".
    """
    text = url.strip()
    lowered = text.lower()

    if lowered.startswith("spotify:"):
        # spotify:intl-de:track:<id> -> the country prefix is optional noise
        parts = [p for p in text.split(":") if p and not SPOTIFY_INTL_RE.fullmatch(p)]
        if len(parts) < 3:
            return None
        kind, spotify_id = parts[-2].lower(), parts[-1]

    elif _is_domain(_host_part(lowered), "spotify.com"):
        # Discord doesn't autolink scheme-less text, and people paste it anyway
        if "://" not in text:
            text = f"https://{text}"
        segments = [s for s in urlsplit(text).path.split("/") if s]
        if len(segments) >= 3 and SPOTIFY_INTL_RE.fullmatch(segments[0]):
            segments = segments[1:]
        if len(segments) < 2:
            return None
        kind, spotify_id = segments[0].lower(), segments[1]

    else:
        return None

    if kind not in SPOTIFY_KINDS or not SPOTIFY_ID_RE.fullmatch(spotify_id):
        return None
    return kind, spotify_id


async def _spotify_access_token(session: aiohttp.ClientSession) -> str | None:
    """Client-credentials token from the Spotify Web API, cached until it expires."""
    global _spotify_token
    client_id = os.environ.get("SPOTIPY_CLIENT_ID")
    client_secret = os.environ.get("SPOTIPY_CLIENT_SECRET")
    if not (client_id and client_secret):
        return None
    if _spotify_token and _spotify_token[1] > time.monotonic():
        return _spotify_token[0]

    auth = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()
    try:
        async with session.post(
            SPOTIFY_TOKEN_URL,
            data={"grant_type": "client_credentials"},
            headers={"Authorization": f"Basic {auth}"},
        ) as response:
            if response.status != 200:
                return None
            payload = await response.json()
    except Exception:
        return None

    token = payload.get("access_token")
    if not token:
        return None
    # refresh a minute early so a request never races the expiry
    lifetime = max(60, int(payload.get("expires_in", 3600)) - 60)
    _spotify_token = (token, time.monotonic() + lifetime)
    return token


SPOTIFY_EMBED = "https://open.spotify.com/embed"
_SPOTIFY_BROWSER_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
_SPOTIFY_ENTITY_RE = re.compile(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', re.DOTALL)


def _metadata_from_embed_html(html: str) -> dict | None:
    """Pull ``{title, artist}`` out of a Spotify embed page.

    The zero-config path: the embed widget ships the full track entity as JSON,
    including every credited artist, so no API credentials are needed.
    """
    match = _SPOTIFY_ENTITY_RE.search(html)
    if not match:
        return None
    try:
        entity = json.loads(match.group(1))["props"]["pageProps"]["state"]["data"]["entity"]
    except (KeyError, TypeError, ValueError):
        return None
    if not isinstance(entity, dict):
        return None

    title = (entity.get("name") or entity.get("title") or "").strip()
    artists = entity.get("artists") or []
    artist = ", ".join(
        a.get("name", "") for a in artists if isinstance(a, dict) and a.get("name")
    ).strip()
    if title:
        return {"title": title, "artist": artist}
    return None


async def _fetch_spotify_embed(session: aiohttp.ClientSession, spotify_id: str) -> dict | None:
    try:
        async with session.get(
            f"{SPOTIFY_EMBED}/track/{spotify_id}",
            headers={"User-Agent": _SPOTIFY_BROWSER_UA},
        ) as response:
            if response.status != 200:
                return None
            html = await response.text()
    except Exception:
        return None
    return _metadata_from_embed_html(html)


async def fetch_spotify_metadata(spotify_id: str) -> dict | None:
    """Resolve a Spotify track id to ``{title, artist}`` for a YouTube search.

    yt-dlp cannot do this: its Spotify extractor was removed because the audio is
    DRM-protected, so we ask Spotify directly. Three tiers, best first:

    1. the Web API, when ``SPOTIPY_CLIENT_ID``/``SPOTIPY_CLIENT_SECRET`` are set;
    2. the public embed page, which needs no credentials and still includes the
       credited artists;
    3. the oEmbed endpoint, which yields the title alone.
    """
    timeout = aiohttp.ClientTimeout(total=15)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        token = await _spotify_access_token(session)
        if token:
            try:
                async with session.get(
                    f"{SPOTIFY_API}/tracks/{spotify_id}",
                    headers={"Authorization": f"Bearer {token}"},
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        title = (data.get("name") or "").strip()
                        artist = ", ".join(
                            a["name"] for a in (data.get("artists") or []) if a.get("name")
                        )
                        if title and artist:
                            return {"title": title, "artist": artist}
            except Exception:
                pass

        embed = await _fetch_spotify_embed(session, spotify_id)
        if embed:
            return embed

        try:
            async with session.get(
                SPOTIFY_OEMBED, params={"url": f"https://open.spotify.com/track/{spotify_id}"}
            ) as response:
                if response.status != 200:
                    return None
                data = await response.json()
            title = (data.get("title") or "").strip()
            if title:
                return {"title": title, "artist": ""}
        except Exception:
            return None
    return None


def search_query_for(title: str, artist: str) -> str:
    """Build the YouTube search string for a resolved track.

    ``Artist - Title`` is how YouTube tracks are conventionally titled, and it
    steers the search toward the artist's own upload over reupload/lyrics
    channels: ``Hello Adele`` finds a lyrics channel, ``Adele - Hello`` finds
    Adele.
    """
    title = (title or "").strip()
    artist = (artist or "").strip()
    if artist and title:
        return f"{artist} - {title}"
    return title



def is_apple_url(url: str) -> bool:
    return _host_part(url) in {"music.apple.com", "itunes.apple.com"}


def parse_apple_url(url: str) -> tuple[str, str] | None:
    """Return ``("song", itunes_id)`` / ``("album", "")`` for an Apple Music link.

    Apple's song links carry the track id in the ``?i=`` query parameter
    (``/album/<slug>/<album_id>?i=<track_id>``); newer share links use a
    ``/song/<slug>/<track_id>`` path instead.
    """
    text = url.strip()
    if "://" not in text:
        text = f"https://{text}"
    if not is_apple_url(text):
        return None

    parts = urlsplit(text)
    segments = [s for s in parts.path.split("/") if s]
    if segments and re.fullmatch(r"[a-z]{2}", segments[0], re.IGNORECASE):
        segments = segments[1:]  # drop the storefront, e.g. /us/

    track_id = (parse_qs(parts.query).get("i") or [""])[0]
    if track_id.isdigit():
        return "song", track_id
    if len(segments) >= 2 and segments[0] == "song" and segments[-1].isdigit():
        return "song", segments[-1]
    if segments and segments[0] == "album":
        return "album", ""
    return None


async def fetch_apple_metadata(song_id: str) -> dict | None:
    """Resolve an Apple Music song id to ``{title, artist}`` via iTunes lookup.

    yt-dlp dropped its Apple Music extractor for the same DRM reason as Spotify,
    but the iTunes lookup API needs no credentials.
    """
    timeout = aiohttp.ClientTimeout(total=15)
    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(
                "https://itunes.apple.com/lookup",
                params={"id": song_id, "entity": "song"},
            ) as response:
                if response.status != 200:
                    return None
                # iTunes serves JSON as text/javascript, which aiohttp refuses by default
                data = await response.json(content_type=None)
    except Exception:
        return None

    results = data.get("results") or []
    if not results:
        return None
    result = results[0]
    title = (result.get("trackName") or result.get("collectionName") or "").strip()
    artist = (result.get("artistName") or "").strip()
    if title:
        return {"title": title, "artist": artist}
    return None



def is_playable_url(url: str) -> bool:
    supported = ("youtube.com", "youtu.be", "spotify.com", "apple.com", "bandcamp.com", "twitch.tv")
    return any(_is_domain(_hostname(url), d) for d in supported)


def youtube_search_query(query: str) -> str:
    return f"ytsearch1:{query}"


def is_youtube_search_failure(error: Exception | str) -> bool:
    """True when YouTube's search API returned an empty/blocked response."""
    low = str(error).lower()
    return any(
        marker in low
        for marker in (
            "failed to parse json",
            "jsondecodeerror",
            "sign in to confirm",
            "confirm you're not a bot",
            "bot check",
            "page needs to be reloaded",
        )
    )


def _video_id_from_search_item(item: dict) -> str | None:
    """Pull an 11-char YouTube id out of a Piped or Invidious search hit."""
    if not isinstance(item, dict):
        return None
    for key in ("videoId", "id", "url", "webpageUrl", "webpage_url"):
        value = item.get(key)
        if not value:
            continue
        text = str(value)
        if re.fullmatch(r"[A-Za-z0-9_-]{11}", text):
            return text
        match = re.search(r"(?:v=|/watch/|/v/|youtu\.be/)([A-Za-z0-9_-]{11})", text)
        if match:
            return match.group(1)
    return None


async def resolve_youtube_search_results(
    query: str, *, limit: int = 1
) -> list[dict[str, str]]:
    """Resolve a search term to YouTube hits via Piped/Invidious.

    Each hit is ``{"title", "url", "id"}``. Used when ``ytsearch`` fails because
    the host IP gets an empty YouTube search API response. Returns ``[]`` when
    every mirror fails.
    """
    encoded = quote_plus(query.strip())
    if not encoded or limit < 1:
        return []
    timeout = aiohttp.ClientTimeout(total=10)
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; SuperAlphaDo/1.0; +https://github.com/)",
        "Accept": "application/json",
    }
    async with aiohttp.ClientSession(timeout=timeout, headers=headers) as session:
        for template in _SEARCH_FALLBACK_ENDPOINTS:
            url = template.format(q=encoded)
            try:
                async with session.get(url) as response:
                    if response.status != 200:
                        continue
                    raw = (await response.text()).lstrip()
                    if not raw or raw[0] not in "{[":
                        continue
                    payload = json.loads(raw)
            except Exception as exc:
                print(f"YouTube search fallback missed {url}: {exc}")
                continue

            items = payload if isinstance(payload, list) else (payload.get("items") or [])
            if not isinstance(items, list):
                continue

            results: list[dict[str, str]] = []
            seen: set[str] = set()
            for item in items:
                if not isinstance(item, dict):
                    continue
                # Piped marks streams as type "stream"; Invidious uses "video".
                kind = (item.get("type") or item.get("typeOf") or "video").lower()
                if kind not in {"video", "stream", ""}:
                    continue
                video_id = _video_id_from_search_item(item)
                if not video_id or video_id in seen:
                    continue
                seen.add(video_id)
                title = (item.get("title") or query).strip() or query
                watch_url = f"https://www.youtube.com/watch?v={video_id}"
                results.append({"title": title, "url": watch_url, "id": video_id})
                if len(results) >= limit:
                    break
            if results:
                print(
                    f"YouTube search fallback resolved '{query}' -> "
                    f"{len(results)} result(s) via {urlsplit(url).hostname}"
                )
                return results
    return []


async def resolve_youtube_via_fallback(query: str) -> str | None:
    """Resolve a search term to a single YouTube watch URL via Piped/Invidious."""
    results = await resolve_youtube_search_results(query, limit=1)
    return results[0]["url"] if results else None


def classify_ytdl_error(error: Exception) -> str:
    """Turn a yt-dlp exception into a human-friendly message."""
    msg = str(error)
    low = msg.lower()
    if "failed to parse json" in low or "jsondecodeerror" in low:
        return (
            "**YouTube returned an empty or invalid search response.** "
            "This usually means the host IP is blocked. Add a valid "
            "`cookies.txt`, set `YTDL_PROXY`, or paste a direct YouTube link."
        )
    if any(k in low for k in (
        "cookies", "cookie not found", "sign in to confirm", "logged out",
        "logged_out", "must provide login", "use cookies",
    )):
        return (
            "**YouTube cookie expired or bot-check triggered.**\n"
            "Refresh `cookies.txt`, restart the bot, or update yt-dlp "
            "with `pip install -U yt-dlp`."
        )
    if any(k in low for k in (
        "video unavailable", "unavailable", "has been removed",
        "private video", "age-restricted", "age restriction",
    )):
        return "That video is unavailable (removed, private, age-restricted, or region-locked)."
    if any(k in low for k in ("429", "too many requests", "request has been blocked", "rate limit", "repeated request")):
        return "YouTube is rate-limiting the bot. Wait a minute and try again."
    if "not a valid url" in low or "unsupported url" in low:
        return (
            "That doesn't look like a link I can play. Try a YouTube, "
            "Bandcamp, Spotify, or Apple Music link, or a search term."
        )
    return f"Could not fetch that track: `{msg[:200]}`"


async def extract_info(
    query: str,
    *,
    skip_download: bool = False,
    flat: bool = False,
) -> dict | None:
    """Run yt-dlp in a process pool and return the extracted info dict.

    Use ``flat=True`` (``extract_flat``) for playlist/search listings where
    stream URLs are not needed yet — e.g. radio mode and related-track search.
    Full extraction (``flat=False``) is required when a playable stream URL
    is needed.
    """
    loop = asyncio.get_running_loop()
    opts = get_ytdl_opts()
    if skip_download:
        opts["skip_download"] = True
    if flat:
        opts["extract_flat"] = "in_playlist"
        opts["noplaylist"] = False
    elif skip_download:
        opts["extract_flat"] = False
        opts["noplaylist"] = True
    return await loop.run_in_executor(
        _get_ytdl_pool(),
        _ytdl_extract,
        query,
        opts,
    )

