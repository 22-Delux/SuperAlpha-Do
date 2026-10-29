# Tutorials - Setup and Features

Step-by-step guides to help you master SuperAlpha Do's features.

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
   alpha logsetup #mod-logs
   ```

2. **Configure auto-moderation**
   ```
   alpha automod enable
   alpha automod word add scam
   alpha automod word add phishing
   alpha automod mentions 6
   alpha automod action warn
   alpha automod alert #mod-logs
   ```

3. **Whitelist safe links**
   ```
   alpha automod allow add discord.com
   alpha automod allow add youtube.com
   alpha automod allow add github.com
   ```

4. **Test it** - Try the mod commands
   ```
   alpha mute @user 10m
   alpha purge 10
   ```

### Tips
- Use `/modsettings` for easy toggles
- Check automod status with `alpha automod status`

---

## Tutorial 3: Premium Music Setup

**Time:** 3 minutes | **Difficulty:** Beginner

### Goal
Learn to use all the premium music features.

### Steps

1. **Join a voice channel** and play music
   ```
   alpha play never gonna give you up
   ```

2. **Explore queue features**
   ```
   alpha queue        # View premium queue UI
   alpha nowplaying   # See now playing with thumbnail
   alpha loop queue   # Loop the whole queue
   alpha shuffle      # Shuffle queue
   ```

3. **Try premium features**
   ```
   alpha partymode    # Enable party mode
   alpha similar      # Get song suggestions
   alpha history      # View recently played
   alpha favorite     # Save current track
   alpha myfavorites  # View your favorites
   ```

4. **Control playback**
   ```
   alpha volume 80
   alpha skip
   alpha pause/resume
   alpha stop
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
   alpha rank
   ```

2. **View leaderboard**
   ```
   alpha leaderboard
   ```

3. **Set up level-up notifications**
   ```
   alpha levelchannel set #level-ups
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
   alpha giveaway create 1h 1w Nitro Classic
   ```
   Duration: 1h (1 hour), Winners: 1, Prize: Nitro Classic

2. **Manage giveaways**
   ```
   alpha giveaway list    # View active giveaways
   alpha giveaway end <message_id>  # End early
   alpha giveaway reroll <message_id> # Reroll winners
   alpha giveaway cancel <message_id> # Cancel
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
- **Help system**: `alpha man` is powerful - search by function or keywords
- **Branding**: The bot has a consistent, polished look throughout
- **Premium feel**: Features like party mode, DJ mode, and polished embeds enhance the experience
- **Stay organized**: Use the dashboard for all admin tasks

## Need More Help?

- [Command Reference](COMMAND_REFERENCE.md) - All commands
- [FAQ](FAQ.md) - Common issues
- [Quick Start for Admins](QUICK_START_ADMINS.md) - Admin guide
- Use `alpha status` to check bot health
