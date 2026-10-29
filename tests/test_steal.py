"""Steal command: name sanitisation, source extraction, and full flow."""

from __future__ import annotations

import io
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import aiohttp
import discord
import pytest
from PIL import Image

from bot.cogs.steal import Steal, _sanitise_name, _sanitise_sticker_name

from helpers import (
    TEXT_CHANNEL_ID,
    USER_IDS,
    make_channel,
    make_ctx,
    make_guild,
    make_member,
    make_real_message,
)


# ── Pure helpers ───────────────────────────────────────────────────────────────
@pytest.mark.parametrize("raw,expected", [
    ("My Emoji!!1", "MyEmoji1"),
    ("  _pad_  ", "pad"),
    ("a", None),
    ("", None),
    (None, None),
    ("x" * 40, "x" * 32),
])
def test_sanitise_name(raw, expected):
    assert _sanitise_name(raw) == expected


def test_emoji_from_message():
    assert Steal._emoji_from_message(make_real_message("join <:lol:123>")) == (123, False)
    assert Steal._emoji_from_message(make_real_message("<a:yikes:456> 😄")) == (456, True)
    assert Steal._emoji_from_message(make_real_message("no emoji here")) is None


def test_image_from_message_attachment_picks_largest():
    from types import SimpleNamespace
    small = SimpleNamespace(content_type="image/png", size=10, filename="a.png", url="https://x/a.png")
    big = SimpleNamespace(content_type="image/png", size=1000, filename="b.png", url="https://x/b.png")
    msg = make_real_message("", attachments=[small, big])
    url, animated = Steal._image_from_message(msg)
    assert url == "https://x/b.png"
    assert animated is False


def test_image_from_message_gif_animated():
    from types import SimpleNamespace
    gif = SimpleNamespace(content_type="image/gif", size=10, filename="x.gif", url="https://x/x.gif")
    msg = make_real_message("", attachments=[gif])
    _, animated = Steal._image_from_message(msg)
    assert animated is True


def test_image_from_message_embed_fallback():
    embed = discord.Embed()
    embed.set_image(url="https://cdn/x.png")
    msg = make_real_message("", attachments=[], embeds=[embed])
    url, _ = Steal._image_from_message(msg)
    assert url == "https://cdn/x.png"


def test_image_from_message_none():
    assert Steal._image_from_message(make_real_message("")) is None


def test_filtered_name_avoids_collisions():
    guild = make_guild()
    guild.emojis = [SimpleNamespace(name="base"), SimpleNamespace(name="base_2")]
    assert Steal._filtered_name(guild, "base") == "base_3"
    assert Steal._filtered_name(guild, "fresh") == "fresh"


# ── Command flow ──────────────────────────────────────────────────────────────
def _emoji_ref():
    ref = make_real_message("<:lol:123>")
    ref.author = make_member(USER_IDS["member"], guild=make_guild())
    return ref


async def _cog_with_guild(bot, name="my_emoji"):
    cog = Steal(bot)
    guild = make_guild()
    guild.emoji_limit = 50
    guild.emojis = []
    guild.create_custom_emoji = AsyncMock(return_value=None)
    return cog, guild


async def test_steal_without_reference(bot):
    cog = Steal(bot)
    ctx = make_ctx(bot)
    ctx.message.reference = None
    await cog.steal.callback(cog, ctx)
    assert ctx.send.await_args.kwargs["embed"].author.name == "❌ Nothing to Steal"


async def test_steal_invalid_name(bot):
    cog, _guild = await _cog_with_guild(bot)
    guild = make_guild()
    ctx = make_ctx(bot, author=make_member(USER_IDS["member"], guild=guild), guild=guild)
    ctx.message.reference = SimpleNamespace(resolved=_emoji_ref())
    await cog.steal.callback(cog, ctx, name="a")
    assert ctx.send.await_args.kwargs["embed"].author.name == "❌ Invalid Name"


async def test_steal_no_source(bot):
    cog, _guild = await _cog_with_guild(bot)
    guild = make_guild()
    ref = make_real_message("just text")
    ref.author = make_member(USER_IDS["member"], guild=guild)
    ctx = make_ctx(bot, author=make_member(USER_IDS["member"], guild=guild), guild=guild)
    ctx.message.reference = SimpleNamespace(resolved=ref)
    await cog.steal.callback(cog, ctx, name="whatever")
    assert ctx.send.await_args.kwargs["embed"].author.name == "❌ Nothing to Steal"


async def test_steal_full_flow(bot):
    cog = Steal(bot)
    guild = make_guild()
    guild.emoji_limit = 50
    guild.emojis = []
    emoji = MagicMock()
    emoji.id = 111
    emoji.name = "my_emoji"
    emoji.animated = False
    emoji.url = "https://cdn.example/111.png"
    guild.create_custom_emoji = AsyncMock(return_value=emoji)
    cog._fetch = AsyncMock(return_value=b"\x89PNG fake")

    author = make_member(USER_IDS["member"], guild=guild)
    ctx = make_ctx(bot, author=author, guild=guild)
    ctx.message.reference = SimpleNamespace(resolved=_emoji_ref())

    await cog.steal.callback(cog, ctx, name="my_emoji")

    guild.create_custom_emoji.assert_awaited_once()
    call_kwargs = guild.create_custom_emoji.await_args.kwargs
    assert call_kwargs["name"] == "my_emoji"
    assert call_kwargs["image"] == b"\x89PNG fake"
    embed = ctx.send.await_args.kwargs["embed"]
    assert embed.author.name == "✅ Stolen & Added — :my_emoji:"


async def test_steal_uses_referenced_emoji_name(bot):
    cog = Steal(bot)
    guild = make_guild()
    guild.emoji_limit = 50
    guild.emojis = []
    emoji = MagicMock()
    emoji.id = 111
    emoji.name = "lol"
    emoji.animated = False
    guild.create_custom_emoji = AsyncMock(return_value=emoji)
    cog._fetch = AsyncMock(return_value=b"data")

    author = make_member(USER_IDS["member"], guild=guild)
    ctx = make_ctx(bot, author=author, guild=guild)
    ctx.message.reference = SimpleNamespace(resolved=_emoji_ref())

    await cog.steal.callback(cog, ctx)
    assert guild.create_custom_emoji.await_args.kwargs["name"] == "lol"


async def test_steal_slots_full(bot):
    cog = Steal(bot)
    guild = make_guild()
    guild.emoji_limit = 1
    guild.emojis = [SimpleNamespace(animated=False, name="used")]
    cog._fetch = AsyncMock(return_value=b"data")

    author = make_member(USER_IDS["member"], guild=guild)
    ctx = make_ctx(bot, author=author, guild=guild)
    ctx.message.reference = SimpleNamespace(resolved=_emoji_ref())
    await cog.steal.callback(cog, ctx, name="new_emoji")
    assert ctx.send.await_args.kwargs["embed"].author.name == "❌ Emoji Slots Full"


async def test_steal_download_failure(bot):
    cog = Steal(bot)
    guild = make_guild()
    guild.emoji_limit = 50
    guild.emojis = []
    cog._fetch = AsyncMock(side_effect=aiohttp.ClientError("boom"))

    author = make_member(USER_IDS["member"], guild=guild)
    ctx = make_ctx(bot, author=author, guild=guild)
    ctx.message.reference = SimpleNamespace(resolved=_emoji_ref())
    await cog.steal.callback(cog, ctx, name="new_emoji")
    assert ctx.send.await_args.kwargs["embed"].author.name == "❌ Download Failed"


async def test_steal_forbidden(bot):
    cog = Steal(bot)
    guild = make_guild()
    guild.emoji_limit = 50
    guild.emojis = []
    guild.create_custom_emoji = AsyncMock(side_effect=discord.Forbidden(MagicMock(status=403), "nope"))
    cog._fetch = AsyncMock(return_value=b"data")

    author = make_member(USER_IDS["member"], guild=guild)
    ctx = make_ctx(bot, author=author, guild=guild)
    ctx.message.reference = SimpleNamespace(resolved=_emoji_ref())
    await cog.steal.callback(cog, ctx, name="new_emoji")
    assert ctx.send.await_args.kwargs["embed"].author.name == "❌ Permission Denied"


# ── Stickers ──────────────────────────────────────────────────────────────────
def _source_sticker(name="cool", fmt=discord.StickerFormatType.png):
    return SimpleNamespace(name=name, format=fmt, url="https://cdn.example/sticker.png")


def _created_sticker(name="cool", fmt=discord.StickerFormatType.png):
    sticker = MagicMock()
    sticker.name = name
    sticker.format = fmt
    sticker.url = f"https://cdn.example/{name}.png"
    return sticker


@pytest.mark.parametrize("raw,expected", [
    ("My Sticker!!1", "MySticker1"),
    ("  _pad_  ", "pad"),
    ("a", None),
    ("", None),
    (None, None),
    ("x" * 40, "x" * 30),
])
def test_sanitise_sticker_name(raw, expected):
    assert _sanitise_sticker_name(raw) == expected


def test_sticker_from_message():
    sticker = _source_sticker()
    assert Steal._sticker_from_message(make_real_message("", stickers=[sticker])) is sticker
    assert Steal._sticker_from_message(make_real_message("")) is None


@pytest.mark.parametrize("fmt,expected", [
    (discord.StickerFormatType.png, "png"),
    (discord.StickerFormatType.apng, "png"),
    (discord.StickerFormatType.gif, "gif"),
    (discord.StickerFormatType.lottie, "json"),
])
def test_sticker_extension(fmt, expected):
    assert Steal._sticker_extension(SimpleNamespace(format=fmt)) == expected


def test_filtered_sticker_name_avoids_collisions():
    guild = make_guild()
    guild.stickers = [SimpleNamespace(name="base"), SimpleNamespace(name="base_2")]
    assert Steal._filtered_sticker_name(guild, "base") == "base_3"
    assert Steal._filtered_sticker_name(guild, "fresh") == "fresh"


def test_prepare_image_for_sticker_static():
    buf = io.BytesIO()
    Image.new("RGB", (640, 480), (255, 0, 0)).save(buf, format="JPEG")

    data, extension = Steal._prepare_image_for_sticker(buf.getvalue())

    assert extension == "png"
    with Image.open(io.BytesIO(data)) as image:
        assert image.format == "PNG"
        assert image.size == (320, 320)


def test_prepare_image_for_sticker_animated():
    frames = [Image.new("RGBA", (64, 64), (i * 40, 0, 0, 255)) for i in range(3)]
    buf = io.BytesIO()
    frames[0].save(
        buf, format="GIF", save_all=True, append_images=frames[1:], duration=100, loop=0
    )

    data, extension = Steal._prepare_image_for_sticker(buf.getvalue())

    assert extension in {"png", "gif"}
    with Image.open(io.BytesIO(data)) as image:
        assert getattr(image, "n_frames", 1) == 3


def test_prepare_image_for_sticker_rejects_non_image():
    with pytest.raises(ValueError):
        Steal._prepare_image_for_sticker(b"definitely not an image")


def _sticker_cog(bot):
    cog = Steal(bot)
    guild = make_guild()
    guild.sticker_limit = 5
    guild.stickers = []
    guild.create_sticker = AsyncMock(
        side_effect=lambda **kwargs: _created_sticker(name=kwargs["name"])
    )
    cog._fetch = AsyncMock(return_value=b"\x89PNG sticker data")
    return cog, guild


async def test_stealsticker_from_sticker(bot):
    cog, guild = _sticker_cog(bot)
    author = make_member(USER_IDS["member"], guild=guild)
    ref = make_real_message("", author=author, stickers=[_source_sticker()])
    ctx = make_ctx(bot, author=author, guild=guild)
    ctx.message.reference = SimpleNamespace(resolved=ref)

    await cog.stealsticker.callback(cog, ctx, name="my_sticker")

    guild.create_sticker.assert_awaited_once()
    kwargs = guild.create_sticker.await_args.kwargs
    assert kwargs["name"] == "my_sticker"
    assert kwargs["description"] == "Stolen sticker: my_sticker"
    assert kwargs["emoji"] == "⭐"
    assert kwargs["file"].filename == "my_sticker.png"
    assert ctx.send.await_args.kwargs["embed"].author.name == "✅ Sticker Added — my_sticker"


async def test_stealsticker_from_attachment_image(bot, monkeypatch):
    cog, guild = _sticker_cog(bot)
    monkeypatch.setattr(
        Steal, "_prepare_image_for_sticker", staticmethod(lambda raw: (b"PNG", "png"))
    )
    attachment = SimpleNamespace(
        content_type="image/jpeg", size=1000, filename="photo.jpg", url="https://x/photo.jpg"
    )
    author = make_member(USER_IDS["member"], guild=guild)
    ref = make_real_message("", author=author, attachments=[attachment])
    ctx = make_ctx(bot, author=author, guild=guild)
    ctx.message.reference = SimpleNamespace(resolved=ref)

    await cog.stealsticker.callback(cog, ctx)

    kwargs = guild.create_sticker.await_args.kwargs
    assert kwargs["name"] == "photo"
    assert kwargs["file"].filename == "photo.png"


async def test_stealsticker_uses_command_attachment(bot, monkeypatch):
    cog, guild = _sticker_cog(bot)
    monkeypatch.setattr(
        Steal, "_prepare_image_for_sticker", staticmethod(lambda raw: (b"PNG", "png"))
    )
    attachment = SimpleNamespace(
        content_type="image/png", size=1000, filename="direct.png", url="https://x/direct.png"
    )
    author = make_member(USER_IDS["member"], guild=guild)
    ctx = make_ctx(bot, author=author, guild=guild)
    ctx.message.attachments = [attachment]
    ctx.message.reference = None

    await cog.stealsticker.callback(cog, ctx, name="direct")

    kwargs = guild.create_sticker.await_args.kwargs
    assert kwargs["name"] == "direct"
    assert kwargs["file"].filename == "direct.png"


async def test_stealsticker_without_source(bot):
    cog, guild = _sticker_cog(bot)
    author = make_member(USER_IDS["member"], guild=guild)
    ctx = make_ctx(bot, author=author, guild=guild)
    ctx.message.reference = SimpleNamespace(resolved=make_real_message("just text"))

    await cog.stealsticker.callback(cog, ctx)

    assert ctx.send.await_args.kwargs["embed"].author.name == "❌ Nothing to Steal"


async def test_stealsticker_slots_full(bot):
    cog, guild = _sticker_cog(bot)
    guild.sticker_limit = 1
    guild.stickers = [SimpleNamespace(name="used")]
    author = make_member(USER_IDS["member"], guild=guild)
    ref = make_real_message("", author=author, stickers=[_source_sticker()])
    ctx = make_ctx(bot, author=author, guild=guild)
    ctx.message.reference = SimpleNamespace(resolved=ref)

    await cog.stealsticker.callback(cog, ctx, name="new_sticker")

    guild.create_sticker.assert_not_awaited()
    assert ctx.send.await_args.kwargs["embed"].author.name == "❌ Sticker Slots Full"


async def test_stealsticker_invalid_name(bot):
    cog, guild = _sticker_cog(bot)
    author = make_member(USER_IDS["member"], guild=guild)
    ref = make_real_message("", author=author, stickers=[_source_sticker()])
    ctx = make_ctx(bot, author=author, guild=guild)
    ctx.message.reference = SimpleNamespace(resolved=ref)

    await cog.stealsticker.callback(cog, ctx, name="a")

    guild.create_sticker.assert_not_awaited()
    assert ctx.send.await_args.kwargs["embed"].author.name == "❌ Invalid Name"


async def test_stealsticker_forbidden(bot):
    cog, guild = _sticker_cog(bot)
    guild.create_sticker = AsyncMock(
        side_effect=discord.Forbidden(MagicMock(status=403), "nope")
    )
    author = make_member(USER_IDS["member"], guild=guild)
    ref = make_real_message("", author=author, stickers=[_source_sticker()])
    ctx = make_ctx(bot, author=author, guild=guild)
    ctx.message.reference = SimpleNamespace(resolved=ref)

    await cog.stealsticker.callback(cog, ctx, name="new_sticker")

    assert ctx.send.await_args.kwargs["embed"].author.name == "❌ Permission Denied"


async def test_steal_points_sticker_users_to_stealsticker(bot):
    cog = Steal(bot)
    guild = make_guild()
    author = make_member(USER_IDS["member"], guild=guild)
    ref = make_real_message("", author=author, stickers=[_source_sticker()])
    ctx = make_ctx(bot, author=author, guild=guild)
    ctx.message.reference = SimpleNamespace(resolved=ref)

    await cog.steal.callback(cog, ctx)

    assert ctx.send.await_args.kwargs["embed"].author.name == "❌ That's a Sticker"