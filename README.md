# SuperAlpha Do

A feature-rich, polished Discord bot with moderation, music, XP, games, and premium admin tools. Built for speed, usability, and a clean user experience.

## Features

- **🛡️ Moderation & Admin** - Advanced automod, logging, audit reports, centralized config dashboard with UI
- **🎵 Premium Music** - High-quality playback with queue management, now-playing embeds with thumbnails, loop/repeat, party mode, DJ mode, similar song suggestions, queue history, favorites
- **⭐ XP & Levels** - Chat/VC XP, leaderboards, level-up notifications, customizable level-up channels
- **🎉 Giveaways** - Easy giveaway creation with automatic endings and rerolls
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
- `POT_SERVER_URL` - YouTube PO token provider URL for better playback
- `POT_SCRIPT_PATH` - Path to PO token script

## Getting Started

1. Invite the bot to your server with appropriate permissions
2. Run `/setup` or `alpha setup` for guided configuration
3. Use `/config` or `alpha config` to access the admin dashboard
4. Check out `/help` or `alpha man` for all commands

## Support

For issues, questions, or feedback, join our support server or check the documentation.

## License

See LICENSE file for details.
