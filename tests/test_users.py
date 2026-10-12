"""Resolving command targets by mention, raw snowflake ID, or name.

Covers the ``bot.services.users`` helpers plus the commands that now accept an
ID for someone who isn't (or is no longer) a member of the server.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import discord
import pytest
from discord.ext import commands

from bot.cogs.info import Info
from bot.cogs.moderation import Moderation
from bot.services.users import GlobalUser, GuildMember, extract_id, resolve_user
from helpers import USER_IDS, make_ctx, make_guild, make_member, sent_embed

NOT_MEMBER_ID = 987654321098765432
MEMBER_ID = 111111111111111111


def _not_found() -> discord.NotFound:
    return discord.NotFound(SimpleNamespace(status=404, reason="Not Found"), "unknown user")


# ── extract_id ────────────────────────────────────────────────────────────────
def test_extract_id_accepts_raw_ids_and_mentions():
    assert extract_id("123456789012345678") == 123456789012345678
    assert extract_id("<@123456789012345678>") == 123456789012345678
    assert extract_id("<@!123456789012345678>") == 123456789012345678
    assert extract_id("  <@123456789012345678>  ") == 123456789012345678


@pytest.mark.parametrize("value", ["", "Alice", "123", "@Alice", "<@Alice>", "#1234"])
def test_extract_id_rejects_non_ids(value):
    assert extract_id(value) is None


# ── resolve_user ──────────────────────────────────────────────────────────────
async def test_resolve_user_prefers_a_guild_member():
    bot = SimpleNamespace(get_user=lambda _id: None, users=[])
    member = make_member(MEMBER_ID)
    guild = SimpleNamespace(
        get_member=lambda i: member if i == member.id else None,
        get_member_named=lambda _n: None,
    )

    assert await resolve_user(bot, str(member.id), guild) is member
    assert await resolve_user(bot, member.mention, guild) is member


async def test_resolve_user_fetches_an_uncached_id():
    fetched = make_member(NOT_MEMBER_ID)
    bot = SimpleNamespace(
        get_user=lambda _id: None, users=[], fetch_user=AsyncMock(return_value=fetched)
    )

    assert await resolve_user(bot, str(NOT_MEMBER_ID)) is fetched
    bot.fetch_user.assert_awaited_once_with(NOT_MEMBER_ID)


async def test_resolve_user_fetch_failure_is_none_not_an_error():
    bot = SimpleNamespace(
        get_user=lambda _id: None, users=[], fetch_user=AsyncMock(side_effect=_not_found())
    )

    assert await resolve_user(bot, str(NOT_MEMBER_ID)) is None


async def test_resolve_user_matches_names_from_the_cache():
    cached = make_member(NOT_MEMBER_ID, name="Alice")
    bot = SimpleNamespace(get_user=lambda _id: None, users=[cached])

    assert await resolve_user(bot, "Alice") is cached


# ── GlobalUser converter ──────────────────────────────────────────────────────
async def test_global_user_converter_returns_a_fetched_user(bot, monkeypatch):
    fetched = make_member(NOT_MEMBER_ID, name="Stranger")
    monkeypatch.setattr(bot, "fetch_user", AsyncMock(return_value=fetched))
    ctx = make_ctx(bot)

    assert await GlobalUser().convert(ctx, str(NOT_MEMBER_ID)) is fetched


async def test_global_user_converter_raises_for_unknown(bot, monkeypatch):
    monkeypatch.setattr(bot, "fetch_user", AsyncMock(side_effect=_not_found()))
    ctx = make_ctx(bot)

    with pytest.raises(commands.UserNotFound):
        await GlobalUser().convert(ctx, str(NOT_MEMBER_ID))


# ── GuildMember converter ─────────────────────────────────────────────────────
async def test_guild_member_converter_delegates_to_the_builtin(bot, monkeypatch):
    member = make_member(MEMBER_ID)
    delegate = AsyncMock(return_value=member)
    monkeypatch.setattr(commands.MemberConverter, "convert", delegate)
    ctx = make_ctx(bot)

    assert await GuildMember().convert(ctx, str(MEMBER_ID)) is member
    delegate.assert_awaited_once()


async def test_guild_member_converter_explains_a_non_member(bot, monkeypatch):
    stranger = make_member(NOT_MEMBER_ID, name="Stranger")
    monkeypatch.setattr(
        commands.MemberConverter, "convert", AsyncMock(side_effect=commands.MemberNotFound("x"))
    )
    monkeypatch.setattr(bot, "fetch_user", AsyncMock(return_value=stranger))
    ctx = make_ctx(bot)

    with pytest.raises(commands.BadArgument) as excinfo:
        await GuildMember().convert(ctx, str(NOT_MEMBER_ID))

    assert "not in this server" in str(excinfo.value)
    assert str(NOT_MEMBER_ID) in str(excinfo.value)


# ── massban-style comma/ID lists ──────────────────────────────────────────────
async def test_global_user_converts_multiple_ids(bot, monkeypatch):
    first = make_member(111111111111111111, name="one")
    second = make_member(222222222222222222, name="two")

    async def fake_fetch(user_id):
        return {first.id: first, second.id: second}[user_id]

    monkeypatch.setattr(bot, "fetch_user", AsyncMock(side_effect=fake_fetch))
    ctx = make_ctx(bot)
    converter = GlobalUser()

    result = [await converter.convert(ctx, str(u.id)) for u in (first, second)]

    assert [u.id for u in result] == [first.id, second.id]


# ── info commands ─────────────────────────────────────────────────────────────
async def test_avatar_accepts_a_non_member_user(bot):
    user = make_member(NOT_MEMBER_ID, name="Stranger")
    ctx = make_ctx(bot)
    cog = Info(bot)

    await cog.avatar.callback(cog, ctx, user)

    assert sent_embed(ctx).image.url == user.display_avatar.url


async def test_userinfo_shows_global_profile_for_a_non_member(bot):
    user = make_member(NOT_MEMBER_ID, name="Stranger")
    ctx = make_ctx(bot)
    cog = Info(bot)

    await cog.userinfo.callback(cog, ctx, user)

    embed = sent_embed(ctx)
    assert embed.author.name == "👤 Stranger"
    assert any(f.name == "ℹ️ Not a member" for f in embed.fields)


async def test_userinfo_keeps_full_profile_for_a_member(bot):
    member = make_member(MEMBER_ID, name="Bob")
    member.roles = []
    member.status = discord.Status.online
    member.activity = None
    member.nick = None
    member.premium_since = None
    member.joined_at = discord.utils.utcnow()
    member.color = discord.Color.default()
    member.created_at = discord.utils.utcnow()
    guild = make_guild(members=[member])
    ctx = make_ctx(bot, guild=guild)
    cog = Info(bot)

    await cog.userinfo.callback(cog, ctx, member)

    embed = sent_embed(ctx)
    assert any(f.name.startswith("🎭 Roles") for f in embed.fields)
    assert not any(f.name == "ℹ️ Not a member" for f in embed.fields)


async def test_banner_reports_none_for_a_bannerless_user(bot, monkeypatch):
    user = make_member(NOT_MEMBER_ID, name="Stranger")
    fetched = SimpleNamespace(banner=None, accent_color=None)
    monkeypatch.setattr(bot, "fetch_user", AsyncMock(return_value=fetched))
    ctx = make_ctx(bot)
    cog = Info(bot)

    await cog.banner.callback(cog, ctx, user)

    assert "no banner" in sent_embed(ctx).description.lower()


# ── moderation commands ───────────────────────────────────────────────────────
async def test_ban_bans_a_non_member_by_id(bot):
    user = make_member(NOT_MEMBER_ID, name="Stranger")
    guild = make_guild()
    guild.ban = AsyncMock()
    ctx = make_ctx(bot, guild=guild)
    cog = Moderation(bot)

    await cog.ban.callback(cog, ctx, user, reason="spam")

    guild.ban.assert_awaited_once()
    assert guild.ban.await_args.args[0] is user
    assert str(NOT_MEMBER_ID) in " ".join(str(f.value) for f in sent_embed(ctx).fields)


async def test_unban_reports_when_the_user_is_not_banned(bot):
    user = make_member(NOT_MEMBER_ID, name="Stranger")
    guild = make_guild()
    guild.unban = AsyncMock(side_effect=_not_found())
    ctx = make_ctx(bot, guild=guild)
    cog = Moderation(bot)

    await cog.unban.callback(cog, ctx, user)

    assert "not banned" in sent_embed(ctx).description.lower()


async def test_mute_still_takes_a_real_member(bot):
    member = make_member(MEMBER_ID)
    member.timeout = AsyncMock()
    ctx = make_ctx(bot)
    cog = Moderation(bot)

    await cog.mute.callback(cog, ctx, member, 10, reason="quiet")

    member.timeout.assert_awaited_once()
