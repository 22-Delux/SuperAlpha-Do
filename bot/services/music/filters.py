"""Lavalink audio filters (bass, nightcore, 8D, EQ presets, slowed, ...).

Filters are applied server-side by Lavalink through :mod:`wavelink`, so the bot
does no local audio processing.
"""

from __future__ import annotations

import wavelink

# Lavalink's equalizer has 15 bands.  Presets are gain maps; gains range from
# -0.25 (muted) to 1.0 (doubled).
EQ_PRESETS: dict[str, dict[int, float]] = {
    "flat": {},
    "bass": {0: 0.22, 1: 0.22, 2: 0.18, 3: 0.12, 4: 0.06},
    "treble": {10: 0.08, 11: 0.12, 12: 0.16, 13: 0.18, 14: 0.18},
    "pop": {3: 0.08, 6: 0.06, 10: 0.08, 13: 0.08},
    "rock": {1: 0.12, 3: 0.08, 7: -0.04, 11: 0.08, 13: 0.12},
    "jazz": {2: 0.08, 5: 0.06, 9: 0.04, 12: 0.06},
    "classical": {4: 0.06, 7: 0.05, 10: 0.04, 13: 0.04},
    "electronic": {0: 0.18, 1: 0.16, 2: 0.10, 11: 0.08, 13: 0.10},
}

VALID_PRESETS = tuple(EQ_PRESETS)


def _equalizer_bands(player) -> list[dict[str, float | int]]:
    gains = dict(EQ_PRESETS.get((getattr(player, "equalizer", "flat") or "flat").lower(), {}))
    if getattr(player, "bassboost", False):
        for band, gain in EQ_PRESETS["bass"].items():
            gains[band] = min(1.0, gains.get(band, 0.0) + gain)
    return [{"band": band, "gain": max(-0.25, min(1.0, gains.get(band, 0.0)))} for band in range(15)]


def build_filters(player) -> wavelink.Filters:
    """Translate a :class:`GuildPlayer`'s settings into Lavalink filters."""
    filters = wavelink.Filters()

    bands = _equalizer_bands(player)
    if any(band["gain"] for band in bands):
        filters.equalizer.set(bands=bands)

    if getattr(player, "nightcore", False):
        filters.timescale.set(speed=1.3, pitch=1.3, rate=1.0)

    if getattr(player, "slowed", False):
        filters.timescale.set(speed=0.8, pitch=0.8, rate=1.0)
        filters.low_pass.set(smoothing=20.0)

    if getattr(player, "eight_d", False):
        filters.rotation.set(rotation_hz=0.2)

    return filters


def describe_filters(player) -> str:
    """Human-readable list of active effects, for status embeds."""
    active: list[str] = []
    if getattr(player, "bassboost", False):
        active.append("bass boost")
    if getattr(player, "nightcore", False):
        active.append("nightcore")
    if getattr(player, "slowed", False):
        active.append("slowed + reverb")
    if getattr(player, "eight_d", False):
        active.append("8D audio")
    preset = (getattr(player, "equalizer", "flat") or "flat").lower()
    if preset != "flat":
        active.append(f"{preset} EQ")
    return ", ".join(active) if active else "none"


__all__ = ["EQ_PRESETS", "VALID_PRESETS", "build_filters", "describe_filters"]
