# FAQ - Frequently Asked Questions

## General

### Q: How do I see all commands?
**A:** Use `sudo man` or `/help` to browse all commands. Use `sudo man <command>` for detailed information about a specific command.

### Q: Does the bot support slash commands?
**A:** Yes! Most commands support both prefix (`sudo <command>`) and slash commands (`/<command>`). Slash commands are often more convenient with auto-complete.

### Q: How do I get help with a specific command?
**A:** Run `sudo man <command name>` for detailed usage, examples, and aliases.

## Setup & Configuration

### Q: How do I set up the bot quickly?
**A:** Use the guided setup wizard with `/setup` or `sudo setup`. It will walk you through configuring welcome messages, logging, and more.

### Q: Where can I manage all settings?
**A:** Use the central admin dashboard with `/config` or `sudo config`. It has a nice UI with buttons for all major settings.

### Q: How do I enable/disable features?
**A:** Use `/modsettings` for quick toggles, or `/config_set` for specific settings. You can also use individual commands like `sudo automod enable/disable`.

## Music Issues

### Q: The bot says "The page needs to be reloaded" or has YouTube errors
**A:** This is common with YouTube's bot protection. Solutions:
1. Make sure you have a valid `cookies.txt` file in the bot directory
2. For better results on flagged hosts, set up a PO token provider with `POT_SERVER_URL`
3. Use the `sudo refresh` command after updating cookies
4. Try different tracks - some may work better than others

### Q: Music won't play or bot won't join VC
**A:** Check that:
- The bot has Connect and Speak permissions in the voice channel
- You're in a voice channel
- The bot isn't already in another channel in the same server

### Q: How do I use the premium music features?
**A:** All premium features are available by default:
- **Party Mode**: `sudo partymode` - Enhanced queue experience
- **DJ Mode**: `sudo djmode` - Priority controls
- **Similar Songs**: `sudo similar` - Get song suggestions
- **History**: `sudo history` - See recently played tracks
- **Favorites**: `sudo favorite` to save, `sudo myfavorites` to view

### Q: How do I set up repeat/loop?
**A:** Use `sudo loop` to toggle. Options:
- `sudo loop` or `sudo loop single` - Repeat current track
- `sudo loop queue` - Repeat entire queue
- `sudo loop off` - Turn off looping

## Moderation

### Q: How do I set up auto-moderation?
**A:** Use `sudo automod enable` then configure:
- Block words: `sudo automod word add <word>`
- Link filtering: `sudo automod allow add <domain>`
- Mention limits: `sudo automod mentions 5`
- Alert channel: `sudo automod alert #mod-logs`

Or use `/modsettings` for easy toggles.

### Q: How do I set up logging?
**A:** Use `sudo logsetup #channel` to enable logging. All major events (joins, leaves, messages, bans, etc.) will be logged.

### Q: How do I see server audit information?
**A:** Use `/audit` or `sudo audit` to generate a comprehensive audit report showing your server's configuration and security status.

## XP & Levels

### Q: How does XP work?
**A:** Users gain XP by chatting and being in voice channels. Levels increase based on XP earned.

### Q: How do I change where level-up messages go?
**A:** Use `sudo levelchannel set #channel` to set a specific channel, or `sudo levelchannel off` to have messages in chat, or `sudo levelchannel status` to check.

### Q: Is XP enabled by default?
**A:** Yes, XP is enabled by default. You can disable it with `/config_set setting:xp_enabled enable:false` or via the dashboard.

## Troubleshooting

### Q: Commands aren't working
**A:** Check:
- Bot has necessary permissions
- You're using the correct prefix (`sudo `)
- For slash commands, make sure they're synced (bot does this on startup)

### Q: Bot isn't responding
**A:** Try:
- Check if bot is online
- Verify bot has Read Messages and Send Messages permissions
- Use `sudo ping` to check latency

### Q: I see "Permission denied" errors
**A:** Make sure you have the required permissions for that command. Some commands require Administrator, Manage Server, or specific moderation permissions.

### Q: The dashboard/UI buttons don't work
**A:** Make sure you have Manage Server permissions. UI interactions are restricted to users with appropriate permissions.

## Still Need Help?

If your issue isn't covered here:
1. Check the [Command Reference](COMMAND_REFERENCE.md)
2. Use `sudo man <command>` for specific command help
3. Join our support server for direct assistance
4. Check the bot status with `sudo status`
