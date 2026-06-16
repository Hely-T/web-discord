from __future__ import annotations

import json
import mimetypes
import os
import secrets
import sqlite3
import time
import urllib.error
import urllib.parse
import urllib.request
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse


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
    "casino_client_id": os.getenv("CASINO_BOT_CLIENT_ID", ""),
    "general_client_id": os.getenv("GENERAL_BOT_CLIENT_ID", ""),
    "bot_permissions": os.getenv("BOT_PERMISSIONS", "8"),
    "admin_password": os.getenv("ADMIN_PASSWORD", ""),
    "contact_url": os.getenv("CONTACT_ADMIN_URL", "https://discord.com"),
    "casino_server_count": os.getenv("CASINO_SERVER_COUNT", ""),
    "general_server_count": os.getenv("GENERAL_SERVER_COUNT", ""),
}

SESSIONS: dict[str, dict] = {}
OAUTH_STATES: dict[str, dict] = {}
ADMIN_SESSIONS: set[str] = set()


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


def ensure_column(conn: sqlite3.Connection, table: str, column: str, ddl: str) -> None:
    columns = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})")}
    if column not in columns:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")


def connect_readonly(path: str) -> sqlite3.Connection | None:
    db_path = Path(path)
    try:
        if not db_path.exists():
            return None
        uri = f"file:{db_path}?mode=ro"
        conn = sqlite3.connect(uri, uri=True, timeout=5)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA query_only = 1")
        conn.execute("PRAGMA busy_timeout = 5000")
        return conn
    except (OSError, sqlite3.Error):
        return None


def fetch_all(path: str, sql: str, params: tuple = ()) -> list[dict]:
    conn = connect_readonly(path)
    if not conn:
        return []
    try:
        rows = conn.execute(sql, params).fetchall()
        return [dict(row) for row in rows]
    except sqlite3.Error:
        return []
    finally:
        conn.close()


def fetch_one(path: str, sql: str, params: tuple = ()) -> dict:
    rows = fetch_all(path, sql, params)
    return rows[0] if rows else {}


def table_exists(path: str, table: str) -> bool:
    row = fetch_one(
        path,
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table,),
    )
    return bool(row)


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
    with urllib.request.urlopen(request, timeout=15) as response:
        return json.loads(response.read().decode("utf-8"))


def discord_get(path: str, token: str) -> dict | list:
    request = urllib.request.Request(f"https://discord.com/api{path}")
    request.add_header("Authorization", f"Bearer {token}")
    request.add_header("Accept", "application/json")
    with urllib.request.urlopen(request, timeout=15) as response:
        return json.loads(response.read().decode("utf-8"))


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
            SELECT key, guild_id, guild_name, claimed_at
            FROM license_claims
            WHERE discord_user_id = ?
            """,
            (discord_user_id,),
        ).fetchall()
    return {str(row["guild_id"]): dict(row) for row in rows}


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


def claim_license(key: str, user: dict, guild: dict) -> tuple[bool, str]:
    key = key.strip()
    if not key:
        return False, "Bạn chưa nhập key."
    status = web_user_status(str(user.get("id", "")))
    if status.get("status") == "banned":
        return False, "Tài khoản của bạn đã bị khóa trên web."
    with web_db() as conn:
        license_row = conn.execute(
            "SELECT key, status, max_guilds, expires_at FROM license_keys WHERE key = ?",
            (key,),
        ).fetchone()
        if not license_row or license_row["status"] != "active":
            return False, "Key không tồn tại hoặc đã bị khóa."
        if key_is_expired(license_row):
            return False, "Key đã hết hạn."
        count = conn.execute(
            "SELECT COUNT(*) AS total FROM license_claims WHERE key = ?",
            (key,),
        ).fetchone()["total"]
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
                k.key, k.status, k.note, k.max_guilds, k.duration_days,
                k.expires_at, k.created_at, k.revoked_at,
                COUNT(c.id) AS used_guilds,
                GROUP_CONCAT(c.discord_username || ' (' || c.guild_name || ')', ', ') AS used_by
            FROM license_keys k
            LEFT JOIN license_claims c ON c.key = k.key
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
            "SELECT key, status, max_guilds, expires_at FROM license_keys WHERE key = ?",
            (key,),
        ).fetchone()
        if not row or row["status"] != "active":
            return False, "Key không tồn tại hoặc đã bị khóa.", ""
        if key_is_expired(row):
            return False, "Key đã hết hạn.", ""
        used = conn.execute(
            "SELECT COUNT(*) AS total FROM license_claims WHERE key = ?",
            (key,),
        ).fetchone()["total"]
    if int(used) >= int(row["max_guilds"]):
        return False, "Key đã dùng hết số server cho phép.", ""
    return True, "Key hợp lệ. Bạn có thể invite bot tổng.", invite_url(CONFIG["general_client_id"])


def config_count(name: str, fallback: int) -> int:
    raw = str(CONFIG.get(name, "")).strip()
    if not raw:
        return fallback
    return int_value(raw, fallback)


def uptime_seconds() -> int:
    return max(0, int(time.time()) - STARTED_AT)


def status_summary(cash: dict, bank: dict, casino: dict) -> list[dict]:
    general_servers = config_count("general_server_count", licensed_server_count())
    casino_servers = config_count("casino_server_count", 0)
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
            "name": "Payment/Key",
            "state": "operational" if bank["available"] else "manual mode",
            "online": bank["available"],
            "servers": general_servers,
            "users": bank["paid"] + bank["pending"],
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


def cash_summary() -> dict:
    if not table_exists(CONFIG["cash_db"], "users"):
        return {
            "available": False,
            "users": 0,
            "cash_total": 0,
            "donate_total": 0,
            "top": [],
        }

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
        return {
            "available": False,
            "paid": 0,
            "pending": 0,
            "paid_amount": 0,
            "recent": [],
            "donate_top": [],
        }

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
        return {
            "available": False,
            "players": 0,
            "owo_total": 0,
            "transactions": 0,
            "top": [],
            "games": [],
        }

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
            "login_enabled": bool(
                CONFIG["discord_client_id"]
                and CONFIG["discord_client_secret"]
                and CONFIG["discord_redirect_uri"]
            ),
        },
        "status": status_summary(cash, bank, casino),
        "cash": cash,
        "bank": bank,
        "casino": casino,
    }


class Handler(BaseHTTPRequestHandler):
    server_version = "BleckLousWeb/1.0"

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/auth/login":
            self.handle_login(parsed.query)
            return
        if parsed.path == "/auth/callback":
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
        if parsed.path == "/api/search":
            params = parse_qs(parsed.query)
            query = params.get("q", [""])[0].strip()
            self.send_json({"query": query, "results": search_user(query)})
            return
        if parsed.path == "/api/admin/snapshot":
            self.handle_admin_snapshot()
            return
        if parsed.path == "/admin":
            self.send_file(STATIC_DIR / "admin.html")
            return
        if parsed.path in {"/", "/status", "/dashboard"}:
            self.send_file(STATIC_DIR / "index.html")
            return
        safe_path = parsed.path.lstrip("/")
        target = (STATIC_DIR / safe_path).resolve()
        if STATIC_DIR in target.parents and target.exists() and target.is_file():
            self.send_file(target)
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
        if not public_summary()["app"]["login_enabled"]:
            self.redirect("/")
            return
        params_in = parse_qs(query)
        next_view = params_in.get("next", ["dashboard"])[0]
        if next_view not in {"dashboard", "admin", "status", "support"}:
            next_view = "dashboard"
        state = secrets.token_urlsafe(24)
        OAUTH_STATES[state] = {"created_at": time.time(), "next": next_view}
        params = {
            "client_id": CONFIG["discord_client_id"],
            "redirect_uri": CONFIG["discord_redirect_uri"],
            "response_type": "code",
            "scope": "identify guilds",
            "state": state,
        }
        self.redirect("https://discord.com/oauth2/authorize?" + urllib.parse.urlencode(params))

    def handle_callback(self, query: str) -> None:
        params = parse_qs(query)
        code = params.get("code", [""])[0]
        state = params.get("state", [""])[0]
        if not code or state not in OAUTH_STATES:
            self.redirect("/?login=failed")
            return
        state_data = OAUTH_STATES.pop(state, {"next": "dashboard"})
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
            user = discord_get("/users/@me", access_token)
            guilds = owned_guilds(discord_get("/users/@me/guilds", access_token))
        except (KeyError, urllib.error.URLError, urllib.error.HTTPError, TimeoutError):
            self.redirect("/?login=failed")
            return
        save_web_login(user, guilds)
        sid = secrets.token_urlsafe(32)
        SESSIONS[sid] = {"user": user, "guilds": guilds, "created_at": time.time()}
        save_web_session(sid, user, guilds)
        next_view = str(state_data.get("next", "dashboard"))
        self.redirect(f"/#{next_view}", cookies=[self.cookie_value("bl_session", sid, http_only=True)])

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
                "casino_invite": invite_url(CONFIG["casino_client_id"]),
                "general_invite": "",
                "guilds": [],
            }
        user = session["user"]
        user_state = web_user_status(str(user.get("id", "")))
        if user_state.get("status") == "banned":
            return {
                "logged_in": False,
                "banned": True,
                "message": "Tài khoản của bạn đã bị khóa trên web.",
                "casino_invite": invite_url(CONFIG["casino_client_id"]),
                "general_invite": "",
                "guilds": [],
            }
        claims = claims_for_user(str(user["id"]))
        guilds = []
        for guild in session["guilds"]:
            claim = claims.get(str(guild["id"]))
            guilds.append(
                {
                    **guild,
                    "has_key": bool(claim),
                    "claim": claim,
                    "casino_invite": invite_url(CONFIG["casino_client_id"], str(guild["id"])),
                    "general_invite": invite_url(CONFIG["general_client_id"], str(guild["id"]))
                    if claim
                    else "",
                }
            )
        return {
            "logged_in": True,
            "user": {
                "id": str(user.get("id", "")),
                "username": user.get("username", ""),
                "avatar": user.get("avatar"),
                "role": user_state.get("role", "user"),
                "status": user_state.get("status", "active"),
            },
            "guilds": guilds,
            "requests": user_requests(str(user.get("id", ""))),
            "casino_invite": invite_url(CONFIG["casino_client_id"]),
            "general_invite": "",
        }

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
        guild = next((item for item in session["guilds"] if str(item["id"]) == guild_id), None)
        if not guild:
            self.send_json({"ok": False, "message": "Server không hợp lệ hoặc bạn không có quyền quản lý."})
            return
        ok, message = claim_license(key, session["user"], guild)
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
        note = str(body.get("note", "")).strip()
        created = []
        with web_db() as conn:
            for _ in range(amount):
                key = "BL-" + secrets.token_urlsafe(18).replace("_", "").replace("-", "").upper()[:24]
                conn.execute(
                    """
                    INSERT INTO license_keys (key, note, max_guilds, duration_days, expires_at)
                    VALUES (?, ?, ?, ?, datetime('now', ?))
                    """,
                    (key, note, max_guilds, duration_days, f"+{duration_days} days"),
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

    def send_file(self, path: Path) -> None:
        body = path.read_bytes()
        content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        if path.suffix == ".html":
            content_type = "text/html; charset=utf-8"
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def redirect(self, url: str, cookies: list[str] | None = None) -> None:
        self.send_response(HTTPStatus.FOUND)
        self.send_header("Location", url)
        for cookie in cookies or []:
            self.send_header("Set-Cookie", cookie)
        self.end_headers()

    def cookie(self, name: str) -> str:
        cookie_header = self.headers.get("Cookie", "")
        for chunk in cookie_header.split(";"):
            if "=" not in chunk:
                continue
            key, value = chunk.strip().split("=", 1)
            if key == name:
                return value
        return ""

    def cookie_value(self, name: str, value: str, http_only: bool = False) -> str:
        parts = [f"{name}={value}", "Path=/", "SameSite=Lax"]
        if http_only:
            parts.append("HttpOnly")
        return "; ".join(parts)

    def clear_cookie(self, name: str) -> None:
        self.send_response(HTTPStatus.FOUND)
        self.send_header("Location", "/")
        self.send_header("Set-Cookie", f"{name}=; Path=/; Max-Age=0; SameSite=Lax")
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


def run() -> None:
    init_web_db()
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "8088"))
    server = ThreadingHTTPServer((host, port), Handler)
    print(f"{CONFIG['brand']} web listening on http://{host}:{port}")
    server.serve_forever()


if __name__ == "__main__":
    run()
