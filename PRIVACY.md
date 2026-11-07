# SuperAlpha Do — Privacy Policy

**Effective date:** 29 September 2026
**Last updated:** 29 September 2026

This Privacy Policy explains what information **SuperAlpha Do** (the "Bot") collects
when you use it on Discord, how that information is used, who it is shared with, and
the choices you have. It applies to the Bot itself and to the operator of the Bot.

By using the Bot, you agree to this Privacy Policy. If you do not agree, please do
not use the Bot. On its own, the Bot is not enough to obtain a paid hosted service —
see our [Terms of Service](./TERMS.md) for the terms that govern your use.

---

## 1. Who we are

The Bot is operated by **Ayushmaan Gupta** (the "Operator", "we", "us"). For the
purposes of applicable data protection law, the Operator is the controller of the
personal data described below.

- Support server: https://discord.gg/Z2NXkwkFK3
- Bot owner contact: `@r4ve_x` on Discord
- Contact email: guptamaamayush@gmail.com

---

## 2. Information we collect

The Bot only receives information that Discord makes available to it through the
Discord API, and information that you or a server administrator choose to provide.
We do not operate an account system of our own.

### 2.1 Discord account and server data

When you interact with the Bot, we may process:

- Your Discord **user ID**, **username**, **display name**, and **avatar**;
- The **ID of the server (guild)** where you interact with the Bot, and the IDs of
  the relevant channels, roles, messages and threads;
- Membership events, such as joins, leaves, role changes, nickname changes, and
  bans (only if a server administrator has enabled logging — see Section 2.2);
- Your **voice state** (whether you are in a voice channel), used to run music
  playback and voice features. We do not record or store voice audio.

### 2.2 Message content and attachments

The Bot processes the content of messages in order to function:

- **Commands.** When you run a command (for example `alpha play …`), the command
  name and its arguments are processed. Command text is stored locally, as described
  in Section 7.
- **Message logging (optional, per server).** If a server administrator enables a
  logging feature, the Bot may republish the following into a Discord channel chosen
  by that server: deleted message text, edited message text (before and after),
  message attachments, member join/leave events, role changes, nickname changes, and
  bans. This is configured and controlled entirely by the server administrator, not
  by the Bot globally.
- **Attachments.** If a message containing images is logged, the Bot may download
  those images from Discord's CDN into **temporary memory only** so they can be
  re-uploaded to the log channel. Cached images are not written to disk and are lost
  when the Bot restarts.

> **Note on the Message Content intent.** The Bot enables Discord's privileged
> "Message Content" intent, as well as the Members, Presence and Voice State intents.
> These are required for command parsing, optional logging, and voice features. The Bot
> is designed to process message content only for the features described in this policy;
> it does not use it for advertising, profiling, or any purpose beyond operating the Bot.

### 2.3 Commands and usage data

The Bot keeps local records for debugging and for its `journalctl`/`history` features:

- **Server activity journal.** Records the command name, server and user identifiers
  (stored in hashed form), timestamps, and truncated command details.
- **Per-user command history.** Stores your **last 100 command lines** as you typed
  them, so you can re-run them with `history`, `!!` and `!<line>`. This can include text
  you entered as part of a command — for example an AI prompt, the text of a
  suggestion, or text you asked the Bot to translate. This history is stored locally
  and is not shared with third parties, but it is kept as plain text.

See Section 7 for the exact scope and retention.

### 2.4 AI conversations

If you use the AI chat feature, the text you send is processed to generate a
response. The **last 20 messages of the conversation per user** are stored locally so
the AI can keep context, and your prompt (together with recent conversation history)
is sent to our AI provider, **Groq**, to generate the reply. Use `alpha aiclear` to
delete your stored AI conversation.

### 2.5 Feature data

Depending on which features you use, the Bot may store:

- Levelling/XP statistics (XP, level, messages counted, voice time, command count,
  daily streaks);
- Economy balances and purchased items;
- Clan membership, clan scores, and clan war records;
- Music favorites and playlists;
- Suggestions you submit, and your votes on them;
- Giveaway participation metadata;
- AFK status and the reason you supplied;
- Guess-game scores (for example the distro guessing game);
- Automod strike counts.

### 2.6 Server configuration

Server administrators can configure the Bot (welcome messages, log channels, automod
word lists, XP settings, suggestion boards, and so on). This configuration is stored
locally and may contain channel IDs, role IDs, and message IDs.

### 2.7 Technical and log data

The Bot writes operational logs to its console/hosting environment. These logs can
include the command name, your user ID and tag, the server name, and the channel — but
not your command arguments or message bodies.

---

## 3. Information we do **not** collect

- We do **not** collect your email address, real name, phone number, or payment
  information.
- We do **not** record voice audio.
- We do **not** process regular (non-command) message content, except where a server
  administrator has enabled message logging, or where an image must be temporarily
  cached to re-post it in a log channel.
- We do **not** sell your personal data, and we do **not** use it for advertising.
- We do **not** use your data to train AI models.

---

## 4. How we use your information

We use the information described above to:

- Provide, operate and maintain the Bot's features;
- Respond to your commands and requests;
- Keep server activity journals and per-user command history;
- Enable optional logging configured by server administrators;
- Generate AI responses;
- Detect abuse, spam, and violations of our Terms of Service;
- Diagnose errors and improve reliability.

---

## 5. Legal bases (where applicable)

Where laws such as the GDPR or UK GDPR apply, we rely on:

- **Legitimate interests** — to operate and secure the Bot, prevent abuse, and
  provide functionality that server administrators have enabled;
- **Consent** — for optional features you actively trigger, such as AI chat, and for
  server logging where the server administrator has obtained member consent;
- **Legal obligation** — where we must retain or disclose information to comply with
  the law.

---

## 6. Third-party services

Some features send limited data to third parties. We do not control these services;
their own privacy policies apply. The data sent is limited to what the feature needs.

| Service | What is sent | Why |
|---|---|---|
| **Discord** | All interactions with the Bot | Required to operate the Bot |
| **Groq** (`api.groq.com`) | Your AI prompt and recent conversation history | Generate AI replies |
| **GitHub** (`api.github.com`) | Suggestion text and your Discord mention, when a suggestion is linked to an issue | Create/link GitHub issues; read public repository metadata |
| **Spotify** (`open.spotify.com`, `api.spotify.com`, `accounts.spotify.com`) | The Spotify track ID from a link you paste | Resolve a Spotify link to a song title and artist |
| **Apple / iTunes** (`itunes.apple.com`) | The Apple Music song ID from a link you paste | Resolve an Apple Music link to a song title and artist |
| **YouTube / SoundCloud / Bandcamp / Twitch** (via Lavalink) | Your search term or the URL you paste, sent to the Lavalink node that handles playback | Find and stream audio for playback |
| **Lavalink nodes** (public pool or Operator-configured) | Your search term, pasted URL, and Discord voice-channel/guild identifiers needed to route audio | Resolve and stream audio; the Bot's public-node pool may change between requests |
| **JokeAPI** (`v2.jokeapi.dev`) | No personal data (fixed category) | Joke command |
| **ZenQuotes** (`zenquotes.io`) | No personal data | Quote command |
| **Wikipedia** (`en.wikipedia.org`) | Your search term | Wiki command |
| **wttr.in** | The city name you enter | Weather command |
| **Urban Dictionary** (`api.urbandictionary.com`) | Your search term | Urban dictionary command |
| **Free Dictionary** (`dictionaryapi.dev`) | The word you enter | Define command |
| **TinyURL** (`tinyurl.com`) | The URL you ask to shorten | Shorten command |
| **MyMemory** (`api.mymemory.translated.net`) | The text you ask to translate and the language pair | Translate command |
| **Discord CDN** (`cdn.discordapp.com`) | Attachment bytes, re-uploaded into log channels | Message logging |

Because these requests originate from the Bot's hosting environment, the third party
will see the Bot's IP address and request details. They may log these requests under
their own policies.

---

## 7. Data storage and retention

Data is stored locally on the Operator's hosting environment, primarily in an SQLite
database and JSON/plain-text files. We keep data only as long as needed for the
purposes above, but retention varies by feature:

| Data | Retention |
|---|---|
| AI conversation memory | Last 20 messages per user; deleted with `alpha aiclear` |
| Server activity journal | Last 400 entries in total |
| Per-user command history | Last 100 commands per user |
| Levelling/XP, economy, clans, shop | Kept until deleted on request |
| Suggestions and votes | Kept until deleted on request |
| Giveaways | Kept until the giveaway ends or is deleted |
| Music favorites | Kept until deleted on request |
| AFK status | Kept until you return or clear it |
| Automod strikes | Automatically expire after 24 hours |
| Welcome/log configuration | Kept until changed or the Bot is removed |
| Cached attachment images | In memory only; lost on restart |
| Reminders, temporary voice, player state | In memory only; lost on restart |

---

## 8. Security

We take reasonable measures to protect the data we hold:

- Secrets (the Discord token, API keys, and any Lavalink node passwords) are kept
  in an environment file that is **not** committed to source control.
- User and server identifiers in the server activity journal are stored in **hashed**
  form.
- Attachment images are held in memory with strict size and count limits, and are
  never written to disk.

However, no method of storage or transmission is completely secure. We cannot
guarantee absolute security, and you provide information at your own risk.

---

## 9. International transfers

The Bot may be hosted in a country different from yours, and the third-party services
listed in Section 6 are located in various countries (including the United States).
By using the Bot, you understand that your information may be transferred to and
processed in those countries.

---

## 10. Your rights and choices

Depending on where you live, you may have the right to:

- **Access** the personal data we hold about you;
- **Correct** inaccurate data;
- **Delete** your data ("right to erasure");
- **Object to** or **restrict** certain processing;
- **Withdraw consent** at any time, without affecting processing already carried out;
- **Port** your data to another service;
- **Complain** to your local data protection authority.

To exercise any of these rights, contact us using the details in Section 1. We may ask
you to verify that you control the Discord account in question. Some data can be
cleared by you directly (for example `alpha aiclear` for AI memory). Note that some
features do not yet offer a self-service deletion command, so deletion requests for
XP, clans and favorites are handled manually by the Operator.

If you are a member of a server that uses the Bot's logging features, please contact
that server's administrators first — they control what is logged and where it is sent.

---

## 11. Children

The Bot is intended for users who meet Discord's minimum age requirement (13 years
old, or older where local law requires). We do not knowingly collect data from anyone
below that age. If you believe a child has provided data to the Bot, contact us and we
will delete it.

---

## 12. Changes to this policy

We may update this Privacy Policy from time to time. When we do, we will change the
"Last updated" date at the top and, where the change is significant, provide notice
in the support server. Continued use of the Bot after a change means you accept the
updated policy.

---

## 13. Contact

Questions about this policy or requests about your data:

- Support server: https://discord.gg/Z2NXkwkFK3
- Discord: `@r4ve_x`
- Email: guptamaamayush@gmail.com
