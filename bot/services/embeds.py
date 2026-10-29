"""
bot/services/embeds.py — Branded embed styling and helpers for a polished, consistent look.
"""

from __future__ import annotations

from typing import Optional

import discord

# Brand palette
COLOR_BRAND = 0x5865F2  # Blurple
COLOR_SUCCESS = 0x2ECC71
COLOR_INFO = 0x3498DB
COLOR_WARNING = 0xF1C40F
COLOR_DANGER = 0xE74C3C
COLOR_MUSIC = 0x9B59B6
COLOR_XP = 0xF39C12
COLOR_GIVEAWAY = 0xE91E63
COLOR_EVENT = 0x1ABC9C
COLOR_DASHBOARD = 0x1ABC9C

BRAND_NAME = "alpha"
BRAND_FOOTER = "Powered by alpha • Clean. Fast. Reliable."


class AlphaEmbed(discord.Embed):
    def __init__(self, *args, **kwargs):
        color = kwargs.pop("color", COLOR_BRAND)
        footer_text = kwargs.pop("footer_text", None)
        super().__init__(*args, color=color, **kwargs)
        if footer_text:
            self.set_footer(text=footer_text)
        elif self.footer.text is None:
            self.set_footer(text=BRAND_FOOTER)


def brand_embed(
    title: str = None,
    description: str = None,
    color: int = COLOR_BRAND,
    footer: str = None,
    thumbnail: str = None,
    image: str = None,
) -> discord.Embed:
    embed = discord.Embed(title=title, description=description, color=color)
    if footer:
        embed.set_footer(text=footer)
    else:
        embed.set_footer(text=BRAND_FOOTER)
    if thumbnail:
        embed.set_thumbnail(url=thumbnail)
    if image:
        embed.set_image(url=image)
    return embed


def success_embed(title: str, description: str = None, **kwargs) -> discord.Embed:
    return brand_embed(title=f"✅ {title}", description=description, color=COLOR_SUCCESS, **kwargs)


def info_embed(title: str, description: str = None, **kwargs) -> discord.Embed:
    return brand_embed(title=f"ℹ️ {title}", description=description, color=COLOR_INFO, **kwargs)


def warning_embed(title: str, description: str = None, **kwargs) -> discord.Embed:
    return brand_embed(title=f"⚠️ {title}", description=description, color=COLOR_WARNING, **kwargs)


def error_embed(title: str, description: str = None, **kwargs) -> discord.Embed:
    return brand_embed(title=f"❌ {title}", description=description, color=COLOR_DANGER, **kwargs)


def music_embed(title: str, description: str = None, **kwargs) -> discord.Embed:
    return brand_embed(title=f"🎵 {title}", description=description, color=COLOR_MUSIC, **kwargs)


def xp_embed(title: str, description: str = None, **kwargs) -> discord.Embed:
    return brand_embed(title=f"⭐ {title}", description=description, color=COLOR_XP, **kwargs)


def giveaway_embed(title: str, description: str = None, **kwargs) -> discord.Embed:
    return brand_embed(title=f"🎉 {title}", description=description, color=COLOR_GIVEAWAY, **kwargs)


def event_embed(title: str, description: str = None, **kwargs) -> discord.Embed:
    return brand_embed(title=f"📅 {title}", description=description, color=COLOR_EVENT, **kwargs)


def stats_embed(title: str, description: str = None, **kwargs) -> discord.Embed:
    return brand_embed(title=f"📊 {title}", description=description, color=COLOR_INFO, **kwargs)


def leaderboard_embed(title: str, description: str = None, **kwargs) -> discord.Embed:
    return brand_embed(title=f"🏆 {title}", description=description, color=COLOR_XP, **kwargs)


def queue_embed(title: str = "Music Queue", description: str = None, **kwargs) -> discord.Embed:
    return brand_embed(title=f"🎶 {title}", description=description, color=COLOR_MUSIC, **kwargs)


def set_brand_footer(embed: discord.Embed, text: str = None) -> discord.Embed:
    if text:
        embed.set_footer(text=text)
    else:
        embed.set_footer(text=BRAND_FOOTER)
    return embed


def add_author_brand(embed: discord.Embed, bot: discord.Client = None) -> discord.Embed:
    if bot and bot.user:
        embed.set_author(name=BRAND_NAME, icon_url=bot.user.display_avatar.url)
    else:
        embed.set_author(name=BRAND_NAME)
    return embed
