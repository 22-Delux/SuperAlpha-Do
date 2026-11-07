"""URL sniffing and metadata helpers for music links.

Lavalink handles the actual audio extraction.  The helpers here only exist so
that Spotify/Apple Music share links (which Lavalink cannot always play
directly) can be translated into a normal search query, and so the command
layer can reject links that point at an album or playlist instead of a song.
"""

from __future__ import annotations

import base64
import json
import os
import re
import time
from urllib.parse import parse_qs, urlsplit

import aiohttp

SPOTIFY_API = "https://api.spotify.com/v1"
SPOTIFY_TOKEN_URL = "https://accounts.spotify.com/api/token"
SPOTIFY_OEMBED = "https://open.spotify.com/oembed"
SPOTIFY_EMBED = "https://open.spotify.com/embed"
SPOTIFY_ID_RE = re.compile(r"[0-9A-Za-z]{22}")
SPOTIFY_INTL_RE = re.compile(r"intl[.-][a-z]{2}", re.IGNORECASE)
SPOTIFY_KINDS = ("track", "album", "playlist", "episode", "show")

_SPOTIFY_BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
_SPOTIFY_ENTITY_RE = re.compile(
    r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', re.DOTALL
)

_spotify_token: tuple[str, float] | None = None


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


async def _fetch_spotify_embed(
    session: aiohttp.ClientSession, spotify_id: str
) -> dict | None:
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
    """Resolve a Spotify track id to ``{title, artist}`` for a search query.

    Three tiers, best first:

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
                            a["name"]
                            for a in (data.get("artists") or [])
                            if a.get("name")
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
                SPOTIFY_OEMBED,
                params={"url": f"https://open.spotify.com/track/{spotify_id}"},
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
    """Build the search string for a resolved track.

    ``Artist - Title`` is how music tracks are conventionally titled, and it
    steers the search toward the artist's own upload over reupload channels.
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
    """Resolve an Apple Music song id to ``{title, artist}`` via iTunes lookup."""
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


def is_supported_url(url: str) -> bool:
    """Whether a URL is worth handing to Lavalink directly."""
    supported = (
        "youtube.com",
        "youtu.be",
        "soundcloud.com",
        "bandcamp.com",
        "twitch.tv",
        "vimeo.com",
        "spotify.com",
        "apple.com",
    )
    return any(_is_domain(_hostname(url), d) for d in supported)


__all__ = [
    "SPOTIFY_API",
    "SPOTIFY_TOKEN_URL",
    "SPOTIFY_OEMBED",
    "fetch_apple_metadata",
    "fetch_spotify_metadata",
    "is_apple_url",
    "is_spotify_url",
    "is_supported_url",
    "parse_apple_url",
    "parse_spotify_url",
    "search_query_for",
]
