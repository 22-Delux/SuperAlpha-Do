"""
cogs/steal.py — Steal emojis, stickers, or images and re-host them in your server.

Reply to a message containing a custom emoji or an image, then run
`alpha steal <name>`; the bot creates a new server emoji with that name.

To copy a sticker (including one used from another server) or turn an image
into a sticker, reply to a message containing a sticker/image — or attach an
image directly to the command — and run `alpha stealsticker <name>`.

Needs Manage Expressions permission. Slot limits (per-guild, scaled by boosts)
are respected, and the feature is throttled so concurrent steals don't trip
over each other.

Commands: steal, stealsticker
"""

import asyncio
import io
import re
from pathlib import Path

import aiohttp
import discord
from discord.ext import commands

from bot.cogs.checks import perms_or_developer

NAME_MIN = 2
NAME_MAX = 32

STICKER_NAME_MIN = 2
STICKER_NAME_MAX = 30
STICKER_DESC_MAX = 100
STICKER_SIZE = 320
STICKER_MAX_BYTES = 512 * 1024
STICKER_DEFAULT_EMOJI = "⭐"

_EMOJI_RE = re.compile(r"<(?P<animated>a)?:(?P<name>\w+):(?P<id>\d+)>")

try:  # Pillow is optional; without it we can still copy existing stickers.
    from PIL import Image, ImageOps
except ImportError:  # pragma: no cover - exercised only when Pillow is absent
    Image = None
    ImageOps = None


def _sanitise_name(raw: str | None) -> str | None:
    """A Discord emoji name: 2-32 chars of letters/digits/underscore."""
    if not raw:
        return None
    name = re.sub(r"[^\w]", "", raw)[:NAME_MAX].strip("_")
    return name if len(name) >= NAME_MIN else None


def _sanitise_sticker_name(raw: str | None) -> str | None:
    """A Discord sticker name: 2-30 chars of letters/digits/underscore."""
    if not raw:
        return None
    name = re.sub(r"[^\w]", "", raw)[:STICKER_NAME_MAX].strip("_")
    return name if len(name) >= STICKER_NAME_MIN else None


class Steal(commands.Cog, name="steal"):
    """Steal emojis, stickers, and images to add them to your server."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self._locks: dict[int, asyncio.Lock] = {}

    def _make_embed(self, title: str, color: int, description: str = "") -> discord.Embed:
        embed = discord.Embed(color=color)
        embed.set_author(name=title, icon_url=None)
        if description:
            embed.description = description
        return embed

    def _lock_for(self, guild_id: int) -> asyncio.Lock:
        return self._locks.setdefault(guild_id, asyncio.Lock())

    # ── Source extraction ─────────────────────────────────────────────────────
    @staticmethod
    def _emoji_from_message(message: discord.Message) -> tuple[int, bool] | None:
        """First custom emoji in a message's content -> (id, is_animated)."""
        hit = _EMOJI_RE.search(message.content or "")
        if not hit:
            return None
        return int(hit.group("id")), bool(hit.group("animated"))

    @staticmethod
    def _sticker_from_message(message: discord.Message) -> discord.StickerItem | None:
        """First sticker attached to a message, if any."""
        stickers = getattr(message, "stickers", None) or []
        return stickers[0] if stickers else None

    @staticmethod
    def _image_source_from_message(
        message: discord.Message,
    ) -> tuple[str, bool, str | None] | None:
        """Largest image attachment or first embed image -> (url, animated, name)."""
        picks = [a for a in message.attachments
                 if a.content_type and a.content_type.lower().startswith("image")]
        if picks:
            largest = max(picks, key=lambda a: a.size or 0)
            low = (largest.filename or "").lower()
            animated = low.endswith(".gif") or (largest.content_type or "").lower() == "image/gif"
            stem = Path(largest.filename or "").stem or None
            return str(largest.url), animated, stem
        for embed in message.embeds:
            for probe in (embed.image, embed.thumbnail):
                if probe.url:
                    return str(probe.url), False, None
        return None

    @staticmethod
    def _image_from_message(message: discord.Message) -> tuple[str, bool] | None:
        """Largest image attachment or first embed image -> (url, is_animated)."""
        source = Steal._image_source_from_message(message)
        return (source[0], source[1]) if source else None

    async def _fetch(self, url: str) -> bytes:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                resp.raise_for_status()
                return await resp.read()

    @staticmethod
    def _filtered_name(guild: discord.Guild, base: str) -> str:
        """Pick `base`, `base_2`, `base_3`, ... if the name is already taken."""
        taken = {e.name for e in guild.emojis}
        candidate, i = base, 1
        while candidate in taken:
            i += 1
            suffix = str(i)
            candidate = f"{base[: NAME_MAX - len(suffix) - 1]}_{i}"
        return candidate

    @staticmethod
    def _filtered_sticker_name(guild: discord.Guild, base: str) -> str:
        """Pick `base`, `base_2`, `base_3`, ... if the name is already taken."""
        taken = {s.name for s in getattr(guild, "stickers", [])}
        candidate, i = base, 1
        while candidate in taken:
            i += 1
            suffix = str(i)
            candidate = f"{base[: STICKER_NAME_MAX - len(suffix) - 1]}_{i}"
        return candidate

    @staticmethod
    def _sticker_extension(sticker: discord.StickerItem) -> str:
        """File extension for a sticker's CDN asset."""
        fmt = getattr(sticker, "format", None)
        if fmt is discord.StickerFormatType.lottie:
            return "json"
        if fmt is discord.StickerFormatType.gif:
            return "gif"
        return "png"

    @staticmethod
    def _prepare_image_for_sticker(raw: bytes) -> tuple[bytes, str]:
        """Resize/convert an uploaded image into a Discord-compatible sticker.

        Returns ``(data, extension)``. Animated images become APNG (or GIF when
        the APNG would be too large); static images become PNG.
        """
        if Image is None or ImageOps is None:
            raise ValueError(
                "Image conversion isn't available on this bot. "
                "Please upload a PNG or GIF instead."
            )

        try:
            with Image.open(io.BytesIO(raw)) as image:
                frame_count = getattr(image, "n_frames", 1)
                animated = bool(getattr(image, "is_animated", False) and frame_count > 1)
                duration = image.info.get("duration", 100)
                loop = image.info.get("loop", 0)

                frames = []
                for index in range(frame_count if animated else 1):
                    if animated:
                        image.seek(index)
                    frames.append(
                        ImageOps.pad(
                            image.convert("RGBA"),
                            (STICKER_SIZE, STICKER_SIZE),
                            color=(0, 0, 0, 0),
                        )
                    )
        except Exception as exc:
            raise ValueError(
                "I couldn't read that image. Try a PNG, JPEG, WebP, or GIF."
            ) from exc

        if animated:
            out = io.BytesIO()
            frames[0].save(
                out,
                format="PNG",
                save_all=True,
                append_images=frames[1:],
                duration=duration,
                loop=loop,
                optimize=True,
            )
            data = out.getvalue()
            if len(data) <= STICKER_MAX_BYTES:
                return data, "png"

            out = io.BytesIO()
            frames[0].save(
                out,
                format="GIF",
                save_all=True,
                append_images=frames[1:],
                duration=duration,
                loop=loop,
                optimize=True,
                disposal=2,
            )
            return out.getvalue(), "gif"

        out = io.BytesIO()
        frames[0].save(out, format="PNG", optimize=True)
        data = out.getvalue()
        if len(data) <= STICKER_MAX_BYTES:
            return data, "png"

        # Too big for Discord's 512 KB sticker limit — fall back to a GIF.
        out = io.BytesIO()
        frames[0].save(out, format="GIF", optimize=True)
        return out.getvalue(), "gif"

    # ── Emoji command ─────────────────────────────────────────────────────────
    @commands.command(name="steal", aliases=["emojisteal", "copysteal"])
    @perms_or_developer(manage_expressions=True)
    async def steal(self, ctx: commands.Context, *, name: str | None = None) -> None:
        """Steal an emoji/image from a message you reply to. Usage: alpha steal <name>"""
        if not ctx.message.reference:
            embed = self._make_embed(
                "❌ Nothing to Steal", 0xE74C3C,
                f"Reply to a message containing an emoji or image, then use "
                f"`{ctx.prefix}steal <name>`.\nExample: reply to a message with a "
                f"custom emoji and type `{ctx.prefix}steal my_new_emoji`.",
            )
            await ctx.send(embed=embed)
            return

        try:
            ref = ctx.message.reference.resolved
            if ref is None:
                ref = await ctx.message.channel.fetch_message(ctx.message.reference.message_id)
        except discord.HTTPException:
            embed = self._make_embed(
                "❌ Cannot Read", 0xE74C3C,
                "I couldn't read the message you replied to.",
            )
            await ctx.send(embed=embed)
            return
        if not isinstance(ref, discord.Message):
            embed = self._make_embed(
                "❌ Nothing to Steal", 0xE74C3C,
                "The message you replied to doesn't contain an emoji or image.",
            )
            await ctx.send(embed=embed)
            return

        name = name.strip() if name else None

        source = self._emoji_from_message(ref)
        default_name = None
        if source:
            emoji_id, animated = source
            if not name:
                hit = _EMOJI_RE.search(ref.content or "")
                default_name = hit.group("name") if hit else None
            url = f"https://cdn.discordapp.com/emojis/{emoji_id}.{'gif' if animated else 'png'}"
        else:
            image = self._image_from_message(ref)
            if not image:
                if self._sticker_from_message(ref):
                    embed = self._make_embed(
                        "❌ That's a Sticker", 0xE74C3C,
                        f"That message contains a sticker. Use "
                        f"`{ctx.prefix}stealsticker <name>` to copy it as a sticker.",
                    )
                else:
                    embed = self._make_embed(
                        "❌ Nothing to Steal", 0xE74C3C,
                        "That message has no custom emoji, image attachment, or embed image to steal.",
                    )
                await ctx.send(embed=embed)
                return
            url, animated = image

        emoji_name = _sanitise_name(name or default_name)
        if not emoji_name:
            embed = self._make_embed(
                "❌ Invalid Name", 0xE74C3C,
                f"Emoji names need **{NAME_MIN}-{NAME_MAX}** letters, digits, or underscores. "
                f"You gave: `{name or default_name or '(none)'}`.",
            )
            await ctx.send(embed=embed)
            return

        async with self._lock_for(ctx.guild.id):
            emoji_limit = ctx.guild.emoji_limit
            counts = {"static": 0, "animated": 0}
            for e in ctx.guild.emojis:
                counts["animated" if e.animated else "static"] += 1
            kind = "animated" if animated else "static"
            if counts[kind] >= emoji_limit:
                embed = self._make_embed(
                    "❌ Emoji Slots Full", 0xE74C3C,
                    f"This server has reached its **{emoji_limit}** {kind} emoji slot limit. "
                    "Remove an emoji or boost the server to add more.",
                )
                await ctx.send(embed=embed)
                return

            try:
                raw = await self._fetch(url)
            except (aiohttp.ClientError, UnicodeDecodeError, ValueError):
                embed = self._make_embed(
                    "❌ Download Failed", 0xE74C3C,
                    "I couldn't download that emoji/image. Source may be unavailable.",
                )
                await ctx.send(embed=embed)
                return

            final_name = self._filtered_name(ctx.guild, emoji_name)
            try:
                emoji = await ctx.guild.create_custom_emoji(
                    name=final_name,
                    image=raw,
                    reason=f"Stolen by {ctx.author}",
                )
            except discord.Forbidden:
                embed = self._make_embed(
                    "❌ Permission Denied", 0xE74C3C,
                    "I need the **Manage Expressions** permission to add emojis.",
                )
                await ctx.send(embed=embed)
                return
            except discord.HTTPException as exc:
                embed = self._make_embed(
                    "❌ Emoji Not Added", 0xE74C3C,
                    f"Discord rejected the emoji: `{exc.text or exc}`. "
                    "It may be too large (Discord allows up to 256 KB).",
                )
                await ctx.send(embed=embed)
                return

        shown = f"<{'a' if emoji.animated else ''}:{emoji.name}:{emoji.id}>"
        embed = discord.Embed(color=0x2ECC71)
        embed.set_author(name=f"✅ Stolen & Added — :{emoji.name}:")
        embed.add_field(name="Emoji", value=shown, inline=True)
        embed.add_field(name="Name", value=f"`{emoji.name}`", inline=True)
        embed.set_image(url=emoji.url)
        embed.set_footer(text=f"Stolen from {ref.author.display_name} · Added by {ctx.author.display_name}")
        await ctx.send(embed=embed)

    # ── Sticker command ───────────────────────────────────────────────────────
    @commands.command(
        name="stealsticker",
        aliases=["addsticker", "stickersteal", "copysticker"],
    )
    @perms_or_developer(manage_expressions=True)
    async def stealsticker(
        self,
        ctx: commands.Context,
        name: str | None = None,
        *,
        description: str | None = None,
    ) -> None:
        """Steal a sticker or turn an image into a sticker. Usage: alpha stealsticker <name> [description]"""
        source_message = ctx.message
        ref = None

        if ctx.message.reference:
            try:
                ref = ctx.message.reference.resolved
                if ref is None:
                    ref = await ctx.message.channel.fetch_message(
                        ctx.message.reference.message_id
                    )
            except discord.HTTPException:
                embed = self._make_embed(
                    "❌ Cannot Read", 0xE74C3C,
                    "I couldn't read the message you replied to.",
                )
                await ctx.send(embed=embed)
                return
            if isinstance(ref, discord.Message):
                source_message = ref

        sticker = self._sticker_from_message(source_message)
        if sticker:
            url = sticker.url
            extension = self._sticker_extension(sticker)
            default_name = sticker.name
            convert = False
        else:
            image = self._image_source_from_message(source_message)
            if not image:
                embed = self._make_embed(
                    "❌ Nothing to Steal", 0xE74C3C,
                    "Reply to a message with a sticker or image, or attach an image "
                    "to this command.",
                )
                await ctx.send(embed=embed)
                return
            url, _animated, default_name = image
            extension = "png"
            convert = True

        sticker_name = _sanitise_sticker_name(
            name.strip() if name else default_name
        )
        if not sticker_name:
            embed = self._make_embed(
                "❌ Invalid Name", 0xE74C3C,
                f"Sticker names need **{STICKER_NAME_MIN}-{STICKER_NAME_MAX}** letters, "
                f"digits, or underscores. You gave: "
                f"`{name or default_name or '(none)'}`.",
            )
            await ctx.send(embed=embed)
            return

        desc = (description or "").strip()[:STICKER_DESC_MAX]
        if len(desc) < 2:
            desc = f"Stolen sticker: {sticker_name}"[:STICKER_DESC_MAX]

        async with self._lock_for(ctx.guild.id):
            sticker_limit = ctx.guild.sticker_limit
            if len(ctx.guild.stickers) >= sticker_limit:
                embed = self._make_embed(
                    "❌ Sticker Slots Full", 0xE74C3C,
                    f"This server has reached its **{sticker_limit}** sticker slot limit. "
                    "Remove a sticker or boost the server to add more.",
                )
                await ctx.send(embed=embed)
                return

            try:
                raw = await self._fetch(url)
            except (aiohttp.ClientError, UnicodeDecodeError, ValueError):
                embed = self._make_embed(
                    "❌ Download Failed", 0xE74C3C,
                    "I couldn't download that sticker/image. Source may be unavailable.",
                )
                await ctx.send(embed=embed)
                return

            if convert:
                try:
                    raw, extension = self._prepare_image_for_sticker(raw)
                except ValueError as exc:
                    embed = self._make_embed(
                        "❌ Unsupported Image", 0xE74C3C, str(exc),
                    )
                    await ctx.send(embed=embed)
                    return

            final_name = self._filtered_sticker_name(ctx.guild, sticker_name)
            try:
                created = await ctx.guild.create_sticker(
                    name=final_name,
                    description=desc,
                    emoji=STICKER_DEFAULT_EMOJI,
                    file=discord.File(io.BytesIO(raw), filename=f"{final_name}.{extension}"),
                    reason=f"Stolen by {ctx.author}",
                )
            except discord.Forbidden:
                embed = self._make_embed(
                    "❌ Permission Denied", 0xE74C3C,
                    "I need the **Manage Expressions** permission to add stickers.",
                )
                await ctx.send(embed=embed)
                return
            except discord.HTTPException as exc:
                embed = self._make_embed(
                    "❌ Sticker Not Added", 0xE74C3C,
                    f"Discord rejected the sticker: `{exc.text or exc}`. "
                    "It may be too large (Discord allows up to 512 KB) or the "
                    "server may not support Lottie stickers.",
                )
                await ctx.send(embed=embed)
                return

        embed = discord.Embed(color=0x2ECC71)
        embed.set_author(name=f"✅ Sticker Added — {created.name}")
        embed.add_field(name="Sticker", value=f"`{created.name}`", inline=True)
        embed.add_field(name="Format", value=created.format.name.upper(), inline=True)
        if created.format is not discord.StickerFormatType.lottie:
            embed.set_image(url=created.url)
        embed.set_footer(
            text=f"Stolen from {source_message.author.display_name} · "
            f"Added by {ctx.author.display_name}"
        )
        await ctx.send(embed=embed)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Steal(bot))
