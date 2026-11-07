"""Music domain objects: a single track and per-guild player state."""

from __future__ import annotations

import asyncio
from collections import deque
from collections.abc import Mapping
from typing import Any

import discord


class Track:
    """A playable track plus the user who requested it.

    Wraps a :class:`wavelink.Playable` while keeping the small, stable surface
    the command layer uses (``title``, ``url``, ``duration``, ``fmt_duration``).
    A plain mapping is also accepted, which keeps the object easy to construct
    in tests and for locally generated entries such as playlist imports.
    """

    __slots__ = ("playable", "title", "url", "duration", "requester", "artwork", "identifier")

    def __init__(self, data: Any, requester: discord.Member) -> None:
        self.requester = requester
        self.playable = None if isinstance(data, Mapping) else data

        if isinstance(data, Mapping):
            self.title = str(data.get("title") or "Unknown")
            self.url = str(data.get("webpage_url") or data.get("url") or "")
            self.artwork = data.get("artwork") or data.get("thumbnail")
            self.identifier = str(data.get("id") or self.url)
            duration = data.get("duration", 0)
            try:
                self.duration = int(float(duration or 0))
            except (TypeError, ValueError, OverflowError):
                self.duration = 0
        else:
            self.title = str(getattr(data, "title", None) or "Unknown")
            self.url = str(getattr(data, "uri", None) or "")
            self.artwork = getattr(data, "artwork", None)
            self.identifier = str(getattr(data, "identifier", None) or self.url)
            length = getattr(data, "length", 0) or 0
            try:
                self.duration = int(length) // 1000
            except (TypeError, ValueError, OverflowError):
                self.duration = 0

    @property
    def encoded(self) -> str | None:
        if self.playable is None:
            return None
        return getattr(self.playable, "encoded", None)

    def fmt_duration(self) -> str:
        m, s = divmod(max(0, self.duration), 60)
        h, m = divmod(m, 60)
        return f"{h:02d}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"

    def __repr__(self) -> str:
        return f"<Track title={self.title!r} duration={self.duration}>"


class GuildPlayer:
    """Per-guild queue, settings, and playback bookkeeping."""

    def __init__(self, guild_id: int) -> None:
        self.guild_id: int = guild_id
        self.queue: deque[Track] = deque()
        self.current: Track | None = None
        self.last_track: Track | None = None
        self.volume: float = 1.0
        self.loop: bool = False
        self.queue_loop: bool = False
        self.autoplay: bool = False
        self.bassboost: bool = False
        self.nightcore: bool = False
        self.eight_d: bool = False
        self.slowed: bool = False
        self.equalizer: str = "flat"
        self.skip_event: asyncio.Event = asyncio.Event()
        self.original_nick: str | None = None
        self.text_channel: discord.Messageable | None = None
        self.skip_votes: set[int] = set()
        self.vote_msg_id: int | None = None
        self._start_time: float = 0
        self._paused_time: float = 0
        self._play_generation: int = 0
        self._advance_on_stop: bool = False
        self.game_active: bool = False
        # Premium features
        self.party_mode: bool = False
        self.dj_mode: bool = False
        self.dj_role_id: int | None = None
        self.queue_history: deque[Track] = deque(maxlen=50)
        self.favorites: list[str] = []


__all__ = ["GuildPlayer", "Track"]
