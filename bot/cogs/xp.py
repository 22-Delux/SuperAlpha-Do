"""
cogs/xp.py — XP and ranking system with SP currency.
Awards XP/SP for: chatting, VC time, using bot commands.

Persistence lives in ``bot.models.xp_store``; level math in
``bot.services.leveling``. This file re-exports those symbols so existing
imports (``from bot.cogs.xp import award_game_xp``) keep working.
"""

import asyncio
import random
import time
from datetime import datetime, timedelta, timezone

import discord
from discord import app_commands
from discord.ext import commands

from bot.cogs.checks import perms_or_developer
from bot.models.xp_store import (
    flush_all,
    get_level_channel,
    init_db,
    is_xp_enabled,
    load_user,
    save_user,
    set_level_channel,
    set_xp_enabled,
    top_users,
    migrate_legacy_data_to_postgres,
    reset_weekly_leaderboard,
)
from bot.services.users import GlobalUser, GuildMember
from bot.services.embeds import leaderboard_embed, xp_embed, brand_embed, COLOR_XP, COLOR_SUCCESS, COLOR_INFO, add_author_brand
from bot.services import leveling
from bot.services.leveling import (
    award_game_xp,
    cumulative_xp,
    get_level_progress,
    level_from_xp,
    xp_for_level,
)

__all__ = [
    "XP",
    "award_game_xp",
    "cumulative_xp",
    "flush_all",
    "get_level_channel",
    "get_level_progress",
    "init_db",
    "is_xp_enabled",
    "level_from_xp",
    "load_user",
    "save_user",
    "set_level_channel",
    "set_xp_enabled",
    "top_users",
    "xp_for_level",
]


class XP(commands.Cog, name="xp"):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self._vc_sessions: dict[int, float] = {}
        self._last_message: dict[int, float] = {}

    async def _leaderboard_name(
        self, user_id: int, guild: discord.Guild | None = None
    ) -> str:
        user = guild.get_member(user_id) if guild is not None else None
        if user is None:
            user = self.bot.get_user(user_id)
        if user is None:
            try:
                user = await self.bot.fetch_user(user_id)
            except discord.NotFound:
                return f"Unknown user ({user_id})"
        return user.display_name[:15]

    async def cog_load(self) -> None:
        if hasattr(self.bot, "db") and self.bot.db:
            await init_db(self.bot.db)
            
            # UNCOMMENT THIS TO MIGRATE LEGACY DATA (Already done by the GOAT Peikaw)
            # await migrate_legacy_data_to_postgres(self.bot.db)
        self._weekly_reset_task = asyncio.create_task(self._weekly_reset_loop())

    async def cog_unload(self) -> None:
        if getattr(self, "_weekly_reset_task", None) is not None and not self._weekly_reset_task.done():
            self._weekly_reset_task.cancel()
            self._weekly_reset_task = None
        self._vc_sessions.clear()
        self._last_message.clear()

    async def _weekly_reset_loop(self) -> None:
        IST = timezone(timedelta(hours=5, minutes=30))
        while True:
            now = datetime.now(IST)
            days_until_monday = (0 - now.weekday()) % 7
            next_reset = now.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=days_until_monday)
            if next_reset <= now:
                next_reset += timedelta(days=7)
            await asyncio.sleep((next_reset - now).total_seconds())
            if hasattr(self.bot, "db") and self.bot.db:
                try:
                    await reset_weekly_leaderboard(self.bot.db)
                except Exception:
                    pass

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if message.author.bot:
            return
        if not message.guild:
            return
        if not await is_xp_enabled(self.bot.db, message.guild.id):
            return

        user_id = message.author.id
        now = time.time()
        
        # We can track last_message in memory or directly from db object loaded
        data = await load_user(self.bot.db, user_id)

        if now - data["last_message"] < 30:
            return

        data["messages"] += 1
        data["last_message"] = now

        xp_gain = random.randint(10, 25)
        sp_gain = random.randint(1, 3)

        data["xp"] += xp_gain
        data["sp"] += sp_gain
        data["weekly_xp"] = data.get("weekly_xp", 0) + xp_gain
        data["weekly_sp"] = data.get("weekly_sp", 0) + sp_gain

        old_level = data["level"]
        data["level"] = level_from_xp(data["xp"])

        await save_user(self.bot.db, user_id, data)

        if data["level"] > old_level:
            try:
                embed = discord.Embed(
                    color=0xF1C40F,
                    title="🎉 Level Up!",
                    description=f"**{message.author.mention}** reached **Level {data['level']}**!"
                )
                embed.add_field(name="XP", value=f"{xp_gain} xp earned", inline=True)
                embed.add_field(name="SP", value=f"{sp_gain} sp earned", inline=True)
                channel = None
                level_channel_id = await get_level_channel(self.bot.db, message.guild.id)
                if level_channel_id:
                    channel = message.guild.get_channel(level_channel_id)
                await (channel or message.channel).send(embed=embed)
            except Exception:
                pass

    @commands.Cog.listener()
    async def on_voice_state_update(
        self,
        member: discord.Member,
        before: discord.VoiceState,
        after: discord.VoiceState,
    ) -> None:
        if member.bot:
            return
        if not member.guild:
            return
        if not await is_xp_enabled(self.bot.db, member.guild.id):
            return

        user_id = member.id
        data = await load_user(self.bot.db, user_id)

        if after.channel and not before.channel:
            data["vc_start"] = time.time()
            await save_user(self.bot.db, user_id, data)

        elif before.channel and not after.channel:
            if data["vc_start"] > 0:
                elapsed = time.time() - data["vc_start"]
                minutes = int(elapsed / 60)

                if minutes >= 1:
                    xp_gain = minutes * 5
                    sp_gain = minutes // 3
                    data["xp"] += xp_gain
                    data["sp"] += sp_gain
                    data["vc_time"] += int(elapsed)
                    data["weekly_xp"] = data.get("weekly_xp", 0) + xp_gain
                    data["weekly_sp"] = data.get("weekly_sp", 0) + sp_gain
                    data["weekly_vc_time"] = data.get("weekly_vc_time", 0) + int(elapsed)
                    data["level"] = level_from_xp(data["xp"])

                data["vc_start"] = 0
                await save_user(self.bot.db, user_id, data)

    async def _award_command_xp(self, user_id: int) -> None:
        data = await load_user(self.bot.db, user_id)
        xp_gain = random.randint(5, 15)
        sp_gain = random.randint(1, 2)
        data["xp"] += xp_gain
        data["sp"] += sp_gain
        data["weekly_xp"] = data.get("weekly_xp", 0) + xp_gain
        data["weekly_sp"] = data.get("weekly_sp", 0) + sp_gain
        data["commands_used"] += 1
        data["level"] = level_from_xp(data["xp"])
        await save_user(self.bot.db, user_id, data)

    @commands.Cog.listener()
    async def on_command(self, ctx: commands.Context) -> None:
        if ctx.author.bot:
            return
        if ctx.guild and not await is_xp_enabled(self.bot.db, ctx.guild.id):
            return
        await self._award_command_xp(ctx.author.id)

    @commands.Cog.listener()
    async def on_interaction(self, interaction: discord.Interaction) -> None:
        if interaction.user.bot:
            return
        if interaction.guild and not await is_xp_enabled(self.bot.db, interaction.guild.id):
            return
        await self._award_command_xp(interaction.user.id)

    def _make_embed(self, title: str, color: int, description: str = "") -> discord.Embed:
        embed = discord.Embed(color=color)
        embed.set_author(name=title)
        if description:
            embed.description = description
        return embed

    @commands.command(name="rank", aliases=["profile", "stats"])
    async def rank(self, ctx: commands.Context, *, member: discord.Member = None) -> None:
        """View your rank and stats. Usage: alpha rank [user]"""
        member = member or ctx.author
        data = await load_user(ctx.bot.db, member.id)
        xp_in_level, xp_needed, level = get_level_progress(data["xp"])

        vc_time_min = data["vc_time"] // 60
        hours = vc_time_min // 60
        mins = vc_time_min % 60

        embed = discord.Embed(color=0x9B59B6)
        embed.set_author(name=f"📊 {member.display_name}'s Stats")
        embed.set_thumbnail(url=member.display_avatar.url)

        embed.add_field(name="Level", value=f"**{level}**", inline=True)
        embed.add_field(name="Total XP", value=f"**{data['xp']:,}**", inline=True)
        embed.add_field(name="SP Balance", value=f"**{data['sp']:,}**", inline=True)

        embed.add_field(name="Progress", value=f"`{'█' * int(xp_in_level / xp_needed * 10)}{'░' * (10 - int(xp_in_level / xp_needed * 10))}`", inline=False)
        embed.add_field(name="XP in Level", value=f"{xp_in_level} / {xp_needed}", inline=True)
        embed.add_field(name="Messages", value=f"{data['messages']:,}", inline=True)

        embed.add_field(name="VC Time", value=f"{hours}h {mins}m", inline=True)
        embed.add_field(name="Commands Used", value=f"{data['commands_used']:,}", inline=True)

        await ctx.send(embed=embed)

    @commands.command(name="leaderboard", aliases=["lb", "top"])
    async def leaderboard(self, ctx: commands.Context, first: str = "xp", second: str = None) -> None:
        scope = "universal"
        type_key = "xp"
        for val in (first, second):
            if val is None:
                continue
            low = str(val).lower()
            if low in ("universal", "guild", "server", "global"):
                scope = "universal" if low in ("universal", "global") else "guild"
                if low == "server":
                    scope = "guild"
            elif low in ("xp", "sp", "messages", "vc"):
                type_key = low

        weekly = scope == "universal"
        user_ids = None
        if scope == "guild" and ctx.guild is not None:
            user_ids = [m.id for m in getattr(ctx.guild, "members", []) if not getattr(m, "bot", False)]
            if not user_ids:
                user_ids = None

        top = await top_users(ctx.bot.db, type_key, 10, weekly=weekly, user_ids=user_ids)

        field_name = {"sp": "SP", "messages": "Messages", "vc": "VC Time", "xp": "XP"}[type_key]
        if scope == "universal":
            title = "🌍 Universal Leaderboard — " + field_name
        else:
            title = "🏠 Guild Leaderboard — " + field_name

        embed = discord.Embed(color=0xF1C40F)
        embed.set_author(name=title)

        if not top:
            embed.description = "No data yet!"
            await ctx.send(embed=embed)
            return

        lines = []
        medals = ["🥇", "🥈", "🥉"]
        for i, (user_id, data) in enumerate(top):
            name = await self._leaderboard_name(user_id, ctx.guild)

            if type_key == "vc":
                mins = data["vc_time"] // 60
                val = f"{mins // 60}h {mins % 60}m"
            elif type_key == "messages":
                val = f"{data['messages']:,}"
            elif type_key == "sp":
                val = f"{data['sp']:,}"
            else:
                val = f"{data['xp']:,}"

            medal = medals[i] if i < 3 else f"`{i+1}.`"
            lines.append(f"{medal} **{name}** — {data['level']} lvl — {val} {field_name}")

        embed.description = "\n".join(lines)
        embed.set_footer(text=f"Showing top {len(top)} | Universal resets Monday 00:00 IST")
        await ctx.send(embed=embed)

    @commands.command(name="daily", aliases=["claim"])
    async def daily(self, ctx: commands.Context) -> None:
        """Claim your daily SP reward. Usage: alpha daily"""
        user_id = ctx.author.id
        data = await load_user(ctx.bot.db, user_id)

        now = datetime.now(timezone.utc)
        today = now.strftime("%Y-%m-%d")

        if data["daily_claimed"] == today:
            next_claim = datetime.strptime(data["daily_claimed"], "%Y-%m-%d").replace(tzinfo=timezone.utc) + timedelta(days=1)
            remaining = next_claim - now
            hours = int(remaining.total_seconds() / 3600)
            minutes = int((remaining.total_seconds() % 3600) / 60)
            embed = self._make_embed("❌ Already Claimed", 0xE74C3C, f"Come back in **{hours}h {minutes}m**")
            await ctx.send(embed=embed)
            return

        base_reward = 100
        streak_bonus = data["streak"] * 10
        total_reward = base_reward + streak_bonus

        data["sp"] += total_reward
        data["daily_claimed"] = today
        data["streak"] += 1

        await save_user(ctx.bot.db, user_id, data)

        embed = discord.Embed(color=0x2ECC71)
        embed.set_author(name="💰 Daily Claimed!")
        embed.description = f"**+{total_reward} SP**"
        embed.add_field(name="Base", value=f"{base_reward} SP", inline=True)
        embed.add_field(name="Streak Bonus", value=f"+{streak_bonus} SP", inline=True)
        embed.add_field(name="🔥 Streak", value=f"{data['streak']} days", inline=True)
        embed.add_field(name="Total SP", value=f"**{data['sp']:,}**", inline=False)
        await ctx.send(embed=embed)

    @commands.command(name="give", aliases=["pay", "transfer"])
    async def give(self, ctx: commands.Context, member: discord.Member, amount: int) -> None:
        """Give SP to another user. Usage: alpha give @user <amount>"""
        if member.bot:
            embed = self._make_embed("❌ Invalid User", 0xE74C3C, "Cannot give SP to bots")
            await ctx.send(embed=embed)
            return

        if member.id == ctx.author.id:
            embed = self._make_embed("❌ Invalid", 0xE74C3C, "Cannot give SP to yourself")
            await ctx.send(embed=embed)
            return

        if amount <= 0:
            embed = self._make_embed("❌ Invalid Amount", 0xE74C3C, "Amount must be positive")
            await ctx.send(embed=embed)
            return

        sender_data = await load_user(ctx.bot.db, ctx.author.id)
        if sender_data["sp"] < amount:
            embed = self._make_embed("❌ Insufficient SP", 0xE74C3C, f"You only have **{sender_data['sp']:,} SP**")
            await ctx.send(embed=embed)
            return

        sender_data["sp"] -= amount
        await save_user(ctx.bot.db, ctx.author.id, sender_data)

        receiver_data = await load_user(ctx.bot.db, member.id)
        receiver_data["sp"] += amount
        await save_user(ctx.bot.db, member.id, receiver_data)

        embed = discord.Embed(color=0x2ECC71)
        embed.set_author(name="💸 SP Transferred")
        embed.description = f"**{ctx.author.mention}** sent **{amount:,} SP** to **{member.mention}**"
        await ctx.send(embed=embed)

    @commands.command(name="bet")
    async def bet(self, ctx: commands.Context, amount: int) -> None:
        """Bet SP for a chance to double it. Usage: alpha bet <amount>"""
        if amount <= 0:
            embed = self._make_embed("❌ Invalid Amount", 0xE74C3C, "Amount must be positive")
            await ctx.send(embed=embed)
            return

        user_data = await load_user(ctx.bot.db, ctx.author.id)
        if user_data["sp"] < amount:
            embed = self._make_embed("❌ Insufficient SP", 0xE74C3C, f"You only have **{user_data['sp']:,} SP**")
            await ctx.send(embed=embed)
            return

        win = random.random() < 0.5

        if win:
            user_data["sp"] += amount
            embed = discord.Embed(color=0x2ECC71)
            embed.set_author(name="🎉 You Won!")
            embed.description = f"You doubled your **{amount:,} SP** to **{user_data['sp']:,} SP**!"
        else:
            user_data["sp"] -= amount
            embed = discord.Embed(color=0xE74C3C)
            embed.set_author(name="😢 You Lost!")
            embed.description = f"You lost **{amount:,} SP**. Now at **{user_data['sp']:,} SP**"

        await save_user(ctx.bot.db, ctx.author.id, user_data)
        await ctx.send(embed=embed)

    @commands.command(name="work")
    @commands.cooldown(1, 3600, commands.BucketType.user)
    async def work(self, ctx: commands.Context) -> None:
        """Work to earn SP (1 hour cooldown). Usage: alpha work"""
        user_data = await load_user(ctx.bot.db, ctx.author.id)
        reward = random.randint(50, 200)
        user_data["sp"] += reward
        await save_user(ctx.bot.db, ctx.author.id, user_data)

        embed = discord.Embed(color=0x3498DB)
        embed.set_author(name="💼 Work Complete!")
        embed.description = f"You earned **{reward:,} SP**!\nTotal: **{user_data['sp']:,} SP**"
        await ctx.send(embed=embed)

    @app_commands.command(name="rank", description="View your rank and stats")
    @app_commands.describe(member="User to check (optional)")
    async def slash_rank(self, interaction: discord.Interaction, member: discord.Member = None) -> None:
        await interaction.response.defer()
        member = member or interaction.user
        data = await load_user(interaction.client.db, member.id)
        xp_in_level, xp_needed, level = get_level_progress(data["xp"])

        embed = discord.Embed(color=0x9B59B6)
        embed.set_author(name=f"📊 {member.display_name}'s Stats")
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.add_field(name="Level", value=f"**{level}**", inline=True)
        embed.add_field(name="Total XP", value=f"**{data['xp']:,}**", inline=True)
        embed.add_field(name="SP Balance", value=f"**{data['sp']:,}**", inline=True)
        embed.add_field(name="Progress", value=f"`{'█' * int(xp_in_level / xp_needed * 10)}{'░' * (10 - int(xp_in_level / xp_needed * 10))}`", inline=False)
        embed.add_field(name="XP in Level", value=f"{xp_in_level} / {xp_needed}", inline=True)
        await interaction.followup.send(embed=embed)

    @app_commands.command(name="leaderboard", description="View the server leaderboard")
    @app_commands.describe(type="Type of leaderboard (xp, sp, messages, vc)")
    @app_commands.choices(type=[
        app_commands.Choice(name="XP", value="xp"),
        app_commands.Choice(name="SP", value="sp"),
        app_commands.Choice(name="Messages", value="messages"),
        app_commands.Choice(name="VC Time", value="vc"),
    ])
    async def slash_leaderboard(self, interaction: discord.Interaction, type: str = "xp") -> None:
        await interaction.response.defer()
        if type == "sp":
            title = "💰 SP Leaderboard"
            field_name = "SP"
        elif type == "messages":
            title = "💬 Messages Leaderboard"
            field_name = "Messages"
        elif type == "vc":
            title = "🎤 VC Time Leaderboard"
            field_name = "VC Time"
        else:
            type = "xp"
            title = "⭐ XP Leaderboard"
            field_name = "XP"

        top = await top_users(interaction.client.db, type, 10, weekly=True)
        embed = discord.Embed(color=0xF1C40F)
        embed.set_author(name=title)

        if not top:
            embed.description = "No data yet!"
            await interaction.followup.send(embed=embed)
            return

        lines = []
        medals = ["🥇", "🥈", "🥉"]
        for i, (user_id, data) in enumerate(top):
            name = await self._leaderboard_name(user_id, interaction.guild)

            if type == "vc":
                mins = data["vc_time"] // 60
                val = f"{mins // 60}h {mins % 60}m"
            elif type == "messages":
                val = f"{data['messages']:,}"
            elif type == "sp":
                val = f"{data['sp']:,}"
            else:
                val = f"{data['xp']:,}"
            medal = medals[i] if i < 3 else f"`{i+1}.`"
            lines.append(f"{medal} **{name}** — {data['level']} lvl — {val} {field_name}")

        embed.description = "\n".join(lines)
        await interaction.followup.send(embed=embed)

    @commands.command(name="levelchannel", aliases=["lvlchannel", "levelupchannel"])
    @perms_or_developer(administrator=True)
    async def levelchannel(self, ctx: commands.Context, action: str = None, channel: discord.TextChannel = None) -> None:
        """Set the channel for level-up messages. Usage: alpha levelchannel [set #channel|off|status]"""
        if not action:
            current = await get_level_channel(ctx.bot.db, ctx.guild.id)
            if current:
                ch = ctx.guild.get_channel(current)
                desc = f"Level-up messages are sent to **{ch.mention if ch else f'<#{current}>'}**."
            else:
                desc = "Level-up messages are sent where the user last chatted. Set a channel with `alpha levelchannel set #channel`."
            embed = discord.Embed(color=0x9B59B6)
            embed.set_author(name="📣 Level-Up Channel")
            embed.description = desc
            await ctx.send(embed=embed)
            return

        action = action.lower()

        if action in ["set", "channel"]:
            if channel is None:
                embed = self._make_embed("❌ Missing Channel", 0xE74C3C, "Usage: `alpha levelchannel set #channel`")
                await ctx.send(embed=embed)
                return
            await set_level_channel(ctx.bot.db, ctx.guild.id, channel.id)
            embed = discord.Embed(color=0x2ECC71)
            embed.set_author(name="✅ Level-Up Channel Set")
            embed.description = f"Level-up messages will now be sent to **{channel.mention}**."
            await ctx.send(embed=embed)

        elif action in ["off", "disable", "none", "clear", "reset"]:
            await set_level_channel(ctx.bot.db, ctx.guild.id, None)
            embed = discord.Embed(color=0x95A5A6)
            embed.set_author(name="🔕 Level-Up Channel Cleared")
            embed.description = "Level-up messages will be sent where the user last chatted."
            await ctx.send(embed=embed)

        else:
            embed = self._make_embed("❌ Invalid Action", 0xE74C3C, "Usage: `alpha levelchannel set #channel | off | status`")
            await ctx.send(embed=embed)

    @levelchannel.error
    async def levelchannel_error(self, ctx: commands.Context, error) -> None:
        if isinstance(error, commands.MissingPermissions):
            embed = self._make_embed("❌ Permission Denied", 0xE74C3C, "You need **Administrator** permission to use this command.")
            await ctx.send(embed=embed)

    @commands.command(name="xpsystem")
    @perms_or_developer(administrator=True)
    async def xpsystem(self, ctx: commands.Context, action: str = None) -> None:
        """Enable/disable XP system. Usage: alpha xpsystem [enable|disable|status]"""
        if not action:
            enabled = await is_xp_enabled(ctx.bot.db, ctx.guild.id)
            status = "✅ Enabled" if enabled else "❌ Disabled"
            embed = discord.Embed(color=0x9B59B6)
            embed.set_author(name="📊 XP System Status")
            embed.description = f"XP/Level system is currently **{status}**"
            await ctx.send(embed=embed)
            return

        action = action.lower()

        if action in ["enable", "on", "true", "1", "yes"]:
            await set_xp_enabled(ctx.bot.db, ctx.guild.id, True)
            embed = discord.Embed(color=0x2ECC71)
            embed.set_author(name="✅ XP System Enabled")
            embed.description = "XP/Level system has been **enabled** for this server."
            await ctx.send(embed=embed)

        elif action in ["disable", "off", "false", "0", "no"]:
            await set_xp_enabled(ctx.bot.db, ctx.guild.id, False)
            embed = discord.Embed(color=0xE74C3C)
            embed.set_author(name="❌ XP System Disabled")
            embed.description = "XP/Level system has been **disabled** for this server."
            await ctx.send(embed=embed)

        else:
            embed = self._make_embed("❌ Invalid Action", 0xE74C3C, "Usage: `alpha xpsystem [enable|disable|status]`")
            await ctx.send(embed=embed)

    @xpsystem.error
    async def xpsystem_error(self, ctx: commands.Context, error) -> None:
        if isinstance(error, commands.MissingPermissions):
            embed = self._make_embed("❌ Permission Denied", 0xE74C3C, "You need **Administrator** permission to use this command.")
            await ctx.send(embed=embed)

    @commands.command(name="xpgrant", hidden=True)
    @commands.is_owner()
    async def addxp(self, ctx: commands.Context, member: discord.Member, amount: int) -> None:
        """[Owner] Add or remove XP for a user. Usage: alpha xpgrant <user> <amount>"""
        if amount == 0:
            embed = self._make_embed("❌ Invalid Amount", 0xE74C3C, "Amount must not be zero")
            await ctx.send(embed=embed)
            return

        old_data = await load_user(ctx.bot.db, member.id)
        old_xp = old_data["xp"]
        new_level = await award_game_xp(ctx.bot.db, member.id, amount)
        new_xp = old_xp + amount

        embed = discord.Embed(color=0x2ECC71 if amount > 0 else 0xE74C3C)
        embed.set_author(name="✅ XP Updated" if amount > 0 else "❌ XP Removed")
        embed.description = (
            f"**{member.mention}** — **{old_xp:,} → {new_xp:,} XP** (`{amount:+d}`) · **Level {new_level}**"
        )
        await ctx.send(embed=embed)

    @commands.command(name="addsp", aliases=["givesp", "grantsp", "stealsp", "removesp"], hidden=True)
    @commands.is_owner()
    async def addsp(self, ctx: commands.Context, member: discord.Member, amount: int) -> None:
        """[Owner] Add or remove SP for a user. Usage: alpha addsp <user> <amount>"""
        if amount == 0:
            await ctx.send(embed=self._make_embed("❌ Invalid Amount", 0xE74C3C, "Amount must not be zero"))
            return
        data = await load_user(ctx.bot.db, member.id)
        data["sp"] += amount
        data["weekly_sp"] = data.get("weekly_sp", 0) + amount
        await save_user(ctx.bot.db, member.id, data)
        embed = discord.Embed(color=0x2ECC71 if amount > 0 else 0xE74C3C)
        embed.set_author(name="✅ SP Updated" if amount > 0 else "❌ SP Removed")
        embed.description = f"**{member.mention}** — **{data['sp'] - amount:,} → {data['sp']:,} SP** (`{amount:+d}`)"
        await ctx.send(embed=embed)

    @addxp.error
    async def addxp_error(self, ctx: commands.Context, error) -> None:
        if isinstance(error, commands.NotOwner):
            embed = self._make_embed("❌ Access Denied", 0xE74C3C, "Only the bot owner / super user can use this command.")
            await ctx.send(embed=embed)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(XP(bot))
