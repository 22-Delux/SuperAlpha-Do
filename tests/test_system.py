"""System commands: constants, ping, latency, invite, reload, shutdown."""

from __future__ import annotations

import re
from unittest.mock import AsyncMock, MagicMock

import pytest
from discord.ext import commands

from bot.cogs.system import INVITE_URL, OWNER_HANDLE, SUPPORT_SERVER, System
from bot.services import ansi
from bot.services.ansi import Color as C, c

from helpers import REPO_ROOT, USER_IDS, make_ctx, make_guild, make_member, strip_ansi


def test_info_constants():
    assert INVITE_URL.startswith("https://discord.com/oauth2/authorize?client_id=")
    assert SUPPORT_SERVER.startswith("https://discord.gg/")
    assert OWNER_HANDLE.startswith("@")
    assert OWNER_HANDLE == "@r4ve_x"


def test_ws_ms_zero_with_no_latency(bot):
    cog = System(bot)
    bot.ws.latency = 0.0
    assert cog._ws_ms() == 0
    bot.ws.latency = 0.35
    assert cog._ws_ms() == 350


async def test_ping_edits_message(bot):
    cog = System(bot)
    sent = MagicMock()
    sent.edit = AsyncMock()
    ctx = make_ctx(bot)
    ctx.send = AsyncMock(return_value=sent)
    await cog.ping.callback(cog, ctx)

    assert "Pinging" in ctx.send.call_args_list[0].args[0]
    sent.edit.assert_awaited_once()
    content = sent.edit.await_args.kwargs["content"]
    visible = strip_ansi(content)
    assert content.startswith("```ansi")
    assert "ws: 0 ms" in visible
    assert "rtt:" in visible


async def test_latency_quality(bot):
    cog = System(bot)
    bot.ws.latency = 0.05
    ctx = make_ctx(bot)
    await cog.latency.callback(cog, ctx)
    assert "excellent" in ctx.send.await_args.args[0]

    bot.ws.latency = 1.0
    ctx2 = make_ctx(bot)
    await cog.latency.callback(cog, ctx2)
    assert "poor" in ctx2.send.await_args.args[0]


async def test_uptime_formats(bot):
    cog = System(bot)
    ctx = make_ctx(bot)
    await cog.uptime.callback(cog, ctx)
    assert " up " in strip_ansi(ctx.send.await_args.args[0])


async def test_invite_embed_has_urls(bot):
    cog = System(bot)
    ctx = make_ctx(bot)
    await cog.invite.callback(cog, ctx)
    embed = ctx.send.await_args.kwargs["embed"]
    assert INVITE_URL in embed.description
    by_name = {f.name: f.value for f in embed.fields}
    assert "⚠️ Registration required" in by_name
    assert OWNER_HANDLE in by_name["⚠️ Registration required"]


async def test_reload_owner_only(bot):
    cog = System(bot)
    bot.reload_extension = AsyncMock()

    guild = make_guild()
    member = make_member(USER_IDS["member"], guild=guild)
    ctx = make_ctx(bot, author=member, guild=guild)
    with pytest.raises(commands.NotOwner):
        await cog.reload.can_run(ctx)

    owner = make_member(USER_IDS["owner"], guild=guild)
    ctx_owner = make_ctx(bot, author=owner, guild=guild)
    await cog.reload.can_run(ctx_owner)
    await cog.reload.callback(cog, ctx_owner, "utility")
    assert "reloaded successfully" in ctx_owner.send.await_args.args[0]


async def test_shutdown_owner_only(bot):
    cog = System(bot)
    bot.close = AsyncMock()
    guild = make_guild()

    member = make_member(USER_IDS["member"], guild=guild)
    ctx = make_ctx(bot, author=member, guild=guild)
    with pytest.raises(commands.NotOwner):
        await cog.shutdown.can_run(ctx)
    bot.close.assert_not_awaited()

    owner = make_member(USER_IDS["owner"], guild=guild)
    ctx_owner = make_ctx(bot, author=owner, guild=guild)
    await cog.shutdown.can_run(ctx_owner)
    await cog.shutdown.callback(cog, ctx_owner)
    assert "shutdown now" in ctx_owner.send.await_args.args[0]
    bot.close.assert_awaited_once()


async def test_unloadcog_protects_system(bot):
    cog = System(bot)
    ctx = make_ctx(bot)
    bot.unload_extension = AsyncMock()
    await cog.unloadcog.callback(cog, ctx, "system")
    assert "cannot unload system cog" in ctx.send.await_args.args[0]
    bot.unload_extension.assert_not_awaited()


ISSUE_PAYLOAD = {
    "number": 42,
    "title": "Fix the thing",
    "state": "open",
    "body": "The thing is broken.",
    "user": {"login": "tester"},
    "labels": [{"name": "bug"}, {"name": "good first issue"}],
    "comments": 3,
    "created_at": "2026-01-02T03:04:05Z",
    "html_url": "https://github.com/guptamaan/SuperAlpha-Do/issues/42",
}

PR_PAYLOAD = {
    **ISSUE_PAYLOAD,
    "merged": False,
    "merged_at": None,
    "mergeable": True,
    "commits": 5,
    "additions": 120,
    "deletions": 30,
    "changed_files": 4,
    "base": {"ref": "main"},
    "head": {"ref": "feature/x"},
    "html_url": "https://github.com/guptamaan/SuperAlpha-Do/pull/42",
}


async def test_issue_shows_embed(bot, monkeypatch):
    cog = System(bot)
    monkeypatch.setattr("bot.cogs.system._gh_issue", AsyncMock(return_value=ISSUE_PAYLOAD))
    ctx = make_ctx(bot)
    await cog.issue.callback(cog, ctx, 42)
    embed = ctx.send.await_args.kwargs["embed"]
    assert "42" in embed.title and "Fix the thing" in embed.title
    by_name = {f.name: f.value for f in embed.fields}
    assert by_name["State"] == "Open"
    assert "`bug`" in by_name["Labels"]
    assert by_name["Comments"] == "3"
    assert embed.url == ISSUE_PAYLOAD["html_url"]


async def test_pr_shows_merge_info(bot, monkeypatch):
    cog = System(bot)
    monkeypatch.setattr("bot.cogs.system._gh_pr", AsyncMock(return_value=PR_PAYLOAD))
    ctx = make_ctx(bot)
    await cog.pr.callback(cog, ctx, 42)
    embed = ctx.send.await_args.kwargs["embed"]
    assert "🟢 open" in embed.title
    by_name = {f.name: f.value for f in embed.fields}
    assert by_name["Base → Head"] == "`main` → `feature/x`"
    assert "+120 −30" in by_name["Merge"]


async def test_issue_missing_payload(bot, monkeypatch):
    cog = System(bot)
    monkeypatch.setattr("bot.cogs.system._gh_issue", AsyncMock(return_value=None))
    ctx = make_ctx(bot)
    await cog.issue.callback(cog, ctx, 9999)
    content = ctx.send.await_args.args[0]
    assert content.startswith("```ansi")
    assert "Resource not found or GitHub unreachable" in strip_ansi(content)


# ── ANSI terminal output ──────────────────────────────────────────────────────
def test_no_plain_bash_blocks_remain():
    """Every terminal-style block should be an ANSI one, in every file that
    prints terminal output."""
    for name in ("bot/cogs/system.py", "bot/cogs/journal.py", "main.py"):
        source = (REPO_ROOT / name).read_text(encoding="utf-8")
        assert "```bash" not in source, f"{name} still has a plain bash block"


async def test_latency_and_uptime_are_ansi(bot):
    cog = System(bot)
    ctx = make_ctx(bot)
    await cog.latency.callback(cog, ctx)
    content = ctx.send.await_args.args[0]
    assert content.startswith("```ansi")
    assert "\x1b[" in content
    assert "excellent" in strip_ansi(content)

    up_ctx = make_ctx(bot)
    await cog.uptime.callback(cog, up_ctx)
    up_content = up_ctx.send.await_args.args[0]
    assert up_content.startswith("```ansi")
    assert " up " in strip_ansi(up_content)


async def test_htop_block_is_ansi_and_width_capped(bot):
    cog = System(bot)
    ctx = make_ctx(bot)
    # MagicMock will not format member_count with a thousands separator.
    ctx.guild.member_count = 1234
    block = cog._htop_block(ctx)

    assert block.startswith("```ansi")
    assert "alpha htop" in strip_ansi(block)
    assert "1,234" in strip_ansi(block)

    body = block[len("```ansi\n") : -len("\n```")]
    reset = f"\x1b[{C.RESET}m"
    for line in body.split("\n"):
        assert ansi.visible_len(line) <= 104, repr(strip_ansi(line))
        # A colour span cut in half would leak colour into later lines, so every
        # style start needs a matching reset.
        seqs = re.findall(r"\x1b\[[0-9;]*m", line)
        starts = len([s for s in seqs if s != reset])
        # Every style start must be closed, or its colour bleeds into later
        # lines. A clipped line may carry one extra reset, which is harmless.
        assert starts <= seqs.count(reset), repr(line)


def test_clip_keeps_colour_spans_whole():
    reset = f"\x1b[{C.RESET}m"
    text = f"{c(C.RED, 'abcdefghij')}{c(C.GREEN, 'klmnop')}"
    clipped = ansi.clip(text, 6)

    assert ansi.visible_len(clipped) == 6
    assert strip_ansi(clipped) == "abcdef"
    assert clipped.endswith(reset)
    assert ansi.clip("short", 40) == "short"
    assert ansi.visible_len(ansi.clip(text, 40)) == 16


def test_field_pads_before_colouring():
    # Padding a coloured string would count the escape codes and misalign.
    reset = f"\x1b[{C.RESET}m"
    coloured = ansi.field("ab", 5, C.CYAN)
    assert strip_ansi(coloured) == "ab   "
    assert coloured == c(C.CYAN, "ab   ")


def test_clean_strips_escape_injection():
    assert ansi.clean("evil\x1b[31mred") == "evil[31mred"
    assert strip_ansi(ansi.err("bad")) == "bad"
    assert "\x1b[" in ansi.err("bad")


def test_latency_colour_bands():
    assert ansi.latency(10).startswith(c(C.BOLD, C.GREEN, "")[:4])   # excellent
    assert ansi.latency(100).startswith(c(C.BOLD, C.YELLOW, "")[:4])  # fair
    assert ansi.latency(900).startswith(c(C.BOLD, C.RED, "")[:4])     # poor
    for ms in (0, 79, 80, 149, 150, 5000):
        assert strip_ansi(ansi.latency(ms)) == f"{ms} ms"


def test_term_wraps_in_ansi_fence():
    assert ansi.term("a", "b") == "```ansi\na\nb\n```"


# ── Discord length limits ─────────────────────────────────────────────────────
# Discord validates the raw string, and colour codes are invisible characters
# that count toward the cap.
def _assert_block_fits(name: str, block: str, cap: int) -> None:
    assert len(block) <= cap, f"{name}: {len(block)} raw chars exceeds {cap}"
    assert block.startswith("```ansi\n"), name
    assert block.endswith("\n```"), name
    reset = f"\x1b[{C.RESET}m"
    for line in block[len("```ansi\n") : -len("\n```")].split("\n"):
        seqs = re.findall(r"\x1b\[[0-9;]*m", line)
        assert len([s for s in seqs if s != reset]) <= seqs.count(reset), repr(line)


def test_term_keeps_newest_lines_and_marks_the_rest():
    lines = [ansi.note(f"line {i}") for i in range(500)]
    block = ansi.term(*lines, limit=400)

    _assert_block_fits("term(400)", block, 400)
    body = block[len("```ansi\n") : -len("\n```")]
    assert "line 499" in strip_ansi(body), "newest line must survive"
    assert "line 0" not in strip_ansi(body), "oldest line should be dropped"
    assert "not shown" in strip_ansi(body)


def test_term_clips_a_single_oversized_line():
    block = ansi.term(ansi.note("z" * 9000))

    _assert_block_fits("term(monster)", block, ansi.embed_limit())
    body = strip_ansi(block)
    assert body.startswith("```ansi\nz")
    assert body.endswith("…\n```")


def test_term_survives_when_every_line_is_oversized():
    block = ansi.term(*([ansi.note("z" * 9000)] * 3), limit=500)

    _assert_block_fits("term(all monsters)", block, 500)


def test_embed_sites_fit_the_embed_limit():
    """The journal embeds are the widest terminal output the bot builds."""
    from bot.cogs.journal import HISTORY_LIMIT, MAX_SHOW, _render

    entries = [
        {
            "ts": 1756400000, "guild": "G" * 12, "user": "U" * 12, "uid": "9" * 11,
            "kind": "alpha", "cog": "musi", "cmd": "c" * 24, "args": "a" * 80 + f" {i}",
        }
        for i in range(MAX_SHOW)
    ]
    _assert_block_fits("journalctl", ansi.term(_render(entries, MAX_SHOW, []), limit=ansi.embed_limit()), 4096)

    rows = [{"line": 99999, "content": "x" * 200} for _ in range(HISTORY_LIMIT)]
    body = [ansi.prompt("alpha history")]
    body += [f"  {ansi.field(r['line'], 5, C.CYAN)}  {ansi.note(r['content'])}" for r in rows]
    _assert_block_fits("history", ansi.term(*body, limit=ansi.embed_limit()), 4096)


async def test_message_output_capped_to_message_limit(bot):
    """A pathological error string must not produce an over-long message."""
    cog = System(bot)
    bot.reload_extension = AsyncMock(side_effect=Exception("X" * 3000))
    ctx = make_ctx(bot)
    await cog.reload.callback(cog, ctx, "system")

    _assert_block_fits("reload", ctx.send.await_args.args[0], 2000)