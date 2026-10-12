"""Resolve command targets from mentions, raw snowflake IDs, or names.

Discord's built-in member converter only finds users who are *currently in the
guild*, so `alpha banner 123456789012345678` (and `alpha ban` on someone who
already left) failed for anyone outside the server. These converters accept a
mention, a raw ID, or a name, and for an ID fall back to a global user fetch so
profile lookups, bans, and un-bans work for any user the bot can see.
"""

from __future__ import annotations

import re

import discord
from discord.ext import commands

__all__ = [
    "extract_id",
    "resolve_user",
    "GlobalUser",
    "GuildMember",
]

_MENTION_RE = re.compile(r"<@!?([0-9]{15,20})>")
_ID_RE = re.compile(r"([0-9]{15,20})")


def extract_id(argument: str) -> int | None:
    """Pull a snowflake out of a mention (``<@123>``) or a bare ID (``123``)."""
    if not argument:
        return None
    text = argument.strip()
    match = _MENTION_RE.fullmatch(text) or _ID_RE.fullmatch(text)
    return int(match.group(1)) if match else None


async def resolve_user(
    bot: commands.Bot,
    argument: str,
    guild: discord.Guild | None = None,
) -> discord.User | None:
    """Resolve a mention/ID/name to a user, fetching by ID when not cached.

    Members are preferred over plain users so callers can still read member-only
    attributes when the target happens to share the guild. Returns ``None`` when
    nothing matches instead of raising.
    """
    user_id = extract_id(argument)
    if user_id is not None:
        if guild is not None:
            member = guild.get_member(user_id)
            if member is not None:
                return member
        cached = bot.get_user(user_id)
        if cached is not None:
            return cached
        try:
            return await bot.fetch_user(user_id)
        except discord.HTTPException:
            return None

    name = (argument or "").strip()
    if not name:
        return None
    for candidate in list(bot.users):
        if candidate.name == name or getattr(candidate, "global_name", None) == name:
            return candidate
    if guild is not None:
        member = guild.get_member_named(name)
        if member is not None:
            return member
    return None


class GlobalUser(commands.Converter):
    """A mention, raw ID, or name -> a :class:`discord.User`.

    Unlike the built-in member converter this never requires the user to share a
    guild with the bot, so it can target people who left or were never here.
    """

    async def convert(self, ctx: commands.Context, argument: str) -> discord.User:
        user = await resolve_user(ctx.bot, argument, ctx.guild)
        if user is None:
            raise commands.UserNotFound(argument)
        return user


class GuildMember(commands.Converter):
    """A mention, raw ID, or name -> a :class:`discord.Member` in this guild.

    A bare ID that resolves to a user who isn't a member raises a clear error
    naming them instead of discord.py's generic "Member not found".
    """

    async def convert(self, ctx: commands.Context, argument: str) -> discord.Member:
        try:
            return await commands.MemberConverter().convert(ctx, argument)
        except commands.MemberNotFound:
            user = await resolve_user(ctx.bot, argument)
            if user is not None:
                raise commands.BadArgument(
                    f"**{user}** (`{user.id}`) is not in this server."
                ) from None
            raise
