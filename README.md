# SuperAlpha Do

A feature-rich, polished Discord bot with moderation, music, XP, games, and premium admin tools. Built for speed, usability, and a clean user experience.

## Features

- **🛡️ Moderation & Admin** - Advanced automod, logging, audit reports, centralized config dashboard with UI
- **🎵 Premium Music** - Lavalink-powered playback with a failover node pool, queue management, now-playing embeds with thumbnails, loop/repeat, party mode, DJ mode, similar song suggestions, queue history, favorites
- **⭐ XP & Levels** - Chat/VC XP, leaderboards, level-up notifications, customizable level-up channels
- **🎉 Giveaways** - Easy giveaway creation with automatic endings and rerolls
- **🎨 Emoji & Sticker Stealing** - Copy emojis, steal cross-server stickers, and turn images into stickers
- **🎮 Games & Fun** - Minigames, 8ball, trivia, and more
- **🤖 AI Integration** - AI-powered features
- **⚡ Onboarding** - Guided setup wizard for new servers with auto-configuration
- **🎨 Polished UI** - Branded embeds, consistent styling, intuitive interfaces

## Quick Links

- [Quick Start Guide for Admins](docs/QUICK_START_ADMINS.md)
- [Command Reference](docs/COMMAND_REFERENCE.md)
- [FAQ](docs/FAQ.md)
- [Tutorials](docs/TUTORIALS.md)

## Installation

1. Clone the repository
2. Install dependencies: `pip install -r requirements.txt`
3. Configure your `.env` file (see below)
4. Run the bot: `python main.py`

## Environment Variables

Required:
- `DISCORD_TOKEN` - Your Discord bot token
- `GROQ_API_KEY` - API key for AI features
- `SUPER_USERS` - Comma-separated list of super user IDs
- `BANNED_GUILDS` - Comma-separated list of banned guild IDs

Optional:
- `DB_URL` - PostgreSQL connection URL (for alpha-style DB)
- `LAVALINK_NODES` - Semicolon-separated node list, each `identifier|uri|password`
- `LAVALINK_URI` / `LAVALINK_PASSWORD` - Single-node override used when `LAVALINK_NODES` is unset
- `LAVALINK_SECURE` - `true`/`false` for the single-node override (default `true`)
- `LAVALINK_NODE_RETRIES` - Reconnect attempts per health check (default `1`)

### PostgreSQL permissions

The role used by `DB_URL` needs permission to create XP tables in PostgreSQL's
`public` schema. Run this as the database/schema owner, replacing `bot_role`
with the username from `DB_URL`:

```sql
GRANT USAGE, CREATE ON SCHEMA public TO bot_role;
```

### Music backend

Music is played by **Lavalink v4** through [Wavelink](https://github.com/PythonistaGuild/Wavelink).
No local media tooling is required on the bot host.

By default the bot connects to a pool of public Lavalink nodes and automatically
fails over when one is offline or under maintenance. Public nodes are shared and
can be busy; for reliable production use, point the bot at your own Lavalink
server (or several) with `LAVALINK_NODES`:

```env
LAVALINK_NODES=main|https://lavalink.example.com:443|your-password; backup|http://backup.example.com:2333|your-password
```

Use `alpha refresh` to reconnect disconnected nodes and report pool health.

## Getting Started

1. Invite the bot to your server with appropriate permissions
2. Run `/setup` or `alpha setup` for guided configuration
3. Use `/config` or `alpha config` to access the admin dashboard
4. Check out `/help` or `alpha man` for all commands

## Support

For issues, questions, or feedback, join our support server or check the documentation.

## License

See LICENSE file for details.
