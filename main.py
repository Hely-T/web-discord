from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
import threading
from pathlib import Path

import discord
from discord import app_commands
from discord.ext import commands

import app as web_app
from bot_runtime import runtime as bot_runtime


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
    if hasattr(intents, "members"):
        intents.members = True
    return intents


async def verified_role(guild: discord.Guild) -> discord.Role:
    configured = os.getenv("VERIFY_ROLE_ID", "").strip()
    role = guild.get_role(int(configured)) if configured.isdigit() else None
    role_name = os.getenv("VERIFY_ROLE_NAME", "Verified").strip() or "Verified"
    role = role or discord.utils.get(guild.roles, name=role_name)
    if role is None:
        role = await guild.create_role(name=role_name, reason="Bleck Lous verification")
    return role


async def grant_verified(member: discord.Member, source: str = "discord") -> tuple[bool, str]:
    web_app.verify_user(str(member.id), str(member), source)
    try:
        role = await verified_role(member.guild)
        if role not in member.roles:
            await member.add_roles(role, reason="Bleck Lous verified user")
    except discord.Forbidden:
        return False, "Đã lưu xác minh nhưng bot thiếu Manage Roles hoặc role bot đang nằm quá thấp."
    return True, "Xác minh thành công. Bạn đã được cấp quyền truy cập server."


class VerifyView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Verify / Xác minh", style=discord.ButtonStyle.success, custom_id="bleck_lous:verify:v1", emoji="✅")
    async def verify_button(self, interaction: discord.Interaction, _button: discord.ui.Button):
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message("Hãy xác minh trong server Discord.", ephemeral=True)
            return
        ok, message = await grant_verified(interaction.user)
        await interaction.response.send_message(message, ephemeral=True)


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
        bot_runtime.attach(self, asyncio.get_running_loop())
        self.add_view(VerifyView())
        register_verify_commands(self)
        await self.load_archive_cogs()
        try:
            await self.tree.sync()
        except Exception as exc:
            logger.warning("Không sync được slash commands: %s", exc)

    async def close(self):
        bot_runtime.detach(self)
        await super().close()

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

    async def on_member_join(self, member: discord.Member):
        if web_app.is_verified(str(member.id)):
            ok, message = await grant_verified(member, "sync")
            if not ok:
                logger.warning("Không đồng bộ verified role cho %s: %s", member, message)


def register_verify_commands(bot: BleckLousBot) -> None:
    @bot.tree.command(name="verify", description="Xác minh để mở quyền truy cập server")
    async def verify(interaction: discord.Interaction):
        await interaction.response.send_message(
            "Bấm nút bên dưới để xác minh. Trạng thái này được lưu để dùng lại ở server mới.",
            view=VerifyView(), ephemeral=True,
        )

    @bot.tree.command(name="verify-panel", description="Đăng bảng xác minh cho thành viên")
    @app_commands.checks.has_permissions(administrator=True)
    async def verify_panel(interaction: discord.Interaction):
        embed = discord.Embed(
            title="Xác minh thành viên",
            description="Bấm **Verify / Xác minh** để mở quyền xem các kênh.",
            color=discord.Color.green(),
        )
        await interaction.response.send_message(embed=embed, view=VerifyView())

    @bot.tree.command(name="verify-setup", description="Ẩn các kênh cho tới khi thành viên xác minh")
    @app_commands.describe(confirm="Chọn true để xác nhận thay đổi quyền View Channel")
    @app_commands.checks.has_permissions(administrator=True)
    async def verify_setup(interaction: discord.Interaction, confirm: bool = False):
        if not interaction.guild or not interaction.channel:
            await interaction.response.send_message("Lệnh này chỉ dùng trong server.", ephemeral=True)
            return
        if not confirm:
            await interaction.response.send_message(
                "Lệnh này sẽ ẩn toàn bộ kênh khỏi @everyone, trừ kênh hiện tại, và mở chúng cho role Verified. Chạy lại với `confirm: true`.",
                ephemeral=True,
            )
            return
        await interaction.response.defer(ephemeral=True, thinking=True)
        role = await verified_role(interaction.guild)
        changed = 0
        for channel in interaction.guild.channels:
            if channel.id == interaction.channel.id:
                await channel.set_permissions(interaction.guild.default_role, view_channel=True, reason="Verification entry channel")
            else:
                await channel.set_permissions(interaction.guild.default_role, view_channel=False, reason="Verification gate")
                await channel.set_permissions(role, view_channel=True, reason="Verified access")
            changed += 1
        await interaction.followup.send(
            f"Đã bật verification gate cho {changed} kênh. Hãy dùng `/verify-panel` trong kênh hiện tại.", ephemeral=True
        )

    @bot.tree.command(name="verify-sync", description="Đồng bộ role cho toàn bộ user đã xác minh")
    @app_commands.checks.has_permissions(administrator=True)
    async def verify_sync(interaction: discord.Interaction):
        if not interaction.guild:
            await interaction.response.send_message("Lệnh này chỉ dùng trong server.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True, thinking=True)
        updated = 0
        async for member in interaction.guild.fetch_members(limit=None):
            if web_app.is_verified(str(member.id)):
                ok, _ = await grant_verified(member, "sync")
                updated += int(ok)
        await interaction.followup.send(f"Đã đồng bộ role Verified cho {updated} thành viên.", ephemeral=True)


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
