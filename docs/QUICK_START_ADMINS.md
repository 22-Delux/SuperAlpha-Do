# Quick Start Guide for Admins

Get your server up and running with SuperAlpha Do in minutes.

## Step 1: Invite the Bot

1. Use the bot's invite link with Administrator permissions (recommended for full functionality)
2. Select your server and authorize

## Step 2: Run the Setup Wizard

The easiest way to get started is with the guided setup wizard.

**Using Slash Commands (Recommended):**
```
/setup
```

**Using Prefix Commands:**
```
alpha setup
```

The wizard will guide you through configuring:
- **Welcome Channel** - Auto-welcome new members
- **Mod Role** - Designate your moderation role
- **Logging Channel** - Track server events
- **XP/Level-up Channel** - Where level-up messages go

## Step 3: Access the Admin Dashboard

For ongoing management, use the central admin dashboard:

**Slash Command:**
```
/config
```

**Prefix Command:**
```
alpha config
```

The dashboard provides:
- **View Config** - See all current settings
- **Mod Settings** - Toggle features with buttons
- **Logs Summary** - Check logging configuration
- **Audit Report** - Security/configuration audit

## Step 4: Configure Moderation

### Auto-Moderation
Enable and configure automod:

```
alpha automod enable
alpha automod word add <word>
alpha automod mentions <number>
alpha automod action <warn|delete|mute>
alpha automod alert #channel
```

Or use `/modsettings` for a toggle UI.

### Server Logging
Set up comprehensive logging:

```
alpha logsetup #logs
```

### Welcome Messages
Configure welcome messages:

```
alpha welcomesetup #welcome Welcome {user} to {server}!
```

Placeholders: `{user}`, `{user_name}`, `{server}`, `{member_count}`

## Step 5: Set Up XP System

XP is enabled by default. Configure it:

```
alpha levelchannel set #level-ups
```

Or disable it:
```
alpha levelchannel off
```

## Quick Configuration via Commands

You can also use `/config_set` for quick changes:

- Set welcome channel: `/config_set setting:welcome_channel channel:#welcome`
- Enable/disable features: `/config_set setting:welcome_enabled enable:true`
- Set XP channel: `/config_set setting:xp_channel channel:#level-ups`

## Recommended Permissions

For full functionality, grant these permissions:
- Manage Server
- Manage Roles
- Kick Members
- Ban Members
- Moderate Members (Timeout)
- Manage Messages
- Manage Channels
- View Audit Log
- Connect/Speak (for music)
- Embed Links
- Attach Files
- Read Message History

## Tips for Admins

- Use `/config` regularly to review your server setup
- Run `/audit` to check for security/configuration issues
- The setup wizard can be run again anytime with `/setup`
- Use `/modsettings` for quick toggles without memorizing commands
- Check `/logsummary` to verify logging is configured correctly

## Next Steps

- Read the [Command Reference](COMMAND_REFERENCE.md) for all available commands
- Check the [FAQ](FAQ.md) for common issues
- Follow [Tutorials](TUTORIALS.md) for feature-specific guides
