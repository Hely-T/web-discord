from __future__ import annotations

import json
import base64
import binascii
import hashlib
import hmac
import mimetypes
import os
import secrets
import sqlite3
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from bot_runtime import BotRuntimeError, runtime as bot_runtime


BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
STARTED_AT = int(time.time())


def env_path(name: str, default: str) -> str:
    return os.getenv(name, default).strip()


CONFIG = {
    "brand": os.getenv("APP_BRAND", "Bleck Lous"),
    "domain": os.getenv("PUBLIC_DOMAIN", "nasdaq-fx.com"),
    "cash_db": env_path("CASH_DB_PATH", "/opt/bot-discord/database/users.db"),
    "bank_db": env_path("BANK_DB_PATH", "/opt/bot-discord/database/bank_payments.db"),
    "casino_db": env_path("CASINO_DB_PATH", "/opt/casino/database/casino.db"),
    "web_db": env_path("WEB_DB_PATH", str(BASE_DIR / "web.sqlite3")),
    "discord_client_id": os.getenv("DISCORD_CLIENT_ID", ""),
    "discord_client_secret": os.getenv("DISCORD_CLIENT_SECRET", ""),
    "discord_redirect_uri": os.getenv("DISCORD_REDIRECT_URI", ""),
    "discord_oauth_mode": os.getenv("DISCORD_OAUTH_MODE", "implicit").strip().lower(),
    "casino_client_id": os.getenv("CASINO_BOT_CLIENT_ID", ""),
    "general_client_id": os.getenv("GENERAL_BOT_CLIENT_ID", ""),
    "extension_client_id": os.getenv("EXTENSION_BOT_CLIENT_ID", "") or os.getenv("DISCORD_CLIENT_ID", ""),
    "casino_bot_token": os.getenv("CASINO_BOT_TOKEN", "") or os.getenv("CASINO_DISCORD_TOKEN", ""),
    "general_bot_token": os.getenv("GENERAL_BOT_TOKEN", "") or os.getenv("BOT_TONG_TOKEN", "") or os.getenv("GENERAL_DISCORD_TOKEN", ""),
    "rpc_application_id": os.getenv("RPC_APPLICATION_ID", "") or os.getenv("EXTENSION_BOT_CLIENT_ID", "") or os.getenv("DISCORD_CLIENT_ID", ""),
    "bot_permissions": os.getenv("BOT_PERMISSIONS", "8"),
    "admin_password": os.getenv("ADMIN_PASSWORD", ""),
    "contact_url": os.getenv("CONTACT_ADMIN_URL", "https://discord.com"),
    "casino_server_count": os.getenv("CASINO_SERVER_COUNT", ""),
    "general_server_count": os.getenv("GENERAL_SERVER_COUNT", ""),
    "extension_server_count": os.getenv("EXTENSION_SERVER_COUNT", ""),
    "cookie_domain": os.getenv("COOKIE_DOMAIN", ""),
}

ARCHIVE_FEATURES = {
    "source": "archive_bot",
    "summary": "Discord bot source imported from archive-2026-02-12T215354+0100 and connected to the web dashboard.",
    "groups": [
        {
            "name": "Web Bot Control",
            "accent": "cyan",
            "description": "Control the live Discord bot from the authenticated dashboard.",
            "commands": [
                {"name": "Voice room", "aliases": "Web dashboard", "usage": "Dashboard > Treo Voice", "description": "Choose an authorized server and voice room, then join, move, or leave."},
                {"name": "Bot Presence", "aliases": "Admin only", "usage": "Dashboard > Presence / RPC", "description": "Set the bot activity type, text, details, state, stream URL, and status."},
            ],
        },
        {
            "name": "Voice Manager",
            "accent": "cyan",
            "description": "Join/leave voice, auto-reconnect, mic/speaker control, and voice status.",
            "commands": [
                {"name": "$joinvoice", "aliases": "$jv, $join", "usage": "$jv [voice_channel_id]", "description": "Join a voice channel by ID or the channel you are in."},
                {"name": "$leavevoice", "aliases": "$lv, $leave", "usage": "$lv [guild_or_channel_id]", "description": "Leave a specific voice connection or the current one."},
                {"name": "$leaveall", "aliases": "$lvall", "usage": "$lvall", "description": "Disconnect from every voice channel."},
                {"name": "$vcstatus", "aliases": "$vcs", "usage": "$vcs", "description": "Show voice channel, uptime, mic, speaker, reconnect, and latency."},
                {"name": "$mic", "aliases": "$togglemic, $tm", "usage": "$mic [guild_id]", "description": "Toggle self mute."},
                {"name": "$speaker", "aliases": "$togglespeaker, $ts", "usage": "$speaker [guild_id]", "description": "Toggle self deaf."},
                {"name": "$setvoice", "aliases": "$sv", "usage": "$sv off on", "description": "Set mic and speaker state explicitly."},
            ],
        },
        {
            "name": "Spam Tools",
            "accent": "red",
            "description": "Repeat text or random lines from data/spam.txt with delay and stop controls.",
            "commands": [
                {"name": "$spam", "aliases": "", "usage": "$spam [channel_id] [delay] <message>", "description": "Send repeated text with random suffix."},
                {"name": "$spamfile", "aliases": "", "usage": "$spamfile [channel_id] [delay]", "description": "Send random lines from archive_bot/data/spam.txt."},
                {"name": "$stopspam", "aliases": "$ss", "usage": "$ss [channel_id]", "description": "Stop one spam task."},
                {"name": "$stopallspam", "aliases": "$ssa", "usage": "$ssa", "description": "Stop all spam tasks."},
            ],
        },
        {
            "name": "Auto Quotes",
            "accent": "pink",
            "description": "Post rotating quote lines from data/quotes.txt to one channel.",
            "commands": [
                {"name": "$quotes", "aliases": "", "usage": "$quotes [channel_id] [delay]", "description": "Start automatic quote posting."},
                {"name": "$stop_quotes", "aliases": "$sq", "usage": "$sq [channel_id]", "description": "Stop quote posting."},
            ],
        },
        {
            "name": "Monitoring",
            "accent": "yellow",
            "description": "Status dashboard for uptime, ping, voice sessions, spam tasks, and quote tasks.",
            "commands": [
                {"name": "$status", "aliases": "$st", "usage": "$status", "description": "Show bot runtime, voice, spam, and quote state."},
            ],
        },
        {
            "name": "Help & Reload",
            "accent": "orange",
            "description": "Command discovery and hot reload for cog files.",
            "commands": [
                {"name": "$help", "aliases": "$h, $menu", "usage": "$help [command_or_group]", "description": "Show all commands or details for one command/group."},
                {"name": "$quickhelp", "aliases": "$qh", "usage": "$quickhelp", "description": "Show common commands."},
                {"name": "$reload", "aliases": "$rl", "usage": "$reload [cog]", "description": "Reload one cog or every cog."},
            ],
        },
    ],
}

SESSIONS: dict[str, dict] = {}
ADMIN_SESSIONS: set[str] = set()
DB_WARNINGS: dict[str, str] = {}
GUILD_COUNT_CACHE: dict[str, tuple[float, int]] = {}
DISCORD_GUILD_COUNT_CACHE: dict[str, tuple[float, int]] = {}


def auth_secret() -> bytes:
    secret = (
        CONFIG["discord_client_secret"]
        or CONFIG["admin_password"]
        or CONFIG["brand"]
        or "bleck-lous-web"
    )
    return secret.encode("utf-8")


def b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def b64url_decode(data: str) -> bytes:
    return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4))


def make_oauth_state(next_view: str) -> str:
    payload = {"next": next_view, "created_at": int(time.time()), "nonce": secrets.token_urlsafe(12)}
    body = b64url_encode(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    sig = hmac.new(auth_secret(), body.encode("ascii"), hashlib.sha256).digest()
    return f"{body}.{b64url_encode(sig)}"


def read_oauth_state(state: str) -> dict:
    try:
        body, sig = state.split(".", 1)
        expected = hmac.new(auth_secret(), body.encode("ascii"), hashlib.sha256).digest()
        if not hmac.compare_digest(b64url_decode(sig), expected):
            raise ValueError("bad signature")
        payload = json.loads(b64url_decode(body).decode("utf-8"))
        if int(time.time()) - int(payload.get("created_at", 0)) > 600:
            raise ValueError("expired")
        next_view = str(payload.get("next", "dashboard"))
        if next_view not in {"dashboard", "control", "admin", "status", "support"}:
            next_view = "dashboard"
        return {"next": next_view}
    except (ValueError, TypeError, json.JSONDecodeError, binascii.Error) as exc:
        print(f"[oauth] invalid state: {exc}")
        return {}


def cookie_domain() -> str:
    configured = CONFIG["cookie_domain"].strip()
    domain = configured or CONFIG["domain"].strip()
    if not domain or domain in {"localhost", "127.0.0.1"} or ":" in domain:
        return ""
    if domain.startswith("www."):
        domain = domain[4:]
    return domain


def cookie_domains() -> list[str]:
    domain = cookie_domain()
    return ["", domain] if domain else [""]


def web_db() -> sqlite3.Connection:
    path = Path(CONFIG["web_db"])
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def init_web_db() -> None:
    with web_db() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS web_users (
                discord_user_id TEXT PRIMARY KEY,
                username TEXT NOT NULL,
                avatar TEXT,
                role TEXT NOT NULL DEFAULT 'user',
                status TEXT NOT NULL DEFAULT 'active',
                banned_at TEXT,
                reset_at TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                last_login_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                login_count INTEGER NOT NULL DEFAULT 1
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS web_user_guilds (
                discord_user_id TEXT NOT NULL,
                guild_id TEXT NOT NULL,
                guild_name TEXT NOT NULL,
                owner INTEGER NOT NULL DEFAULT 0,
                manageable INTEGER NOT NULL DEFAULT 1,
                last_seen_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (discord_user_id, guild_id)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS web_sessions (
                sid TEXT PRIMARY KEY,
                discord_user_id TEXT NOT NULL,
                user_json TEXT NOT NULL,
                guilds_json TEXT NOT NULL,
                created_at INTEGER NOT NULL,
                last_seen_at INTEGER NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS license_keys (
                key TEXT PRIMARY KEY,
                status TEXT NOT NULL DEFAULT 'active',
                note TEXT NOT NULL DEFAULT '',
                max_guilds INTEGER NOT NULL DEFAULT 1,
                duration_days INTEGER NOT NULL DEFAULT 30,
                expires_at TEXT,
                created_by TEXT NOT NULL DEFAULT 'admin',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                revoked_at TEXT
            )
            """
        )
        ensure_column(conn, "web_users", "role", "TEXT NOT NULL DEFAULT 'user'")
        ensure_column(conn, "web_users", "status", "TEXT NOT NULL DEFAULT 'active'")
        ensure_column(conn, "web_users", "banned_at", "TEXT")
        ensure_column(conn, "web_users", "reset_at", "TEXT")
        ensure_column(conn, "license_keys", "duration_days", "INTEGER NOT NULL DEFAULT 30")
        ensure_column(conn, "license_keys", "expires_at", "TEXT")
        ensure_column(conn, "license_keys", "key_type", "TEXT NOT NULL DEFAULT 'bot'")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS topup_requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                discord_user_id TEXT NOT NULL,
                discord_username TEXT NOT NULL,
                amount INTEGER NOT NULL,
                method TEXT NOT NULL DEFAULT 'manual',
                note TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'pending',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                handled_at TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS rental_requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                discord_user_id TEXT NOT NULL,
                discord_username TEXT NOT NULL,
                guild_id TEXT NOT NULL,
                guild_name TEXT NOT NULL,
                plan TEXT NOT NULL DEFAULT 'bot_tong',
                months INTEGER NOT NULL DEFAULT 1,
                note TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'pending',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                handled_at TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS license_claims (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                key TEXT NOT NULL,
                discord_user_id TEXT NOT NULL,
                discord_username TEXT NOT NULL,
                guild_id TEXT NOT NULL,
                guild_name TEXT NOT NULL,
                claimed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(key, guild_id),
                FOREIGN KEY(key) REFERENCES license_keys(key)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS extension_claims (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                key TEXT NOT NULL,
                discord_user_id TEXT NOT NULL,
                discord_username TEXT NOT NULL,
                claimed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(key, discord_user_id),
                FOREIGN KEY(key) REFERENCES license_keys(key)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS verified_users (
                discord_user_id TEXT PRIMARY KEY,
                username TEXT NOT NULL DEFAULT '',
                source TEXT NOT NULL DEFAULT 'discord',
                verified_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                last_seen_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS rpc_profiles (
                discord_user_id TEXT PRIMARY KEY,
                activity_type TEXT NOT NULL DEFAULT 'playing',
                details TEXT NOT NULL DEFAULT '',
                state TEXT NOT NULL DEFAULT '',
                large_image TEXT NOT NULL DEFAULT '',
                large_text TEXT NOT NULL DEFAULT '',
                button_label TEXT NOT NULL DEFAULT '',
                button_url TEXT NOT NULL DEFAULT '',
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS rpc_device_tokens (
                token_hash TEXT PRIMARY KEY,
                discord_user_id TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                last_seen_at TEXT,
                revoked_at TEXT
            )
            """
        )


def ensure_column(conn: sqlite3.Connection, table: str, column: str, ddl: str) -> None:
    columns = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})")}
    if column not in columns:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")


def connect_readonly(path: str) -> sqlite3.Connection | None:
    db_path = Path(path)
    try:
        if not db_path.exists():
            DB_WARNINGS[path] = "not found"
            return None
        uri = f"file:{db_path}?mode=ro"
        conn = sqlite3.connect(uri, uri=True, timeout=5)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA query_only = 1")
        conn.execute("PRAGMA busy_timeout = 5000")
        DB_WARNINGS.pop(path, None)
        return conn
    except (OSError, sqlite3.Error) as exc:
        DB_WARNINGS[path] = f"{type(exc).__name__}: {exc}"
        print(f"[db] read-only open failed for {path}: {exc}", file=sys.stderr)
        return None


def fetch_all(path: str, sql: str, params: tuple = ()) -> list[dict]:
    conn = connect_readonly(path)
    if not conn:
        return []
    try:
        rows = conn.execute(sql, params).fetchall()
        return [dict(row) for row in rows]
    except sqlite3.Error as exc:
        DB_WARNINGS[path] = f"{type(exc).__name__}: {exc}"
        print(f"[db] query failed for {path}: {exc}", file=sys.stderr)
        return []
    finally:
        conn.close()


def fetch_one(path: str, sql: str, params: tuple = ()) -> dict:
    rows = fetch_all(path, sql, params)
    return rows[0] if rows else {}


def table_exists(path: str, table: str) -> bool:
    try:
        row = fetch_one(
            path,
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name = ?",
            (table,),
        )
        return bool(row)
    except Exception as exc:
        DB_WARNINGS[path] = f"{type(exc).__name__}: {exc}"
        print(f"[db] table check failed for {path}: {exc}", file=sys.stderr)
        return False


def unavailable_summary(path: str, **values: object) -> dict:
    payload = {"available": False, **values}
    warning = DB_WARNINGS.get(path)
    if warning:
        payload["error"] = warning
    return payload


def int_value(value: object, default: int = 0) -> int:
    try:
        return int(value or default)
    except (TypeError, ValueError):
        return default


def json_body(handler: BaseHTTPRequestHandler) -> dict:
    size = int(handler.headers.get("Content-Length", "0") or "0")
    if size <= 0:
        return {}
    raw = handler.rfile.read(size).decode("utf-8")
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {}


def post_form(url: str, data: dict) -> dict:
    encoded = urllib.parse.urlencode(data).encode("utf-8")
    request = urllib.request.Request(url, data=encoded, method="POST")
    request.add_header("Content-Type", "application/x-www-form-urlencoded")
    request.add_header("Accept", "application/json")
    request.add_header("User-Agent", "BleckLousVoiceStation/1.0 (https://nasdaq-fx.com)")
    with urllib.request.urlopen(request, timeout=15) as response:
        return json.loads(response.read().decode("utf-8"))


class DiscordAPIError(RuntimeError):
    def __init__(self, status: int, path: str, message: str = "") -> None:
        self.status = int(status)
        self.path = path
        super().__init__(message or f"Discord API trả về HTTP {status} tại {path}")


def discord_get(path: str, token: str) -> dict | list:
    request = urllib.request.Request(f"https://discord.com/api/v10{path}")
    request.add_header("Authorization", f"Bearer {token}")
    request.add_header("Accept", "application/json")
    request.add_header("User-Agent", "BleckLousVoiceStation/1.0 (https://nasdaq-fx.com)")
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        try:
            payload = json.loads(exc.read().decode("utf-8"))
            detail = str(payload.get("message", "")) if isinstance(payload, dict) else ""
        except (UnicodeDecodeError, json.JSONDecodeError):
            detail = ""
        raise DiscordAPIError(exc.code, path, detail) from exc


def invite_url(client_id: str, guild_id: str = "") -> str:
    if not client_id:
        return ""
    params = {
        "client_id": client_id,
        "scope": "bot applications.commands",
        "permissions": CONFIG["bot_permissions"],
    }
    if guild_id:
        params["guild_id"] = guild_id
        params["disable_guild_select"] = "true"
    return "https://discord.com/oauth2/authorize?" + urllib.parse.urlencode(params)


def guild_is_manageable(guild: dict) -> bool:
    permissions = int_value(guild.get("permissions"))
    return bool(guild.get("owner")) or bool(permissions & 0x20)


def owned_guilds(guilds: list[dict]) -> list[dict]:
    return [
        {
            "id": str(guild.get("id", "")),
            "name": guild.get("name", "Unknown Server"),
            "icon": guild.get("icon"),
            "owner": bool(guild.get("owner")),
            "manageable": guild_is_manageable(guild),
        }
        for guild in guilds
        if guild_is_manageable(guild)
    ]


def claims_for_user(discord_user_id: str) -> dict:
    with web_db() as conn:
        rows = conn.execute(
            """
            SELECT c.key, c.guild_id, c.guild_name, c.claimed_at,
                   k.status, k.expires_at
            FROM license_claims c
            JOIN license_keys k ON k.key = c.key
            WHERE c.discord_user_id = ?
              AND k.status = 'active'
              AND (k.expires_at IS NULL OR datetime(k.expires_at) >= datetime('now'))
            """,
            (discord_user_id,),
        ).fetchall()
    return {str(row["guild_id"]): dict(row) for row in rows}


def claims_for_guilds(guild_ids: list[str]) -> dict[str, dict]:
    ids = [str(guild_id) for guild_id in guild_ids if str(guild_id)]
    if not ids:
        return {}
    placeholders = ",".join("?" for _ in ids)
    with web_db() as conn:
        rows = conn.execute(
            f"""
            SELECT c.key, c.guild_id, c.guild_name, c.claimed_at,
                   c.discord_user_id, c.discord_username, k.status, k.expires_at
            FROM license_claims c
            JOIN license_keys k ON k.key = c.key
            WHERE c.guild_id IN ({placeholders})
              AND k.key_type = 'bot'
              AND k.status = 'active'
              AND (k.expires_at IS NULL OR datetime(k.expires_at) >= datetime('now'))
            ORDER BY c.claimed_at DESC
            """,
            tuple(ids),
        ).fetchall()
    return {str(row["guild_id"]): dict(row) for row in rows}


def extension_access_for_user(discord_user_id: str) -> dict | None:
    with web_db() as conn:
        row = conn.execute(
            """
            SELECT c.key, c.claimed_at, k.expires_at
            FROM extension_claims c
            JOIN license_keys k ON k.key = c.key
            WHERE c.discord_user_id = ? AND k.status = 'active'
              AND (k.expires_at IS NULL OR datetime(k.expires_at) >= datetime('now'))
            ORDER BY c.claimed_at DESC LIMIT 1
            """,
            (discord_user_id,),
        ).fetchone()
    return dict(row) if row else None


def rpc_profile_for_user(discord_user_id: str) -> dict:
    with web_db() as conn:
        row = conn.execute(
            "SELECT activity_type, details, state, large_image, large_text, button_label, button_url, updated_at FROM rpc_profiles WHERE discord_user_id = ?",
            (str(discord_user_id),),
        ).fetchone()
    return dict(row) if row else {
        "activity_type": "playing", "details": "Bleck Lous", "state": "nasdaq-fx.com",
        "large_image": "", "large_text": "", "button_label": "", "button_url": "", "updated_at": "",
    }


def rpc_device_payload(raw_token: str) -> dict | None:
    token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
    with web_db() as conn:
        row = conn.execute(
            "SELECT discord_user_id FROM rpc_device_tokens WHERE token_hash = ? AND revoked_at IS NULL",
            (token_hash,),
        ).fetchone()
        if not row or not extension_access_for_user(str(row["discord_user_id"])):
            return None
        conn.execute("UPDATE rpc_device_tokens SET last_seen_at = CURRENT_TIMESTAMP WHERE token_hash = ?", (token_hash,))
    return {
        "application_id": str(CONFIG["rpc_application_id"]),
        "profile": rpc_profile_for_user(str(row["discord_user_id"])),
        "poll_seconds": 15,
    }


def is_verified(discord_user_id: str) -> bool:
    with web_db() as conn:
        return conn.execute(
            "SELECT 1 FROM verified_users WHERE discord_user_id = ?", (str(discord_user_id),)
        ).fetchone() is not None


def verify_user(discord_user_id: str, username: str = "", source: str = "discord") -> None:
    if not str(discord_user_id):
        return
    with web_db() as conn:
        conn.execute(
            """
            INSERT INTO verified_users (discord_user_id, username, source)
            VALUES (?, ?, ?)
            ON CONFLICT(discord_user_id) DO UPDATE SET
                username = excluded.username,
                source = CASE WHEN verified_users.source = 'web' THEN 'web' ELSE excluded.source END,
                last_seen_at = CURRENT_TIMESTAMP
            """,
            (str(discord_user_id), str(username), str(source)),
        )


def web_user_status(discord_user_id: str) -> dict:
    with web_db() as conn:
        row = conn.execute(
            """
            SELECT discord_user_id, username, role, status, banned_at, reset_at
            FROM web_users
            WHERE discord_user_id = ?
            """,
            (discord_user_id,),
        ).fetchone()
    return dict(row) if row else {"role": "user", "status": "active"}


def key_is_expired(row: sqlite3.Row | dict) -> bool:
    expires_at = row["expires_at"] if row else None
    if not expires_at:
        return False
    with web_db() as conn:
        value = conn.execute(
            "SELECT CASE WHEN datetime(?) < datetime('now') THEN 1 ELSE 0 END AS expired",
            (expires_at,),
        ).fetchone()["expired"]
    return bool(value)


def claim_license(
    key: str, user: dict, guild: dict | None = None, expected_type: str = ""
) -> tuple[bool, str]:
    key = key.strip()
    if not key:
        return False, "Bạn chưa nhập key."
    status = web_user_status(str(user.get("id", "")))
    if status.get("status") == "banned":
        return False, "Tài khoản của bạn đã bị khóa trên web."
    with web_db() as conn:
        license_row = conn.execute(
            "SELECT key, status, max_guilds, expires_at, key_type FROM license_keys WHERE key = ?",
            (key,),
        ).fetchone()
        if not license_row or license_row["status"] != "active":
            return False, "Key không tồn tại hoặc đã bị khóa."
        if key_is_expired(license_row):
            return False, "Key đã hết hạn."
        key_type = str(license_row["key_type"] or "bot")
        if expected_type and key_type != expected_type:
            if expected_type == "bot":
                return False, "Đây là key Extension. Hãy nhập key loại Bot để kích hoạt server."
            return False, "Đây là key Bot. Hãy kích hoạt key này tại đúng server bên dưới."
        if key_type == "extension":
            count = conn.execute("SELECT COUNT(*) AS total FROM extension_claims WHERE key = ?", (key,)).fetchone()["total"]
            existing = conn.execute(
                "SELECT id FROM extension_claims WHERE key = ? AND discord_user_id = ?",
                (key, str(user["id"])),
            ).fetchone()
            if not existing and int(count) >= int(license_row["max_guilds"]):
                return False, "Key extension đã dùng hết số tài khoản cho phép."
            conn.execute(
                "INSERT OR IGNORE INTO extension_claims (key, discord_user_id, discord_username) VALUES (?, ?, ?)",
                (key, str(user["id"]), str(user.get("username", ""))),
            )
            return True, "Kích hoạt key extension thành công. RPC đã được mở."
        if not guild:
            return False, "Key bot cần chọn một server để kích hoạt."
        count = conn.execute("SELECT COUNT(*) AS total FROM license_claims WHERE key = ?", (key,)).fetchone()["total"]
        existing = conn.execute(
            """
            SELECT id FROM license_claims
            WHERE key = ? AND guild_id = ?
            """,
            (key, str(guild["id"])),
        ).fetchone()
        if not existing and int(count) >= int(license_row["max_guilds"]):
            return False, "Key đã dùng hết số server cho phép."
        conn.execute(
            """
            INSERT OR IGNORE INTO license_claims
                (key, discord_user_id, discord_username, guild_id, guild_name)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                key,
                str(user["id"]),
                user.get("username", ""),
                str(guild["id"]),
                guild.get("name", ""),
            ),
        )
    return True, "Kích hoạt key thành công."


def admin_keys() -> list[dict]:
    with web_db() as conn:
        rows = conn.execute(
            """
            SELECT
                k.key, k.key_type, k.status, k.note, k.max_guilds, k.duration_days,
                k.expires_at, k.created_at, k.revoked_at,
                COUNT(DISTINCT c.id) + COUNT(DISTINCT e.id) AS used_guilds,
                COALESCE(GROUP_CONCAT(DISTINCT c.discord_username || ' (' || c.guild_name || ')'),
                         GROUP_CONCAT(DISTINCT e.discord_username)) AS used_by
            FROM license_keys k
            LEFT JOIN license_claims c ON c.key = k.key
            LEFT JOIN extension_claims e ON e.key = k.key
            GROUP BY k.key
            ORDER BY k.created_at DESC
            LIMIT 200
            """
        ).fetchall()
    return [dict(row) for row in rows]


def admin_snapshot() -> dict:
    with web_db() as conn:
        users = conn.execute(
            """
            SELECT discord_user_id, username, role, status, banned_at, reset_at,
                   last_login_at, login_count
            FROM web_users
            ORDER BY last_login_at DESC
            LIMIT 100
            """
        ).fetchall()
        verified = conn.execute(
            "SELECT discord_user_id, username, source, verified_at, last_seen_at FROM verified_users ORDER BY verified_at DESC LIMIT 500"
        ).fetchall()
        topups = conn.execute(
            """
            SELECT id, discord_username, amount, status, created_at
            FROM topup_requests
            ORDER BY id DESC
            LIMIT 100
            """
        ).fetchall()
        rentals = conn.execute(
            """
            SELECT id, discord_username, guild_name, months, status, created_at
            FROM rental_requests
            ORDER BY id DESC
            LIMIT 100
            """
        ).fetchall()
    return {
        "keys": admin_keys(),
        "users": [dict(row) for row in users],
        "topups": [dict(row) for row in topups],
        "rentals": [dict(row) for row in rentals],
        "verified": [dict(row) for row in verified],
    }


def save_web_login(user: dict, guilds: list[dict]) -> None:
    discord_user_id = str(user.get("id", ""))
    if not discord_user_id:
        return
    with web_db() as conn:
        conn.execute(
            """
            INSERT INTO web_users (discord_user_id, username, avatar)
            VALUES (?, ?, ?)
            ON CONFLICT(discord_user_id) DO UPDATE SET
                username = excluded.username,
                avatar = excluded.avatar,
                last_login_at = CURRENT_TIMESTAMP,
                login_count = login_count + 1
            """,
            (
                discord_user_id,
                str(user.get("username", "")),
                user.get("avatar"),
            ),
        )
        for guild in guilds:
            conn.execute(
                """
                INSERT INTO web_user_guilds (
                    discord_user_id, guild_id, guild_name, owner, manageable
                )
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(discord_user_id, guild_id) DO UPDATE SET
                    guild_name = excluded.guild_name,
                    owner = excluded.owner,
                    manageable = excluded.manageable,
                    last_seen_at = CURRENT_TIMESTAMP
                """,
                (
                    discord_user_id,
                    str(guild.get("id", "")),
                    str(guild.get("name", "")),
                    1 if guild.get("owner") else 0,
                    1 if guild.get("manageable") else 0,
                ),
            )
    verify_user(discord_user_id, str(user.get("username", "")), "web")
    try:
        bot_runtime.sync_verified_user(discord_user_id)
    except BotRuntimeError:
        # The durable DB record is enough; on_member_join or /verify-sync applies the role later.
        pass


def save_web_session(sid: str, user: dict, guilds: list[dict]) -> None:
    now = int(time.time())
    with web_db() as conn:
        conn.execute(
            """
            INSERT INTO web_sessions (
                sid, discord_user_id, user_json, guilds_json, created_at, last_seen_at
            )
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(sid) DO UPDATE SET
                user_json = excluded.user_json,
                guilds_json = excluded.guilds_json,
                last_seen_at = excluded.last_seen_at
            """,
            (
                sid,
                str(user.get("id", "")),
                json.dumps(user),
                json.dumps(guilds),
                now,
                now,
            ),
        )


def load_web_session(sid: str) -> dict | None:
    if not sid:
        return None
    with web_db() as conn:
        row = conn.execute(
            """
            SELECT user_json, guilds_json
            FROM web_sessions
            WHERE sid = ?
            """,
            (sid,),
        ).fetchone()
        if not row:
            return None
        conn.execute(
            "UPDATE web_sessions SET last_seen_at = ? WHERE sid = ?",
            (int(time.time()), sid),
        )
    try:
        return {
            "user": json.loads(row["user_json"]),
            "guilds": json.loads(row["guilds_json"]),
            "created_at": time.time(),
        }
    except json.JSONDecodeError:
        return None


def delete_web_session(sid: str) -> None:
    if not sid:
        return
    with web_db() as conn:
        conn.execute("DELETE FROM web_sessions WHERE sid = ?", (sid,))


def user_requests(discord_user_id: str) -> dict:
    with web_db() as conn:
        topups = conn.execute(
            """
            SELECT id, amount, method, note, status, created_at
            FROM topup_requests
            WHERE discord_user_id = ?
            ORDER BY id DESC
            LIMIT 8
            """,
            (discord_user_id,),
        ).fetchall()
        rentals = conn.execute(
            """
            SELECT id, guild_id, guild_name, plan, months, note, status, created_at
            FROM rental_requests
            WHERE discord_user_id = ?
            ORDER BY id DESC
            LIMIT 8
            """,
            (discord_user_id,),
        ).fetchall()
    return {
        "topups": [dict(row) for row in topups],
        "rentals": [dict(row) for row in rentals],
    }


def key_public_status(key: str) -> tuple[bool, str, str]:
    key = key.strip()
    if not key:
        return False, "Bạn chưa nhập key.", ""
    with web_db() as conn:
        row = conn.execute(
            "SELECT key, status, max_guilds, expires_at, key_type FROM license_keys WHERE key = ?",
            (key,),
        ).fetchone()
        if not row or row["status"] != "active":
            return False, "Key không tồn tại hoặc đã bị khóa.", ""
        if key_is_expired(row):
            return False, "Key đã hết hạn.", ""
        claim_table = "extension_claims" if row["key_type"] == "extension" else "license_claims"
        used = conn.execute(f"SELECT COUNT(*) AS total FROM {claim_table} WHERE key = ?", (key,)).fetchone()["total"]
    if int(used) >= int(row["max_guilds"]):
        return False, "Key đã dùng hết số server cho phép.", ""
    if row["key_type"] == "extension":
        return True, "Key extension hợp lệ. Hãy đăng nhập web để kích hoạt RPC.", ""
    return True, "Key bot hợp lệ. Bạn có thể mời bot.", invite_url(CONFIG["general_client_id"])


def quote_identifier(identifier: str) -> str:
    return '"' + str(identifier).replace('"', '""') + '"'


def database_guild_count(path: str, ttl_seconds: int = 60) -> int:
    path = str(path or "").strip()
    if not path:
        return 0
    cache_key = f"db:{path}"
    cached = GUILD_COUNT_CACHE.get(cache_key)
    now = time.time()
    if cached and now - cached[0] < ttl_seconds:
        return cached[1]

    conn = connect_readonly(path)
    if not conn:
        return 0

    best = 0
    try:
        tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        for table_row in tables:
            table = str(table_row["name"])
            if table.startswith("sqlite_"):
                continue
            try:
                columns = conn.execute(f"PRAGMA table_info({quote_identifier(table)})").fetchall()
            except sqlite3.Error:
                continue
            for column_row in columns:
                column = str(column_row["name"])
                normalized = column.lower().replace("_", "")
                if normalized not in {"guildid", "serverid"}:
                    continue
                quoted_table = quote_identifier(table)
                quoted_column = quote_identifier(column)
                try:
                    row = conn.execute(
                        f"""
                        SELECT COUNT(DISTINCT CAST({quoted_column} AS TEXT)) AS total
                        FROM {quoted_table}
                        WHERE {quoted_column} IS NOT NULL
                          AND TRIM(CAST({quoted_column} AS TEXT)) != ''
                        """
                    ).fetchone()
                    best = max(best, int_value(row["total"] if row else 0))
                except sqlite3.Error:
                    continue
    finally:
        conn.close()

    GUILD_COUNT_CACHE[cache_key] = (now, best)
    return best


def discord_bot_guild_count(token: str, cache_key: str, ttl_seconds: int = 300) -> int:
    token = str(token or "").strip()
    if not token:
        return 0
    token_key = hashlib.sha256(token.encode("utf-8")).hexdigest()[:16]
    cache_name = f"discord:{cache_key}:{token_key}"
    cached = DISCORD_GUILD_COUNT_CACHE.get(cache_name)
    now = time.time()
    if cached and now - cached[0] < ttl_seconds:
        return cached[1]

    total = 0
    after = ""
    try:
        while True:
            query = {"limit": "200"}
            if after:
                query["after"] = after
            url = "https://discord.com/api/v10/users/@me/guilds?" + urllib.parse.urlencode(query)
            request = urllib.request.Request(
                url,
                headers={
                    "Authorization": f"Bot {token}",
                    "User-Agent": "BleckLousWeb/1.0",
                },
            )
            with urllib.request.urlopen(request, timeout=4) as response:
                payload = json.loads(response.read().decode("utf-8"))
            if not isinstance(payload, list) or not payload:
                break
            total += len(payload)
            if len(payload) < 200:
                break
            after = str(payload[-1].get("id", ""))
            if not after:
                break
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError, OSError, ValueError):
        total = 0

    DISCORD_GUILD_COUNT_CACHE[cache_name] = (now, total)
    return total


def config_count(name: str, fallback: int) -> int:
    raw = str(CONFIG.get(name, "")).strip()
    if not raw:
        return fallback
    value = int_value(raw, fallback)
    return value if value > 0 else fallback


def uptime_seconds() -> int:
    return max(0, int(time.time()) - STARTED_AT)


def status_summary(cash: dict, bank: dict, casino: dict) -> list[dict]:
    general_servers = config_count(
        "general_server_count",
        max(
            licensed_server_count(),
            database_guild_count(CONFIG["cash_db"]),
            discord_bot_guild_count(CONFIG["general_bot_token"], "general"),
        ),
    )
    casino_servers = config_count(
        "casino_server_count",
        max(
            database_guild_count(CONFIG["casino_db"]),
            discord_bot_guild_count(CONFIG["casino_bot_token"], "casino"),
        ),
    )
    extension = extension_runtime_summary()
    return [
        {
            "name": "Casino Bot",
            "state": "operational" if casino["available"] else "database unavailable",
            "online": casino["available"],
            "servers": casino_servers,
            "users": casino["players"],
            "uptime_seconds": uptime_seconds(),
            "accent": "cyan",
        },
        {
            "name": "Bot Tong",
            "state": "operational" if cash["available"] else "database unavailable",
            "online": cash["available"],
            "servers": general_servers,
            "users": cash["users"],
            "uptime_seconds": uptime_seconds(),
            "accent": "red",
        },
        {
            "name": "Extension Bot",
            "state": "operational" if extension["online"] else "offline",
            "online": extension["online"],
            "servers": extension["servers"],
            "users": extension["users"],
            "uptime_seconds": uptime_seconds(),
            "accent": "pink",
        },
    ]


def licensed_server_count() -> int:
    with web_db() as conn:
        row = conn.execute(
            "SELECT COUNT(DISTINCT guild_id) AS total FROM license_claims"
        ).fetchone()
    return int_value(row["total"] if row else 0)


def active_extension_user_count() -> int:
    with web_db() as conn:
        row = conn.execute(
            """
            SELECT COUNT(DISTINCT c.discord_user_id) AS total
            FROM extension_claims c JOIN license_keys k ON k.key=c.key
            WHERE k.status='active' AND (k.expires_at IS NULL OR datetime(k.expires_at)>=datetime('now'))
            """
        ).fetchone()
    return int_value(row["total"] if row else 0)


def extension_runtime_summary() -> dict:
    fallback = {
        "online": False,
        "servers": config_count("extension_server_count", 0),
        "users": active_extension_user_count(),
    }
    try:
        live = bot_runtime.public_status()
        return {
            "online": bool(live.get("online")),
            "servers": int_value(live.get("servers"), fallback["servers"]),
            "users": int_value(live.get("users"), fallback["users"]),
        }
    except BotRuntimeError:
        return fallback


def cash_summary() -> dict:
    if not table_exists(CONFIG["cash_db"], "users"):
        return unavailable_summary(
            CONFIG["cash_db"],
            users=0,
            cash_total=0,
            donate_total=0,
            top=[],
        )

    row = fetch_one(
        CONFIG["cash_db"],
        """
        SELECT
            COUNT(*) AS users,
            COALESCE(SUM(cash), 0) AS cash_total,
            COALESCE(SUM(total_donate), 0) AS donate_total
        FROM users
        """,
    )
    top = fetch_all(
        CONFIG["cash_db"],
        """
        SELECT CAST(user_id AS TEXT) AS user_id, username, cash, level, total_donate, total_hours
        FROM users
        ORDER BY cash DESC
        LIMIT 12
        """,
    )
    return {
        "available": True,
        "users": int_value(row.get("users")),
        "cash_total": int_value(row.get("cash_total")),
        "donate_total": int_value(row.get("donate_total")),
        "top": top,
    }


def bank_summary() -> dict:
    if not table_exists(CONFIG["bank_db"], "bank_payments"):
        return unavailable_summary(
            CONFIG["bank_db"],
            paid=0,
            pending=0,
            paid_amount=0,
            recent=[],
            donate_top=[],
        )

    row = fetch_one(
        CONFIG["bank_db"],
        """
        SELECT
            SUM(CASE WHEN status = 'paid' THEN 1 ELSE 0 END) AS paid,
            SUM(CASE WHEN status = 'pending' THEN 1 ELSE 0 END) AS pending,
            SUM(CASE WHEN status = 'paid' THEN amount ELSE 0 END) AS paid_amount
        FROM bank_payments
        """,
    )
    recent = fetch_all(
        CONFIG["bank_db"],
        """
        SELECT username, kind, amount, status, created_at, paid_at
        FROM bank_payments
        ORDER BY id DESC
        LIMIT 10
        """,
    )
    donate_top = fetch_all(
        CONFIG["bank_db"],
        """
        SELECT username, amount, donate_count, updated_at
        FROM donate_leaderboard
        ORDER BY amount DESC
        LIMIT 8
        """,
    )
    return {
        "available": True,
        "paid": int_value(row.get("paid")),
        "pending": int_value(row.get("pending")),
        "paid_amount": int_value(row.get("paid_amount")),
        "recent": recent,
        "donate_top": donate_top,
    }


def casino_summary() -> dict:
    if not table_exists(CONFIG["casino_db"], "users"):
        return unavailable_summary(
            CONFIG["casino_db"],
            players=0,
            owo_total=0,
            transactions=0,
            top=[],
            games=[],
        )

    users = fetch_one(
        CONFIG["casino_db"],
        "SELECT COUNT(*) AS players, COALESCE(SUM(balance), 0) AS owo_total FROM users",
    )
    tx = fetch_one(
        CONFIG["casino_db"],
        "SELECT COUNT(*) AS transactions FROM transaction_logs",
    )
    top = fetch_all(
        CONFIG["casino_db"],
        """
        SELECT id AS user_id, balance, role, updated_at
        FROM users
        ORDER BY balance DESC
        LIMIT 12
        """,
    )
    games = fetch_all(
        CONFIG["casino_db"],
        """
        SELECT game, SUM(plays) AS plays, SUM(profit) AS profit
        FROM game_history
        GROUP BY game
        ORDER BY plays DESC
        LIMIT 8
        """,
    )
    return {
        "available": True,
        "players": int_value(users.get("players")),
        "owo_total": int_value(users.get("owo_total")),
        "transactions": int_value(tx.get("transactions")),
        "top": top,
        "games": games,
    }


def public_summary() -> dict:
    now = int(time.time())
    cash = cash_summary()
    bank = bank_summary()
    casino = casino_summary()
    return {
        "app": {
            "brand": CONFIG["brand"],
            "domain": CONFIG["domain"],
            "updated_at": now,
            "contact_url": CONFIG["contact_url"],
            "login_enabled": login_enabled(),
            "invites": {
                "general": invite_url(CONFIG["general_client_id"]),
                "casino": invite_url(CONFIG["casino_client_id"]),
                "extension": invite_url(CONFIG["extension_client_id"]),
            },
        },
        "status": status_summary(cash, bank, casino),
        "archive_features": ARCHIVE_FEATURES,
        "cash": cash,
        "bank": bank,
        "casino": casino,
    }


def login_enabled() -> bool:
    required = [CONFIG["discord_client_id"], CONFIG["discord_redirect_uri"]]
    if CONFIG["discord_oauth_mode"] == "code":
        required.append(CONFIG["discord_client_secret"])
    return all(required)


def oauth_next_url(next_view: str) -> str:
    if next_view == "dashboard":
        return "/dashboard"
    if next_view == "control":
        return "/control"
    if next_view == "admin":
        return "/admin"
    if next_view in {"status", "support"}:
        return f"/#{next_view}"
    return "/"


def oauth_error_url(message: str) -> str:
    return "/?" + urllib.parse.urlencode({"login_error": message[:240]})


class Handler(BaseHTTPRequestHandler):
    server_version = "BleckLousWeb/1.0"

    def do_HEAD(self) -> None:
        self.route(send_body=False)

    def do_GET(self) -> None:
        self.route(send_body=True)

    def route(self, send_body: bool) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/auth/login":
            self.handle_login(parsed.query)
            return
        if parsed.path == "/auth/callback":
            if CONFIG["discord_oauth_mode"] == "implicit":
                self.send_file(STATIC_DIR / "oauth-callback.html", send_body=send_body)
            else:
                self.handle_callback(parsed.query)
            return
        if parsed.path == "/auth/logout":
            delete_web_session(self.cookie("bl_session"))
            self.clear_cookie("bl_session")
            return
        if parsed.path == "/api/me":
            self.send_json(self.current_user_payload())
            return
        if parsed.path == "/api/summary":
            self.send_json(public_summary())
            return
        if parsed.path == "/api/archive/features":
            self.send_json(ARCHIVE_FEATURES)
            return
        if parsed.path == "/api/bot/control":
            self.handle_bot_control()
            return
        if parsed.path == "/api/rpc/profile":
            self.handle_rpc_profile()
            return
        if parsed.path == "/api/rpc/device":
            self.handle_rpc_device()
            return
        if parsed.path == "/api/search":
            params = parse_qs(parsed.query)
            query = params.get("q", [""])[0].strip()
            self.send_json({"query": query, "results": search_user(query)})
            return
        if parsed.path == "/api/admin/snapshot":
            self.handle_admin_snapshot()
            return
        if parsed.path == "/admin":
            self.send_file(STATIC_DIR / "admin.html", send_body=send_body)
            return
        if parsed.path in {"/dashboard", "/control"} and not self.current_session():
            next_view = parsed.path.lstrip("/")
            self.redirect(f"/auth/login?next={next_view}")
            return
        if parsed.path in {"/", "/status", "/dashboard", "/control"}:
            self.send_file(STATIC_DIR / "index.html", send_body=send_body)
            return
        safe_path = parsed.path.lstrip("/")
        target = (STATIC_DIR / safe_path).resolve()
        if STATIC_DIR in target.parents and target.exists() and target.is_file():
            self.send_file(target, send_body=send_body)
            return
        self.send_error(HTTPStatus.NOT_FOUND, "Not found")

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/api/key/claim":
            self.handle_claim_key()
            return
        if parsed.path == "/api/key/check":
            self.handle_check_key()
            return
        if parsed.path == "/api/topup/request":
            self.handle_topup_request()
            return
        if parsed.path == "/api/rent/request":
            self.handle_rent_request()
            return
        if parsed.path == "/api/bot/voice":
            self.handle_bot_voice()
            return
        if parsed.path == "/api/bot/presence":
            self.handle_bot_presence()
            return
        if parsed.path == "/api/rpc/profile":
            self.handle_rpc_profile_save()
            return
        if parsed.path == "/api/rpc/device-token":
            self.handle_rpc_device_token()
            return
        if parsed.path == "/api/auth/implicit":
            self.handle_implicit_auth()
            return
        if parsed.path == "/api/admin/login":
            self.handle_admin_login()
            return
        if parsed.path == "/api/admin/keys":
            self.handle_admin_create_key()
            return
        if parsed.path == "/api/admin/revoke":
            self.handle_admin_revoke_key()
            return
        if parsed.path == "/api/admin/key-action":
            self.handle_admin_key_action()
            return
        if parsed.path == "/api/admin/user-action":
            self.handle_admin_user_action()
            return
        self.send_error(HTTPStatus.NOT_FOUND, "Not found")

    def handle_login(self, query: str = "") -> None:
        if not login_enabled():
            self.redirect(oauth_error_url("OAuth chưa được cấu hình trên máy chủ."))
            return
        params_in = parse_qs(query)
        next_view = params_in.get("next", ["dashboard"])[0]
        if next_view not in {"dashboard", "control", "admin", "status", "support"}:
            next_view = "dashboard"
        state = make_oauth_state(next_view)
        params = {
            "client_id": CONFIG["discord_client_id"],
            "redirect_uri": CONFIG["discord_redirect_uri"],
            "response_type": "token" if CONFIG["discord_oauth_mode"] == "implicit" else "code",
            "scope": "identify guilds",
            "state": state,
        }
        self.redirect("https://discord.com/oauth2/authorize?" + urllib.parse.urlencode(params))

    def discord_identity(self, access_token: str) -> tuple[dict, list[dict]]:
        user = discord_get("/users/@me", access_token)
        raw_guilds = discord_get("/users/@me/guilds", access_token)
        if not isinstance(user, dict) or not isinstance(raw_guilds, list):
            raise ValueError("Discord trả về dữ liệu tài khoản không hợp lệ.")
        return user, owned_guilds(raw_guilds)

    def create_web_session(self, user: dict, guilds: list[dict]) -> tuple[str, list[str]]:
        save_web_login(user, guilds)
        sid = secrets.token_urlsafe(32)
        SESSIONS[sid] = {"user": user, "guilds": guilds, "created_at": time.time()}
        save_web_session(sid, user, guilds)
        return sid, self.cookie_values("bl_session", sid, http_only=True)

    def handle_implicit_auth(self) -> None:
        if CONFIG["discord_oauth_mode"] != "implicit" or not login_enabled():
            self.send_json({"ok": False, "message": "Implicit OAuth chưa được bật."})
            return
        body = json_body(self)
        access_token = str(body.get("access_token", "")).strip()
        state_data = read_oauth_state(str(body.get("state", "")).strip())
        if not access_token or not state_data:
            self.send_json({"ok": False, "message": "Phiên Discord OAuth không hợp lệ hoặc đã hết hạn."})
            return
        try:
            user, guilds = self.discord_identity(access_token)
            sid, cookies = self.create_web_session(user, guilds)
        except (KeyError, ValueError, json.JSONDecodeError, sqlite3.Error, OSError, urllib.error.URLError, DiscordAPIError, TimeoutError) as exc:
            print(f"[oauth] implicit login failed: {type(exc).__name__}: {exc}")
            if isinstance(exc, DiscordAPIError) and exc.status == 401:
                message = "Discord access token không hợp lệ hoặc đã hết hạn. Hãy đăng nhập lại."
            elif isinstance(exc, DiscordAPIError) and exc.status == 403:
                message = "Discord từ chối quyền truy cập. Kiểm tra OAuth scope identify + guilds."
            elif isinstance(exc, DiscordAPIError) and exc.path == "/users/@me/guilds":
                message = "Không đọc được danh sách server Discord. OAuth cần scope guilds."
            else:
                message = "Không kết nối được Discord API. Hãy thử đăng nhập lại."
            self.send_json({"ok": False, "message": message})
            return
        next_view = str(state_data.get("next", "control"))
        print(f"[oauth] implicit login ok user={user.get('id', '')} sid={sid[:8]} next={next_view}")
        self.send_json({"ok": True, "next": oauth_next_url(next_view)}, cookies=cookies)

    def handle_callback(self, query: str) -> None:
        params = parse_qs(query)
        discord_error = params.get("error_description", params.get("error", [""]))[0]
        if discord_error:
            self.redirect(oauth_error_url(f"Discord từ chối đăng nhập: {discord_error}"))
            return
        code = params.get("code", [""])[0]
        state = params.get("state", [""])[0]
        state_data = read_oauth_state(state)
        if not code or not state_data:
            print(
                "[oauth] callback rejected "
                f"has_code={bool(code)} has_state={bool(state)} path=/auth/callback"
            )
            self.redirect(oauth_error_url("Phiên đăng nhập đã hết hạn. Hãy thử lại."))
            return
        try:
            token = post_form(
                "https://discord.com/api/oauth2/token",
                {
                    "client_id": CONFIG["discord_client_id"],
                    "client_secret": CONFIG["discord_client_secret"],
                    "grant_type": "authorization_code",
                    "code": code,
                    "redirect_uri": CONFIG["discord_redirect_uri"],
                },
            )
            access_token = token["access_token"]
            user, guilds = self.discord_identity(access_token)
        except (KeyError, ValueError, json.JSONDecodeError, urllib.error.URLError, urllib.error.HTTPError, DiscordAPIError, TimeoutError) as exc:
            print(f"[oauth] callback failed: {type(exc).__name__}: {exc}")
            if isinstance(exc, urllib.error.HTTPError) and exc.code == 401:
                message = "OAuth Client ID hoặc Client Secret không đúng cùng một Discord Application."
            elif isinstance(exc, urllib.error.HTTPError) and exc.code == 400:
                message = "Redirect URI hoặc mã OAuth không khớp cấu hình Discord Developer Portal."
            else:
                message = "Không thể kết nối Discord OAuth. Kiểm tra cấu hình và thử lại."
            self.redirect(oauth_error_url(message))
            return
        sid, cookies = self.create_web_session(user, guilds)
        next_view = str(state_data.get("next", "dashboard"))
        print(
            "[oauth] login ok "
            f"user={user.get('id', '')} sid={sid[:8]} next={next_view} "
            f"cookie_domains={cookie_domains()}"
        )
        self.redirect(
            oauth_next_url(next_view),
            cookies=cookies,
        )

    def current_session(self) -> dict | None:
        sid = self.cookie("bl_session")
        if not sid:
            return None
        session = SESSIONS.get(sid)
        if session:
            return session
        session = load_web_session(sid)
        if session:
            SESSIONS[sid] = session
        return session

    def current_user_payload(self) -> dict:
        session = self.current_session()
        if not session:
            return {
                "logged_in": False,
                "login_enabled": login_enabled(),
                "casino_invite": invite_url(CONFIG["casino_client_id"]),
                "general_invite": invite_url(CONFIG["general_client_id"]),
                "extension_invite": invite_url(CONFIG["extension_client_id"]),
                "guilds": [],
            }
        user = session["user"]
        user_state = web_user_status(str(user.get("id", "")))
        if user_state.get("status") == "banned":
            return {
                "logged_in": False,
                "login_enabled": login_enabled(),
                "banned": True,
                "message": "Tài khoản của bạn đã bị khóa trên web.",
                "casino_invite": invite_url(CONFIG["casino_client_id"]),
                "general_invite": invite_url(CONFIG["general_client_id"]),
                "extension_invite": invite_url(CONFIG["extension_client_id"]),
                "guilds": [],
            }
        claims = claims_for_guilds([str(guild.get("id", "")) for guild in session["guilds"]])
        extension = extension_access_for_user(str(user["id"]))
        guilds = []
        for guild in session["guilds"]:
            claim = claims.get(str(guild["id"]))
            guilds.append(
                {
                    **guild,
                    "has_key": bool(claim),
                    "has_bot_key": bool(claim),
                    "claim": claim,
                    "casino_invite": invite_url(CONFIG["casino_client_id"], str(guild["id"])),
                    "extension_invite": invite_url(CONFIG["extension_client_id"], str(guild["id"])),
                    "general_invite": invite_url(CONFIG["general_client_id"], str(guild["id"]))
                    if claim
                    else "",
                }
            )
        return {
            "logged_in": True,
            "login_enabled": login_enabled(),
            "user": {
                "id": str(user.get("id", "")),
                "username": user.get("username", ""),
                "avatar": user.get("avatar"),
                "role": user_state.get("role", "user"),
                "status": user_state.get("status", "active"),
            },
            "guilds": guilds,
            "extension_access": extension,
            "verified": is_verified(str(user.get("id", ""))),
            "requests": user_requests(str(user.get("id", ""))),
            "casino_invite": invite_url(CONFIG["casino_client_id"]),
            "general_invite": invite_url(CONFIG["general_client_id"]),
            "extension_invite": invite_url(CONFIG["extension_client_id"]),
        }

    def bot_access(self) -> tuple[dict | None, dict, dict[str, dict]]:
        session = self.current_session()
        if not session:
            return None, {}, {}
        user_id = str(session["user"].get("id", ""))
        user_state = web_user_status(user_id)
        if user_state.get("status") == "banned":
            return None, user_state, {}
        claims = claims_for_guilds([str(guild.get("id", "")) for guild in session["guilds"]])
        is_admin = user_state.get("role") == "admin"
        allowed = {
            str(guild["id"]): guild
            for guild in session["guilds"]
            if is_admin or str(guild["id"]) in claims
        }
        return session, user_state, allowed

    def handle_bot_control(self) -> None:
        session, user_state, allowed = self.bot_access()
        if not session:
            self.send_json({"ok": False, "message": "Bạn cần login Discord và tài khoản phải đang hoạt động."})
            return
        try:
            all_guilds = {str(guild["id"]): guild for guild in session["guilds"]}
            snapshot = bot_runtime.snapshot(all_guilds.keys())
        except BotRuntimeError as exc:
            self.send_json({"ok": False, "message": str(exc), "online": False})
            return
        runtime_guilds = {str(item["id"]): item for item in snapshot.get("guilds", [])}
        bot_client_id = str(snapshot.get("user", {}).get("id", "")) or str(CONFIG["general_client_id"])
        snapshot["guilds"] = [
            {
                **runtime_guilds.get(
                    guild_id,
                    {
                        "id": guild_id,
                        "name": str(guild.get("name", "Unknown Server")),
                        "channels": [],
                        "voice_channel_id": "",
                    },
                ),
                "bot_present": guild_id in runtime_guilds,
                "invite_url": invite_url(bot_client_id),
            }
            for guild_id, guild in all_guilds.items()
        ]
        for guild in snapshot["guilds"]:
            guild["licensed"] = str(guild["id"]) in allowed
            guild["has_key"] = guild["licensed"]
        self.send_json(
            {
                "ok": True,
                **snapshot,
                "can_manage_presence": user_state.get("role") == "admin"
                or bool(extension_access_for_user(str(session["user"].get("id", "")))),
            }
        )

    def handle_bot_voice(self) -> None:
        session, _, allowed = self.bot_access()
        if not session:
            self.send_json({"ok": False, "message": "Bạn cần login Discord và tài khoản phải đang hoạt động."})
            return
        body = json_body(self)
        guild_id = str(body.get("guild_id", "")).strip()
        if guild_id not in allowed:
            self.send_json({"ok": False, "message": "Server chưa có key hiệu lực hoặc bạn không có quyền quản lý."})
            return
        action = str(body.get("action", "join")).strip().lower()
        try:
            if action == "join":
                result = bot_runtime.join_voice(guild_id, str(body.get("channel_id", "")).strip())
            elif action == "leave":
                result = bot_runtime.leave_voice(guild_id)
            else:
                self.send_json({"ok": False, "message": "Thao tác voice không hợp lệ."})
                return
        except BotRuntimeError as exc:
            self.send_json({"ok": False, "message": str(exc)})
            return
        self.send_json(result)

    def handle_bot_presence(self) -> None:
        session, user_state, _ = self.bot_access()
        if not session:
            self.send_json({"ok": False, "message": "Bạn cần login Discord."})
            return
        if user_state.get("role") != "admin":
            self.send_json({"ok": False, "message": "Chỉ admin được đổi presence chung của bot."})
            return
        try:
            result = bot_runtime.set_presence(json_body(self))
        except BotRuntimeError as exc:
            self.send_json({"ok": False, "message": str(exc)})
            return
        self.send_json(result)

    def rpc_user(self) -> tuple[dict | None, str]:
        session = self.current_session()
        if not session:
            return None, ""
        user_id = str(session["user"].get("id", ""))
        if web_user_status(user_id).get("status") == "banned":
            return None, ""
        return session, user_id

    def handle_rpc_profile(self) -> None:
        session, user_id = self.rpc_user()
        if not session:
            self.send_json({"ok": False, "message": "Bạn cần login Discord."})
            return
        access = extension_access_for_user(user_id)
        self.send_json({
            "ok": True,
            "enabled": bool(access),
            "application_id": str(CONFIG["rpc_application_id"]),
            "profile": rpc_profile_for_user(user_id),
        })

    def handle_rpc_profile_save(self) -> None:
        session, user_id = self.rpc_user()
        if not session or not extension_access_for_user(user_id):
            self.send_json({"ok": False, "message": "Cần key Extension còn hiệu lực để dùng RPC cá nhân."})
            return
        body = json_body(self)
        activity_type = str(body.get("activity_type", "playing")).strip().lower()
        if activity_type not in {"playing", "listening", "watching", "competing"}:
            activity_type = "playing"
        values = (
            activity_type,
            str(body.get("details", "")).strip()[:128],
            str(body.get("state", "")).strip()[:128],
            str(body.get("large_image", "")).strip()[:256],
            str(body.get("large_text", "")).strip()[:128],
            str(body.get("button_label", "")).strip()[:32],
            str(body.get("button_url", "")).strip()[:500],
        )
        if values[6] and not values[6].startswith(("https://", "http://")):
            self.send_json({"ok": False, "message": "URL nút RPC không hợp lệ."})
            return
        with web_db() as conn:
            conn.execute(
                """
                INSERT INTO rpc_profiles (discord_user_id, activity_type, details, state, large_image, large_text, button_label, button_url)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(discord_user_id) DO UPDATE SET
                    activity_type=excluded.activity_type, details=excluded.details, state=excluded.state,
                    large_image=excluded.large_image, large_text=excluded.large_text,
                    button_label=excluded.button_label, button_url=excluded.button_url, updated_at=CURRENT_TIMESTAMP
                """,
                (user_id, *values),
            )
        self.send_json({"ok": True, "message": "Đã lưu cấu hình RPC cá nhân.", "profile": rpc_profile_for_user(user_id)})

    def handle_rpc_device_token(self) -> None:
        session, user_id = self.rpc_user()
        if not session or not extension_access_for_user(user_id):
            self.send_json({"ok": False, "message": "Cần key Extension còn hiệu lực."})
            return
        raw_token = "blrpc_" + secrets.token_urlsafe(32)
        token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
        with web_db() as conn:
            conn.execute("UPDATE rpc_device_tokens SET revoked_at=CURRENT_TIMESTAMP WHERE discord_user_id=? AND revoked_at IS NULL", (user_id,))
            conn.execute("INSERT INTO rpc_device_tokens (token_hash, discord_user_id) VALUES (?, ?)", (token_hash, user_id))
        self.send_json({
            "ok": True,
            "token": raw_token,
            "command": f"python3 rpc_companion.py --server https://{CONFIG['domain']} --token {raw_token}",
            "commands": {
                "mac": f"curl -O https://{CONFIG['domain']}/rpc_companion.py\npython3 rpc_companion.py --server https://{CONFIG['domain']} --token {raw_token}",
                "windows": f"Invoke-WebRequest https://{CONFIG['domain']}/rpc_companion.py -OutFile rpc_companion.py\npy rpc_companion.py --server https://{CONFIG['domain']} --token {raw_token}",
            },
        })

    def handle_rpc_device(self) -> None:
        authorization = str(self.headers.get("Authorization", ""))
        raw_token = authorization[7:].strip() if authorization.lower().startswith("bearer ") else ""
        payload = rpc_device_payload(raw_token) if raw_token else None
        if not payload:
            self.send_json({"ok": False, "message": "RPC device token không hợp lệ hoặc key đã hết hạn."})
            return
        self.send_json({"ok": True, **payload})

    def handle_claim_key(self) -> None:
        session = self.current_session()
        if not session:
            self.send_json({"ok": False, "message": "Bạn cần login Discord trước."})
            return
        if web_user_status(str(session["user"].get("id", ""))).get("status") == "banned":
            self.send_json({"ok": False, "message": "Tài khoản của bạn đã bị khóa trên web."})
            return
        body = json_body(self)
        guild_id = str(body.get("guild_id", ""))
        key = str(body.get("key", ""))
        guild = next((item for item in session["guilds"] if str(item["id"]) == guild_id), None) if guild_id else None
        expected_type = "bot" if guild_id else "extension"
        if guild_id and not guild:
            self.send_json({"ok": False, "message": "Server không hợp lệ hoặc bạn không có quyền quản lý."})
            return
        ok, message = claim_license(key, session["user"], guild, expected_type)
        self.send_json({"ok": ok, "message": message, "me": self.current_user_payload()})

    def handle_check_key(self) -> None:
        body = json_body(self)
        ok, message, url = key_public_status(str(body.get("key", "")))
        self.send_json({"ok": ok, "message": message, "invite_url": url})

    def handle_topup_request(self) -> None:
        session = self.current_session()
        if not session:
            self.send_json({"ok": False, "message": "Bạn cần login Discord trước."})
            return
        if web_user_status(str(session["user"].get("id", ""))).get("status") == "banned":
            self.send_json({"ok": False, "message": "Tài khoản của bạn đã bị khóa trên web."})
            return
        body = json_body(self)
        amount = int_value(body.get("amount"))
        if amount <= 0:
            self.send_json({"ok": False, "message": "Số tiền nạp không hợp lệ."})
            return
        user = session["user"]
        with web_db() as conn:
            conn.execute(
                """
                INSERT INTO topup_requests (
                    discord_user_id, discord_username, amount, method, note
                )
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    str(user.get("id", "")),
                    str(user.get("username", "")),
                    amount,
                    str(body.get("method", "manual")),
                    str(body.get("note", "")).strip(),
                ),
            )
        self.send_json({"ok": True, "message": "Đã gửi yêu cầu nạp tiền.", "me": self.current_user_payload()})

    def handle_rent_request(self) -> None:
        session = self.current_session()
        if not session:
            self.send_json({"ok": False, "message": "Bạn cần login Discord trước."})
            return
        if web_user_status(str(session["user"].get("id", ""))).get("status") == "banned":
            self.send_json({"ok": False, "message": "Tài khoản của bạn đã bị khóa trên web."})
            return
        body = json_body(self)
        guild_id = str(body.get("guild_id", ""))
        guild = next((item for item in session["guilds"] if str(item["id"]) == guild_id), None)
        if not guild:
            self.send_json({"ok": False, "message": "Server không hợp lệ hoặc bạn không có quyền quản lý."})
            return
        months = max(1, min(int_value(body.get("months"), 1), 24))
        user = session["user"]
        with web_db() as conn:
            conn.execute(
                """
                INSERT INTO rental_requests (
                    discord_user_id, discord_username, guild_id, guild_name,
                    plan, months, note
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(user.get("id", "")),
                    str(user.get("username", "")),
                    str(guild.get("id", "")),
                    str(guild.get("name", "")),
                    str(body.get("plan", "bot_tong")),
                    months,
                    str(body.get("note", "")).strip(),
                ),
            )
        self.send_json({"ok": True, "message": "Đã gửi yêu cầu thuê key.", "me": self.current_user_payload()})

    def handle_admin_login(self) -> None:
        body = json_body(self)
        if not CONFIG["admin_password"]:
            self.send_json({"ok": False, "message": "Chưa cấu hình ADMIN_PASSWORD."})
            return
        if str(body.get("password", "")) != CONFIG["admin_password"]:
            self.send_json({"ok": False, "message": "Sai mật khẩu admin."})
            return
        sid = secrets.token_urlsafe(32)
        ADMIN_SESSIONS.add(sid)
        self.send_json(
            {"ok": True, **admin_snapshot()},
            cookies=[self.cookie_value("bl_admin", sid, http_only=True)],
        )

    def is_admin(self) -> bool:
        sid = self.cookie("bl_admin")
        return bool(sid and sid in ADMIN_SESSIONS)

    def handle_admin_snapshot(self) -> None:
        if not self.is_admin():
            self.send_json({"ok": False, "message": "Chưa đăng nhập admin."})
            return
        self.send_json({"ok": True, **admin_snapshot()})

    def handle_admin_create_key(self) -> None:
        if not self.is_admin():
            self.send_json({"ok": False, "message": "Chưa đăng nhập admin."})
            return
        body = json_body(self)
        amount = max(1, min(int_value(body.get("amount"), 1), 100))
        max_guilds = max(1, min(int_value(body.get("max_guilds"), 1), 50))
        duration_days = max(1, min(int_value(body.get("duration_days"), 30), 3650))
        key_type = str(body.get("key_type", "bot")).strip().lower()
        if key_type not in {"bot", "extension"}:
            self.send_json({"ok": False, "message": "Loại key không hợp lệ."})
            return
        note = str(body.get("note", "")).strip()
        created = []
        with web_db() as conn:
            for _ in range(amount):
                key = "BL-" + secrets.token_urlsafe(18).replace("_", "").replace("-", "").upper()[:24]
                conn.execute(
                    """
                    INSERT INTO license_keys (key, key_type, note, max_guilds, duration_days, expires_at)
                    VALUES (?, ?, ?, ?, ?, datetime('now', ?))
                    """,
                    (key, key_type, note, max_guilds, duration_days, f"+{duration_days} days"),
                )
                created.append(key)
        self.send_json({"ok": True, "created": created, **admin_snapshot()})

    def handle_admin_revoke_key(self) -> None:
        if not self.is_admin():
            self.send_json({"ok": False, "message": "Chưa đăng nhập admin."})
            return
        body = json_body(self)
        key = str(body.get("key", "")).strip()
        with web_db() as conn:
            conn.execute(
                """
                UPDATE license_keys
                SET status = 'revoked', revoked_at = CURRENT_TIMESTAMP
                WHERE key = ?
                """,
                (key,),
            )
        self.send_json({"ok": True, **admin_snapshot()})

    def handle_admin_key_action(self) -> None:
        if not self.is_admin():
            self.send_json({"ok": False, "message": "Chưa đăng nhập admin."})
            return
        body = json_body(self)
        key = str(body.get("key", "")).strip()
        action = str(body.get("action", "")).strip()
        days = max(1, min(int_value(body.get("days"), 30), 3650))
        if not key:
            self.send_json({"ok": False, "message": "Thiếu key."})
            return
        with web_db() as conn:
            if action == "lock":
                conn.execute(
                    "UPDATE license_keys SET status = 'revoked', revoked_at = CURRENT_TIMESTAMP WHERE key = ?",
                    (key,),
                )
            elif action == "unlock":
                conn.execute(
                    "UPDATE license_keys SET status = 'active', revoked_at = NULL WHERE key = ?",
                    (key,),
                )
            elif action == "extend":
                conn.execute(
                    """
                    UPDATE license_keys
                    SET expires_at = datetime(CASE
                            WHEN expires_at IS NULL OR datetime(expires_at) < datetime('now')
                            THEN 'now'
                            ELSE expires_at
                        END, ?),
                        duration_days = duration_days + ?
                    WHERE key = ?
                    """,
                    (f"+{days} days", days, key),
                )
            else:
                self.send_json({"ok": False, "message": "Action key không hợp lệ."})
                return
        self.send_json({"ok": True, **admin_snapshot()})

    def handle_admin_user_action(self) -> None:
        if not self.is_admin():
            self.send_json({"ok": False, "message": "Chưa đăng nhập admin."})
            return
        body = json_body(self)
        user_id = str(body.get("user_id", "")).strip()
        action = str(body.get("action", "")).strip()
        role = str(body.get("role", "user")).strip()
        if not user_id:
            self.send_json({"ok": False, "message": "Thiếu user ID."})
            return
        with web_db() as conn:
            if action == "ban":
                conn.execute(
                    "UPDATE web_users SET status = 'banned', banned_at = CURRENT_TIMESTAMP WHERE discord_user_id = ?",
                    (user_id,),
                )
            elif action == "unban":
                conn.execute(
                    "UPDATE web_users SET status = 'active', banned_at = NULL WHERE discord_user_id = ?",
                    (user_id,),
                )
            elif action == "role":
                if role not in {"user", "admin"}:
                    self.send_json({"ok": False, "message": "Role không hợp lệ."})
                    return
                conn.execute(
                    "UPDATE web_users SET role = ? WHERE discord_user_id = ?",
                    (role, user_id),
                )
            elif action == "reset":
                conn.execute("DELETE FROM license_claims WHERE discord_user_id = ?", (user_id,))
                conn.execute("DELETE FROM extension_claims WHERE discord_user_id = ?", (user_id,))
                conn.execute("DELETE FROM rpc_profiles WHERE discord_user_id = ?", (user_id,))
                conn.execute("DELETE FROM rpc_device_tokens WHERE discord_user_id = ?", (user_id,))
                conn.execute("DELETE FROM topup_requests WHERE discord_user_id = ?", (user_id,))
                conn.execute("DELETE FROM rental_requests WHERE discord_user_id = ?", (user_id,))
                conn.execute("DELETE FROM web_user_guilds WHERE discord_user_id = ?", (user_id,))
                conn.execute(
                    """
                    UPDATE web_users
                    SET login_count = 0,
                        reset_at = CURRENT_TIMESTAMP,
                        status = 'active',
                        banned_at = NULL
                    WHERE discord_user_id = ?
                    """,
                    (user_id,),
                )
            else:
                self.send_json({"ok": False, "message": "Action user không hợp lệ."})
                return
        self.send_json({"ok": True, **admin_snapshot()})

    def send_json(self, payload: dict, cookies: list[str] | None = None) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        for cookie in cookies or []:
            self.send_header("Set-Cookie", cookie)
        self.end_headers()
        self.wfile.write(body)

    def send_file(self, path: Path, send_body: bool = True) -> None:
        body = path.read_bytes()
        content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        if path.suffix == ".html":
            content_type = "text/html; charset=utf-8"
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        if path.suffix in {".html", ".js", ".css"}:
            self.send_header("Cache-Control", "no-store, no-cache, must-revalidate")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if send_body:
            self.wfile.write(body)

    def redirect(self, url: str, cookies: list[str] | None = None) -> None:
        self.send_response(HTTPStatus.FOUND)
        self.send_header("Location", url)
        for cookie in cookies or []:
            self.send_header("Set-Cookie", cookie)
        self.end_headers()

    def cookie(self, name: str) -> str:
        cookie_header = self.headers.get("Cookie", "")
        found = ""
        for chunk in cookie_header.split(";"):
            if "=" not in chunk:
                continue
            key, value = chunk.strip().split("=", 1)
            if key == name:
                found = value
        return found

    def cookie_values(self, name: str, value: str, http_only: bool = False) -> list[str]:
        return [
            self.cookie_value(name, value, http_only=http_only, domain=domain)
            for domain in cookie_domains()
        ]

    def cookie_value(
        self,
        name: str,
        value: str,
        http_only: bool = False,
        domain: str = "",
    ) -> str:
        parts = [f"{name}={value}", "Path=/", "Max-Age=2592000", "SameSite=Lax"]
        if domain:
            parts.append(f"Domain=.{domain}")
        if CONFIG["discord_redirect_uri"].startswith("https://"):
            parts.append("Secure")
        if http_only:
            parts.append("HttpOnly")
        return "; ".join(parts)

    def clear_cookie(self, name: str) -> None:
        self.send_response(HTTPStatus.FOUND)
        self.send_header("Location", "/")
        for domain in cookie_domains():
            parts = [f"{name}=", "Path=/", "Max-Age=0", "SameSite=Lax"]
            if domain:
                parts.append(f"Domain=.{domain}")
            if CONFIG["discord_redirect_uri"].startswith("https://"):
                parts.append("Secure")
            self.send_header("Set-Cookie", "; ".join(parts))
        self.end_headers()

    def log_message(self, fmt: str, *args: object) -> None:
        print("[%s] %s" % (self.log_date_time_string(), fmt % args))


def search_user(query: str) -> list[dict]:
    if len(query) < 3 or not table_exists(CONFIG["cash_db"], "users"):
        return []
    like = f"%{query}%"
    return fetch_all(
        CONFIG["cash_db"],
        """
        SELECT CAST(user_id AS TEXT) AS user_id, username, cash, level, total_donate, total_hours
        FROM users
        WHERE CAST(user_id AS TEXT) LIKE ? OR username LIKE ?
        ORDER BY cash DESC
        LIMIT 10
        """,
        (like, like),
    )


def make_server() -> ThreadingHTTPServer:
    init_web_db()
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "8088"))
    return ThreadingHTTPServer((host, port), Handler)


def serve(server: ThreadingHTTPServer) -> None:
    host, port = server.server_address
    print(f"{CONFIG['brand']} web listening on http://{host}:{port}")
    server.serve_forever()


def start_background() -> ThreadingHTTPServer:
    server = make_server()
    thread = threading.Thread(target=serve, args=(server,), daemon=True)
    thread.start()
    return server


def run() -> None:
    serve(make_server())


if __name__ == "__main__":
    run()
