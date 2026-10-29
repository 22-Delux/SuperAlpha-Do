# Command Reference

Complete reference of all commands available in SuperAlpha Do. Use `alpha man <command>` for detailed info or `/help` for quick access.

## Prefix & Slash Commands

The bot supports both prefix commands (`alpha <command>`) and slash commands (`/<command>`) for most features.

## Admin & Configuration

| Command | Type | Permission | Description |
|---------|------|------------|-------------|
| `/config` or `alpha config` | Slash/Prefix | Manage Server | Central admin dashboard with UI |
| `/config_set` | Slash | Manage Server | Quick config changes |
| `/modsettings` or `alpha modsettings` | Slash/Prefix | Manage Server | Moderation settings with toggles |
| `/setup` or `alpha setup` | Slash/Prefix | Manage Server | Guided setup wizard |
| `/dashboard` | Slash | - | Server configuration overview |
| `/audit` or `alpha audit` | Slash/Prefix | Manage Server | Generate audit report |
| `/logsummary` or `alpha logsummary` | Slash/Prefix | Manage Server | Log configuration summary |

## Moderation

| Command | Type | Permission | Description |
|---------|------|------------|-------------|
| `alpha kick` / `/kick` | Prefix/Slash | Kick Members | Kick a member |
| `alpha ban` / `/ban` | Prefix/Slash | Ban Members | Ban a member |
| `alpha mute` / `/mute` | Prefix/Slash | Moderate Members | Timeout a member |
| `alpha unmute` / `/unmute` | Prefix/Slash | Moderate Members | Remove timeout |
| `alpha purge` / `/purge` | Prefix/Slash | Manage Messages | Delete messages |
| `alpha automod` | Prefix | Administrator | Configure auto-moderation |
| `alpha warns` | Prefix | Moderate Members | View warnings |
| `alpha warn` | Prefix | Moderate Members | Warn a member |

## Logging & Welcome

| Command | Type | Permission | Description |
|---------|------|------------|-------------|
| `alpha welcomesetup` | Prefix | Administrator | Setup welcome messages |
| `alpha welcomedisable` | Prefix | Administrator | Disable welcome messages |
| `alpha logsetup` | Prefix | Administrator | Setup logging channel |
| `alpha logdisable` | Prefix | Administrator | Disable logging |
| `alpha logconfig` | Prefix | Administrator | View logging config |

## Music (Premium)

| Command | Type | Permission | Description |
|---------|------|------------|-------------|
| `alpha play` / `/play` | Prefix/Slash | - | Play a song or add to queue |
| `alpha pause` | Prefix | - | Pause playback |
| `alpha resume` | Prefix | - | Resume playback |
| `alpha skip` | Prefix | - | Skip current track |
| `alpha stop` / `alpha leave` | Prefix | - | Stop and disconnect |
| `alpha queue` or `alpha q` | Prefix | - | View queue with premium UI |
| `alpha nowplaying` or `alpha np` | Prefix | - | Show now playing with thumbnail |
| `alpha loop` or `alpha repeat` | Prefix | - | Loop track or queue |
| `alpha shuffle` | Prefix | - | Shuffle queue |
| `alpha volume` or `alpha vol` | Prefix | - | Adjust volume (0-200) |
| `alpha similar` / `/similar` | Prefix/Slash | - | Add similar song suggestion |
| `alpha partymode` / `/partymode` | Prefix/Slash | - | Toggle party mode |
| `alpha djmode` / `/djmode` | Prefix/Slash | - | Toggle DJ mode |
| `alpha history` / `/history` | Prefix/Slash | - | View queue history |
| `alpha favorite` or `alpha fav` | Prefix | - | Favorite current track |
| `alpha favorites` or `alpha favs` | Prefix | - | Manage favorites |
| `alpha myfavorites` or `alpha playlist` | Prefix | - | View your favorites |
| `alpha autoplay` | Prefix | - | Toggle autoplay |

## XP & Levels

| Command | Type | Permission | Description |
|---------|------|------------|-------------|
| `alpha rank` or `alpha level` | Prefix | - | Check your rank |
| `alpha leaderboard` or `alpha lb` | Prefix | - | View server leaderboard |
| `alpha levelchannel` | Prefix | Administrator | Set level-up channel |

## Utility & Info

| Command | Type | Permission | Description |
|---------|------|------------|-------------|
| `alpha help` or `alpha man` | Prefix | - | Help/manual system |
| `/help` | Slash | - | Quick help guide |
| `alpha userinfo` or `alpha whois` | Prefix | - | User information |
| `alpha serverinfo` | Prefix | - | Server information |
| `alpha avatar` | Prefix | - | View avatar |
| `alpha ping` | Prefix | - | Check bot latency |
| `alpha botinfo` | Prefix | - | Bot information |
| `alpha status` | Prefix | - | System status dashboard |

## Emojis & Stickers

| Command | Type | Permission | Description |
|---------|------|------------|-------------|
| `alpha steal <name>` | Prefix | Manage Expressions | Copy an emoji or image from a replied message |
| `alpha stealsticker <name>` | Prefix | Manage Expressions | Copy a sticker (including cross-server), or turn an image into a sticker |
| `alpha addsticker <name>` | Prefix | Manage Expressions | Alias for `stealsticker` |

## Fun & Games

| Command | Type | Permission | Description |
|---------|------|------------|-------------|
| `/8ball` | Slash | - | Ask the magic 8-ball |
| `/coinflip` | Slash | - | Flip a coin |
| `/roll` | Slash | - | Roll dice |
| `/joke` | Slash | - | Get a joke |
| `/fact` | Slash | - | Get a fun fact |
| `alpha giveaway` | Prefix | Manage Server | Manage giveaways |

## Tips

- Use `alpha man <command>` for detailed usage and examples
- Many commands support both prefix and slash forms
- Use the admin dashboard (`/config`) for easy configuration with UI buttons
- Enable party mode or DJ mode for enhanced music experiences
