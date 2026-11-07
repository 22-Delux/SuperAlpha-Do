"""Lavalink node pool: configuration, connection, health checks, and failover.

Playback is handled entirely by Lavalink through :mod:`wavelink`.  This module
owns the set of public nodes the bot connects to.  A search or playback request
is retried on the next healthy node when one goes down, so a single flaky public
Lavalink instance does not take music offline.

Environment overrides
---------------------
``LAVALINK_NODES``
    A ``;`` or newline separated list of ``identifier|uri|password`` entries.
    ``uri`` may be a bare ``host:port`` or a full ``http(s)://`` URL.  When the
    URI has no scheme, ``https`` is assumed.
``LAVALINK_URI`` / ``LAVALINK_PASSWORD``
    A single-node override used when ``LAVALINK_NODES`` is not set.
``LAVALINK_NODE_RETRIES``
    Optional number of reconnect attempts per health pass (default ``1``).
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from dataclasses import dataclass
from typing import Any, Iterable

import wavelink

log = logging.getLogger(__name__)


class NodePoolError(RuntimeError):
    """Base class for node-pool failures."""


class NoNodesAvailable(NodePoolError):
    """Raised when no configured node is currently connected."""


class TrackSearchError(NodePoolError):
    """Raised when every healthy node failed to answer a search."""


@dataclass(frozen=True)
class LavalinkNodeConfig:
    """A single Lavalink node definition."""

    identifier: str
    uri: str
    password: str
    secure: bool = True

    def normalised_uri(self) -> str:
        uri = (self.uri or "").strip().rstrip("/")
        if not uri:
            return ""
        if "://" in uri:
            return uri
        scheme = "https" if self.secure else "http"
        return f"{scheme}://{uri}"

    def to_node(self) -> wavelink.Node:
        return wavelink.Node(
            identifier=self.identifier,
            uri=self.normalised_uri(),
            password=self.password,
            # Start with a single attempt so Pool.connect never hangs on a dead
            # public node.  Successful nodes are switched to unlimited retries.
            retries=0,
        )


# A spread of public Lavalink v4 nodes.  They are volunteers and come and go;
# the pool exists precisely so the bot can move on when one does.
DEFAULT_NODES: tuple[LavalinkNodeConfig, ...] = (
    LavalinkNodeConfig("serenetia-ssl", "https://lavalinkv4.serenetia.com:443", "https://seretia.link/discord", True),
    LavalinkNodeConfig("jirayu-ssl", "https://lavalink.jirayu.net:443", "youshallnotpass", True),
    LavalinkNodeConfig("millohost", "https://lava-v4.millohost.my.id:443", "https://discord.gg/mjS5J2K3ep", True),
    LavalinkNodeConfig("trinium-ssl", "https://lavalink-v4.triniumhost.com:443", "free", True),
    LavalinkNodeConfig("nazha", "https://lavalink.nazha.online:443", "nazhafreelava", True),
    LavalinkNodeConfig("nodelink", "https://nodelink.gdjkhp.com:443", "youshallnotpass", True),
    LavalinkNodeConfig("serenetia-http", "http://lavalinkv4.serenetia.com:80", "https://seretia.link/discord", False),
    LavalinkNodeConfig("g3v", "http://lava.g3v.co.uk:9008", "lavalinklol", False),
    LavalinkNodeConfig("trinium-http", "http://lavalink.triniumhost.com:4333", "free", False),
    LavalinkNodeConfig("nexcloud", "http://n3.nexcloud.in:2026", "nexcloud", False),
    LavalinkNodeConfig("vexanode", "http://omega.vexanode.cloud:2031", "https://discord.vexanode.cloud", False),
    LavalinkNodeConfig("kasawa", "http://lava2.kasawa.pro:2334", "youshallnotpass", False),
    LavalinkNodeConfig("minecuta", "http://lavav4.minecuta.com:2333", "discord.gg/gKuXdHs", False),
    LavalinkNodeConfig("heaven-budget", "http://budget-us7.bot.heavencloud.in:6706", "youshallnotpass", False),
    LavalinkNodeConfig("heaven-free", "http://free-lava.heavencloud.in:4000", "heavencloud.in", False),
)


def _config_from_mapping(data: dict[str, Any]) -> LavalinkNodeConfig | None:
    uri = str(data.get("uri") or data.get("url") or "").strip()
    password = str(data.get("password") or data.get("pass") or "")
    if not uri or not password:
        return None
    identifier = str(data.get("identifier") or data.get("name") or uri)
    secure = bool(data.get("secure", "https" in uri.lower()))
    return LavalinkNodeConfig(identifier=identifier, uri=uri, password=password, secure=secure)


def parse_node_spec(raw: str) -> list[LavalinkNodeConfig]:
    """Parse a ``;``/newline separated node specification.

    Accepts JSON (a list of objects) as well as the compact
    ``identifier|uri|password`` form.
    """
    text = (raw or "").strip()
    if not text:
        return []

    if text.startswith("[") or text.startswith("{"):
        try:
            parsed = json.loads(text)
        except (TypeError, ValueError):
            parsed = None
        if isinstance(parsed, dict):
            parsed = [parsed]
        if isinstance(parsed, list):
            configs = [_config_from_mapping(item) for item in parsed if isinstance(item, dict)]
            return [config for config in configs if config is not None]

    configs: list[LavalinkNodeConfig] = []
    for line in text.replace("\r", "\n").replace(";", "\n").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = [part.strip() for part in line.split("|")]
        if len(parts) < 3:
            log.warning("Ignoring malformed LAVALINK_NODES entry: %r", line)
            continue
        identifier, uri, password = parts[0], parts[1], "|".join(parts[2:])
        if not identifier or not uri or not password:
            continue
        configs.append(
            LavalinkNodeConfig(
                identifier=identifier,
                uri=uri,
                password=password,
                secure="https" in uri.lower() or "://" not in uri,
            )
        )
    return configs


def load_node_configs() -> list[LavalinkNodeConfig]:
    """Resolve the configured node list, falling back to the public pool."""
    raw = os.getenv("LAVALINK_NODES", "").strip()
    if raw:
        parsed = parse_node_spec(raw)
        if parsed:
            return parsed
        log.warning("LAVALINK_NODES was set but could not be parsed; using public nodes")

    uri = os.getenv("LAVALINK_URI", "").strip()
    password = os.getenv("LAVALINK_PASSWORD", "").strip()
    if uri and password:
        secure = os.getenv("LAVALINK_SECURE", "true").strip().lower() not in {"0", "false", "no"}
        return [
            LavalinkNodeConfig(
                identifier=os.getenv("LAVALINK_IDENTIFIER", "default"),
                uri=uri,
                password=password,
                secure=secure,
            )
        ]

    return list(DEFAULT_NODES)


def _node_sort_key(node: wavelink.Node) -> tuple[int, int]:
    """Prefer nodes with fewer players, then lower Lavalink load."""
    players = node._total_player_count
    if players is None:
        players = len(node.players)
    return (players, len(node.players))


class NodeManager:
    """Owns the Lavalink nodes and hides failover from the command layer."""

    def __init__(
        self,
        bot: Any,
        configs: Iterable[LavalinkNodeConfig] | None = None,
        *,
        health_interval: float = 30.0,
    ) -> None:
        self.bot = bot
        self.configs = list(configs) if configs is not None else load_node_configs()
        self.health_interval = health_interval
        self.nodes: list[wavelink.Node] = []
        self._health_task: asyncio.Task[None] | None = None
        self._closing = False
        self._closed = False

    # ── lifecycle ────────────────────────────────────────────────────────────
    async def connect(self) -> dict[str, wavelink.Node]:
        """Connect every configured node concurrently and start health checks."""
        if not self.configs:
            log.warning("No Lavalink nodes are configured; music commands will report unavailable")
            return {}

        self.nodes = [config.to_node() for config in self.configs]
        results = await asyncio.gather(
            *(self._connect_node(node) for node in self.nodes),
            return_exceptions=True,
        )
        for result in results:
            if isinstance(result, Exception):
                log.warning("Lavalink node connection error: %s", result)

        connected = self.connected_nodes
        log.info(
            "Lavalink pool ready: %d/%d nodes connected (%s)",
            len(connected),
            len(self.nodes),
            ", ".join(node.identifier for node in connected) or "none",
        )
        self._start_health()
        return {node.identifier: node for node in connected}

    async def _connect_node(self, node: wavelink.Node) -> None:
        node._retries = 0
        try:
            await wavelink.Pool.connect(nodes=[node], client=self.bot)
        except Exception as exc:  # pragma: no cover - network dependent
            log.warning("Could not connect Lavalink node %s: %s", node.identifier, exc)
            return
        if node.status is wavelink.NodeStatus.CONNECTED:
            # Once a node is up let wavelink keep its websocket alive forever.
            node._retries = None

    async def close(self) -> None:
        self._closing = True
        if self._health_task is not None:
            self._health_task.cancel()
            self._health_task = None
        if self._closed:
            return
        self._closed = True
        try:
            await wavelink.Pool.close()
        except Exception as exc:  # pragma: no cover - shutdown best effort
            log.debug("Error closing Lavalink pool: %s", exc)

    # ── health / selection ───────────────────────────────────────────────────
    @property
    def closing(self) -> bool:
        """Whether the pool is shutting down (used to ignore late node events)."""
        return self._closing

    @property
    def connected_nodes(self) -> list[wavelink.Node]:
        return [node for node in self.nodes if node.status is wavelink.NodeStatus.CONNECTED]

    def pick_node(self, exclude: Iterable[str] | None = None) -> wavelink.Node | None:
        """Return the least-loaded connected node, optionally skipping identifiers."""
        excluded = set(exclude or ())
        candidates = [node for node in self.connected_nodes if node.identifier not in excluded]
        if not candidates:
            return None
        return sorted(candidates, key=_node_sort_key)[0]

    async def wait_for_node(self, timeout: float = 8.0) -> wavelink.Node | None:
        """Wait briefly for a node to come up, then return the best one."""
        node = self.pick_node()
        if node is not None:
            return node
        deadline = asyncio.get_running_loop().time() + max(0.0, timeout)
        while asyncio.get_running_loop().time() < deadline:
            await asyncio.sleep(0.25)
            node = self.pick_node()
            if node is not None:
                return node
        return None

    def _start_health(self) -> None:
        if self._health_task is None or self._health_task.done():
            self._health_task = asyncio.create_task(self._health_loop(), name="lavalink-health")

    async def _health_loop(self) -> None:
        while not self._closing:
            try:
                await asyncio.sleep(self.health_interval)
            except asyncio.CancelledError:
                return
            try:
                await self.reconnect_disconnected()
            except Exception as exc:  # pragma: no cover - defensive
                log.debug("Lavalink health pass failed: %s", exc)

    async def reconnect_disconnected(self) -> list[wavelink.Node]:
        """Attempt to bring every disconnected node back into the pool."""
        if self._closing:
            return []
        retries = max(0, int(os.getenv("LAVALINK_NODE_RETRIES", "1") or 1))
        reconnected: list[wavelink.Node] = []
        known = wavelink.Pool.nodes
        for node in self.nodes:
            if node.status is not wavelink.NodeStatus.DISCONNECTED:
                continue
            node._retries = retries
            try:
                if node.identifier in known:
                    # Previously registered nodes are reconnected in place.
                    await node._connect(client=self.bot)
                else:
                    # Nodes that never connected are not in the Pool yet; adding
                    # them lets Wavelink route new players to them.
                    await wavelink.Pool.connect(nodes=[node], client=self.bot)
            except Exception as exc:  # pragma: no cover - network dependent
                log.debug("Reconnect failed for %s: %s", node.identifier, exc)
                continue
            finally:
                node._retries = None if node.status is wavelink.NodeStatus.CONNECTED else 0
            if node.status is wavelink.NodeStatus.CONNECTED:
                reconnected.append(node)
                log.info("Lavalink node %s reconnected", node.identifier)
        return reconnected

    # ── searches with failover ───────────────────────────────────────────────
    def candidate_nodes(self, exclude: Iterable[str] | None = None) -> list[wavelink.Node]:
        excluded = set(exclude or ())
        return sorted(
            (node for node in self.connected_nodes if node.identifier not in excluded),
            key=_node_sort_key,
        )

    async def search(
        self,
        query: str,
        *,
        source: wavelink.TrackSource | str | None = wavelink.TrackSource.YouTube,
        limit: int | None = None,
    ) -> list[wavelink.Playable] | wavelink.Playlist:
        """Search every healthy node until one returns a result.

        Raises :class:`NoNodesAvailable` when nothing is connected and
        :class:`TrackSearchError` when every node failed or returned no tracks.
        """
        nodes = self.candidate_nodes()
        if not nodes:
            raise NoNodesAvailable("No Lavalink nodes are currently connected.")

        errors: list[str] = []
        for node in nodes:
            try:
                result = await wavelink.Playable.search(query, source=source, node=node)
            except Exception as exc:
                errors.append(f"{node.identifier}: {exc}")
                log.warning("Search failed on Lavalink node %s: %s", node.identifier, exc)
                continue

            if isinstance(result, wavelink.Playlist):
                if len(result) > 0:
                    return result
                errors.append(f"{node.identifier}: empty playlist")
                continue

            tracks = list(result or [])
            if tracks:
                return tracks[:limit] if limit else tracks
            errors.append(f"{node.identifier}: no results")

        raise TrackSearchError("; ".join(errors) or "No node returned any results.")

    async def search_first(
        self,
        query: str,
        *,
        source: wavelink.TrackSource | str | None = wavelink.TrackSource.YouTube,
    ) -> wavelink.Playable | None:
        result = await self.search(query, source=source, limit=1)
        if isinstance(result, wavelink.Playlist):
            return result[0] if len(result) else None
        return result[0] if result else None

    # ── mid-playback failover ────────────────────────────────────────────────
    async def failover_player(self, player: wavelink.Player, exclude: Iterable[str] | None = None) -> wavelink.Node | None:
        """Move an existing player to another node.  Returns the new node or None."""
        new_node = self.pick_node(exclude=exclude)
        if new_node is None:
            return None
        try:
            await player.switch_node(new_node)
        except Exception as exc:  # pragma: no cover - network dependent
            log.warning("Could not move player to %s: %s", new_node.identifier, exc)
            return None
        return new_node


__all__ = [
    "DEFAULT_NODES",
    "LavalinkNodeConfig",
    "NodeManager",
    "NodePoolError",
    "NoNodesAvailable",
    "TrackSearchError",
    "load_node_configs",
    "parse_node_spec",
]
