from __future__ import annotations

import json
import logging
import os
import sys
import threading
from pathlib import Path

import discord
from discord.ext import commands

import app as web_app


BASE_DIR = Path(__file__).resolve().parent
ARCHIVE_DIR = BASE_DIR / "archive_bot"
COGS_DIR = ARCHIVE_DIR / "cogs"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("BleckLousMain")
logging.getLogger("discord").setLevel(logging.ERROR)


class NormalDiscordReconnectFilter(logging.Filter):
    """Hide only Discord's expected clean-close reconnect traceback."""

    def filter(self, record: logging.LogRecord) -> bool:
        if record.name != "discord.client" or not record.getMessage().startswith("Attempting a reconnect in"):
            return True
        exc_info = record.exc_info
        exc = exc_info[1] if isinstance(exc_info, tuple) else exc_info
        return not isinstance(exc, discord.ConnectionClosed) or getattr(exc, "code", None) != 1000


logging.getLogger("discord.client").addFilter(NormalDiscordReconnectFilter())


def load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning("Không đọc được config bot %s: %s", path, exc)
        return {}


def bot_config() -> dict:
    config_path = Path(os.getenv("BOT_CONFIG_PATH", str(ARCHIVE_DIR / "config.json")))
    config = load_json(config_path)
    config["token"] = os.getenv("DISCORD_TOKEN") or os.getenv("BOT_TOKEN") or config.get("token", "")
    config["prefix"] = os.getenv("BOT_PREFIX") or config.get("prefix", "$")
    return config


def discord_intents():
    intents_factory = getattr(discord, "Intents", None)
    if not intents_factory:
        return None
    intents = intents_factory.default()
    if hasattr(intents, "message_content"):
        intents.message_content = True
    if hasattr(intents, "voice_states"):
        intents.voice_states = True
    return intents


class BleckLousBot(commands.Bot):
    def __init__(self, config: dict):
        self.config = config
        kwargs = {
            "command_prefix": config.get("prefix", "$"),
            "help_command": None,
            "case_insensitive": True,
        }
        intents = discord_intents()
        if intents is not None:
            kwargs["intents"] = intents
        super().__init__(**kwargs)

    async def setup_hook(self):
        await self.load_archive_cogs()

    async def on_ready(self):
        logger.info(
            "BOT ONLINE: %s | ID: %s | Prefix: %s | Web: running",
            self.user.name,
            self.user.id,
            self.command_prefix,
        )

    async def on_disconnect(self):
        logger.warning("Discord gateway tạm ngắt kết nối; bot đang tự reconnect.")

    async def on_resumed(self):
        logger.info("Discord gateway đã reconnect thành công.")

    async def load_archive_cogs(self):
        if not COGS_DIR.exists():
            logger.warning("Không thấy thư mục cogs: %s", COGS_DIR)
            return
        for file in sorted(COGS_DIR.glob("*.py")):
            if file.name.startswith("_"):
                continue
            extension = f"archive_bot.cogs.{file.stem}"
            try:
                await self.load_extension(extension)
                logger.info("Loaded cog: %s", file.stem)
            except Exception as exc:
                logger.error("Lỗi load cog %s: %s", file.stem, exc)

    async def on_error(self, event, *args, **kwargs):
        exc_type, exc_value, _ = sys.exc_info()
        if exc_type and exc_type.__name__ == "AttributeError" and "_MissingSentinel" in str(exc_value):
            logger.debug("Ignored voice protocol error: %s", exc_value)
            return
        logger.error("Error in %s: %s: %s", event, getattr(exc_type, "__name__", "Error"), exc_value)

    async def on_voice_state_update(self, member, before, after):
        if not self.user or member.id != self.user.id:
            return
        if before.channel and not after.channel:
            logger.warning("Bot bị disconnect từ %s", before.channel.name)


def register_reload_command(bot: BleckLousBot) -> None:
    @bot.command(name="reload", aliases=["rl"])
    async def reload_cog(ctx, cog_name: str = None):
        try:
            await ctx.message.delete()
        except Exception:
            pass

        targets = [cog_name] if cog_name else [
            file.stem for file in sorted(COGS_DIR.glob("*.py")) if not file.name.startswith("_")
        ]
        reloaded = []
        for name in targets:
            extension = f"archive_bot.cogs.{name}"
            try:
                await bot.reload_extension(extension)
                reloaded.append(name)
            except Exception as exc:
                logger.error("Failed to reload %s: %s", extension, exc)
        if reloaded:
            await ctx.send(f"Reloaded: {', '.join(reloaded)}", delete_after=5)
        else:
            await ctx.send("Không có cog nào được reload.", delete_after=5)


def run_bot(config: dict) -> None:
    token = str(config.get("token", "")).strip()
    if not token:
        logger.warning("Không có DISCORD_TOKEN/BOT_TOKEN hoặc archive_bot/config.json. Chỉ chạy web.")
        web_app.run()
        return

    web_app.start_background()
    bot = BleckLousBot(config)
    register_reload_command(bot)
    try:
        bot.run(token, log_handler=None)
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
        raise
    except Exception as exc:
        logger.critical(
            "Bot bị tắt đột ngột: %s. Web vẫn tiếp tục chạy; kiểm tra DISCORD_TOKEN nếu muốn bật voice bot.",
            exc,
        )

    logger.warning("Discord bot đã dừng, giữ web dashboard tiếp tục chạy.")
    threading.Event().wait()


def main() -> None:
    run_bot(bot_config())


if __name__ == "__main__":
    main()
