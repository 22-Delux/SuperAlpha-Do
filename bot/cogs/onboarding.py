"""
cogs/onboarding.py — Better onboarding with first-run setup wizard.
"""

import json
import os
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from bot.cogs.checks import perms_or_developer
from bot.services.embeds import info_embed, brand_embed, success_embed, event_embed, stats_embed, add_author_brand, COLOR_INFO, COLOR_SUCCESS, COLOR_BRAND
from bot.cogs import automod
from bot.cogs import welcomelogs
from bot.models import xp_store

DATA_DIR = "data/onboarding"
CONFIG_FILE = os.path.join(DATA_DIR, "config.json")
os.makedirs(DATA_DIR, exist_ok=True)


def _load() -> dict:
    try:
        with open(CONFIG_FILE, "r") as f:
            return json.load(f)
    except Exception:
        return {}


def _save(data: dict) -> None:
    with open(CONFIG_FILE, "w") as f:
        json.dump(data, f, indent=2)


def get_onboarded(guild_id: int) -> bool:
    data = _load()
    return bool(data.get(str(guild_id), {}).get("done", False))


def mark_onboarded(guild_id: int) -> None:
    data = _load()
    gid = str(guild_id)
    if gid not in data:
        data[gid] = {}
    data[gid]["done"] = True
    _save(data)


class OnboardingView(discord.ui.View):
    def __init__(self, bot: commands.Bot, guild: discord.Guild):
        super().__init__(timeout=600)
        self.bot = bot
        self.guild = guild

    @discord.ui.button(label="Run Setup Wizard", style=discord.ButtonStyle.primary, emoji="🛠️")
    async def run_setup(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.manage_guild and not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("You need Manage Server permissions to run setup.", ephemeral=True)
            return
        await interaction.response.send_modal(SetupModal(self.bot, self.guild))

    @discord.ui.button(label="View Help", style=discord.ButtonStyle.secondary, emoji="📖")
    async def view_help(self, interaction: discord.Interaction, button: discord.ui.Button):
        prefix = self.bot.command_prefix
        if callable(prefix):
            try:
                p = prefix(self.bot, interaction.message)  # type: ignore
                prefix_str = p[0] if isinstance(p, (list, tuple)) and p else "$ "
            except Exception:
                prefix_str = "alpha "
        else:
            prefix_str = prefix[0] if isinstance(prefix, (list, tuple)) and prefix else "alpha "
        embed = discord.Embed(
            title="Quick Help",
            description=f"Use `{prefix_str}man` or slash commands.\n\n**Key commands:**\n• `/help` or `{prefix_str}man` - Browse all commands\n• `/setup` - Guided setup wizard\n• `/dashboard` - Server overview",
            color=0x3498DB,
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @discord.ui.button(label="Skip", style=discord.ButtonStyle.gray)
    async def skip(self, interaction: discord.Interaction, button: discord.ui.Button):
        mark_onboarded(self.guild.id)
        await interaction.response.edit_message(content="Setup skipped. You can run `/setup` anytime.", view=None, embed=None)


class SetupModal(discord.ui.Modal, title="Quick Server Setup"):
    def __init__(self, bot: commands.Bot, guild: discord.Guild):
        super().__init__()
        self.bot = bot
        self.guild = guild

        self.welcome = discord.ui.TextInput(
            label="Welcome Channel (mention/name/ID)",
            placeholder="e.g. #welcome or channel ID",
            required=False,
            max_length=100,
        )
        self.modrole = discord.ui.TextInput(
            label="Mod Role (name/ID)",
            placeholder="e.g. Moderator or role ID",
            required=False,
            max_length=100,
        )
        self.logs = discord.ui.TextInput(
            label="Logging Channel (mention/name/ID)",
            placeholder="e.g. #logs or channel ID",
            required=False,
            max_length=100,
        )
        self.xpchan = discord.ui.TextInput(
            label="XP/Level-up Channel (mention/name/ID)",
            placeholder="e.g. #level-ups or leave blank to reply in channel",
            required=False,
            max_length=100,
        )
        self.add_item(self.welcome)
        self.add_item(self.modrole)
        self.add_item(self.logs)
        self.add_item(self.xpchan)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        results = []

        def find_channel(text: str) -> Optional[discord.abc.GuildChannel]:
            if not text:
                return None
            text = text.strip()
            # mention
            if text.startswith("<#") and text.endswith(">"):
                cid = int(text[2:-1])
                return self.guild.get_channel(cid)
            # ID
            if text.isdigit():
                ch = self.guild.get_channel(int(text))
                if ch:
                    return ch
            # name
            name = text.lstrip("#").lower()
            for ch in self.guild.channels:
                if isinstance(ch, (discord.TextChannel, discord.ThreadChannel)):
                    if ch.name.lower() == name:
                        return ch
            return None

        def find_role(text: str) -> Optional[discord.Role]:
            if not text:
                return None
            text = text.strip()
            if text.startswith("<@&") and text.endswith(">"):
                rid = int(text[3:-1])
                return self.guild.get_role(rid)
            if text.isdigit():
                r = self.guild.get_role(int(text))
                if r:
                    return r
            name = text.lower()
            for r in self.guild.roles:
                if r.name.lower() == name and not r.is_bot_managed() and not r.is_integration():
                    return r
            return None

        # Welcome channel
        wch = find_channel(self.welcome.value)
        if wch and isinstance(wch, discord.TextChannel):
            try:
                cfg = welcomelogs.get_guild_config(self.guild.id)
                cfg["welcome_channel"] = wch.id
                cfg["welcome_enabled"] = True
                if not cfg.get("welcome_message"):
                    cfg["welcome_message"] = "Welcome {user} to {server}!"
                welcomelogs.save_guild_config(self.guild.id, cfg)
                results.append(f"✅ Welcome channel set to {wch.mention} (enabled)")
            except Exception as e:
                results.append(f"⚠️ Failed to set welcome: {e}")
        elif self.welcome.value:
            results.append("⚠️ Could not find welcome channel")

        # Mod role (store in automod alert context as a hint; also just note)
        mrole = find_role(self.modrole.value)
        if mrole:
            results.append(f"✅ Mod role noted: {mrole.mention} (use with permission checks as needed)")

        # Logging channel
        lch = find_channel(self.logs.value)
        if lch and isinstance(lch, discord.TextChannel):
            try:
                cfg = welcomelogs.get_guild_config(self.guild.id)
                cfg["logs_channel"] = lch.id
                cfg["logs_enabled"] = True
                welcomelogs.save_guild_config(self.guild.id, cfg)
                results.append(f"✅ Logging channel set to {lch.mention} (enabled)")
            except Exception as e:
                results.append(f"⚠️ Failed to set logs: {e}")
        elif self.logs.value:
            results.append("⚠️ Could not find logging channel")

        # XP channel
        xch = find_channel(self.xpchan.value)
        if xch and isinstance(xch, discord.TextChannel):
            try:
                xp_store.set_level_channel(self.guild.id, xch.id)
                results.append(f"✅ XP level-up channel set to {xch.mention}")
            except Exception as e:
                results.append(f"⚠️ Failed to set XP channel: {e}")
        elif self.xpchan.value:
            results.append("⚠️ Could not find XP channel")

        # Enable automod lightly if nothing set? keep optional
        try:
            acfg = automod.get_guild_config(self.guild.id)
            if not acfg.get("alert_channel") and lch and isinstance(lch, discord.TextChannel):
                acfg["alert_channel"] = lch.id
                automod.set_guild_config(self.guild.id, acfg)
                results.append("✅ Automod alerts routed to logs channel")
        except Exception:
            pass

        mark_onboarded(self.guild.id)
        embed = discord.Embed(
            title="Setup Complete",
            description="\n".join(results) if results else "No changes made.",
            color=0x2ECC71,
        )
        embed.set_footer(text="Run /setup again anytime to reconfigure")
        await interaction.followup.send(embed=embed, ephemeral=True)


class Onboarding(commands.Cog, name="onboarding"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_guild_join(self, guild: discord.Guild):
        try:
            # Find a good channel to send onboarding message
            channel = guild.system_channel
            if channel is None or not channel.permissions_for(guild.me).send_messages:
                for ch in guild.text_channels:
                    if ch.permissions_for(guild.me).send_messages and ch.permissions_for(guild.me).embed_links:
                        channel = ch
                        break
            if channel is None:
                return
            embed = discord.Embed(
                title="👋 Thanks for adding me!",
                description=(
                    "**What this bot can do**\n\n"
                    "• **Moderation** - kick/ban/mute, automod, logging\n"
                    "• **Utility** - info, reminders, AFK, suggestions\n"
                    "• **Fun & Games** - minigames, music, giveaways\n"
                    "• **XP System** - levels, ranks, rewards\n"
                    "• **Music** - play from YouTube/SoundCloud/Spotify/Apple Music\n\n"
                    "**Quick Start:**\n"
                    "• `/help` or `alpha man` - See all commands\n"
                    "• `/setup` - Guided setup wizard (auto-configure channels/roles)\n"
                    "• `/dashboard` - Server overview & quick settings\n"
                ),
                color=0x5865F2,
            )
            embed.set_thumbnail(url=self.bot.user.display_avatar.url if self.bot.user else None)
            view = OnboardingView(self.bot, guild)
            await channel.send(embed=embed, view=view)
        except Exception:
            pass

    @app_commands.command(name="setup", description="Run the guided server setup wizard")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def setup_slash(self, interaction: discord.Interaction):
        if not interaction.guild:
            await interaction.response.send_message("This can only be used in a server.", ephemeral=True)
            return
        await interaction.response.send_modal(SetupModal(self.bot, interaction.guild))

    @setup_slash.error
    async def setup_slash_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.MissingPermissions):
            await interaction.response.send_message("You need Manage Server permissions to run setup.", ephemeral=True)
        else:
            await interaction.response.send_message("An error occurred.", ephemeral=True)

    @app_commands.command(name="help", description="View bot help and quick start guide")
    async def help_slash(self, interaction: discord.Interaction):
        prefix = self.bot.command_prefix
        if callable(prefix):
            try:
                ctx = await self.bot.get_context(interaction.message)  # type: ignore
                p = prefix(self.bot, ctx) if ctx else None
                prefix_str = p[0] if isinstance(p, (list, tuple)) and p else "alpha "
            except Exception:
                prefix_str = "alpha "
        else:
            prefix_str = prefix[0] if isinstance(prefix, (list, tuple)) and prefix else "alpha "
        embed = discord.Embed(
            title="📖 Help - Quick Start",
            description=(
                f"**Prefix:** `{prefix_str}` | **Slash:** Available for most commands\n\n"
                "**Key Commands:**\n"
                f"• `{prefix_str}man` or `/help` - Full command manual\n"
                f"• `/setup` - Guided setup wizard\n"
                f"• `/dashboard` - Server overview\n\n"
                "**Categories:** Moderation, Utility, Fun, Games, Music, XP, AFK, Giveaways, Suggestions, etc.\n\n"
                "Use the setup wizard to auto-configure welcome messages, logging, mod roles, and XP channels."
            ),
            color=0x3498DB,
        )
        if self.bot.user:
            embed.set_thumbnail(url=self.bot.user.display_avatar.url)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="dashboard", description="View server configuration dashboard")
    async def dashboard_slash(self, interaction: discord.Interaction):
        if not interaction.guild:
            await interaction.response.send_message("This can only be used in a server.", ephemeral=True)
            return
        guild = interaction.guild
        # Gather config
        wcfg = welcomelogs.get_guild_config(guild.id)
        wch = guild.get_channel(wcfg.get("welcome_channel")) if wcfg.get("welcome_channel") else None
        lch = guild.get_channel(wcfg.get("logs_channel")) if wcfg.get("logs_channel") else None
        lvlch = guild.get_channel(xp_store.get_level_channel(guild.id)) if xp_store.get_level_channel(guild.id) else None
        acfg = automod.get_guild_config(guild.id)
        ach = guild.get_channel(acfg.get("alert_channel")) if acfg.get("alert_channel") else None

        embed = discord.Embed(title=f"📊 Dashboard - {guild.name}", color=0x1ABC9C)
        embed.add_field(name="Welcome", value=f"Channel: {wch.mention if wch else '`Not set`'}\nEnabled: {'Yes' if wcfg.get('welcome_enabled') else 'No'}", inline=True)
        embed.add_field(name="Logging", value=f"Channel: {lch.mention if lch else '`Not set`'}\nEnabled: {'Yes' if wcfg.get('logs_enabled') else 'No'}", inline=True)
        embed.add_field(name="XP Level-ups", value=f"Channel: {lvlch.mention if lvlch else '`Not set` (replies in chat)'}", inline=True)
        embed.add_field(name="Automod Alerts", value=f"Channel: {ach.mention if ach else '`Not set`'}", inline=True)
        embed.add_field(name="XP", value=f"Enabled: {'Yes' if xp_store.is_xp_enabled(guild.id) else 'No'}", inline=True)
        embed.add_field(name="Onboarded", value="Yes" if get_onboarded(guild.id) else "No (run /setup)", inline=True)
        embed.set_thumbnail(url=guild.icon.url if guild.icon else None)
        view = OnboardingView(self.bot, guild)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Onboarding(bot))
