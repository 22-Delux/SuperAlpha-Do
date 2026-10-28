"""Music services: playback domain objects, audio filters, and yt-dlp sources."""

from bot.services.music.filters import build_filter_string, get_ffmpeg_opts
from bot.services.music.models import GuildPlayer, Track
from bot.services.music.sources import (
    BASE_YTDL_OPTS,
    COOKIES_FILE,
    classify_ytdl_error,
    extract_info,
    fetch_apple_metadata,
    fetch_spotify_metadata,
    get_ytdl_opts,
    is_apple_url,
    is_playable_url,
    is_spotify_url,
    is_youtube_search_failure,
    parse_apple_url,
    parse_spotify_url,
    resolve_youtube_search_results,
    resolve_youtube_via_fallback,
    search_query_for,
    shutdown_ytdl_pool,
    youtube_search_query,
)

__all__ = [
    "BASE_YTDL_OPTS",
    "COOKIES_FILE",
    "GuildPlayer",
    "Track",
    "build_filter_string",
    "classify_ytdl_error",
    "extract_info",
    "fetch_apple_metadata",
    "fetch_spotify_metadata",
    "get_ffmpeg_opts",
    "get_ytdl_opts",
    "is_apple_url",
    "is_playable_url",
    "is_spotify_url",
    "is_youtube_search_failure",
    "parse_apple_url",
    "parse_spotify_url",
    "resolve_youtube_search_results",
    "resolve_youtube_via_fallback",
    "search_query_for",
    "shutdown_ytdl_pool",
    "youtube_search_query",
]
