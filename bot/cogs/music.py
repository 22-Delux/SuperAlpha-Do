"""
bot/cogs/music.py — Music commands powered by Wavelink (Lavalink v4).

Playback, queue state, and effects are handled by a pool of Lavalink nodes.

Commands: join, leave, play, pause, resume, stop, skip, queue, revive,
          nowplaying, volume, shuffle, loop, remove, clearqueue, seek, replay,
          autoplay, bassboost, nightcore, 8d, equalizer, lyrics, favorite,
          favorites, playlist, refresh, slowed, similar, partymode, djmode,
          history, myfavorites, radio
"""

from __future__ import annotations

import asyncio
import logging
import math
import os
import random
from collections import deque
from urllib.parse import quote_plus

import discord
import wavelink
from discord import app_commands
from discord.abc import Messageable
from discord.ext import commands

from bot.cogs.checks import perms_or_developer
from bot.services.embeds import music_embed, queue_embed
from bot.services.music import (
    VALID_PRESETS,
    GuildPlayer,
    NodeManager,
    NoNodesAvailable,
    Track,
    TrackSearchError,
    build_filters,
    describe_filters,
    fetch_apple_metadata,
    fetch_spotify_metadata,
    is_apple_url,
    is_spotify_url,
    parse_apple_url,
    parse_spotify_url,
    search_query_for,
)

log = logging.getLogger(__name__)

# How long to wait for Wavelink to resume a dropped node before moving players
# to another node.  Lavalink session resumption is usually much faster than this.
NODE_FAILOVER_GRACE = 12.0

EMOJI_MUSIC_PLAY = "<a:musicplay:1485243787084042270>"
EMOJI_MUSIC_PAUSE = "<a:musicpause:1485244346386350111>"
EMOJI_MUSIC_STOP = "⏹️"
EMOJI_MUSIC_SHUFFLE = "<a:musicshuffle:1485245854548885626>"
EMOJI_MUSIC_LOOP = "<a:musicloop:1485246094505017515>"
EMOJI_MUSIC_VOL = "<a:musicvol:1485246400940867695>"

__all__ = ["Music", "Track", "GuildPlayer", "build_filters", "NodeManager"]


class Music(commands.Cog, name="music"):
    """Music playback commands backed by a failover pool of Lavalink nodes."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self._players: dict[int, GuildPlayer] = {}
        self._last_fetch_error: str | None = None
        self.nodes = NodeManager(bot)
        self._node_task: asyncio.Task[None] | None = None

    async def cog_load(self) -> None:
        # Cogs are loaded before the bot logs in, and Wavelink needs the bot's
        # user id for the Lavalink handshake.  Wait for ``on_ready`` first.
        self._node_task = asyncio.create_task(self._connect_nodes(), name="lavalink-connect")

    async def _connect_nodes(self) -> None:
        try:
            await self.bot.wait_until_ready()
        except asyncio.CancelledError:
            return
        try:
            await self.nodes.connect()
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # pragma: no cover - defensive
            log.exception("Could not start the Lavalink node pool: %s", exc)

    async def cog_unload(self) -> None:
        if self._node_task is not None and not self._node_task.done():
            self._node_task.cancel()
            self._node_task = None
        await self.nodes.close()

    # ── Wavelink / voice events ──────────────────────────────────────────────
    @commands.Cog.listener()
    async def on_voice_state_update(
        self,
        member: discord.Member,
        before: discord.VoiceState,
        after: discord.VoiceState,
    ) -> None:
        """Auto-leave when everyone leaves the voice channel."""
        if member.bot:
            return
        try:
            if before.channel and before.channel.guild:
                guild = before.channel.guild
                voice_client = guild.voice_client
                player = self._get_player(guild.id)
                player.skip_votes.discard(member.id)
                if voice_client and voice_client.channel == before.channel:
                    if (
                        len(voice_client.channel.members) == 1
                        and voice_client.channel.members[0].bot
                    ):
                        player.last_track = player.current
                        player.queue.clear()
                        player.current = None
                        player._advance_on_stop = False
                        player.skip_votes.clear()
                        self._reset_player_settings(player)
                        try:
                            await self._update_presence(None, guild)
                            await voice_client.disconnect()
                        except Exception:
                            pass
        except Exception:
            pass

    @commands.Cog.listener()
    async def on_wavelink_track_end(self, payload: "wavelink.TrackEndEventPayload") -> None:
        """Advance the custom queue whenever Lavalink finishes a track."""
        wl_player = payload.player
        if wl_player is None or wl_player.guild is None:
            return
        guild_id = wl_player.guild.id
        player = self._get_player(guild_id)
        if player.game_active:
            return
        if payload.reason in ("replaced", "cleanup"):
            return
        if payload.reason == "stopped" and not player._advance_on_stop:
            return
        player._advance_on_stop = False
        if payload.reason == "loadFailed":
            await self._notify(
                player,
                self._make_embed(
                    "❌ Track Failed",
                    0xE74C3C,
                    "Lavalink could not play that track. Trying the next one.",
                ),
            )
        await self._play_next_impl(guild_id)

    @commands.Cog.listener()
    async def on_wavelink_track_exception(self, payload: "wavelink.TrackExceptionEventPayload") -> None:
        wl_player = payload.player
        if wl_player is None or wl_player.guild is None:
            return
        player = self._get_player(wl_player.guild.id)
        message = payload.exception.get("message", "unknown error")
        log.warning("Track exception in guild %s: %s", player.guild_id, message)
        await self._notify(
            player,
            self._make_embed(
                "❌ Playback Error",
                0xE74C3C,
                "The music node hit an error while playing. Trying the next track.",
            ),
        )

    @commands.Cog.listener()
    async def on_wavelink_track_stuck(self, payload: "wavelink.TrackStuckEventPayload") -> None:
        wl_player = payload.player
        if wl_player is None or wl_player.guild is None:
            return
        await self._skip_current(wl_player.guild.id)

    @commands.Cog.listener()
    async def on_wavelink_node_closed(self, node: "wavelink.Node", players: list["wavelink.Player"]) -> None:
        """Move affected players onto another node when one dies mid-song."""
        if self.nodes.closing:
            return
        for wl_player in players:
            asyncio.create_task(self._recover_after_node_close(wl_player, node))

    @commands.Cog.listener()
    async def on_wavelink_node_disconnected(self, payload: "wavelink.NodeDisconnectedEventPayload") -> None:
        """Fail over if a node drops and does not come back promptly.

        Wavelink retries a lost websocket indefinitely (``retries=None``), so a
        dead or maintenance node never emits ``node_closed``.  Snapshot its
        players now, give the reconnect a grace period, then move anything left
        onto a healthy node.
        """
        if self.nodes.closing:
            return
        node = payload.node
        players = list(node.players.values())
        if players:
            asyncio.create_task(self._recover_players_after_disconnect(node, players))

    async def _recover_players_after_disconnect(
        self, node: "wavelink.Node", players: list["wavelink.Player"]
    ) -> None:
        await asyncio.sleep(NODE_FAILOVER_GRACE)
        if self.nodes.closing or node.status is wavelink.NodeStatus.CONNECTED:
            return
        for wl_player in players:
            await self._recover_after_node_close(wl_player, node)

    @commands.Cog.listener()
    async def on_wavelink_inactive_player(self, player: "wavelink.Player") -> None:
        if player.guild is None:
            return
        state = self._get_player(player.guild.id)
        state.last_track = state.current
        state.current = None
        state.queue.clear()
        state._advance_on_stop = False
        try:
            await player.disconnect()
        except Exception:
            pass

    # ── shared helpers ───────────────────────────────────────────────────────
    async def _update_presence(self, track: Track | None, guild: discord.Guild) -> None:
        """Update the voice channel status to show the current track."""
        try:
            voice_client = guild.voice_client
            if voice_client:
                if track:
                    await voice_client.channel.edit(
                        status=f"<a:dance:1484553189964644352> Listening: {track.title[:100]}"
                    )
                else:
                    await voice_client.channel.edit(status=None)
        except Exception:
            pass

    def _build_now_playing_embed(
        self, track: Track, player: GuildPlayer
    ) -> discord.Embed:
        """Build the now playing embed for a track."""
        embed = music_embed(
            title="Now Playing",
            description=f"[{track.title}]({track.url})" if track.url else track.title,
        )
        if track.artwork:
            try:
                embed.set_thumbnail(url=track.artwork)
            except Exception:
                pass
        embed.add_field(name="Duration", value=track.fmt_duration(), inline=True)
        embed.add_field(name="Requested by", value=track.requester.mention, inline=True)
        embed.add_field(name="Loop / Repeat", value=self._loop_state(player), inline=True)
        embed.add_field(name="Volume", value=f"{int(player.volume * 100)}%", inline=True)
        effects = describe_filters(player)
        if effects != "none":
            embed.add_field(name="Effects", value=effects, inline=True)
        if getattr(player, "dj_mode", False):
            embed.add_field(name="DJ Mode", value="✅ Enabled", inline=True)
        if getattr(player, "party_mode", False):
            embed.add_field(name="Party Mode", value="🎉 Active", inline=True)
        if getattr(player, "queue_history", None) and player.queue_history:
            embed.add_field(name="History", value=f"{len(player.queue_history)} tracks", inline=True)
        embed.set_footer(text="Use alpha queue • alpha similar • alpha history • alpha favorites")
        return embed

    def _make_embed(
        self, title: str, color: int, description: str = ""
    ) -> discord.Embed:
        embed = discord.Embed(color=color)
        embed.set_author(name=title, icon_url=None)
        if description:
            embed.description = description
        return embed

    def _get_player(self, guild_id: int) -> GuildPlayer:
        if guild_id not in self._players:
            self._players[guild_id] = GuildPlayer(guild_id)
        return self._players[guild_id]

    @staticmethod
    def _remember_text_channel(player: GuildPlayer, ctx: commands.Context) -> None:
        player.text_channel = ctx.channel if isinstance(ctx.channel, Messageable) else None

    async def _notify(self, player: GuildPlayer, embed: discord.Embed) -> None:
        """Best-effort status message; never breaks playback."""
        channel = player.text_channel
        if channel is None:
            return
        try:
            await channel.send(embed=embed)
        except Exception as exc:
            log.debug("Could not post music status in guild %s: %s", player.guild_id, exc)

    async def _ensure_voice(self, ctx: commands.Context) -> "wavelink.Player":
        """Return a connected Wavelink player, joining the author's channel if needed."""
        if ctx.voice_client is not None:
            existing = ctx.voice_client
            if isinstance(existing, wavelink.Player):
                return existing
            try:
                await existing.disconnect(force=True)
            except Exception:
                pass

        if not getattr(ctx.author, "voice", None) or not ctx.author.voice.channel:
            raise RuntimeError("You must be in a voice channel.")

        node = await self.nodes.wait_for_node(timeout=10.0)
        if node is None:
            raise NoNodesAvailable("No Lavalink nodes are currently connected.")

        return await ctx.author.voice.channel.connect(cls=wavelink.Player, timeout=20.0)

    async def _apply_filters(self, player: GuildPlayer) -> None:
        guild = self.bot.get_guild(player.guild_id)
        voice_client = guild.voice_client if guild else None
        if isinstance(voice_client, wavelink.Player):
            try:
                await voice_client.set_filters(build_filters(player))
            except Exception as exc:
                log.debug("Could not apply filters in guild %s: %s", player.guild_id, exc)

    async def _play_track(self, guild_id: int, track: Track) -> "wavelink.Player":
        """Play *track*, retrying on another node if the first one refuses."""
        guild = self.bot.get_guild(guild_id)
        voice_client = guild.voice_client if guild else None
        if not isinstance(voice_client, wavelink.Player):
            raise RuntimeError("The bot is not connected to a voice channel.")

        player = self._get_player(guild_id)
        if track.playable is None:
            raise RuntimeError("Track has no Lavalink payload.")

        volume = int(max(0, min(1000, player.volume * 100)))
        filters = build_filters(player)
        try:
            await voice_client.play(track.playable, volume=volume, filters=filters)
        except Exception as exc:
            log.warning("Playback failed on node %s: %s", voice_client.node.identifier, exc)
            new_node = await self.nodes.failover_player(voice_client)
            if new_node is None:
                raise
            await voice_client.play(track.playable, volume=volume, filters=filters)

        player.current = track
        player._start_time = asyncio.get_running_loop().time()
        return voice_client

    async def _autoplay_track(self, player: GuildPlayer) -> Track | None:
        base = player.last_track or player.current
        if base is None:
            return None
        try:
            playable = await self.nodes.search_first(f"{base.title} similar")
        except Exception:
            return None
        if playable is None:
            return None
        return Track(playable, base.requester)

    async def _play_next_impl(self, guild_id: int) -> None:
        player = self._get_player(guild_id)
        if player.game_active:
            return
        player.skip_votes.clear()
        player._play_generation += 1

        # Requeue or record the track that just finished.
        if player.current is not None:
            finished = player.current
            if player.loop:
                player.queue.appendleft(finished)
            elif player.queue_loop:
                player.queue.append(finished)
            else:
                player.queue_history.appendleft(finished)
            player.last_track = finished
        player.current = None

        guild = self.bot.get_guild(guild_id)

        attempts = 0
        while player.queue and attempts < 50:
            attempts += 1
            track = player.queue.popleft()
            try:
                await self._play_track(guild_id, track)
            except Exception as exc:
                log.warning("Could not play %r in guild %s: %s", track.title, guild_id, exc)
                await self._notify(
                    player,
                    self._make_embed(
                        "❌ Track Skipped",
                        0xE74C3C,
                        f"Could not play **{track.title}** — trying the next track.",
                    ),
                )
                continue

            # Cosmetic steps must never touch the queue.
            try:
                if guild:
                    await self._update_presence(track, guild)
            except Exception as exc:
                log.debug("Presence update failed in guild %s: %s", guild_id, exc)
            await self._notify(player, self._build_now_playing_embed(track, player))
            return

        if player.autoplay:
            track = await self._autoplay_track(player)
            if track is not None:
                player.queue.append(track)
                await self._play_next_impl(guild_id)
                return

        player.current = None
        player.skip_votes.clear()
        if guild:
            await self._update_presence(None, guild)
        await self._notify(
            player,
            self._make_embed("🎵 Queue Finished", 0x95A5A6, "No more tracks in queue."),
        )

    async def _skip_current(self, guild_id: int) -> None:
        """Stop the current track and let the track-end event advance the queue."""
        guild = self.bot.get_guild(guild_id)
        voice_client = guild.voice_client if guild else None
        if not isinstance(voice_client, wavelink.Player):
            return
        player = self._get_player(guild_id)
        player._advance_on_stop = True
        generation = player._play_generation
        try:
            await voice_client.stop()
        except Exception:
            return
        asyncio.create_task(self._ensure_advance(guild_id, generation))

    async def _ensure_advance(self, guild_id: int, generation: int) -> None:
        """Fallback if Lavalink never sends the stop event for a skip."""
        await asyncio.sleep(1.5)
        player = self._get_player(guild_id)
        if player.game_active or player._play_generation != generation:
            return
        # If the track-end event had been handled, ``_advance_on_stop`` would
        # already be cleared.  It is still set, so the stop never came back.
        if not player._advance_on_stop:
            return
        player._advance_on_stop = False
        await self._play_next_impl(guild_id)

    async def _recover_after_node_close(self, wl_player: "wavelink.Player", node: "wavelink.Node") -> None:
        """Resume a player on a healthy node after its node disconnects."""
        guild = wl_player.guild
        if guild is None:
            return
        player = self._get_player(guild.id)
        if player.game_active:
            return

        track = player.current
        channel = getattr(wl_player, "channel", None)
        # ``position`` returns 0 once the node is gone; fall back to the last
        # position Lavalink reported so the track resumes where it stopped.
        position = max(
            0,
            int(
                getattr(wl_player, "position", 0)
                or getattr(wl_player, "_last_position", 0)
                or 0
            ),
        )
        if track is None or channel is None or track.playable is None:
            player.current = None
            return

        await asyncio.sleep(0.5)
        if not self.nodes.connected_nodes:
            await self.nodes.reconnect_disconnected()
        if not self.nodes.connected_nodes:
            player.current = None
            await self._notify(
                player,
                self._make_embed(
                    "❌ Music Node Offline",
                    0xE74C3C,
                    "Every music node is currently unavailable. Your queue is kept — "
                    "use `alpha revive` once a node is back.",
                ),
            )
            return

        try:
            existing = guild.voice_client
            if existing is not None:
                try:
                    await existing.disconnect(force=True)
                except Exception:
                    pass
            voice_client = await channel.connect(cls=wavelink.Player, timeout=20.0)
            await voice_client.play(
                track.playable,
                start=position,
                volume=int(max(0, min(1000, player.volume * 100))),
                filters=build_filters(player),
            )
            player.current = track
            player._start_time = asyncio.get_running_loop().time() - (position / 1000)
            await self._update_presence(track, guild)
            await self._notify(
                player,
                self._make_embed(
                    "🔄 Node Switched",
                    0x2ECC71,
                    f"Playback resumed on **{voice_client.node.identifier}** after "
                    f"**{node.identifier}** went offline.",
                ),
            )
        except Exception as exc:
            log.warning("Could not recover player in guild %s: %s", guild.id, exc)
            player.current = None
            await self._notify(
                player,
                self._make_embed(
                    "❌ Reconnect Failed",
                    0xE74C3C,
                    "Could not resume playback on another music node. "
                    "Use `alpha play` to start again.",
                ),
            )

    # ── metadata / search ────────────────────────────────────────────────────
    async def _fetch_tracks(
        self, query: str, requester: discord.Member
    ) -> list[Track]:
        """Resolve a query to Lavalink tracks, translating streaming links."""
        self._last_fetch_error = None
        search_query = query.strip()
        source: "wavelink.TrackSource | str | None" = wavelink.TrackSource.YouTube

        spotify = parse_spotify_url(query)
        if spotify:
            kind, spotify_id = spotify
            if kind != "track":
                self._last_fetch_error = (
                    f"I can't play a Spotify **{kind}** link. Open the song in "
                    "Spotify, then send me that song's own link."
                )
                return []
            info = await fetch_spotify_metadata(spotify_id)
            if not info:
                self._last_fetch_error = (
                    "Couldn't read that Spotify track. Add "
                    "`SPOTIPY_CLIENT_ID` and `SPOTIPY_CLIENT_SECRET` to `.env`, "
                    "or just send a search term."
                )
                return []
            search_query = search_query_for(info["title"], info["artist"])
            log.info("Spotify '%s' -> search: %s", spotify_id, search_query)

        apple = parse_apple_url(query)
        if apple:
            kind, song_id = apple
            if kind != "song":
                self._last_fetch_error = (
                    "I can't play an Apple Music **album** link. Open the song "
                    "in Apple Music, then send me that song's own link."
                )
                return []
            info = await fetch_apple_metadata(song_id)
            if not info:
                self._last_fetch_error = (
                    "Couldn't read that Apple Music track. Try sending a search "
                    "term instead."
                )
                return []
            search_query = search_query_for(info["title"], info["artist"])
            log.info("Apple Music '%s' -> search: %s", song_id, search_query)

        if query.startswith("http") and not (spotify or apple):
            if is_spotify_url(query) or is_apple_url(query):
                self._last_fetch_error = (
                    "That link doesn't point at a single song. Send the **song's** "
                    "share link, or just a search term."
                )
                return []

        try:
            result = await self.nodes.search(search_query, source=source)
        except NoNodesAvailable:
            self._last_fetch_error = (
                "No music nodes are available right now. Please try again in a moment."
            )
            return []
        except TrackSearchError as exc:
            log.warning("Every Lavalink node failed the search for %r: %s", search_query, exc)
            self._last_fetch_error = (
                "Couldn't find that track on any available music node. "
                "Try a different search or a direct link."
            )
            return []
        except Exception as exc:
            log.warning("Lavalink search error for %r: %s", search_query, exc)
            self._last_fetch_error = "The music service had a problem searching. Try again."
            return []

        if isinstance(result, wavelink.Playlist):
            playables = list(result.tracks)
        else:
            playables = list(result or [])

        if not playables:
            self._last_fetch_error = f"Could not find **'{query}'**"
            return []
        return [Track(playable, requester) for playable in playables]

    async def _fetch_track(self, query: str, requester: discord.Member) -> Track | None:
        tracks = await self._fetch_tracks(query, requester)
        return tracks[0] if tracks else None

    # ── join ──────────────────────────────────────────────────────────────────
    @commands.command(name="join", aliases=["connect", "j", "cd"])
    async def join(self, ctx: commands.Context) -> None:
        """Join your voice channel to play music. Usage: alpha join"""
        if not ctx.author.voice:
            await ctx.send(embed=self._make_embed(
                "❌ Not Connected", 0xE74C3C, "You are not in a voice channel"
            ))
            return
        channel = ctx.author.voice.channel
        try:
            if ctx.voice_client:
                try:
                    await ctx.voice_client.disconnect(force=True)
                    await asyncio.sleep(0.5)
                except Exception:
                    pass
            await self._ensure_voice(ctx)
            await ctx.send(embed=self._make_embed(
                "Connected", 0x3498DB, f"Joined voice channel: **{channel.name}**"
            ))
        except NoNodesAvailable:
            await ctx.send(embed=self._make_embed(
                "❌ Music Offline", 0xE74C3C,
                "No Lavalink nodes are available right now. Please try again shortly.",
            ))
        except Exception as e:
            await ctx.send(embed=self._make_embed(
                "❌ Connection Failed", 0xE74C3C, f"Could not join voice channel: {e}"
            ))

    # ── leave ─────────────────────────────────────────────────────────────────
    @commands.command(name="leave", aliases=["disconnect", "dc", "exit"])
    async def leave(self, ctx: commands.Context) -> None:
        """Leave the voice channel and stop playback. Usage: alpha leave"""
        if not ctx.voice_client:
            await ctx.send(embed=self._make_embed(
                "❌ Not Connected", 0xE74C3C, "Bot is not in a voice channel"
            ))
            return
        player = self._get_player(ctx.guild.id)
        player.last_track = player.current
        if player.current:
            player.queue_history.appendleft(player.current)
        player.queue.clear()
        player.current = None
        player._advance_on_stop = False
        self._reset_player_settings(player)
        voice_client = ctx.voice_client
        await self._update_presence(None, ctx.guild)
        try:
            await voice_client.disconnect()
        except Exception:
            pass
        await ctx.send(embed=self._make_embed("Disconnected", 0x3498DB, "Left the voice channel."))

    def _reset_player_settings(self, player: GuildPlayer) -> None:
        """Reset all player settings to default."""
        player.volume = 1.0
        player.loop = False
        player.queue_loop = False
        player.autoplay = False
        player.party_mode = False
        player.dj_mode = False
        player.dj_role_id = None
        player.bassboost = False
        player.nightcore = False
        player.eight_d = False
        player.slowed = False
        player.equalizer = "flat"

    # ── revive ────────────────────────────────────────────────────────────────
    @commands.command(name="revive", aliases=["resumequeue", "rq"])
    async def revive(self, ctx: commands.Context) -> None:
        """Revive the last track after bot disconnect. Usage: alpha revive"""
        player = self._get_player(ctx.guild.id)

        if player.current or player.queue:
            await ctx.send(embed=self._make_embed(
                "❌ Queue Active", 0xE74C3C,
                "A queue is already active. Use `alpha skip` to clear it first.",
            ))
            return

        if not player.last_track:
            await ctx.send(embed=self._make_embed(
                "❌ No Queue", 0xE74C3C, "No previous queue found to revive."
            ))
            return

        if not ctx.author.voice:
            await ctx.send(embed=self._make_embed(
                "❌ Not in VC", 0xE74C3C, "You must be in a voice channel"
            ))
            return

        try:
            await self._ensure_voice(ctx)
        except Exception as e:
            await ctx.send(embed=self._make_embed(
                "❌ Connection Failed", 0xE74C3C, f"Could not join voice: {e}"
            ))
            return

        previous = player.last_track
        player.current = previous
        player.last_track = None
        try:
            await self._play_track(ctx.guild.id, previous)
        except Exception as e:
            player.current = None
            player.last_track = previous
            await ctx.send(embed=self._make_embed(
                "❌ Playback Failed", 0xE74C3C,
                f"Could not resume **{previous.title}**: {e}",
            ))
            return
        await self._update_presence(player.current, ctx.guild)
        self._remember_text_channel(player, ctx)
        await ctx.send(embed=self._build_now_playing_embed(player.current, player))

    # ── play ──────────────────────────────────────────────────────────────────
    @commands.command(name="play", aliases=["p"])
    @commands.cooldown(1, 3, commands.BucketType.user)
    async def play(self, ctx: commands.Context, *, query: str) -> None:
        """Play a song or add it to the queue. Usage: alpha play <url or search query>"""
        player = self._get_player(ctx.guild.id)
        if player.game_active:
            await ctx.send(embed=self._make_embed(
                "❌ Game In Progress", 0xE74C3C,
                "A song-guessing game is running in this voice channel. "
                "Wait for it to finish before playing music.",
            ))
            return
        if not ctx.author.voice:
            await ctx.send(embed=self._make_embed(
                "❌ Not Connected", 0xE74C3C, "You must be in a voice channel"
            ))
            return

        try:
            voice_client = await self._ensure_voice(ctx)
        except NoNodesAvailable:
            await ctx.send(embed=self._make_embed(
                "❌ Music Offline", 0xE74C3C,
                "No Lavalink nodes are available right now. Please try again shortly.",
            ))
            return
        except Exception as e:
            await ctx.send(embed=self._make_embed(
                "❌ Connection Failed", 0xE74C3C, f"Could not join voice: {e}"
            ))
            return

        if parse_spotify_url(query):
            msg = await ctx.send(embed=self._make_embed("🔍 Spotify Detected", 0x1DB954, "Finding on Lavalink..."))
        elif is_apple_url(query):
            msg = await ctx.send(embed=self._make_embed("🔍 Apple Music Detected", 0xFC3C44, "Finding on Lavalink..."))
        else:
            msg = await ctx.send(embed=self._make_embed("🔍 Searching...", 0x1DB954, query))

        async with ctx.typing():
            tracks = await self._fetch_tracks(query, ctx.author)

        if msg:
            try:
                await msg.delete()
            except Exception:
                pass

        if not tracks:
            await ctx.send(embed=self._make_embed(
                "❌ Not Found", 0xE74C3C,
                self._last_fetch_error or f"Could not find **'{query}'**",
            ))
            return

        self._remember_text_channel(player, ctx)

        if voice_client.playing or voice_client.paused:
            for track in tracks[:100]:
                player.queue.append(track)
            embed = discord.Embed(color=0x1DB954)
            embed.set_author(name="➕ Added to Queue", icon_url=None)
            first = tracks[0]
            embed.description = f"[{first.title}]({first.url})" if first.url else first.title
            if len(tracks) > 1:
                embed.description += f"\n… and **{len(tracks) - 1}** more track(s)"
            embed.add_field(name="📍 Position", value=f"**{len(player.queue)}**", inline=True)
            embed.add_field(name="⏱️ Duration", value=first.fmt_duration(), inline=True)
            embed.set_footer(text=f"Requested by {first.requester.display_name}")
            await ctx.send(embed=embed)
            return

        first, rest = tracks[0], tracks[1:]
        for track in rest[:100]:
            player.queue.append(track)
        try:
            await self._play_track(ctx.guild.id, first)
        except Exception as e:
            log.warning("Could not start playback in guild %s: %s", ctx.guild.id, e)
            await ctx.send(embed=self._make_embed(
                "❌ Playback Failed", 0xE74C3C,
                "The music node could not start that track. Try another one.",
            ))
            return
        await self._update_presence(first, ctx.guild)
        await ctx.send(embed=self._build_now_playing_embed(first, player))

    # ── pause ─────────────────────────────────────────────────────────────────
    @commands.command(name="pause")
    async def pause(self, ctx: commands.Context) -> None:
        """Pause the current track. Usage: alpha pause"""
        voice_client = ctx.voice_client
        if isinstance(voice_client, wavelink.Player) and voice_client.playing and not voice_client.paused:
            await voice_client.pause(True)
            await ctx.send(embed=self._make_embed(
                "Paused", 0x95A5A6, f"{EMOJI_MUSIC_PAUSE} Playback paused."
            ))
        else:
            await ctx.send(embed=self._make_embed(
                "❌ Nothing Playing", 0xE74C3C, "Nothing is currently playing"
            ))

    # ── resume ────────────────────────────────────────────────────────────────
    @commands.command(name="resume", aliases=["unpause"])
    async def resume(self, ctx: commands.Context) -> None:
        """Resume paused playback. Usage: alpha resume"""
        voice_client = ctx.voice_client
        if isinstance(voice_client, wavelink.Player) and voice_client.paused:
            await voice_client.pause(False)
            await ctx.send(embed=self._make_embed(
                "Resumed", 0x2ECC71, f"{EMOJI_MUSIC_PLAY} Playback resumed."
            ))
        else:
            await ctx.send(embed=self._make_embed(
                "❌ Not Paused", 0xE74C3C, "Playback is not paused"
            ))

    # ── stop ──────────────────────────────────────────────────────────────────
    @commands.command(name="stop")
    async def stop(self, ctx: commands.Context) -> None:
        """Stop playback and clear the queue. Usage: alpha stop"""
        if not ctx.voice_client:
            await ctx.send(embed=self._make_embed(
                "❌ Not Connected", 0xE74C3C, "Bot is not in a voice channel"
            ))
            return
        player = self._get_player(ctx.guild.id)
        if player.game_active:
            await ctx.send(embed=self._make_embed(
                "❌ Game In Progress", 0xE74C3C,
                "A song-guessing game is running in this voice channel. "
                "Wait for it to finish before stopping playback.",
            ))
            return
        player.queue.clear()
        player.current = None
        player._advance_on_stop = False
        self._reset_player_settings(player)
        voice_client = ctx.voice_client
        if isinstance(voice_client, wavelink.Player):
            try:
                await voice_client.set_filters(wavelink.Filters())
                await voice_client.stop()
            except Exception:
                pass
        await self._update_presence(None, ctx.guild)
        await ctx.send(embed=self._make_embed(
            "Stopped", 0xE74C3C, f"{EMOJI_MUSIC_STOP} Playback stopped and queue cleared."
        ))

    # ── skip ──────────────────────────────────────────────────────────────────
    @commands.command(name="skip", aliases=["s", "next"])
    async def skip(self, ctx: commands.Context) -> None:
        """Vote to skip the current track (auto-votes). Skip triggers at 50% votes. Usage: alpha skip"""
        voice_client = ctx.voice_client
        if not isinstance(voice_client, wavelink.Player) or not voice_client.playing:
            await ctx.send(embed=self._make_embed(
                "❌ Nothing Playing", 0xE74C3C, "Nothing is currently playing"
            ))
            return

        if not ctx.author.voice or ctx.author.voice.channel != voice_client.channel:
            await ctx.send(embed=self._make_embed(
                "❌ Not in VC", 0xE74C3C, "You must be in the same voice channel"
            ))
            return

        player = self._get_player(ctx.guild.id)
        if not player.current:
            await ctx.send(embed=self._make_embed(
                "❌ Nothing Playing", 0xE74C3C, "Nothing is currently playing"
            ))
            return

        if ctx.author.id == player.current.requester.id:
            skipped = player.current.title
            await self._skip_current(ctx.guild.id)
            await ctx.send(embed=self._make_embed(
                "Skipped", 0xF39C12, f"Requester skipped: **{skipped}**"
            ))
            return

        if ctx.author.id in player.skip_votes:
            player.skip_votes.discard(ctx.author.id)
            total_members = len([m for m in voice_client.channel.members if not m.bot])
            needed = max(1, math.ceil(total_members / 2))
            await ctx.send(embed=self._make_embed(
                "Vote Removed", 0x95A5A6,
                f"Vote removed. **{len(player.skip_votes)}/{needed}** votes needed.",
            ))
            return

        player.skip_votes.add(ctx.author.id)
        total_members = len([m for m in voice_client.channel.members if not m.bot])
        needed = max(1, math.ceil(total_members / 2))
        current_votes = len(player.skip_votes)

        if current_votes >= needed:
            track_name = player.current.title
            await self._skip_current(ctx.guild.id)
            player.skip_votes.clear()
            await ctx.send(embed=self._make_embed(
                "Vote Skip!", 0x2ECC71,
                f"Skip passed with **{current_votes}/{total_members}** votes!\nSkipped: **{track_name}**",
            ))
        else:
            await ctx.send(embed=self._make_embed(
                "Vote Added", 0x3498DB,
                f"**{ctx.author}** voted to skip.\n**{current_votes}/{needed}** votes needed.",
            ))

    # ── queue ─────────────────────────────────────────────────────────────────
    @commands.command(name="queue", aliases=["q"])
    async def queue(self, ctx: commands.Context) -> None:
        """View the current music queue. Usage: alpha queue"""
        player = self._get_player(ctx.guild.id)
        embed = queue_embed(title="Music Queue")
        if player.current:
            embed.add_field(
                name="🎵 Now Playing",
                value=f"[{player.current.title}]({player.current.url}) — [{player.current.fmt_duration()}] • {player.current.requester.mention}",
                inline=False,
            )
        if player.queue:
            lines = []
            for i, t in enumerate(list(player.queue)[:20]):
                lines.append(f"`{i + 1}.` [{t.title}]({t.url}) [{t.fmt_duration()}] • {t.requester.mention}")
            if len(player.queue) > 20:
                lines.append(f"… and **{len(player.queue) - 20}** more tracks")
            embed.add_field(name=f"Up Next ({len(player.queue)} tracks)", value="\n".join(lines), inline=False)
        else:
            embed.add_field(name="Up Next", value="Empty", inline=False)
        embed.add_field(name="Loop / Repeat", value=self._loop_state(player), inline=True)
        embed.add_field(name="Volume", value=f"{int(player.volume * 100)}%", inline=True)
        effects = describe_filters(player)
        if effects != "none":
            embed.add_field(name="Effects", value=effects, inline=True)
        if getattr(player, "party_mode", False):
            embed.add_field(name="Party Mode", value="🎉 Active", inline=True)
        if getattr(player, "dj_mode", False):
            embed.add_field(name="DJ Mode", value="✅ Enabled", inline=True)
        embed.set_footer(text=f"Total in queue: {len(player.queue)} • Use alpha similar for suggestions")
        await ctx.send(embed=embed)

    # ── nowplaying ────────────────────────────────────────────────────────────
    @commands.command(name="nowplaying", aliases=["np", "current"])
    async def nowplaying(self, ctx: commands.Context) -> None:
        """Show what's currently playing. Usage: alpha nowplaying"""
        player = self._get_player(ctx.guild.id)
        if not player.current:
            await ctx.send(embed=self._make_embed(
                "❌ Nothing Playing", 0xE74C3C, "Nothing is currently playing"
            ))
            return
        await ctx.send(embed=self._build_now_playing_embed(player.current, player))

    # ── volume ────────────────────────────────────────────────────────────────
    @commands.command(name="volume", aliases=["vol"])
    async def volume(self, ctx: commands.Context, level: int) -> None:
        """Adjust the music volume. Usage: alpha volume <0-200>"""
        if not 0 <= level <= 200:
            await ctx.send(embed=self._make_embed(
                "❌ Invalid Volume", 0xE74C3C, "Value must be between 0 and 200"
            ))
            return
        player = self._get_player(ctx.guild.id)
        player.volume = level / 100
        voice_client = ctx.voice_client
        if isinstance(voice_client, wavelink.Player):
            try:
                await voice_client.set_volume(level)
            except Exception as exc:
                log.debug("Volume update failed in guild %s: %s", ctx.guild.id, exc)
        await ctx.send(embed=self._make_embed(
            "Volume Changed", 0x2ECC71, f"{EMOJI_MUSIC_VOL} Volume set to **{level}%**"
        ))

    # ── shuffle ───────────────────────────────────────────────────────────────
    @commands.command(name="shuffle")
    async def shuffle(self, ctx: commands.Context) -> None:
        """Shuffle the music queue. Usage: alpha shuffle"""
        player = self._get_player(ctx.guild.id)
        if len(player.queue) < 2:
            await ctx.send(embed=self._make_embed(
                "❌ Not Enough Tracks", 0xE74C3C,
                "Not enough tracks in queue to shuffle",
            ))
            return
        q = list(player.queue)
        random.shuffle(q)
        player.queue = deque(q)
        await ctx.send(embed=self._make_embed(
            "Queue Shuffled", 0x9B59B6,
            f"{EMOJI_MUSIC_SHUFFLE} Queue shuffled ({len(player.queue)} tracks)",
        ))

    # ── loop ──────────────────────────────────────────────────────────────────
    @staticmethod
    def _requeue_finished(player: GuildPlayer) -> str | None:
        """Where the finished track is re-enqueued: 'front' (single-track loop),
        'back' (whole-queue loop), or None."""
        if player.loop and player.current:
            return "front"
        if player.queue_loop and player.current:
            return "back"
        return None

    @staticmethod
    def _loop_state(player: GuildPlayer) -> str:
        if player.queue_loop:
            return "🔁 ON — Queue (repeat all)"
        if player.loop:
            return "🔂 ON — Single (repeat track)"
        return "➡️ OFF"

    @commands.command(name="loop", aliases=["repeat"])
    async def loop(self, ctx: commands.Context, mode: str = None) -> None:
        """Loop the current track or the whole queue. Usage: alpha loop [queue|single|off]"""
        player = self._get_player(ctx.guild.id)
        choice = (mode or "").strip().lower()

        if choice in ("queue", "all", "playlist"):
            player.queue_loop = not player.queue_loop
            if player.queue_loop:
                player.loop = False
            state = "enabled (**whole queue**)" if player.queue_loop else "disabled"
        elif choice in ("", "single", "track", "one"):
            player.loop = not player.loop
            if player.loop:
                player.queue_loop = False
            state = "enabled (**single track**)" if player.loop else "disabled"
        elif choice in ("off", "none", "stop"):
            player.loop = False
            player.queue_loop = False
            state = "disabled"
        else:
            await ctx.send(embed=self._make_embed(
                "❌ Invalid Mode", 0xE74C3C, "Use: `alpha loop [queue|single|off]`"
            ))
            return

        await ctx.send(embed=self._make_embed(
            "Loop Toggled", 0xF39C12, f"{EMOJI_MUSIC_LOOP} Loop {state}"
        ))

    # ── remove ────────────────────────────────────────────────────────────────
    @commands.command(name="remove")
    async def remove(self, ctx: commands.Context, index: int) -> None:
        """Remove a track from queue by position. Usage: alpha remove <position>"""
        player = self._get_player(ctx.guild.id)
        if not player.queue or not 1 <= index <= len(player.queue):
            await ctx.send(embed=self._make_embed(
                "❌ Invalid Index", 0xE74C3C, "Invalid queue index"
            ))
            return
        q = list(player.queue)
        removed = q.pop(index - 1)
        player.queue = deque(q)
        await ctx.send(embed=self._make_embed(
            "Track Removed", 0xE67E22, f"Removed: **{removed.title}**"
        ))

    # ── radio ─────────────────────────────────────────────────────────────────
    @commands.command(name="radio")
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def radio(self, ctx: commands.Context, *, genre: str) -> None:
        """Play a radio stream of a music genre. Usage: alpha radio <genre>"""
        if not ctx.author.voice:
            await ctx.send(embed=self._make_embed(
                "❌ Not Connected", 0xE74C3C, "You must be in a voice channel"
            ))
            return
        try:
            voice_client = await self._ensure_voice(ctx)
        except Exception as e:
            await ctx.send(embed=self._make_embed(
                "❌ Connection Failed", 0xE74C3C, f"Could not join voice: {e}"
            ))
            return

        loading_msg = await ctx.send(embed=self._make_embed(
            "📻 Loading Radio", 0x3498DB, f"Searching for **{genre}** genre mixes..."
        ))

        player = self._get_player(ctx.guild.id)
        self._remember_text_channel(player, ctx)

        search_queries = [
            f"ytsearch15:{genre} mix",
            f"ytsearch15:{genre} playlist popular",
            f"ytsearch10:{genre} music compilation",
        ]
        playables: list[wavelink.Playable] = []
        for query in search_queries:
            if len(playables) >= 10:
                break
            try:
                result = await self.nodes.search(query, source=None)
            except Exception:
                continue
            if isinstance(result, wavelink.Playlist):
                playables.extend(result.tracks)
            else:
                playables.extend(result or [])

        unique: list[Track] = []
        seen: set[str] = set()
        for playable in playables:
            key = getattr(playable, "encoded", None) or getattr(playable, "identifier", None) or getattr(playable, "uri", None)
            if key and key not in seen:
                seen.add(key)
                unique.append(Track(playable, ctx.author))

        if not unique:
            await loading_msg.edit(embed=self._make_embed(
                "❌ No Results", 0xE74C3C, f"Could not find any **{genre}** genre tracks"
            ))
            return

        random.shuffle(unique)
        added_count = len(unique)
        for track in unique:
            player.queue.append(track)

        if voice_client.playing or voice_client.paused:
            await loading_msg.edit(embed=self._make_embed(
                "📻 Radio Queued", 0x9B59B6,
                f"Added **{added_count}** tracks from **{genre}** genre to queue",
            ))
            return

        if player.queue:
            first = player.queue.popleft()
            try:
                await self._play_track(ctx.guild.id, first)
            except Exception:
                await loading_msg.edit(embed=self._make_embed(
                    "❌ Playback Failed", 0xE74C3C,
                    f"Could not start **{first.title}** — trying the next track.",
                ))
                await self._play_next_impl(ctx.guild.id)
                return
            await self._update_presence(first, ctx.guild)

        embed = discord.Embed(color=0x9B59B6)
        embed.set_author(name="📻 Radio Started", icon_url=None)
        embed.description = f"Playing **{len(player.queue) + (1 if player.current else 0)}** tracks from **{genre}** genre"
        embed.add_field(name="Genre", value=genre.title(), inline=True)
        embed.add_field(name="Tracks", value=f"**{added_count}** in queue", inline=True)
        if player.current:
            embed.add_field(
                name="Now Playing",
                value=f"[{player.current.title}]({player.current.url})" if player.current.url else player.current.title,
                inline=False,
            )
        await loading_msg.edit(embed=embed)

    # ── clearqueue ────────────────────────────────────────────────────────────
    @commands.command(name="clearqueue", aliases=["cq"])
    async def clearqueue(self, ctx: commands.Context) -> None:
        """Clear all tracks from the queue. Usage: alpha clearqueue"""
        player = self._get_player(ctx.guild.id)
        count = len(player.queue)
        player.queue.clear()
        await ctx.send(embed=self._make_embed(
            "Queue Cleared", 0x95A5A6, f"Cleared **{count}** track(s) from queue"
        ))

    # ── seek ──────────────────────────────────────────────────────────────────
    @commands.command(name="seek")
    async def seek(self, ctx: commands.Context, position: str) -> None:
        """Seek to a position in the track. Usage: alpha seek <MM:SS>"""
        voice_client = ctx.voice_client
        if not isinstance(voice_client, wavelink.Player) or not voice_client.playing:
            await ctx.send(embed=self._make_embed("❌ Nothing Playing", 0xE74C3C, "Nothing is currently playing"))
            return

        player = self._get_player(ctx.guild.id)
        if not player.current:
            await ctx.send(embed=self._make_embed("❌ No Track", 0xE74C3C, "No track loaded"))
            return

        try:
            parts = position.split(":")
            if len(parts) == 2:
                secs = int(parts[0]) * 60 + int(parts[1])
            else:
                secs = int(position)
        except ValueError:
            await ctx.send(embed=self._make_embed("❌ Invalid Format", 0xE74C3C, "Use format: MM:SS or seconds"))
            return

        if secs < 0 or secs > player.current.duration:
            await ctx.send(embed=self._make_embed(
                "❌ Out of Range", 0xE74C3C, f"Track duration is {player.current.fmt_duration()}"
            ))
            return

        try:
            await voice_client.seek(secs * 1000)
        except Exception as e:
            await ctx.send(embed=self._make_embed("❌ Seek Failed", 0xE74C3C, str(e)))
            return
        player._start_time = asyncio.get_running_loop().time() - secs
        await ctx.send(embed=self._make_embed("⏩ Seek", 0x2ECC71, f"Jumped to **{position}**"))

    # ── replay ────────────────────────────────────────────────────────────────
    @commands.command(name="replay")
    async def replay(self, ctx: commands.Context) -> None:
        """Replay the current track from the beginning. Usage: alpha replay"""
        voice_client = ctx.voice_client
        if not isinstance(voice_client, wavelink.Player) or not voice_client.playing:
            await ctx.send(embed=self._make_embed("❌ Nothing Playing", 0xE74C3C, "Nothing is currently playing"))
            return

        player = self._get_player(ctx.guild.id)
        if not player.current:
            await ctx.send(embed=self._make_embed("❌ No Track", 0xE74C3C, "No track to replay"))
            return

        title = player.current.title
        player.queue.appendleft(player.current)
        player.current = None
        await self._skip_current(ctx.guild.id)
        await ctx.send(embed=self._make_embed("🔄 Replaying", 0x9B59B6, f"Replaying: **{title}**"))

    # ── autoplay ─────────────────────────────────────────────────────────────
    @commands.command(name="autoplay")
    async def autoplay(self, ctx: commands.Context) -> None:
        """Toggle autoplay for similar tracks. Usage: alpha autoplay"""
        player = self._get_player(ctx.guild.id)
        player.autoplay = not player.autoplay
        state = "**enabled**" if player.autoplay else "**disabled**"
        await ctx.send(embed=self._make_embed("🔄 Autoplay", 0xF39C12, f"Autoplay {state}"))

    # ── effects ───────────────────────────────────────────────────────────────
    @commands.command(name="bassboost")
    async def bassboost(self, ctx: commands.Context) -> None:
        """Toggle bass boost effect. Usage: alpha bassboost"""
        player = self._get_player(ctx.guild.id)
        player.bassboost = not player.bassboost
        await self._apply_filters(player)
        state = "**enabled**" if player.bassboost else "**disabled**"
        await ctx.send(embed=self._make_embed("🔊 Bass Boost", 0xE67E22, f"Bass boost {state}"))

    @commands.command(name="nightcore")
    async def nightcore(self, ctx: commands.Context) -> None:
        """Toggle nightcore effect (faster + higher pitch). Usage: alpha nightcore"""
        player = self._get_player(ctx.guild.id)
        player.nightcore = not player.nightcore
        await self._apply_filters(player)
        state = "**enabled**" if player.nightcore else "**disabled**"
        await ctx.send(embed=self._make_embed("🌙 Nightcore", 0x9B59B6, f"Nightcore effect {state}"))

    @commands.command(name="8d", aliases=["eightd"])
    async def eight_d(self, ctx: commands.Context) -> None:
        """Toggle 8D audio effect. Usage: alpha 8d"""
        voice_client = ctx.voice_client
        if not isinstance(voice_client, wavelink.Player) or not voice_client.playing:
            await ctx.send(embed=self._make_embed("❌ Nothing Playing", 0xE74C3C, "Nothing is currently playing"))
            return
        player = self._get_player(ctx.guild.id)
        player.eight_d = not player.eight_d
        await self._apply_filters(player)
        state = "**enabled**" if player.eight_d else "**disabled**"
        await ctx.send(embed=self._make_embed(
            "🎧 8D Audio", 0x3498DB, f"8D effect {state}\n*Rotating audio with reverb*"
        ))

    @commands.command(name="equalizer", aliases=["eq"])
    async def equalizer(self, ctx: commands.Context, preset: str = "flat") -> None:
        """Set equalizer preset. Usage: alpha equalizer <preset>"""
        player = self._get_player(ctx.guild.id)
        preset = preset.lower()
        if preset not in VALID_PRESETS:
            await ctx.send(embed=self._make_embed(
                "❌ Invalid Preset", 0xE74C3C, f"Valid presets: {', '.join(VALID_PRESETS)}"
            ))
            return
        player.equalizer = preset
        await self._apply_filters(player)
        await ctx.send(embed=self._make_embed("🎚️ Equalizer", 0x2ECC71, f"Equalizer set to **{preset}**"))

    # ── lyrics ───────────────────────────────────────────────────────────────
    @commands.command(name="lyrics")
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def lyrics(self, ctx: commands.Context, *, query: str = None) -> None:
        """Search for song lyrics. Usage: alpha lyrics <song name>"""
        if not query:
            player = self._get_player(ctx.guild.id)
            if player.current:
                query = player.current.title
            else:
                await ctx.send(embed=self._make_embed(
                    "❌ No Query", 0xE74C3C, "Provide a song name or play a song first"
                ))
                return

        msg = await ctx.send(embed=self._make_embed(
            "🔍 Searching...", 0x9B59B6, f"Searching lyrics for: **{query}**"
        ))

        try:
            playable = await self.nodes.search_first(f"{query} lyrics official")
            title = playable.title if playable else query
            url = getattr(playable, "uri", None) or f"https://www.youtube.com/results?search_query={quote_plus(query + ' lyrics')}"
            embed = discord.Embed(color=0x9B59B6)
            embed.set_author(name="🎤 Lyrics Search", icon_url=None)
            embed.description = f"**{title}**"
            embed.add_field(name="Search", value=f"[YouTube Search]({url})", inline=True)
            embed.add_field(name="Tip", value="Search on Genius or lyrics.com", inline=True)
            await msg.edit(embed=embed)
        except Exception as e:
            await msg.edit(embed=self._make_embed("❌ Error", 0xE74C3C, f"Search failed: {e}"))

    # ── favorite / favorites ──────────────────────────────────────────────────
    def _add_favorite(self, user_id: int, entry: str) -> bool:
        """Append *entry* to a user's favorites file; False if already saved."""
        path = f"data/favorites_{user_id}.txt"
        os.makedirs("data", exist_ok=True)
        existing = set()
        if os.path.exists(path):
            with open(path, "r") as f:
                existing = {line.strip().lower() for line in f if line.strip()}
        if entry.lower() in existing:
            return False
        with open(path, "a") as f:
            f.write(f"{entry}\n")
        return True

    @commands.command(name="favorite", aliases=["fav", "star"])
    async def favorite(self, ctx: commands.Context) -> None:
        """Favorite the currently playing track. Usage: alpha favorite"""
        player = self._get_player(ctx.guild.id)
        if not player.current:
            await ctx.send(embed=self._make_embed(
                "❌ Nothing Playing", 0xE74C3C, "Nothing is currently playing"
            ))
            return
        added = self._add_favorite(ctx.author.id, player.current.title)
        if added:
            await ctx.send(embed=self._make_embed(
                "⭐ Favorited", 0xF1C40F, f"Added to favorites: **{player.current.title}**"
            ))
        else:
            await ctx.send(embed=self._make_embed(
                "⭐ Already Saved", 0xF1C40F,
                f"**{player.current.title}** is already in your favorites",
            ))

    @commands.command(name="favorites", aliases=["favs"])
    async def favorites(self, ctx: commands.Context, action: str = None, *, query: str = None) -> None:
        """Manage your favorites. Usage: alpha favorites [add|remove|list] [song name]."""
        player = self._get_player(ctx.guild.id)
        user_id = str(ctx.author.id)
        favorites_file = f"data/favorites_{user_id}.txt"
        os.makedirs("data", exist_ok=True)
        if not os.path.exists(favorites_file):
            with open(favorites_file, "w"):
                pass

        with open(favorites_file, "r") as f:
            user_favs = [line.strip() for line in f if line.strip()]

        if not action:
            if not user_favs:
                await ctx.send(embed=self._make_embed(
                    "⭐ Favorites", 0xF1C40F,
                    "Your favorites list is empty. Use `alpha favorites add <song>` to add.",
                ))
                return
            embed = discord.Embed(color=0xF1C40F)
            embed.set_author(name="⭐ Your Favorites", icon_url=None)
            lines = "\n".join(f"`{i+1}.` {f}" for i, f in enumerate(user_favs[:15]))
            if len(user_favs) > 15:
                lines += f"\n… and {len(user_favs) - 15} more"
            embed.description = lines
            await ctx.send(embed=embed)
            return

        action = action.lower()
        if action == "add":
            if not query:
                await ctx.send(embed=self._make_embed("❌ No Song", 0xE74C3C, "Provide a song name to add"))
                return
            if player.current and query.lower() in player.current.title.lower():
                fav_entry = player.current.title
            else:
                fav_entry = query
            added = self._add_favorite(ctx.author.id, fav_entry)
            if added:
                await ctx.send(embed=self._make_embed("⭐ Added", 0xF1C40F, f"Added to favorites: **{fav_entry}**"))
            else:
                await ctx.send(embed=self._make_embed("⭐ Already Saved", 0xF1C40F, f"**{fav_entry}** is already in your favorites"))

        elif action == "remove":
            if not query:
                await ctx.send(embed=self._make_embed("❌ No Song", 0xE74C3C, "Provide a song name to remove"))
                return
            removed = False
            with open(favorites_file, "r") as f:
                lines = f.readlines()
            with open(favorites_file, "w") as f:
                for line in lines:
                    if query.lower() not in line.strip().lower():
                        f.write(line)
                    else:
                        removed = True
            if removed:
                await ctx.send(embed=self._make_embed("⭐ Removed", 0xE74C3C, f"Removed from favorites: **{query}**"))
            else:
                await ctx.send(embed=self._make_embed("❌ Not Found", 0xE74C3C, f"Could not find: **{query}**"))

        elif action == "list":
            if not user_favs:
                await ctx.send(embed=self._make_embed("⭐ Favorites", 0xF1C40F, "Your favorites list is empty"))
                return
            embed = discord.Embed(color=0xF1C40F)
            embed.set_author(name="⭐ Your Favorites", icon_url=None)
            embed.description = "\n".join(f"`{i+1}.` {f}" for i, f in enumerate(user_favs[:20]))
            await ctx.send(embed=embed)

        else:
            await ctx.send(embed=self._make_embed(
                "❌ Invalid Action", 0xE74C3C,
                "Use: `alpha favorites add <song>`, `alpha favorites remove <song>`, or `alpha favorites`",
            ))

    # ── playlist ────────────────────────────────────────────────────────────
    @commands.command(name="playlist")
    async def playlist(self, ctx: commands.Context, action: str = None, name: str = None, *, query: str = None) -> None:
        """Manage playlists. Usage: alpha playlist [create|delete|add|remove|save|play|list] [name] [song]."""
        playlists_dir = "data/playlists"
        os.makedirs(playlists_dir, exist_ok=True)

        if not action:
            playlists = [f.replace(".txt", "") for f in os.listdir(playlists_dir) if f.endswith(".txt")]
            if not playlists:
                await ctx.send(embed=self._make_embed(
                    "🎶 Playlists", 0x9B59B6,
                    "No playlists yet. Use `alpha playlist create <name>` to create one.",
                ))
                return
            embed = discord.Embed(color=0x9B59B6)
            embed.set_author(name="🎶 Server Playlists", icon_url=None)
            embed.description = "\n".join(f"`{p}`" for p in playlists)
            await ctx.send(embed=embed)
            return

        action = action.lower()

        if action == "create":
            if not name:
                await ctx.send(embed=self._make_embed("❌ No Name", 0xE74C3C, "Provide a playlist name"))
                return
            safe_name = "".join(c for c in name if c.isalnum() or c in " _-").strip()[:50]
            playlist_file = os.path.join(playlists_dir, f"{safe_name}.txt")
            if os.path.exists(playlist_file):
                await ctx.send(embed=self._make_embed("❌ Exists", 0xE74C3C, f"Playlist **{safe_name}** already exists"))
                return
            with open(playlist_file, "w") as f:
                f.write(f"# {safe_name}\n")
            await ctx.send(embed=self._make_embed("✅ Created", 0x2ECC71, f"Created playlist: **{safe_name}**"))

        elif action == "delete":
            if not name:
                await ctx.send(embed=self._make_embed("❌ No Name", 0xE74C3C, "Provide a playlist name"))
                return
            safe_name = "".join(c for c in name if c.isalnum() or c in " _-").strip()[:50]
            playlist_file = os.path.join(playlists_dir, f"{safe_name}.txt")
            if not os.path.exists(playlist_file):
                await ctx.send(embed=self._make_embed("❌ Not Found", 0xE74C3C, f"Playlist **{safe_name}** not found"))
                return
            os.remove(playlist_file)
            await ctx.send(embed=self._make_embed("🗑️ Deleted", 0xE74C3C, f"Deleted playlist: **{safe_name}**"))

        elif action == "add":
            if not name or not query:
                await ctx.send(embed=self._make_embed("❌ Missing Args", 0xE74C3C, "Usage: `alpha playlist add <name> <song>`"))
                return
            safe_name = "".join(c for c in name if c.isalnum() or c in " _-").strip()[:50]
            playlist_file = os.path.join(playlists_dir, f"{safe_name}.txt")
            if not os.path.exists(playlist_file):
                await ctx.send(embed=self._make_embed("❌ Not Found", 0xE74C3C, f"Playlist **{safe_name}** not found"))
                return
            with open(playlist_file, "a") as f:
                f.write(f"{query}\n")
            await ctx.send(embed=self._make_embed("➕ Added", 0x2ECC71, f"Added to **{safe_name}**: {query}"))

        elif action == "remove":
            if not name or not query:
                await ctx.send(embed=self._make_embed("❌ Missing Args", 0xE74C3C, "Usage: `alpha playlist remove <name> <song>`"))
                return
            safe_name = "".join(c for c in name if c.isalnum() or c in " _-").strip()[:50]
            playlist_file = os.path.join(playlists_dir, f"{safe_name}.txt")
            if not os.path.exists(playlist_file):
                await ctx.send(embed=self._make_embed("❌ Not Found", 0xE74C3C, f"Playlist **{safe_name}** not found"))
                return
            with open(playlist_file, "r") as f:
                lines = f.readlines()
            with open(playlist_file, "w") as f:
                for line in lines:
                    if query.lower() not in line.strip().lower():
                        f.write(line)
            await ctx.send(embed=self._make_embed("➖ Removed", 0xF39C12, f"Removed from **{safe_name}**: {query}"))

        elif action in ("save", "savequeue"):
            if not name:
                await ctx.send(embed=self._make_embed("❌ No Name", 0xE74C3C, "Usage: `alpha playlist save <name>`"))
                return
            safe_name = "".join(c for c in name if c.isalnum() or c in " _-").strip()[:50]
            playlist_file = os.path.join(playlists_dir, f"{safe_name}.txt")
            if not os.path.exists(playlist_file):
                await ctx.send(embed=self._make_embed("❌ Not Found", 0xE74C3C, f"Playlist **{safe_name}** not found"))
                return
            player = self._get_player(ctx.guild.id)
            tracks: list[Track] = []
            if player.current:
                tracks.append(player.current)
            tracks.extend(player.queue)
            if not tracks:
                await ctx.send(embed=self._make_embed("❌ Empty Queue", 0xE74C3C, "Nothing in the queue to save"))
                return
            with open(playlist_file, "a") as f:
                for t in tracks:
                    f.write(f"{t.title}\n")
            await ctx.send(embed=self._make_embed(
                "💾 Queue Saved", 0x2ECC71,
                f"Saved **{len(tracks)}** track(s) from the queue to **{safe_name}**",
            ))

        elif action == "play":
            if not name:
                await ctx.send(embed=self._make_embed("❌ No Name", 0xE74C3C, "Provide a playlist name"))
                return
            if not ctx.author.voice:
                await ctx.send(embed=self._make_embed("❌ Not in VC", 0xE74C3C, "You must be in a voice channel"))
                return
            safe_name = "".join(c for c in name if c.isalnum() or c in " _-").strip()[:50]
            playlist_file = os.path.join(playlists_dir, f"{safe_name}.txt")
            if not os.path.exists(playlist_file):
                await ctx.send(embed=self._make_embed("❌ Not Found", 0xE74C3C, f"Playlist **{safe_name}** not found"))
                return

            with open(playlist_file, "r") as f:
                songs = [line.strip() for line in f if line.strip() and not line.startswith("#")]
            if not songs:
                await ctx.send(embed=self._make_embed("❌ Empty", 0xE74C3C, f"Playlist **{safe_name}** is empty"))
                return

            try:
                voice_client = await self._ensure_voice(ctx)
            except Exception as e:
                await ctx.send(embed=self._make_embed("❌ Connection Failed", 0xE74C3C, f"Could not join voice: {e}"))
                return

            player = self._get_player(ctx.guild.id)
            self._remember_text_channel(player, ctx)

            added = 0
            for song in songs[:20]:
                tracks = await self._fetch_tracks(song, ctx.author)
                if tracks:
                    player.queue.append(tracks[0])
                    added += 1

            await ctx.send(embed=self._make_embed(
                "🎶 Playlist Queued", 0x9B59B6,
                f"Added **{added}** songs from **{safe_name}** to queue",
            ))

            if not (voice_client.playing or voice_client.paused):
                await self._play_next_impl(ctx.guild.id)

        elif action == "list":
            if not name:
                playlists = [f.replace(".txt", "") for f in os.listdir(playlists_dir) if f.endswith(".txt")]
                embed = discord.Embed(color=0x9B59B6)
                embed.set_author(name="🎶 All Playlists", icon_url=None)
                embed.description = "\n".join(f"`{p}`" for p in playlists) if playlists else "No playlists yet"
                await ctx.send(embed=embed)
                return
            safe_name = "".join(c for c in name if c.isalnum() or c in " _-").strip()[:50]
            playlist_file = os.path.join(playlists_dir, f"{safe_name}.txt")
            if not os.path.exists(playlist_file):
                await ctx.send(embed=self._make_embed("❌ Not Found", 0xE74C3C, f"Playlist **{safe_name}** not found"))
                return
            with open(playlist_file, "r") as f:
                songs = [line.strip() for line in f if line.strip() and not line.startswith("#")]
            embed = discord.Embed(color=0x9B59B6)
            embed.set_author(name=f"🎶 {safe_name}", icon_url=None)
            embed.description = "\n".join(f"`{i+1}.` {s}" for i, s in enumerate(songs[:20]))
            if len(songs) > 20:
                embed.set_footer(text=f"… and {len(songs) - 20} more")
            await ctx.send(embed=embed)

        else:
            await ctx.send(embed=self._make_embed(
                "❌ Invalid Action", 0xE74C3C, "Use: create, delete, add, remove, save, play, list"
            ))

    # ── refresh / node status ────────────────────────────────────────────────
    @commands.command(name="refresh")
    @perms_or_developer(administrator=True)
    async def refresh(self, ctx: commands.Context) -> None:
        """Reconnect and report Lavalink nodes. Usage: alpha refresh"""
        reconnected = await self.nodes.reconnect_disconnected()
        connected = self.nodes.connected_nodes
        if connected:
            names = ", ".join(f"`{node.identifier}`" for node in connected)
            embed = discord.Embed(color=0x2ECC71)
            embed.set_author(name="✅ Nodes Refreshed")
            embed.description = (
                f"**{len(connected)}/{len(self.nodes.nodes)}** Lavalink node(s) online.\n{names}"
            )
            if reconnected:
                embed.add_field(
                    name="Reconnected",
                    value=", ".join(f"`{node.identifier}`" for node in reconnected),
                    inline=False,
                )
            await ctx.send(embed=embed)
        else:
            embed = discord.Embed(color=0xE74C3C)
            embed.set_author(name="❌ No Nodes Online")
            embed.description = (
                "Every Lavalink node is currently unavailable. "
                "Check the bot logs or set `LAVALINK_NODES` in `.env`."
            )
            await ctx.send(embed=embed)

    @refresh.error
    async def refresh_error(self, ctx: commands.Context, error) -> None:
        if isinstance(error, commands.MissingPermissions):
            await ctx.send(embed=self._make_embed(
                "❌ Permission Denied", 0xE74C3C, "You need **Administrator** permission."
            ))

    # ── slowed ───────────────────────────────────────────────────────────────
    @commands.command(name="slowed")
    async def slowed(self, ctx: commands.Context) -> None:
        """Toggle slowed + reverb effect. Usage: alpha slowed"""
        voice_client = ctx.voice_client
        if not isinstance(voice_client, wavelink.Player) or not voice_client.playing:
            await ctx.send(embed=self._make_embed("❌ Nothing Playing", 0xE74C3C, "Nothing is currently playing"))
            return

        player = self._get_player(ctx.guild.id)
        player.slowed = not player.slowed
        await self._apply_filters(player)
        state = "**enabled**" if player.slowed else "**disabled**"
        await ctx.send(embed=self._make_embed("🐌 Slowed + Reverb", 0x9B59B6, f"Slowed effect {state}"))

    @app_commands.command(name="slowed", description="Toggle slowed + reverb effect")
    async def slash_slowed(self, interaction: discord.Interaction) -> None:
        """Slash command for slowed effect."""
        voice_client = interaction.guild.voice_client if interaction.guild else None
        if not isinstance(voice_client, wavelink.Player):
            await interaction.response.send_message(
                embed=self._make_embed("❌ Not in VC", 0xE74C3C, "Bot is not in a voice channel"),
                ephemeral=True,
            )
            return
        if not voice_client.playing:
            await interaction.response.send_message(
                embed=self._make_embed("❌ Nothing Playing", 0xE74C3C, "Nothing is currently playing"),
                ephemeral=True,
            )
            return

        player = self._get_player(interaction.guild_id)
        player.slowed = not player.slowed
        await self._apply_filters(player)
        state = "**enabled**" if player.slowed else "**disabled**"
        await interaction.response.send_message(
            embed=self._make_embed("🐌 Slowed + Reverb", 0x9B59B6, f"Slowed effect {state}")
        )

    # ── similar ──────────────────────────────────────────────────────────────
    @commands.command(name="similar", aliases=["similarsong", "playsimilar", "related"])
    async def similar(self, ctx: commands.Context) -> None:
        """Queue a track similar to the current one. Usage: alpha similar"""
        if not ctx.voice_client:
            await ctx.send(embed=self._make_embed("❌ Not Connected", 0xE74C3C, "I'm not in a voice channel."))
            return
        player = self._get_player(ctx.guild.id)
        base = player.current or player.last_track
        if not base or not base.title:
            await ctx.send(embed=self._make_embed(
                "❌ Nothing to Base On", 0xE74C3C, "Play a song first, then use alpha similar."
            ))
            return
        track = await self._fetch_track(f"{base.title} similar song", ctx.author)
        if not track:
            await ctx.send(embed=self._make_embed(
                "❌ No Suggestions", 0xE74C3C, "Couldn't find a similar track right now."
            ))
            return
        player.queue.append(track)
        embed = music_embed(
            title="🎯 Play Similar",
            description=f"Added similar track to queue:\n[{track.title}]({track.url})",
        )
        embed.add_field(name="Based on", value=base.title[:100], inline=False)
        await ctx.send(embed=embed)

    # ── party mode ────────────────────────────────────────────────────────────
    @commands.command(name="partymode", aliases=["party"])
    async def partymode(self, ctx: commands.Context) -> None:
        """Toggle party mode. Usage: alpha partymode"""
        if not ctx.voice_client:
            await ctx.send(embed=self._make_embed("❌ Not Connected", 0xE74C3C, "I'm not in a voice channel."))
            return
        player = self._get_player(ctx.guild.id)
        player.party_mode = not player.party_mode
        if player.party_mode:
            await ctx.send(embed=music_embed(title="🎉 Party Mode ON", description="Party mode activated!"))
        else:
            await ctx.send(embed=self._make_embed("Party Mode OFF", 0x95A5A6, "Party mode disabled."))

    # ── DJ mode ───────────────────────────────────────────────────────────────
    @commands.command(name="djmode", aliases=["dj"])
    async def djmode(self, ctx: commands.Context) -> None:
        """Toggle DJ mode. Usage: alpha djmode"""
        if not ctx.voice_client:
            await ctx.send(embed=self._make_embed("❌ Not Connected", 0xE74C3C, "I'm not in a voice channel."))
            return
        player = self._get_player(ctx.guild.id)
        player.dj_mode = not player.dj_mode
        if player.dj_mode:
            await ctx.send(embed=music_embed(title="🎧 DJ Mode ON", description="DJ mode enabled."))
        else:
            await ctx.send(embed=self._make_embed("DJ Mode OFF", 0x95A5A6, "DJ mode disabled."))

    # ── history ───────────────────────────────────────────────────────────────
    @commands.command(name="history")
    async def history(self, ctx: commands.Context) -> None:
        """Show recently played tracks. Usage: alpha history"""
        player = self._get_player(ctx.guild.id)
        hist = list(player.queue_history)
        if not hist:
            await ctx.send(embed=self._make_embed("📜 Queue History", 0x95A5A6, "No track history yet."))
            return
        embed = queue_embed(title="Queue History")
        lines = [f"`{i + 1}.` {t.title} [{t.fmt_duration()}]" for i, t in enumerate(hist[:15])]
        embed.description = "\n".join(lines)
        await ctx.send(embed=embed)

    # ── myfavorites ───────────────────────────────────────────────────────────
    @commands.command(name="myfavorites", aliases=["saved"])
    async def myfavorites(self, ctx: commands.Context) -> None:
        """Show your saved favorites. Usage: alpha myfavorites"""
        favorites_file = f"data/favorites_{ctx.author.id}.txt"
        if not os.path.exists(favorites_file):
            await ctx.send(embed=music_embed(
                title="⭐ Your Favorites",
                description="No favorites yet.\nUse alpha favorite while a song plays.",
            ))
            return
        try:
            with open(favorites_file, "r", encoding="utf-8", errors="ignore") as f:
                favs = [line.strip() for line in f if line.strip()]
            if not favs:
                await ctx.send(embed=music_embed(title="⭐ Your Favorites", description="No favorites yet."))
                return
            embed = music_embed(
                title="⭐ Your Favorites",
                description=f"You have **{len(favs)}** favorite track(s)",
            )
            lines = [f"`{i + 1}.` {fav}" for i, fav in enumerate(favs[:15])]
            if len(favs) > 15:
                lines.append(f"… and {len(favs) - 15} more")
            embed.add_field(name="Saved Tracks", value="\n".join(lines), inline=False)
            await ctx.send(embed=embed)
        except Exception as e:
            await ctx.send(embed=self._make_embed("❌ Error", 0xE74C3C, str(e)))


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Music(bot))


async def teardown(bot: commands.Bot) -> None:
    cog = bot.get_cog("music")
    if cog is not None and isinstance(cog, Music):
        await cog.nodes.close()
