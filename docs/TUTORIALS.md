# Tutorials - Setup and Features

Step-by-step guides to help you master sudo-bot's features.

## Tutorial 1: Complete Server Setup

**Time:** 5 minutes | **Difficulty:** Beginner

### Goal
Set up your server with all essential features configured.

### Steps

1. **Invite the bot** with Administrator permissions
2. **Run setup wizard**
   ```
   /setup
   ```
   Fill in the modal with your preferred channels and roles
3. **Access dashboard**
   ```
   /config
   ```
   Review your configuration
4. **Run audit**
   ```
   /audit
   ```
   Check for any issues
5. **Test features** - Try a few commands to make sure everything works

### Tips
- The setup wizard can be re-run anytime
- Use the dashboard for ongoing management

---

## Tutorial 2: Setting Up Moderation

**Time:** 10 minutes | **Difficulty:** Intermediate

### Goal
Configure comprehensive moderation tools.

### Steps

1. **Set up logging**
   ```
   sudo logsetup #mod-logs
   ```

2. **Configure auto-moderation**
   ```
   sudo automod enable
   sudo automod word add scam
   sudo automod word add phishing
   sudo automod mentions 6
   sudo automod action warn
   sudo automod alert #mod-logs
   ```

3. **Whitelist safe links**
   ```
   sudo automod allow add discord.com
   sudo automod allow add youtube.com
   sudo automod allow add github.com
   ```

4. **Test it** - Try the mod commands
   ```
   sudo mute @user 10m
   sudo purge 10
   ```

### Tips
- Use `/modsettings` for easy toggles
- Check automod status with `sudo automod status`

---

## Tutorial 3: Premium Music Setup

**Time:** 3 minutes | **Difficulty:** Beginner

### Goal
Learn to use all the premium music features.

### Steps

1. **Join a voice channel** and play music
   ```
   sudo play never gonna give you up
   ```

2. **Explore queue features**
   ```
   sudo queue        # View premium queue UI
   sudo nowplaying   # See now playing with thumbnail
   sudo loop queue   # Loop the whole queue
   sudo shuffle      # Shuffle queue
   ```

3. **Try premium features**
   ```
   sudo partymode    # Enable party mode
   sudo similar      # Get song suggestions
   sudo history      # View recently played
   sudo favorite     # Save current track
   sudo myfavorites  # View your favorites
   ```

4. **Control playback**
   ```
   sudo volume 80
   sudo skip
   sudo pause/resume
   sudo stop
   ```

### Tips
- Use slash commands for music too: `/play`, `/similar`, etc.
- Party mode makes the queue experience more fun
- DJ mode gives enhanced control

---

## Tutorial 4: XP & Leveling System

**Time:** 2 minutes | **Difficulty:** Beginner

### Goal
Configure and use the XP system.

### Steps

1. **Check your rank**
   ```
   sudo rank
   ```

2. **View leaderboard**
   ```
   sudo leaderboard
   ```

3. **Set up level-up notifications**
   ```
   sudo levelchannel set #level-ups
   ```
   Or let them appear in chat (default)

4. **Customize** - XP is earned automatically by:
   - Sending messages (with cooldown)
   - Being in voice channels

### Tips
- Level-up messages are automatic
- Use the dashboard to enable/disable XP

---

## Tutorial 5: Giveaways

**Time:** 3 minutes | **Difficulty:** Beginner

### Goal
Create and manage giveaways.

### Steps

1. **Create a giveaway**
   ```
   sudo giveaway create 1h 1w Nitro Classic
   ```
   Duration: 1h (1 hour), Winners: 1, Prize: Nitro Classic

2. **Manage giveaways**
   ```
   sudo giveaway list    # View active giveaways
   sudo giveaway end <message_id>  # End early
   sudo giveaway reroll <message_id> # Reroll winners
   sudo giveaway cancel <message_id> # Cancel
   ```

### Duration formats
- `s` - seconds
- `m` - minutes
- `h` - hours
- `d` - days
- `w` - weeks

### Tips
- Users react with 🎉 to enter
- Winners are picked automatically when time ends

---

## Tutorial 6: Using the Admin Dashboard

**Time:** 4 minutes | **Difficulty:** Beginner

### Goal
Master the centralized admin interface.

### Steps

1. **Open dashboard**
   ```
   /config
   ```

2. **Explore tabs**
   - **View Config** - See all settings at a glance
   - **Mod Settings** - Toggle features with buttons
   - **Logs Summary** - Check logging coverage
   - **Audit Report** - Security review

3. **Use quick toggles** in Mod Settings to enable/disable:
   - Auto-moderation
   - Welcome messages
   - Server logging
   - XP system

4. **Use /config_set for quick changes**
   ```
   /config_set setting:welcome_channel channel:#general
   /config_set setting:automod_enabled enable:true
   ```

### Tips
- All changes are saved immediately
- Use the dashboard instead of memorizing many commands
- Run audit reports regularly for security checks

---

## Pro Tips

- **Keyboard shortcuts**: Use slash commands for better UX with autocomplete
- **Help system**: `sudo man` is powerful - search by function or keywords
- **Branding**: The bot has a consistent, polished look throughout
- **Premium feel**: Features like party mode, DJ mode, and polished embeds enhance the experience
- **Stay organized**: Use the dashboard for all admin tasks

## Need More Help?

- [Command Reference](COMMAND_REFERENCE.md) - All commands
- [FAQ](FAQ.md) - Common issues
- [Quick Start for Admins](QUICK_START_ADMINS.md) - Admin guide
- Use `sudo status` to check bot health
