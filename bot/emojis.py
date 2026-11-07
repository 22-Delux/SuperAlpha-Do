"""Central registry of emoji used across the alpha bot.

Import from here instead of hard-coding emoji literals in cogs:

    from bot.emojis import EMOJI_MUSIC_PLAY, EMOJI_DANCE, EMOJI_TUX_PAT

Custom (server/application) emojis are defined once so their IDs stay in sync.
"""

from __future__ import annotations

# ── Custom animated emojis ────────────────────────────────────────────────────
EMOJI_MUSIC_PLAY = "<a:musicplay:1485243787084042270>"
EMOJI_MUSIC_PAUSE = "<a:musicpause:1485244346386350111>"
EMOJI_MUSIC_STOP = "⏹️"
EMOJI_MUSIC_SHUFFLE = "<a:musicshuffle:1485245854548885626>"
EMOJI_MUSIC_LOOP = "<a:musicloop:1485246094505017515>"
EMOJI_MUSIC_VOL = "<a:musicvol:1485246400940867695>"
EMOJI_DANCE = "<a:dance:1484553189964644352>"
EMOJI_TUX_PAT = "<a:tuxpat:1485238409437118556>"

# ── Common status / UI emojis ─────────────────────────────────────────────────
EMOJI_SUCCESS = "✅"
EMOJI_ERROR = "❌"
EMOJI_WARNING = "⚠️"
EMOJI_INFO = "ℹ️"
EMOJI_LOADING = "🔍"
EMOJI_QUEUE = "🎶"
EMOJI_MUSIC = "🎵"
EMOJI_VOLUME = "🔊"
EMOJI_FAVORITE = "⭐"
EMOJI_HISTORY = "📜"
EMOJI_RADIO = "📻"
EMOJI_PLAYLIST = "🎶"

__all__ = [
    "EMOJI_MUSIC_PLAY",
    "EMOJI_MUSIC_PAUSE",
    "EMOJI_MUSIC_STOP",
    "EMOJI_MUSIC_SHUFFLE",
    "EMOJI_MUSIC_LOOP",
    "EMOJI_MUSIC_VOL",
    "EMOJI_DANCE",
    "EMOJI_TUX_PAT",
    "EMOJI_SUCCESS",
    "EMOJI_ERROR",
    "EMOJI_WARNING",
    "EMOJI_INFO",
    "EMOJI_LOADING",
    "EMOJI_QUEUE",
    "EMOJI_MUSIC",
    "EMOJI_VOLUME",
    "EMOJI_FAVORITE",
    "EMOJI_HISTORY",
    "EMOJI_RADIO",
    "EMOJI_PLAYLIST",
]