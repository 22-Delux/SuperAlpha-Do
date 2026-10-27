# Command Reference

Complete reference of all commands available in sudo-bot. Use `sudo man <command>` for detailed info or `/help` for quick access.

## Prefix & Slash Commands

The bot supports both prefix commands (`sudo <command>`) and slash commands (`/<command>`) for most features.

## Admin & Configuration

| Command | Type | Permission | Description |
|---------|------|------------|-------------|
| `/config` or `sudo config` | Slash/Prefix | Manage Server | Central admin dashboard with UI |
| `/config_set` | Slash | Manage Server | Quick config changes |
| `/modsettings` or `sudo modsettings` | Slash/Prefix | Manage Server | Moderation settings with toggles |
| `/setup` or `sudo setup` | Slash/Prefix | Manage Server | Guided setup wizard |
| `/dashboard` | Slash | - | Server configuration overview |
| `/audit` or `sudo audit` | Slash/Prefix | Manage Server | Generate audit report |
| `/logsummary` or `sudo logsummary` | Slash/Prefix | Manage Server | Log configuration summary |

## Moderation

| Command | Type | Permission | Description |
|---------|------|------------|-------------|
| `sudo kick` / `/kick` | Prefix/Slash | Kick Members | Kick a member |
| `sudo ban` / `/ban` | Prefix/Slash | Ban Members | Ban a member |
| `sudo mute` / `/mute` | Prefix/Slash | Moderate Members | Timeout a member |
| `sudo unmute` / `/unmute` | Prefix/Slash | Moderate Members | Remove timeout |
| `sudo purge` / `/purge` | Prefix/Slash | Manage Messages | Delete messages |
| `sudo automod` | Prefix | Administrator | Configure auto-moderation |
| `sudo warns` | Prefix | Moderate Members | View warnings |
| `sudo warn` | Prefix | Moderate Members | Warn a member |

## Logging & Welcome

| Command | Type | Permission | Description |
|---------|------|------------|-------------|
| `sudo welcomesetup` | Prefix | Administrator | Setup welcome messages |
| `sudo welcomedisable` | Prefix | Administrator | Disable welcome messages |
| `sudo logsetup` | Prefix | Administrator | Setup logging channel |
| `sudo logdisable` | Prefix | Administrator | Disable logging |
| `sudo logconfig` | Prefix | Administrator | View logging config |

## Music (Premium)

| Command | Type | Permission | Description |
|---------|------|------------|-------------|
| `sudo play` / `/play` | Prefix/Slash | - | Play a song or add to queue |
| `sudo pause` | Prefix | - | Pause playback |
| `sudo resume` | Prefix | - | Resume playback |
| `sudo skip` | Prefix | - | Skip current track |
| `sudo stop` / `sudo leave` | Prefix | - | Stop and disconnect |
| `sudo queue` or `sudo q` | Prefix | - | View queue with premium UI |
| `sudo nowplaying` or `sudo np` | Prefix | - | Show now playing with thumbnail |
| `sudo loop` or `sudo repeat` | Prefix | - | Loop track or queue |
| `sudo shuffle` | Prefix | - | Shuffle queue |
| `sudo volume` or `sudo vol` | Prefix | - | Adjust volume (0-200) |
| `sudo similar` / `/similar` | Prefix/Slash | - | Add similar song suggestion |
| `sudo partymode` / `/partymode` | Prefix/Slash | - | Toggle party mode |
| `sudo djmode` / `/djmode` | Prefix/Slash | - | Toggle DJ mode |
| `sudo history` / `/history` | Prefix/Slash | - | View queue history |
| `sudo favorite` or `sudo fav` | Prefix | - | Favorite current track |
| `sudo favorites` or `sudo favs` | Prefix | - | Manage favorites |
| `sudo myfavorites` or `sudo playlist` | Prefix | - | View your favorites |
| `sudo autoplay` | Prefix | - | Toggle autoplay |

## XP & Levels

| Command | Type | Permission | Description |
|---------|------|------------|-------------|
| `sudo rank` or `sudo level` | Prefix | - | Check your rank |
| `sudo leaderboard` or `sudo lb` | Prefix | - | View server leaderboard |
| `sudo levelchannel` | Prefix | Administrator | Set level-up channel |

## Utility & Info

| Command | Type | Permission | Description |
|---------|------|------------|-------------|
| `sudo help` or `sudo man` | Prefix | - | Help/manual system |
| `/help` | Slash | - | Quick help guide |
| `sudo userinfo` or `sudo whois` | Prefix | - | User information |
| `sudo serverinfo` | Prefix | - | Server information |
| `sudo avatar` | Prefix | - | View avatar |
| `sudo ping` | Prefix | - | Check bot latency |
| `sudo botinfo` | Prefix | - | Bot information |
| `sudo status` | Prefix | - | System status dashboard |

## Fun & Games

| Command | Type | Permission | Description |
|---------|------|------------|-------------|
| `/8ball` | Slash | - | Ask the magic 8-ball |
| `/coinflip` | Slash | - | Flip a coin |
| `/roll` | Slash | - | Roll dice |
| `/joke` | Slash | - | Get a joke |
| `/fact` | Slash | - | Get a fun fact |
| `sudo giveaway` | Prefix | Manage Server | Manage giveaways |

## Tips

- Use `sudo man <command>` for detailed usage and examples
- Many commands support both prefix and slash forms
- Use the admin dashboard (`/config`) for easy configuration with UI buttons
- Enable party mode or DJ mode for enhanced music experiences
