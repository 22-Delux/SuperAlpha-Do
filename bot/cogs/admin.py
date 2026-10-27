"""
cogs/admin.py — Central admin dashboard, config UI, mod settings, logs summary, audit reports.
"""

import json
import os
from datetime import datetime, timezone, timedelta
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from bot.cogs.checks import perms_or_developer
from bot.cogs import automod
from bot.cogs import welcomelogs
from bot.models import xp_store
from bot.services.embeds import (
    brand_embed,
    stats_embed,
    info_embed,
    success_embed,
    warning_embed,
    error_embed,
    leaderboard_embed,
    event_embed,
    COLOR_INFO,
    COLOR_SUCCESS,
    COLOR_WARNING,
    COLOR_DANGER,
    COLOR_DASHBOARD,
    add_author_brand,
)


class ConfigView(discord.ui.View):
    def __init__(self, bot: commands.Bot, guild: discord.Guild):
        super().__init__(timeout=300)
        self.bot = bot
        self.guild = guild

    @discord.ui.button(label="View Config", style=discord.ButtonStyle.primary, emoji="📋")
    async def view_config(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.manage_guild and not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("You need Manage Server permissions.", ephemeral=True)
            return
        embed = await build_config_embed(self.bot, self.guild)
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="Mod Settings", style=discord.ButtonStyle.secondary, emoji="🛡️")
    async def mod_settings(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.manage_guild and not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("You need Manage Server permissions.", ephemeral=True)
            return
        embed = build_modsettings_embed(self.guild)
        view = ModSettingsView(self.bot, self.guild)
        await interaction.response.edit_message(embed=embed, view=view)

    @discord.ui.button(label="Logs Summary", style=discord.ButtonStyle.secondary, emoji="📊")
    async def logs_summary(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.manage_guild and not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("You need Manage Server permissions.", ephemeral=True)
            return
        embed = build_logs_summary_embed(self.guild)
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="Audit Report", style=discord.ButtonStyle.secondary, emoji="🧾")
    async def audit_report(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.manage_guild and not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("You need Manage Server permissions.", ephemeral=True)
            return
        embed = await build_audit_embed(self.guild)
        await interaction.response.edit_message(embed=embed, view=self)


class ModSettingsView(discord.ui.View):
    def __init__(self, bot: commands.Bot, guild: discord.Guild):
        super().__init__(timeout=300)
        self.bot = bot
        self.guild = guild

    @discord.ui.button(label="Toggle Automod", style=discord.ButtonStyle.primary, emoji="🛡️")
    async def toggle_automod(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.manage_guild and not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("You need Manage Server permissions.", ephemeral=True)
            return
        cfg = automod.get_guild_config(self.guild.id)
        cfg["enabled"] = not cfg.get("enabled", False)
        automod.set_guild_config(self.guild.id, cfg)
        embed = build_modsettings_embed(self.guild)
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="Toggle Welcome", style=discord.ButtonStyle.secondary)
    async def toggle_welcome(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.manage_guild and not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("You need Manage Server permissions.", ephemeral=True)
            return
        cfg = welcomelogs.get_guild_config(self.guild.id)
        cfg["welcome_enabled"] = not cfg.get("welcome_enabled", False)
        welcomelogs.save_guild_config(self.guild.id, cfg)
        embed = build_modsettings_embed(self.guild)
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="Toggle Logging", style=discord.ButtonStyle.secondary)
    async def toggle_logging(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.manage_guild and not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("You need Manage Server permissions.", ephemeral=True)
            return
        cfg = welcomelogs.get_guild_config(self.guild.id)
        cfg["logs_enabled"] = not cfg.get("logs_enabled", False)
        welcomelogs.save_guild_config(self.guild.id, cfg)
        embed = build_modsettings_embed(self.guild)
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="Toggle XP", style=discord.ButtonStyle.secondary)
    async def toggle_xp(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.manage_guild and not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("You need Manage Server permissions.", ephemeral=True)
            return
        enabled = xp_store.is_xp_enabled(self.guild.id)
        xp_store.set_xp_enabled(self.guild.id, not enabled)
        embed = build_modsettings_embed(self.guild)
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="Back to Config", style=discord.ButtonStyle.gray)
    async def back(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.manage_guild and not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("You need Manage Server permissions.", ephemeral=True)
            return
        embed = await build_config_embed(self.bot, self.guild)
        await interaction.response.edit_message(embed=embed, view=ConfigView(self.bot, self.guild))


async def build_config_embed(bot: commands.Bot, guild: discord.Guild) -> discord.Embed:
    wcfg = welcomelogs.get_guild_config(guild.id)
    wch = guild.get_channel(wcfg.get("welcome_channel")) if wcfg.get("welcome_channel") else None
    lch = guild.get_channel(wcfg.get("logs_channel")) if wcfg.get("logs_channel") else None
    lvlch = guild.get_channel(xp_store.get_level_channel(guild.id)) if xp_store.get_level_channel(guild.id) else None
    acfg = automod.get_guild_config(guild.id)
    ach = guild.get_channel(acfg.get("alert_channel")) if acfg.get("alert_channel") else None

    embed = stats_embed(title=f"Server Config — {guild.name}", description="Central configuration overview")
    if guild.icon:
        embed.set_thumbnail(url=guild.icon.url)
    embed.add_field(name="Welcome", value=f"Channel: {wch.mention if wch else '`Not set`'}\nStatus: {'✅ On' if wcfg.get('welcome_enabled') else '❌ Off'}", inline=True)
    embed.add_field(name="Logging", value=f"Channel: {lch.mention if lch else '`Not set`'}\nStatus: {'✅ On' if wcfg.get('logs_enabled') else '❌ Off'}", inline=True)
    embed.add_field(name="Automod", value=f"Alerts: {ach.mention if ach else '`Not set`'}\nStatus: {'✅ On' if acfg.get('enabled') else '❌ Off'}", inline=True)
    embed.add_field(name="XP", value=f"Level-ups: {lvlch.mention if lvlch else '`Chat`'}\nStatus: {'✅ On' if xp_store.is_xp_enabled(guild.id) else '❌ Off'}", inline=True)
    embed.add_field(name="Members", value=f"{guild.member_count or len(guild.members)}", inline=True)
    embed.add_field(name="Roles/Channels", value=f"{len(guild.roles)} roles • {len(guild.channels)} channels", inline=True)
    embed.set_footer(text="Use /config or buttons below to manage • Powered by sudo")
    return embed


def build_modsettings_embed(guild: discord.Guild) -> discord.Embed:
    wcfg = welcomelogs.get_guild_config(guild.id)
    acfg = automod.get_guild_config(guild.id)
    embed = brand_embed(title="🛡️ Moderation Settings", description="Toggle features with the buttons below.", color=COLOR_DANGER)
    embed.add_field(name="Automod", value="✅ Enabled" if acfg.get("enabled") else "❌ Disabled", inline=True)
    embed.add_field(name="Welcome Messages", value="✅ Enabled" if wcfg.get("welcome_enabled") else "❌ Disabled", inline=True)
    embed.add_field(name="Server Logging", value="✅ Enabled" if wcfg.get("logs_enabled") else "❌ Disabled", inline=True)
    embed.add_field(name="XP System", value="✅ Enabled" if xp_store.is_xp_enabled(guild.id) else "❌ Disabled", inline=True)
    embed.add_field(name="Automod Action", value=acfg.get("action", "warn"), inline=True)
    embed.add_field(name="Max Mentions", value=str(acfg.get("max_mentions", 6)), inline=True)
    embed.set_footer(text="Quick toggles • Use /config set for advanced options")
    return embed


def build_logs_summary_embed(guild: discord.Guild) -> discord.Embed:
    wcfg = welcomelogs.get_guild_config(guild.id)
    lch = guild.get_channel(wcfg.get("logs_channel")) if wcfg.get("logs_channel") else None
    embed = stats_embed(title="📊 Log Summary", description="Current logging configuration & coverage")
    embed.add_field(name="Logging Status", value="✅ Enabled" if wcfg.get("logs_enabled") else "❌ Disabled", inline=True)
    embed.add_field(name="Log Channel", value=lch.mention if lch else "`Not configured`", inline=True)
    events = []
    for k in ["log_messages", "log_joins", "log_leaves", "log_roles", "log_bans", "log_edits", "log_purges", "log_attachments"]:
        events.append(f"{'✅' if wcfg.get(k, True) else '❌'} {k.replace('log_', '').title()}")
    embed.add_field(name="Tracked Events", value="\n".join(events) or "Default coverage", inline=False)
    embed.set_footer(text="Logs are sent to the configured channel when events occur")
    return embed


async def build_audit_embed(guild: discord.Guild) -> discord.Embed:
    wcfg = welcomelogs.get_guild_config(guild.id)
    acfg = automod.get_guild_config(guild.id)
    embed = event_embed(title="🧾 Audit Report", description=f"Security & configuration audit for {guild.name}")
    if guild.icon:
        embed.set_thumbnail(url=guild.icon.url)
    checks = []
    checks.append(f"{'✅' if wcfg.get('logs_enabled') and wcfg.get('logs_channel') else '⚠️'} Server logging configured")
    checks.append(f"{'✅' if acfg.get('enabled') else '⚠️'} Auto-moderation {'enabled' if acfg.get('enabled') else 'disabled'}")
    checks.append(f"{'✅' if guild.rules_channel or guild.public_updates_channel else 'ℹ️'} Community channels present")
    checks.append(f"{'✅' if any(r.permissions.administrator for r in guild.roles if not r.is_default()) else 'ℹ️'} Admin roles exist")
    checks.append(f"{'✅' if wcfg.get('welcome_enabled') else 'ℹ️'} Welcome messages {'enabled' if wcfg.get('welcome_enabled') else 'disabled'}")
    embed.add_field(name="Findings", value="\n".join(checks), inline=False)
    embed.add_field(name="Generated", value=f"<t:{int(datetime.now(timezone.utc).timestamp())}:F>", inline=False)
    embed.set_footer(text="Audit is a snapshot of current configuration")
    return embed


class Admin(commands.Cog, name="admin"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="config", description="Central admin configuration dashboard")
    @app_commands.describe(action="View, set, or open UI")
    @app_commands.choices(action=[
        app_commands.Choice(name="view", value="view"),
        app_commands.Choice(name="ui", value="ui"),
    ])
    @app_commands.checks.has_permissions(manage_guild=True)
    async def config_slash(self, interaction: discord.Interaction, action: app_commands.Choice[str] = None):
        if not interaction.guild:
            await interaction.response.send_message("This can only be used in a server.", ephemeral=True)
            return
        act = action.value if action else "ui"
        if act == "view":
            embed = await build_config_embed(self.bot, interaction.guild)
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        embed = await build_config_embed(self.bot, interaction.guild)
        view = ConfigView(self.bot, interaction.guild)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    @config_slash.error
    async def config_slash_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.MissingPermissions):
            await interaction.response.send_message("You need Manage Server permissions.", ephemeral=True)
        else:
            await interaction.response.send_message("An error occurred.", ephemeral=True)

    @app_commands.command(name="config_set", description="Quickly set config values")
    @app_commands.describe(
        setting="What to configure",
        channel="Target channel (for channel settings)",
        enable="Enable or disable"
    )
    @app_commands.choices(setting=[
        app_commands.Choice(name="welcome_channel", value="welcome_channel"),
        app_commands.Choice(name="logs_channel", value="logs_channel"),
        app_commands.Choice(name="xp_channel", value="xp_channel"),
        app_commands.Choice(name="automod_alerts", value="automod_alerts"),
        app_commands.Choice(name="welcome_enabled", value="welcome_enabled"),
        app_commands.Choice(name="logs_enabled", value="logs_enabled"),
        app_commands.Choice(name="xp_enabled", value="xp_enabled"),
        app_commands.Choice(name="automod_enabled", value="automod_enabled"),
    ])
    @app_commands.checks.has_permissions(manage_guild=True)
    async def config_set_slash(self, interaction: discord.Interaction, setting: app_commands.Choice[str], channel: discord.TextChannel = None, enable: bool = None):
        if not interaction.guild:
            await interaction.response.send_message("This can only be used in a server.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild
        s = setting.value
        try:
            if s == "welcome_channel" and channel:
                cfg = welcomelogs.get_guild_config(guild.id)
                cfg["welcome_channel"] = channel.id
                cfg["welcome_enabled"] = True
                welcomelogs.save_guild_config(guild.id, cfg)
                await interaction.followup.send(f"✅ Welcome channel set to {channel.mention} and enabled.", ephemeral=True)
                return
            if s == "logs_channel" and channel:
                cfg = welcomelogs.get_guild_config(guild.id)
                cfg["logs_channel"] = channel.id
                cfg["logs_enabled"] = True
                welcomelogs.save_guild_config(guild.id, cfg)
                await interaction.followup.send(f"✅ Logs channel set to {channel.mention} and enabled.", ephemeral=True)
                return
            if s == "xp_channel" and channel:
                xp_store.set_level_channel(guild.id, channel.id)
                await interaction.followup.send(f"✅ XP level-up channel set to {channel.mention}.", ephemeral=True)
                return
            if s == "automod_alerts" and channel:
                cfg = automod.get_guild_config(guild.id)
                cfg["alert_channel"] = channel.id
                automod.set_guild_config(guild.id, cfg)
                await interaction.followup.send(f"✅ Automod alerts set to {channel.mention}.", ephemeral=True)
                return
            if s == "welcome_enabled" and enable is not None:
                cfg = welcomelogs.get_guild_config(guild.id)
                cfg["welcome_enabled"] = enable
                welcomelogs.save_guild_config(guild.id, cfg)
                await interaction.followup.send(f"{'✅' if enable else '❌'} Welcome messages {'enabled' if enable else 'disabled'}.", ephemeral=True)
                return
            if s == "logs_enabled" and enable is not None:
                cfg = welcomelogs.get_guild_config(guild.id)
                cfg["logs_enabled"] = enable
                welcomelogs.save_guild_config(guild.id, cfg)
                await interaction.followup.send(f"{'✅' if enable else '❌'} Logging {'enabled' if enable else 'disabled'}.", ephemeral=True)
                return
            if s == "xp_enabled" and enable is not None:
                xp_store.set_xp_enabled(guild.id, enable)
                await interaction.followup.send(f"{'✅' if enable else '❌'} XP {'enabled' if enable else 'disabled'}.", ephemeral=True)
                return
            if s == "automod_enabled" and enable is not None:
                cfg = automod.get_guild_config(guild.id)
                cfg["enabled"] = enable
                automod.set_guild_config(guild.id, cfg)
                await interaction.followup.send(f"{'✅' if enable else '❌'} Automod {'enabled' if enable else 'disabled'}.", ephemeral=True)
                return
            await interaction.followup.send("Missing required parameters for this setting.", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"Error: {e}", ephemeral=True)

    @app_commands.command(name="modsettings", description="Moderation settings with easy toggles")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def modsettings_slash(self, interaction: discord.Interaction):
        if not interaction.guild:
            await interaction.response.send_message("This can only be used in a server.", ephemeral=True)
            return
        embed = build_modsettings_embed(interaction.guild)
        view = ModSettingsView(self.bot, interaction.guild)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    @app_commands.command(name="logsummary", description="View log configuration summary")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def logsummary_slash(self, interaction: discord.Interaction):
        if not interaction.guild:
            await interaction.response.send_message("This can only be used in a server.", ephemeral=True)
            return
        embed = build_logs_summary_embed(interaction.guild)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="audit", description="Generate a server audit report")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def audit_slash(self, interaction: discord.Interaction):
        if not interaction.guild:
            await interaction.response.send_message("This can only be used in a server.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        embed = await build_audit_embed(interaction.guild)
        await interaction.followup.send(embed=embed, ephemeral=True)

    # Prefix fallbacks for /config view/set style
    @commands.group(name="config", invoke_without_command=True)
    @perms_or_developer(manage_guild=True)
    async def config_group(self, ctx: commands.Context):
        embed = await build_config_embed(self.bot, ctx.guild)
        view = ConfigView(self.bot, ctx.guild)
        await ctx.send(embed=embed, view=view)

    @config_group.command(name="view")
    @perms_or_developer(manage_guild=True)
    async def config_view(self, ctx: commands.Context):
        embed = await build_config_embed(self.bot, ctx.guild)
        await ctx.send(embed=embed)

    @config_group.command(name="ui")
    @perms_or_developer(manage_guild=True)
    async def config_ui(self, ctx: commands.Context):
        embed = await build_config_embed(self.bot, ctx.guild)
        view = ConfigView(self.bot, ctx.guild)
        await ctx.send(embed=embed, view=view)

    @commands.command(name="modsettings")
    @perms_or_developer(manage_guild=True)
    async def modsettings_cmd(self, ctx: commands.Context):
        embed = build_modsettings_embed(ctx.guild)
        view = ModSettingsView(self.bot, ctx.guild)
        await ctx.send(embed=embed, view=view)

    @commands.command(name="logsummary")
    @perms_or_developer(manage_guild=True)
    async def logsummary_cmd(self, ctx: commands.Context):
        embed = build_logs_summary_embed(ctx.guild)
        await ctx.send(embed=embed)

    @commands.command(name="audit")
    @perms_or_developer(manage_guild=True)
    async def audit_cmd(self, ctx: commands.Context):
        embed = await build_audit_embed(ctx.guild)
        await ctx.send(embed=embed)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Admin(bot))
