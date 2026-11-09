"""SQLite/JSON persistence for the XP & SP profile system.

Owns user rows, the in-memory write-behind cache, and per-guild XP settings.
Pure persistence — level math lives in ``bot.services.leveling`` and the
command surface in ``bot.cogs.xp``.
"""

from __future__ import annotations

import logging
import os
import sqlite3
import json
import time
from typing import Optional, List, Dict, Tuple, Any

from bot.core.database import Database


logger = logging.getLogger(__name__)

DATA_DIR = "data/xp"
CONFIG_FILE = "data/xp/config.json"
DATABASE_FILE = "data/xp.db"


async def init_db(db: Database) -> None:
    try:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS xp_users (
                user_id        BIGINT PRIMARY KEY,
                xp             BIGINT NOT NULL DEFAULT 0,
                level          INTEGER NOT NULL DEFAULT 1,
                sp             BIGINT NOT NULL DEFAULT 0,
                messages       INTEGER NOT NULL DEFAULT 0,
                vc_time        INTEGER NOT NULL DEFAULT 0,
                commands_used  INTEGER NOT NULL DEFAULT 0,
                last_message   DOUBLE PRECISION NOT NULL DEFAULT 0,
                vc_start       DOUBLE PRECISION NOT NULL DEFAULT 0,
                daily_claimed  TEXT,
                streak         INTEGER NOT NULL DEFAULT 0
            )
        """)
    except Exception as exc:
        logger.warning("init_db: could not create xp_users: %s", exc)
    try:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS xp_guild_settings (
                guild_id       BIGINT PRIMARY KEY,
                enabled        BOOLEAN NOT NULL DEFAULT TRUE,
                level_channel  BIGINT
            )
        """)
    except Exception as exc:
        logger.warning("init_db: could not create xp_guild_settings: %s", exc)


def _default_user() -> dict:
    return {
        "xp": 0,
        "level": 1,
        "sp": 0,
        "messages": 0,
        "vc_time": 0,
        "commands_used": 0,
        "last_message": 0.0,
        "vc_start": 0.0,
        "daily_claimed": None,
        "streak": 0,
    }


async def load_user(db: Database, user_id: int) -> dict:
    row = await db.fetchrow("SELECT * FROM xp_users WHERE user_id = $1", user_id)
    if row is not None:
        return {
            "xp": int(row["xp"] or 0),
            "level": int(row["level"] or 1),
            "sp": int(row["sp"] or 0),
            "messages": int(row["messages"] or 0),
            "vc_time": int(row["vc_time"] or 0),
            "commands_used": int(row["commands_used"] or 0),
            "last_message": float(row["last_message"] or 0),
            "vc_start": float(row["vc_start"] or 0),
            "daily_claimed": row["daily_claimed"],
            "streak": int(row["streak"] or 0),
        }
    return _default_user()


async def save_user(db: Database, user_id: int, data: dict) -> None:
    merged = _default_user()
    merged.update(data)
    await db.execute(
        """
        INSERT INTO xp_users (user_id, xp, level, sp, messages, vc_time,
                              commands_used, last_message, vc_start, daily_claimed, streak)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
        ON CONFLICT(user_id) DO UPDATE SET
            xp=EXCLUDED.xp, level=EXCLUDED.level, sp=EXCLUDED.sp,
            messages=EXCLUDED.messages, vc_time=EXCLUDED.vc_time,
            commands_used=EXCLUDED.commands_used, last_message=EXCLUDED.last_message,
            vc_start=EXCLUDED.vc_start, daily_claimed=EXCLUDED.daily_claimed,
            streak=EXCLUDED.streak
        """,
        user_id,
        int(merged["xp"] or 0),
        int(merged["level"] or 1),
        int(merged["sp"] or 0),
        int(merged["messages"] or 0),
        int(merged["vc_time"] or 0),
        int(merged["commands_used"] or 0),
        float(merged["last_message"] or 0),
        float(merged["vc_start"] or 0),
        merged["daily_claimed"],
        int(merged["streak"] or 0),
    )


def flush_all() -> None:
    pass


_TOP_COLUMNS = {"xp": "xp", "sp": "sp", "messages": "messages", "vc": "vc_time"}


async def top_users(db: Database, key: str, limit: int = 10, weekly: bool = False, user_ids=None) -> list[tuple[int, dict]]:
    """Top `limit` users ranked by a stat key, as [(user_id, data), ...]."""
    column = _TOP_COLUMNS.get(key, _TOP_COLUMNS.get("xp", "xp"))
    params = []
    where = ""
    if user_ids is not None:
        where = " WHERE user_id = ANY($1)"
        params.append(list(user_ids))
    limit_ph = f"${len(params) + 1}"
    params.append(limit)
    rows = await db.fetch(
        f"SELECT * FROM xp_users{where} ORDER BY {column} DESC, user_id ASC LIMIT {limit_ph}",
        *params,
    )
    result = []
    for r in rows:
        data = {
            "xp": int(r["xp"] or 0),
            "level": int(r["level"] or 1),
            "sp": int(r["sp"] or 0),
            "messages": int(r["messages"] or 0),
            "vc_time": int(r["vc_time"] or 0),
            "commands_used": int(r["commands_used"] or 0),
            "last_message": float(r["last_message"] or 0),
            "vc_start": float(r["vc_start"] or 0),
            "daily_claimed": r["daily_claimed"],
            "streak": int(r["streak"] or 0),
        }
        result.append((int(r["user_id"]), data))
    return result


async def reset_weekly_leaderboard(db: Database) -> None:
    pass


async def is_xp_enabled(db: Database, guild_id: int) -> bool:
    row = await db.fetchrow("SELECT enabled FROM xp_guild_settings WHERE guild_id = $1", guild_id)
    if row is not None:
        return bool(row["enabled"])
    return True


async def set_xp_enabled(db: Database, guild_id: int, enabled: bool) -> None:
    await db.execute(
        """
        INSERT INTO xp_guild_settings (guild_id, enabled)
        VALUES ($1, $2)
        ON CONFLICT(guild_id) DO UPDATE SET enabled = EXCLUDED.enabled
        """,
        guild_id,
        enabled,
    )


async def get_level_channel(db: Database, guild_id: int) -> int | None:
    row = await db.fetchrow("SELECT level_channel FROM xp_guild_settings WHERE guild_id = $1", guild_id)
    if row is not None:
        return row["level_channel"]
    return None


async def set_level_channel(db: Database, guild_id: int, channel_id: int | None) -> None:
    await db.execute(
        """
        INSERT INTO xp_guild_settings (guild_id, level_channel)
        VALUES ($1, $2)
        ON CONFLICT(guild_id) DO UPDATE SET level_channel = EXCLUDED.level_channel
        """,
        guild_id,
        channel_id,
    )



# XP DATA MIGRATION
# ===============================================

async def migrate_legacy_data_to_postgres(db: Database) -> None:
    logger.info("Starting legacy XP data migration to PostgreSQL...")
    if os.path.exists(DATABASE_FILE):
        try:
            sqlite_conn = sqlite3.connect(DATABASE_FILE)
            sqlite_conn.row_factory = sqlite3.Row
            cursor = sqlite_conn.execute("SELECT * FROM xp_users")
            rows = cursor.fetchall()
            for row in rows:
                user_data = {
                    "xp": row["xp"],
                    "level": row["level"],
                    "sp": row["sp"],
                    "messages": row["messages"],
                    "vc_time": row["vc_time"],
                    "commands_used": row["commands_used"],
                    "last_message": row["last_message"],
                    "vc_start": row["vc_start"],
                    "daily_claimed": row["daily_claimed"],
                    "streak": row["streak"],
                }
                await save_user(db, int(row["user_id"]), user_data)
            sqlite_conn.close()
            logger.info(f"Successfully migrated {len(rows)} users from SQLite xp.db.")
        except Exception as e:
            logger.error(f"Error migrating SQLite xp.db: {e}")

    if os.path.isdir(DATA_DIR):
        migrated_json = 0
        for filename in os.listdir(DATA_DIR):
            if not filename.endswith(".json"):
                continue
            try:
                user_id = int(filename[:-5])
            except ValueError:
                continue
            try:
                with open(os.path.join(DATA_DIR, filename), "r") as f:
                    data = json.load(f)
                merged = _default_user()
                merged.update({k: v for k, v in data.items() if k in merged})
                await save_user(db, user_id, merged)
                migrated_json += 1
            except Exception:
                continue
        if migrated_json > 0:
            logger.info(f"Successfully migrated {migrated_json} JSON user files.")

    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r") as f:
                config_data = json.load(f)
            for g_id_str, cfg in config_data.items():
                try:
                    guild_id = int(g_id_str)
                    enabled = cfg.get("enabled", True)
                    level_chan = cfg.get("level_channel")
                    await db.execute(
                        """
                        INSERT INTO xp_guild_settings (guild_id, enabled, level_channel)
                        VALUES ($1, $2, $3)
                        ON CONFLICT(guild_id) DO UPDATE SET enabled = EXCLUDED.enabled, level_channel = EXCLUDED.level_channel
                        """,
                        guild_id, enabled, level_chan
                    )
                except ValueError:
                    continue
            logger.info("Successfully migrated guild settings from config.json.")
        except Exception as e:
            logger.error(f"Error migrating config.json: {e}")
    logger.info("Legacy data migration completed!")
