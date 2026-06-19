from __future__ import annotations

import asyncio
import datetime
import threading
from collections.abc import Awaitable, Callable, Iterable
from concurrent.futures import TimeoutError as FutureTimeoutError

import discord


class BotRuntimeError(RuntimeError):
    pass


class BotRuntime:
    def __init__(self) -> None:
        self._bot = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._lock = threading.Lock()

    def attach(self, bot, loop: asyncio.AbstractEventLoop) -> None:
        with self._lock:
            self._bot = bot
            self._loop = loop

    def detach(self, bot) -> None:
        with self._lock:
            if self._bot is bot:
                self._bot = None
                self._loop = None

    def call(self, operation: Callable[[object], Awaitable[dict]], timeout: float = 25.0) -> dict:
        with self._lock:
            bot = self._bot
            loop = self._loop
        if bot is None or loop is None or loop.is_closed():
            raise BotRuntimeError("Bot Discord chưa sẵn sàng.")
        future = asyncio.run_coroutine_threadsafe(operation(bot), loop)
        try:
            return future.result(timeout=timeout)
        except FutureTimeoutError as exc:
            future.cancel()
            raise BotRuntimeError("Bot Discord phản hồi quá lâu.") from exc
        except BotRuntimeError:
            raise
        except Exception as exc:
            raise BotRuntimeError(str(exc) or type(exc).__name__) from exc

    def snapshot(self, guild_ids: Iterable[str]) -> dict:
        allowed = {str(item) for item in guild_ids}
        return self.call(lambda bot: self._snapshot(bot, allowed), timeout=10.0)

    def join_voice(self, guild_id: str, channel_id: str) -> dict:
        return self.call(lambda bot: self._join_voice(bot, guild_id, channel_id), timeout=30.0)

    def leave_voice(self, guild_id: str) -> dict:
        return self.call(lambda bot: self._leave_voice(bot, guild_id), timeout=15.0)

    def set_presence(self, payload: dict) -> dict:
        return self.call(lambda bot: self._set_presence(bot, payload), timeout=10.0)

    @staticmethod
    def _activity_payload(activity) -> dict:
        if activity is None:
            return {"type": "none", "name": "", "details": "", "state": "", "url": ""}
        activity_type = getattr(getattr(activity, "type", None), "name", "playing")
        return {
            "type": activity_type,
            "name": getattr(activity, "name", "") or "",
            "details": getattr(activity, "details", "") or "",
            "state": getattr(activity, "state", "") or "",
            "url": getattr(activity, "url", "") or "",
        }

    async def _snapshot(self, bot, allowed: set[str]) -> dict:
        guilds = []
        connections = []
        for guild_id in sorted(allowed):
            if not guild_id.isdigit():
                continue
            guild = bot.get_guild(int(guild_id))
            if guild is None:
                continue
            voice_client = guild.voice_client
            channels = []
            for channel in sorted(guild.voice_channels, key=lambda item: (item.position, item.id)):
                permissions = channel.permissions_for(guild.me) if guild.me else None
                if permissions and not permissions.connect:
                    continue
                channels.append(
                    {
                        "id": str(channel.id),
                        "name": channel.name,
                        "members": len(channel.members),
                    }
                )
            guilds.append(
                {
                    "id": str(guild.id),
                    "name": guild.name,
                    "channels": channels,
                    "voice_channel_id": str(voice_client.channel.id) if voice_client else "",
                }
            )
            if voice_client:
                connections.append(
                    {
                        "guild_id": str(guild.id),
                        "guild_name": guild.name,
                        "channel_id": str(voice_client.channel.id),
                        "channel_name": voice_client.channel.name,
                        "latency_ms": round(voice_client.latency * 1000),
                    }
                )
        return {
            "online": bool(bot.is_ready()),
            "user": {
                "id": str(bot.user.id) if bot.user else "",
                "name": str(bot.user) if bot.user else "Discord bot",
            },
            "latency_ms": round(bot.latency * 1000) if bot.is_ready() else 0,
            "guilds": guilds,
            "connections": connections,
            "presence": {
                **self._activity_payload(getattr(bot, "activity", None)),
                "status": str(getattr(bot, "status", "offline")),
            },
        }

    @staticmethod
    def _voice_cog(bot):
        return bot.get_cog("Voice")

    async def _join_voice(self, bot, guild_id: str, channel_id: str) -> dict:
        if not guild_id.isdigit() or not channel_id.isdigit():
            raise BotRuntimeError("Server hoặc phòng voice không hợp lệ.")
        guild = bot.get_guild(int(guild_id))
        if guild is None:
            raise BotRuntimeError("Bot chưa được thêm vào server này.")
        channel = guild.get_channel(int(channel_id))
        if not isinstance(channel, (discord.VoiceChannel, discord.StageChannel)):
            raise BotRuntimeError("Không tìm thấy phòng voice.")
        permissions = channel.permissions_for(guild.me) if guild.me else None
        if not permissions or not permissions.connect:
            raise BotRuntimeError("Bot không có quyền Connect vào phòng này.")

        voice_client = guild.voice_client
        if voice_client and voice_client.channel.id != channel.id:
            await voice_client.move_to(channel)
        elif not voice_client:
            await channel.connect(
                timeout=20.0,
                reconnect=True,
                self_mute=True,
                self_deaf=False,
            )

        voice_cog = self._voice_cog(bot)
        if voice_cog:
            voice_cog.auto_reconnect_channels[guild.id] = channel.id
            voice_cog.voice_timers[guild.id] = datetime.datetime.now()
        return {
            "ok": True,
            "message": f"Bot đang treo tại {channel.name}.",
            "guild_id": guild_id,
            "channel_id": channel_id,
        }

    async def _leave_voice(self, bot, guild_id: str) -> dict:
        if not guild_id.isdigit():
            raise BotRuntimeError("Server không hợp lệ.")
        guild = bot.get_guild(int(guild_id))
        if guild is None:
            raise BotRuntimeError("Bot chưa được thêm vào server này.")
        voice_cog = self._voice_cog(bot)
        if voice_cog:
            voice_cog.auto_reconnect_channels.pop(guild.id, None)
            voice_cog.voice_timers.pop(guild.id, None)
        if guild.voice_client:
            await guild.voice_client.disconnect(force=True)
        return {"ok": True, "message": f"Bot đã rời voice tại {guild.name}."}

    async def _set_presence(self, bot, payload: dict) -> dict:
        activity_type = str(payload.get("type", "playing")).strip().lower()
        name = str(payload.get("name", "")).strip()[:128]
        details = str(payload.get("details", "")).strip()[:128]
        state = str(payload.get("state", "")).strip()[:128]
        url = str(payload.get("url", "")).strip()[:500]
        status_name = str(payload.get("status", "online")).strip().lower()

        statuses = {
            "online": discord.Status.online,
            "idle": discord.Status.idle,
            "dnd": discord.Status.dnd,
            "invisible": discord.Status.invisible,
        }
        status = statuses.get(status_name, discord.Status.online)
        if activity_type == "none":
            activity = None
        elif not name:
            raise BotRuntimeError("Tên hoạt động không được để trống.")
        elif activity_type == "streaming":
            if not url.startswith(("https://", "http://")):
                raise BotRuntimeError("Streaming cần URL hợp lệ.")
            activity = discord.Streaming(name=name, url=url)
        else:
            activity_types = {
                "playing": discord.ActivityType.playing,
                "listening": discord.ActivityType.listening,
                "watching": discord.ActivityType.watching,
                "competing": discord.ActivityType.competing,
            }
            kind = activity_types.get(activity_type)
            if kind is None:
                raise BotRuntimeError("Loại hoạt động không hợp lệ.")
            activity = discord.Activity(type=kind, name=name, details=details or None, state=state or None)

        await bot.change_presence(status=status, activity=activity)
        return {"ok": True, "message": "Đã cập nhật presence/RPC của bot."}


runtime = BotRuntime()
