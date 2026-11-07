"""Music cog and Lavalink/Wavelink service tests.

Everything here is offline: Lavalink searches are stubbed, and metadata parsing
is exercised against captured payloads rather than live HTTP responses.
"""

from __future__ import annotations

import pathlib
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest
import wavelink

from bot.cogs import music as music_cog
from bot.cogs.music import Music
from bot.services.music import metadata as music_metadata
from bot.services.music.filters import build_filters, describe_filters
from bot.services.music.metadata import (
    parse_apple_url,
    parse_spotify_url,
    search_query_for,
)
from bot.services.music.models import GuildPlayer, Track
from bot.services.music.nodes import (
    DEFAULT_NODES,
    LavalinkNodeConfig,
    NodeManager,
    NoNodesAvailable,
    TrackSearchError,
    load_node_configs,
    parse_node_spec,
)

from helpers import USER_IDS, make_ctx, make_guild, make_member


def _track(title: str, requester):
    return Track({"title": title, "url": ""}, requester)


def _playable(
    title: str = "Song",
    *,
    uri: str = "https://example.com/song",
    identifier: str | None = None,
    length: int = 180_000,
    artwork: str | None = None,
):
    """A stand-in for :class:`wavelink.Playable` (only the fields Track reads)."""
    return SimpleNamespace(
        title=title,
        uri=uri,
        identifier=identifier or uri,
        length=length,
        artwork=artwork,
        encoded=f"encoded-{title}",
    )


def _manager_with_nodes(*specs: tuple[str, int]) -> NodeManager:
    """Build a NodeManager whose nodes are already connected (no network)."""
    manager = NodeManager(MagicMock(), configs=[])
    manager.nodes = [
        SimpleNamespace(
            identifier=name,
            status=wavelink.NodeStatus.CONNECTED,
            players={},
            _total_player_count=load,
        )
        for name, load in specs
    ]
    return manager


def _favorites_file(member_id: int) -> pathlib.Path:
    return pathlib.Path("data") / f"favorites_{member_id}.txt"


# ── favorites / playlists ────────────────────────────────────────────────────
def test_add_favorite_dedups(bot):
    cog = Music(bot)
    user_id = USER_IDS["member"]
    assert cog._add_favorite(user_id, "Never Gonna Give You Up") is True
    assert cog._add_favorite(user_id, "never gonna give you up") is False
    lines = _favorites_file(user_id).read_text().splitlines()
    assert lines.count("Never Gonna Give You Up") == 1


async def test_favorite_current_track(bot):
    cog = Music(bot)
    member = make_member(USER_IDS["member"])
    player = cog._get_player(1001)
    player.current = _track("Fireflies", member)

    ctx = make_ctx(bot, author=member)
    await cog.favorite.callback(cog, ctx)

    embed = ctx.send.await_args.kwargs["embed"]
    assert "Fireflies" in embed.description
    assert "Fireflies" in _favorites_file(USER_IDS["member"]).read_text()


async def test_favorite_duplicate_reports_already(bot):
    cog = Music(bot)
    member = make_member(USER_IDS["member"])
    player = cog._get_player(1001)
    player.current = _track("Fireflies", member)
    cog._add_favorite(USER_IDS["member"], "Fireflies")

    ctx = make_ctx(bot, author=member)
    await cog.favorite.callback(cog, ctx)

    embed = ctx.send.await_args.kwargs["embed"]
    assert "already in your favorites" in embed.description


async def test_favorite_nothing_playing(bot):
    cog = Music(bot)
    ctx = make_ctx(bot)
    await cog.favorite.callback(cog, ctx)
    assert "Nothing is currently playing" in ctx.send.await_args.kwargs["embed"].description


async def test_playlist_save_saves_whole_queue(bot):
    cog = Music(bot)
    requester = make_member(USER_IDS["member"])
    player = cog._get_player(1001)
    player.current = _track("Song One", requester)
    player.queue.append(_track("Song Two", requester))
    player.queue.append(_track("Song Three", requester))

    ctx = make_ctx(bot, author=requester)
    await cog.playlist.callback(cog, ctx, "create", "RoadTrip")
    await cog.playlist.callback(cog, ctx, "save", "RoadTrip")

    embed = ctx.send.await_args.kwargs["embed"]
    assert "Saved **3** track(s) from the queue to **RoadTrip**" in embed.description

    songs = pathlib.Path("data/playlists/RoadTrip.txt").read_text().splitlines()
    assert "Song One" in songs and "Song Two" in songs and "Song Three" in songs


async def test_playlist_save_empty_queue(bot):
    cog = Music(bot)
    ctx = make_ctx(bot)
    await cog.playlist.callback(cog, ctx, "create", "EmptyList")
    await cog.playlist.callback(cog, ctx, "save", "EmptyList")
    assert "Nothing in the queue to save" in ctx.send.await_args.kwargs["embed"].description


# ── queue looping ─────────────────────────────────────────────────────────────
async def test_requeue_finished_modes(bot):
    cog = Music(bot)
    player = cog._get_player(1001)
    member = make_member(USER_IDS["member"])
    player.current = _track("Original", member)

    assert cog._requeue_finished(player) is None
    player.loop = True
    assert cog._requeue_finished(player) == "front"
    player.loop = False
    player.queue_loop = True
    assert cog._requeue_finished(player) == "back"


def test_loop_state_label(bot):
    cog = Music(bot)
    player = GuildPlayer(1)
    assert cog._loop_state(player) == "➡️ OFF"
    player.loop = True
    assert cog._loop_state(player) == "🔂 ON — Single (repeat track)"
    player.loop = False
    player.queue_loop = True
    assert cog._loop_state(player) == "🔁 ON — Queue (repeat all)"


async def test_loop_no_arg_toggles_single_track(bot):
    cog = Music(bot)
    ctx = make_ctx(bot)
    player = cog._get_player(1001)
    await cog.loop.callback(cog, ctx)
    assert player.loop is True and player.queue_loop is False
    await cog.loop.callback(cog, ctx)
    assert player.loop is False and player.queue_loop is False


async def test_loop_queue_toggles_and_excludes_single(bot):
    cog = Music(bot)
    ctx = make_ctx(bot)
    player = cog._get_player(1001)
    await cog.loop.callback(cog, ctx, "queue")
    assert player.queue_loop is True and player.loop is False
    assert "enabled (**whole queue**)" in ctx.send.await_args.kwargs["embed"].description

    await cog.loop.callback(cog, ctx, "single")
    assert player.loop is True and player.queue_loop is False

    await cog.loop.callback(cog, ctx, "off")
    assert player.loop is False and player.queue_loop is False


async def test_loop_off_turns_everything_off(bot):
    cog = Music(bot)
    ctx = make_ctx(bot)
    player = cog._get_player(1001)
    player.loop = True
    player.queue_loop = True
    await cog.loop.callback(cog, ctx, "off")
    assert player.loop is False and player.queue_loop is False


async def test_loop_invalid_mode(bot):
    cog = Music(bot)
    ctx = make_ctx(bot)
    player = cog._get_player(1001)
    player.loop = True
    await cog.loop.callback(cog, ctx, "banana")
    eb = ctx.send.await_args.kwargs["embed"]
    assert "Invalid Mode" in eb.author.name
    assert player.loop is True


# ── link parsing and metadata ────────────────────────────────────────────────
def test_parse_spotify_link_and_uri():
    track_id = "4cOdK2wGLETKBW3PvgPWqT"
    forms = [
        f"https://open.spotify.com/track/{track_id}",
        f"https://open.spotify.com/track/{track_id}?si=8f2b1c3d4e5f6a7b",
        f"open.spotify.com/track/{track_id}",
        f"spotify:track:{track_id}",
        f"spotify:intl-de:track:{track_id}",
        f"https://open.spotify.com/intl-de/track/{track_id}",
        f"  https://open.spotify.com/track/{track_id}  ",
    ]
    for form in forms:
        assert parse_spotify_url(form) == ("track", track_id), form


def test_parse_spotify_non_track_kinds():
    assert parse_spotify_url("https://open.spotify.com/album/1DFixLWuPkv3KT3TnV35m3")[0] == "album"
    assert parse_spotify_url("https://open.spotify.com/playlist/37i9dQZF1DXcBWIGoYBM5M")[0] == "playlist"
    assert parse_spotify_url("spotify:episode:512ojhOuo1ktJprKbVcKyQ")[0] == "episode"


def test_parse_spotify_rejects_non_spotify():
    for junk in (
        "https://open.spotify.com/track/short",
        "https://open.spotify.com/",
        "spotify:track",
        "https://youtube.com/watch?v=4cOdK2wGLETKBW3PvgPWqT",
        "https://notspotify.com/track/4cOdK2wGLETKBW3PvgPWqT",
        "never gonna give you up",
    ):
        assert parse_spotify_url(junk) is None, junk


def test_parse_apple_song_link():
    url = "https://music.apple.com/us/album/never-gonna-give-you-up/1559885420?i=1559885421"
    assert parse_apple_url(url) == ("song", "1559885421")
    song = "https://music.apple.com/us/song/never-gonna-give-you-up/1559885421"
    assert parse_apple_url(song) == ("song", "1559885421")
    assert parse_apple_url("music.apple.com/us/song/x/1559885421") == ("song", "1559885421")


def test_parse_apple_album_and_rejects():
    assert parse_apple_url("https://music.apple.com/us/album/hits/1559885420")[0] == "album"
    assert parse_apple_url("https://open.spotify.com/track/4cOdK2wGLETKBW3PvgPWqT") is None
    assert parse_apple_url("https://youtube.com/watch?v=abc") is None
    assert parse_apple_url("a search term") is None


def test_metadata_from_embed_html_parses_entity():
    html = (
        '<html><head><script id="__NEXT_DATA__" type="application/json">'
        '{"props":{"pageProps":{"state":{"data":{"entity":{"name":"Blinding Lights",'
        '"artists":[{"name":"The Weeknd"}]}}}}}}</script></head></html>'
    )
    assert music_metadata._metadata_from_embed_html(html) == {
        "title": "Blinding Lights",
        "artist": "The Weeknd",
    }


def test_metadata_from_embed_html_joins_multiple_artists():
    html = (
        '<script id="__NEXT_DATA__">{"props":{"pageProps":{"state":{"data":{"entity":'
        '{"name":"Song","artists":[{"name":"A"},{"name":"B"}]}}}}}}</script>'
    )
    assert music_metadata._metadata_from_embed_html(html)["artist"] == "A, B"


def test_metadata_from_embed_html_is_resilient():
    assert music_metadata._metadata_from_embed_html("<html>no json here</html>") is None
    assert music_metadata._metadata_from_embed_html(
        '<script id="__NEXT_DATA__">{ not json }</script>'
    ) is None
    assert music_metadata._metadata_from_embed_html(
        '<script id="__NEXT_DATA__">{"props":{}}</script>'
    ) is None


def test_search_query_prefers_artist_title():
    assert search_query_for("Hello", "Adele") == "Adele - Hello"
    assert search_query_for("Hello", "") == "Hello"
    assert search_query_for("", "Adele") == ""
    assert search_query_for(" Hello ", " Adele ") == "Adele - Hello"


async def test_spotify_access_token_needs_credentials(monkeypatch):
    monkeypatch.delenv("SPOTIPY_CLIENT_ID", raising=False)
    monkeypatch.delenv("SPOTIPY_CLIENT_SECRET", raising=False)
    assert await music_metadata._spotify_access_token(None) is None


# ── node pool configuration ──────────────────────────────────────────────────
def test_parse_node_spec_compact():
    configs = parse_node_spec(
        "main|lavalink.example.com:2333|secret; backup|http://backup:8080|pw"
    )
    assert [c.identifier for c in configs] == ["main", "backup"]
    assert configs[0].normalised_uri() == "https://lavalink.example.com:2333"
    assert configs[1].normalised_uri() == "http://backup:8080"
    assert configs[1].secure is False


def test_parse_node_spec_json():
    raw = (
        '[{"identifier":"a","uri":"http://a:1","password":"p"},'
        '{"name":"b","url":"https://b:2","pass":"q"}]'
    )
    configs = parse_node_spec(raw)
    assert [c.identifier for c in configs] == ["a", "b"]
    assert configs[0].secure is False
    assert configs[1].secure is True


def test_parse_node_spec_ignores_junk():
    assert parse_node_spec("") == []
    assert parse_node_spec("only-one-field") == []


def test_load_node_configs_uses_env_override(monkeypatch):
    monkeypatch.setenv("LAVALINK_NODES", "one|http://one:1|pw; two|http://two:2|pw")
    monkeypatch.delenv("LAVALINK_URI", raising=False)
    monkeypatch.delenv("LAVALINK_PASSWORD", raising=False)
    configs = load_node_configs()
    assert [c.identifier for c in configs] == ["one", "two"]


def test_load_node_configs_single_uri(monkeypatch):
    monkeypatch.delenv("LAVALINK_NODES", raising=False)
    monkeypatch.setenv("LAVALINK_URI", "https://lava.example.com:443")
    monkeypatch.setenv("LAVALINK_PASSWORD", "secret")
    monkeypatch.setenv("LAVALINK_SECURE", "true")
    configs = load_node_configs()
    assert len(configs) == 1
    assert configs[0].password == "secret"
    assert configs[0].normalised_uri() == "https://lava.example.com:443"


def test_load_node_configs_falls_back_to_public_pool(monkeypatch):
    monkeypatch.delenv("LAVALINK_NODES", raising=False)
    monkeypatch.delenv("LAVALINK_URI", raising=False)
    monkeypatch.delenv("LAVALINK_PASSWORD", raising=False)
    configs = load_node_configs()
    assert len(configs) == len(DEFAULT_NODES)
    assert all(isinstance(c, LavalinkNodeConfig) for c in configs)


def test_pick_node_prefers_least_loaded():
    manager = _manager_with_nodes(("busy", 9), ("free", 1))
    assert manager.pick_node().identifier == "free"
    assert manager.pick_node(exclude=["free"]).identifier == "busy"


async def test_search_without_nodes_raises():
    manager = NodeManager(MagicMock(), configs=[])
    with pytest.raises(NoNodesAvailable):
        await manager.search("query")


async def test_search_fails_over_to_next_node(monkeypatch):
    manager = _manager_with_nodes(("dead", 0), ("alive", 1))
    calls: list[str] = []

    async def fake_search(query, *, source=None, node=None):
        calls.append(node.identifier)
        if node.identifier == "dead":
            raise RuntimeError("node exploded")
        return [_playable("Found It")]

    monkeypatch.setattr(wavelink.Playable, "search", fake_search)

    result = await manager.search("some query")

    assert calls == ["dead", "alive"]
    assert result[0].title == "Found It"


async def test_search_raises_when_every_node_fails(monkeypatch):
    manager = _manager_with_nodes(("a", 0), ("b", 1))

    async def fake_search(query, *, source=None, node=None):
        raise RuntimeError(f"{node.identifier} is down")

    monkeypatch.setattr(wavelink.Playable, "search", fake_search)

    with pytest.raises(TrackSearchError) as excinfo:
        await manager.search("query")
    assert "a is down" in str(excinfo.value) and "b is down" in str(excinfo.value)


async def test_search_skips_empty_results(monkeypatch):
    manager = _manager_with_nodes(("empty", 0), ("alive", 1))

    async def fake_search(query, *, source=None, node=None):
        if node.identifier == "empty":
            return []
        return [_playable("Only Result")]

    monkeypatch.setattr(wavelink.Playable, "search", fake_search)

    result = await manager.search_first("query")
    assert result.title == "Only Result"


# ── streaming-link translation in the cog ────────────────────────────────────
async def test_spotify_track_is_translated_to_a_search(bot, monkeypatch):
    cog = Music(bot)
    seen = {}

    async def fake_metadata(spotify_id):
        seen["id"] = spotify_id
        return {"title": "Never Gonna Give You Up", "artist": "Rick Astley"}

    async def fake_search(query, *, source=None):
        seen["query"] = query
        return [_playable("Never Gonna Give You Up")]

    monkeypatch.setattr(music_cog, "fetch_spotify_metadata", fake_metadata)
    monkeypatch.setattr(cog.nodes, "search", fake_search)

    track = await cog._fetch_track(
        "https://open.spotify.com/track/4cOdK2wGLETKBW3PvgPWqT?si=abc",
        make_member(USER_IDS["member"]),
    )

    assert track is not None
    assert seen["id"] == "4cOdK2wGLETKBW3PvgPWqT"
    assert seen["query"] == "Rick Astley - Never Gonna Give You Up"
    assert "spotify" not in seen["query"]


async def test_spotify_album_link_is_rejected(bot, monkeypatch):
    cog = Music(bot)

    async def boom(*args, **kwargs):
        raise AssertionError("Lavalink must not be searched for an album link")

    monkeypatch.setattr(cog.nodes, "search", boom)

    track = await cog._fetch_track(
        "https://open.spotify.com/album/1DFixLWuPkv3KT3TnV35m3",
        make_member(USER_IDS["member"]),
    )

    assert track is None
    assert "album" in cog._last_fetch_error


async def test_spotify_unresolvable_link_reports_config_hint(bot, monkeypatch):
    cog = Music(bot)

    async def no_metadata(spotify_id):
        return None

    async def boom(*args, **kwargs):
        raise AssertionError("Lavalink must not be searched when metadata is unavailable")

    monkeypatch.setattr(music_cog, "fetch_spotify_metadata", no_metadata)
    monkeypatch.setattr(cog.nodes, "search", boom)

    track = await cog._fetch_track(
        "spotify:track:4cOdK2wGLETKBW3PvgPWqT", make_member(USER_IDS["member"])
    )

    assert track is None
    assert "SPOTIPY_CLIENT_ID" in cog._last_fetch_error


async def test_apple_song_is_translated_to_a_search(bot, monkeypatch):
    cog = Music(bot)
    seen = {}

    async def fake_metadata(song_id):
        seen["id"] = song_id
        return {"title": "Never Gonna Give You Up", "artist": "Rick Astley"}

    async def fake_search(query, *, source=None):
        seen["query"] = query
        return [_playable("Never Gonna Give You Up")]

    monkeypatch.setattr(music_cog, "fetch_apple_metadata", fake_metadata)
    monkeypatch.setattr(cog.nodes, "search", fake_search)

    track = await cog._fetch_track(
        "https://music.apple.com/us/album/x/1559885420?i=1559885421",
        make_member(USER_IDS["member"]),
    )

    assert track is not None
    assert seen["id"] == "1559885421"
    assert seen["query"] == "Rick Astley - Never Gonna Give You Up"


async def test_apple_album_link_is_rejected(bot, monkeypatch):
    cog = Music(bot)

    async def boom(*args, **kwargs):
        raise AssertionError("Lavalink must not be searched for an album link")

    monkeypatch.setattr(cog.nodes, "search", boom)

    track = await cog._fetch_track(
        "https://music.apple.com/us/album/hits/1559885420",
        make_member(USER_IDS["member"]),
    )

    assert track is None
    assert "album" in cog._last_fetch_error


async def test_unparseable_streaming_link_never_reaches_lavalink(bot, monkeypatch):
    cog = Music(bot)

    async def boom(*args, **kwargs):
        raise AssertionError("Lavalink must not be searched for a broken streaming link")

    monkeypatch.setattr(cog.nodes, "search", boom)

    track = await cog._fetch_track(
        "https://open.spotify.com/playlist/not-a-real-id",
        make_member(USER_IDS["member"]),
    )

    assert track is None
    assert cog._last_fetch_error


async def test_fetch_track_reports_no_nodes(bot, monkeypatch):
    cog = Music(bot)

    async def no_nodes(*args, **kwargs):
        raise NoNodesAvailable("none")

    monkeypatch.setattr(cog.nodes, "search", no_nodes)

    assert await cog._fetch_track("hello", make_member(USER_IDS["member"])) is None
    assert "No music nodes" in cog._last_fetch_error


async def test_fetch_track_reports_search_failure(bot, monkeypatch):
    cog = Music(bot)

    async def failed(*args, **kwargs):
        raise TrackSearchError("all nodes failed")

    monkeypatch.setattr(cog.nodes, "search", failed)

    assert await cog._fetch_track("hello", make_member(USER_IDS["member"])) is None
    assert "Couldn't find" in cog._last_fetch_error


# ── Lavalink filters ─────────────────────────────────────────────────────────
def test_build_filters_bassboost_uses_equalizer():
    player = GuildPlayer(1)
    player.bassboost = True
    payload = build_filters(player)()
    bands = payload["equalizer"]
    assert bands[0]["band"] == 0
    assert bands[0]["gain"] > 0


def test_build_filters_nightcore_uses_timescale():
    player = GuildPlayer(1)
    player.nightcore = True
    payload = build_filters(player)()
    assert payload["timescale"]["speed"] == pytest.approx(1.3)
    assert payload["timescale"]["pitch"] == pytest.approx(1.3)


def test_build_filters_slowed_uses_lowpass():
    player = GuildPlayer(1)
    player.slowed = True
    payload = build_filters(player)()
    assert payload["timescale"]["speed"] == pytest.approx(0.8)
    assert payload["lowPass"]["smoothing"] == pytest.approx(20.0)


def test_build_filters_eight_d_uses_rotation():
    player = GuildPlayer(1)
    player.eight_d = True
    payload = build_filters(player)()
    assert payload["rotation"]["rotationHz"] == pytest.approx(0.2)


def test_build_filters_flat_has_no_effects():
    payload = build_filters(GuildPlayer(1))()
    assert "timescale" not in payload
    assert "rotation" not in payload
    assert "lowPass" not in payload
    assert all(band["gain"] == 0 for band in payload.get("equalizer", []))


def test_describe_filters_lists_active_effects():
    player = GuildPlayer(1)
    assert describe_filters(player) == "none"
    player.bassboost = True
    player.nightcore = True
    player.equalizer = "rock"
    description = describe_filters(player)
    assert "bass boost" in description
    assert "nightcore" in description
    assert "rock EQ" in description


# ── queue progression / status messaging ─────────────────────────────────────
def _voice_chat_channel():
    """A voice channel's text chat, as discord.py represents it."""
    return MagicMock(spec=discord.VoiceChannel)


def test_status_channel_accepts_voice_channel_chat(bot):
    cog = Music(bot)
    player = cog._get_player(1001)
    chat = _voice_chat_channel()

    cog._remember_text_channel(player, SimpleNamespace(channel=chat))

    assert player.text_channel is chat


def test_status_channel_accepts_text_channel(bot):
    cog = Music(bot)
    player = cog._get_player(1001)
    text = MagicMock(spec=discord.TextChannel)

    cog._remember_text_channel(player, SimpleNamespace(channel=text))

    assert player.text_channel is text


def test_status_channel_ignores_unusable_channel(bot):
    cog = Music(bot)
    player = cog._get_player(1001)

    cog._remember_text_channel(player, SimpleNamespace(channel=object()))

    assert player.text_channel is None


def _queued_player(cog, guild, member, count: int):
    player = cog._get_player(guild.id)
    for i in range(count):
        player.queue.append(_track(f"song {i}", member))
    return player


async def test_failed_status_update_does_not_clear_the_queue(bot, monkeypatch):
    """A cosmetic failure must never destroy the queue."""
    cog = Music(bot)
    member = make_member(USER_IDS["member"])
    guild = make_guild()
    bot.get_guild = MagicMock(return_value=guild)
    player = _queued_player(cog, guild, member, 3)

    async def fake_play(guild_id, track):
        player.current = track
        return MagicMock()

    async def boom(*args, **kwargs):
        raise RuntimeError("Missing Permissions")

    monkeypatch.setattr(cog, "_play_track", fake_play)
    monkeypatch.setattr(cog, "_update_presence", boom)
    player.text_channel = _voice_chat_channel()
    player.text_channel.send = AsyncMock(side_effect=boom)

    await cog._play_next_impl(guild.id)

    assert player.current is not None  # playback started
    assert len(player.queue) == 2  # one popped, the rest survived


async def test_failed_presence_alone_keeps_the_queue(bot, monkeypatch):
    cog = Music(bot)
    member = make_member(USER_IDS["member"])
    guild = make_guild()
    bot.get_guild = MagicMock(return_value=guild)
    player = _queued_player(cog, guild, member, 2)

    async def fake_play(guild_id, track):
        player.current = track
        return MagicMock()

    async def boom(*args, **kwargs):
        raise RuntimeError("cannot edit channel status")

    monkeypatch.setattr(cog, "_play_track", fake_play)
    monkeypatch.setattr(cog, "_update_presence", boom)
    player.text_channel = None

    await cog._play_next_impl(guild.id)

    assert len(player.queue) == 1


async def test_notify_swallows_send_failures(bot):
    cog = Music(bot)
    player = cog._get_player(1001)
    player.text_channel = _voice_chat_channel()
    player.text_channel.send = AsyncMock(side_effect=RuntimeError("Missing Permissions"))

    # must not raise
    await cog._notify(player, discord.Embed(title="now playing"))


async def test_notify_without_channel_is_a_noop(bot):
    cog = Music(bot)
    player = cog._get_player(1001)

    await cog._notify(player, discord.Embed(title="now playing"))


# ── track wrapper ────────────────────────────────────────────────────────────
def test_track_wraps_playable():
    requester = make_member(USER_IDS["member"])
    track = Track(_playable("Hello", length=245_000, artwork="https://img/x.png"), requester)
    assert track.title == "Hello"
    assert track.url == "https://example.com/song"
    assert track.duration == 245
    assert track.fmt_duration() == "04:05"
    assert track.playable is not None
    assert track.encoded == "encoded-Hello"
    assert track.artwork == "https://img/x.png"


def test_track_accepts_mapping():
    requester = make_member(USER_IDS["member"])
    track = Track({"title": "Mapped", "webpage_url": "https://x", "duration": 61}, requester)
    assert track.title == "Mapped"
    assert track.url == "https://x"
    assert track.duration == 61
    assert track.playable is None
    assert track.fmt_duration() == "01:01"


# ── node failover ────────────────────────────────────────────────────────────
async def test_missing_track_end_still_advances(bot, monkeypatch):
    """If a skip's track-end event never arrives, the queue must still move."""
    cog = Music(bot)
    guild = make_guild()
    bot.get_guild = MagicMock(return_value=guild)
    player = _queued_player(cog, guild, make_member(USER_IDS["member"]), 1)
    player._advance_on_stop = True

    async def no_sleep(*args, **kwargs):
        return None

    monkeypatch.setattr(music_cog.asyncio, "sleep", no_sleep)
    advanced = []

    async def fake_play_next(guild_id):
        advanced.append(guild_id)

    monkeypatch.setattr(cog, "_play_next_impl", fake_play_next)

    await cog._ensure_advance(guild.id, player._play_generation)

    assert advanced == [guild.id]
    assert player._advance_on_stop is False


async def test_handled_track_end_is_not_double_advanced(bot, monkeypatch):
    cog = Music(bot)
    guild = make_guild()
    player = _queued_player(cog, guild, make_member(USER_IDS["member"]), 1)
    # The real track-end handler clears the flag and bumps the generation.
    player._advance_on_stop = False
    player._play_generation += 1

    async def no_sleep(*args, **kwargs):
        return None

    monkeypatch.setattr(music_cog.asyncio, "sleep", no_sleep)

    async def boom(*args, **kwargs):
        raise AssertionError("must not advance twice")

    monkeypatch.setattr(cog, "_play_next_impl", boom)

    await cog._ensure_advance(guild.id, player._play_generation - 1)


async def test_disconnected_node_fails_over_players(bot, monkeypatch):
    cog = Music(bot)
    node = SimpleNamespace(
        identifier="dead",
        status=wavelink.NodeStatus.DISCONNECTED,
        players={},
    )
    wl_player = MagicMock()
    recovered = []

    async def fake_recover(player, failed_node):
        recovered.append((player, failed_node))

    async def no_sleep(*args, **kwargs):
        return None

    monkeypatch.setattr(music_cog.asyncio, "sleep", no_sleep)
    monkeypatch.setattr(cog, "_recover_after_node_close", fake_recover)

    await cog._recover_players_after_disconnect(node, [wl_player])

    assert recovered == [(wl_player, node)]


async def test_reconnected_node_keeps_its_players(bot, monkeypatch):
    cog = Music(bot)
    node = SimpleNamespace(
        identifier="back",
        status=wavelink.NodeStatus.CONNECTED,
        players={},
    )

    async def no_sleep(*args, **kwargs):
        return None

    async def boom(*args, **kwargs):
        raise AssertionError("must not move players off a resumed node")

    monkeypatch.setattr(music_cog.asyncio, "sleep", no_sleep)
    monkeypatch.setattr(cog, "_recover_after_node_close", boom)

    await cog._recover_players_after_disconnect(node, [MagicMock()])


async def test_revive_restores_last_track_on_failure(bot, monkeypatch):
    cog = Music(bot)
    member = make_member(USER_IDS["member"])
    ctx = make_ctx(bot, author=member)
    ctx.author.voice = SimpleNamespace(channel=MagicMock())
    player = cog._get_player(ctx.guild.id)
    player.last_track = _track("Lost Song", member)

    async def fake_ensure_voice(ctx):
        return MagicMock()

    async def boom(guild_id, track):
        raise RuntimeError("node unavailable")

    monkeypatch.setattr(cog, "_ensure_voice", fake_ensure_voice)
    monkeypatch.setattr(cog, "_play_track", boom)

    await cog.revive.callback(cog, ctx)

    assert player.last_track is not None
    assert player.last_track.title == "Lost Song"
    assert player.current is None
    assert "Could not resume" in ctx.send.await_args.kwargs["embed"].description
