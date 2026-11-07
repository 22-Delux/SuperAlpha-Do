"""Music services: Wavelink playback, Lavalink node pool, filters, and metadata."""

from bot.services.music.filters import (
    EQ_PRESETS,
    VALID_PRESETS,
    build_filters,
    describe_filters,
)
from bot.services.music.metadata import (
    fetch_apple_metadata,
    fetch_spotify_metadata,
    is_apple_url,
    is_spotify_url,
    is_supported_url,
    parse_apple_url,
    parse_spotify_url,
    search_query_for,
)
from bot.services.music.models import GuildPlayer, Track
from bot.services.music.nodes import (
    DEFAULT_NODES,
    LavalinkNodeConfig,
    NodeManager,
    NodePoolError,
    NoNodesAvailable,
    TrackSearchError,
    load_node_configs,
    parse_node_spec,
)

__all__ = [
    "DEFAULT_NODES",
    "EQ_PRESETS",
    "GuildPlayer",
    "LavalinkNodeConfig",
    "NoNodesAvailable",
    "NodeManager",
    "NodePoolError",
    "Track",
    "TrackSearchError",
    "VALID_PRESETS",
    "build_filters",
    "describe_filters",
    "fetch_apple_metadata",
    "fetch_spotify_metadata",
    "is_apple_url",
    "is_spotify_url",
    "is_supported_url",
    "load_node_configs",
    "parse_apple_url",
    "parse_node_spec",
    "parse_spotify_url",
    "search_query_for",
]
