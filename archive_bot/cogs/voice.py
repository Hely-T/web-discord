import asyncio
import ctypes.util
import datetime
import json
import logging
import os
import sys
from pathlib import Path

import discord
from discord.ext import commands, tasks

logger = logging.getLogger("Voice")
ARCHIVE_DIR = Path(__file__).resolve().parents[1]
VOICE_STATE_PATH = Path(os.getenv("VOICE_STATE_PATH", str(ARCHIVE_DIR / "data" / "voice_state.json")))

# --- LOAD OPUS LIBRARY ---
def load_opus_lib():
    if discord.opus.is_loaded(): return
    try:
        lib_name = 'opus' if sys.platform == 'win32' else 'libopus.so.0'
        lib_path = ctypes.util.find_library(lib_name)
        if not lib_path:
            possible_paths = ["libopus.so.0", "/usr/lib/x86_64-linux-gnu/libopus.so.0", "libopus-0.x64.dll"]
            for path in possible_paths:
                if os.path.exists(path):
                    lib_path = path
                    break
        if lib_path:
            discord.opus.load_opus(lib_path)
    except: pass
load_opus_lib()

class Voice(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.voice_timers = {}
        self.auto_reconnect_channels = self.load_voice_state()
        self.reconnect_locks = {}
        self.reconnect_tasks = {}
        self.voice_monitor.start()

    def cog_unload(self):
        self.voice_monitor.cancel()
        for task in self.reconnect_tasks.values():
            task.cancel()

    def load_voice_state(self):
        try:
            payload = json.loads(VOICE_STATE_PATH.read_text(encoding="utf-8"))
            channels = payload.get("channels", payload)
            return {
                int(guild_id): int(channel_id)
                for guild_id, channel_id in channels.items()
                if str(guild_id).isdigit() and str(channel_id).isdigit()
            }
        except FileNotFoundError:
            return {}
        except (OSError, ValueError, TypeError, AttributeError, json.JSONDecodeError) as exc:
            logger.warning("Không đọc được voice state %s: %s", VOICE_STATE_PATH, exc)
            return {}

    def save_voice_state(self):
        try:
            VOICE_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
            temp_path = VOICE_STATE_PATH.with_suffix(".tmp")
            temp_path.write_text(
                json.dumps(
                    {"channels": {str(guild_id): str(channel_id) for guild_id, channel_id in self.auto_reconnect_channels.items()}},
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
            temp_path.replace(VOICE_STATE_PATH)
        except OSError as exc:
            logger.error("Không lưu được voice state %s: %s", VOICE_STATE_PATH, exc)

    def set_auto_reconnect(self, guild_id, channel_id):
        self.auto_reconnect_channels[int(guild_id)] = int(channel_id)
        self.voice_timers.setdefault(int(guild_id), datetime.datetime.now())
        self.save_voice_state()

    def clear_auto_reconnect(self, guild_id):
        guild_id = int(guild_id)
        self.auto_reconnect_channels.pop(guild_id, None)
        self.voice_timers.pop(guild_id, None)
        task = self.reconnect_tasks.pop(guild_id, None)
        if task and not task.done():
            task.cancel()
        self.save_voice_state()

    def schedule_reconnect(self, guild_id, delay=2.0):
        guild_id = int(guild_id)
        if guild_id not in self.auto_reconnect_channels:
            return
        current = self.reconnect_tasks.get(guild_id)
        if current and not current.done():
            return

        async def reconnect_later():
            try:
                await asyncio.sleep(delay)
                channel_id = self.auto_reconnect_channels.get(guild_id)
                if channel_id:
                    await self.ensure_voice_connection(guild_id, channel_id)
            finally:
                if self.reconnect_tasks.get(guild_id) is asyncio.current_task():
                    self.reconnect_tasks.pop(guild_id, None)

        self.reconnect_tasks[guild_id] = asyncio.create_task(reconnect_later())

    async def ensure_voice_connection(self, guild_id, channel_id):
        guild_id = int(guild_id)
        channel_id = int(channel_id)
        lock = self.reconnect_locks.setdefault(guild_id, asyncio.Lock())
        async with lock:
            if self.auto_reconnect_channels.get(guild_id) != channel_id:
                return False
            guild = self.bot.get_guild(guild_id)
            if not guild:
                logger.warning("Không tìm thấy server %s để reconnect voice", guild_id)
                return False
            channel = guild.get_channel(channel_id)
            if not isinstance(channel, (discord.VoiceChannel, discord.StageChannel)):
                logger.warning("Không tìm thấy room voice %s trong %s", channel_id, guild.name)
                return False
            permissions = channel.permissions_for(guild.me) if guild.me else None
            if not permissions or not permissions.connect:
                logger.warning("Bot thiếu quyền Connect vào %s / %s", guild.name, channel.name)
                return False

            voice_client = guild.voice_client
            member_channel = guild.me.voice.channel if guild.me and guild.me.voice else None
            current_channel = member_channel or (voice_client.channel if voice_client else None)
            if (
                voice_client
                and voice_client.is_connected()
                and current_channel
                and current_channel.id == channel_id
            ):
                return True

            try:
                if voice_client and voice_client.is_connected() and current_channel:
                    await voice_client.move_to(channel)
                else:
                    if voice_client:
                        try:
                            await asyncio.wait_for(voice_client.disconnect(force=True), timeout=5.0)
                        except Exception:
                            voice_client.cleanup()
                        await asyncio.sleep(1)
                    await channel.connect(
                        self_mute=True,
                        self_deaf=False,
                        timeout=20.0,
                        reconnect=True,
                    )
                self.voice_timers[guild_id] = datetime.datetime.now()
                logger.info("Voice connected: %s / %s (persistent)", guild.name, channel.name)
                return True
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.warning("Voice reconnect thất bại %s / %s: %s", guild.name, channel.name, exc)
                return False

    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        if not self.bot.user or member.id != self.bot.user.id:
            return
        if before.channel and not after.channel:
            guild_id = before.channel.guild.id
            if guild_id in self.auto_reconnect_channels:
                logger.warning("Bot bị disconnect từ %s; reconnect sau 2 giây", before.channel.name)
                self.schedule_reconnect(guild_id, delay=2.0)
        elif after.channel:
            target = self.auto_reconnect_channels.get(after.channel.guild.id)
            if target and target != after.channel.id:
                logger.warning("Bot bị chuyển khỏi room đã ghim; đang chuyển lại")
                self.schedule_reconnect(after.channel.guild.id, delay=2.0)

    @commands.Cog.listener()
    async def on_ready(self):
        for guild_id in self.auto_reconnect_channels:
            self.schedule_reconnect(guild_id, delay=1.0)

    @tasks.loop(seconds=15)
    async def voice_monitor(self):
        for guild_id, channel_id in list(self.auto_reconnect_channels.items()):
            try:
                await self.ensure_voice_connection(guild_id, channel_id)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.error("Voice monitor error tại server %s: %s", guild_id, exc)

    @voice_monitor.before_loop
    async def before_voice_monitor(self):
        await self.bot.wait_until_ready()

    async def get_channel_smart(self, ctx, channel_id):
        """
        FIX: Xử lý trường hợp ctx.guild = None (khi gửi lệnh từ DM)
        """
        if not channel_id: return None
        clean_id = str(channel_id).replace("<#", "").replace(">", "").strip()
        if not clean_id.isdigit(): return None
        cid = int(clean_id)
        
        # FIX: Chỉ check local_channel nếu ctx.guild không phải None
        if ctx.guild:
            local_channel = ctx.guild.get_channel(cid)
            if local_channel and isinstance(local_channel, discord.VoiceChannel):
                return local_channel
        
        # Tìm global
        global_channel = self.bot.get_channel(cid)
        if global_channel and isinstance(global_channel, discord.VoiceChannel):
            return global_channel
            
        try:
            ch = await self.bot.fetch_channel(cid)
            if isinstance(ch, discord.VoiceChannel): return ch
        except: return None
        return None

    @commands.command(name="joinvoice", aliases=["jv", "join"])
    async def joinvoice(self, ctx, id: str = None):
        """Vào voice và giữ kết nối bền vững."""
        try: await ctx.message.delete()
        except: pass

        target_channel = None
        if id:
            target_channel = await self.get_channel_smart(ctx, id)
            if not target_channel:
                return await ctx.send(f"❌ Không tìm thấy ID: `{id}`", delete_after=5)
        elif ctx.author.voice:
            target_channel = ctx.author.voice.channel
        else:
            return await ctx.send("❌ Nhập ID hoặc vào voice trước!", delete_after=5)

        self.set_auto_reconnect(target_channel.guild.id, target_channel.id)
        connected = await self.ensure_voice_connection(target_channel.guild.id, target_channel.id)
        if connected:
            await ctx.send(f"✅ Đang treo **{target_channel.name}** | Persistent: ON", delete_after=5)
        else:
            await ctx.send("⚠️ Chưa kết nối được; hệ thống sẽ tự thử lại mỗi 15 giây.", delete_after=8)

    @commands.command(name="leavevoice", aliases=["lv", "leave"])
    async def leavevoice(self, ctx, id: str = None):
        """Thoát voice (Tự động tìm bot)."""
        try: await ctx.message.delete()
        except: pass

        target_vc = None
        target_guild_id = None
        if id:
            clean_id = str(id).replace("<", "").replace(">", "").strip()
            if clean_id.isdigit():
                sid = int(clean_id)
                for vc in self.bot.voice_clients:
                    if vc.guild.id == sid or vc.channel.id == sid:
                        target_vc = vc
                        target_guild_id = vc.guild.id
                        break
                if target_guild_id is None:
                    if sid in self.auto_reconnect_channels:
                        target_guild_id = sid
                    else:
                        target_guild_id = next(
                            (guild_id for guild_id, channel_id in self.auto_reconnect_channels.items() if channel_id == sid),
                            None,
                        )
        else:
            if ctx.guild:
                target_vc = ctx.guild.voice_client
                target_guild_id = ctx.guild.id
            if not target_vc and len(self.bot.voice_clients) == 1:
                target_vc = self.bot.voice_clients[0]
                target_guild_id = target_vc.guild.id

        if target_guild_id:
            guild = self.bot.get_guild(target_guild_id)
            sname = guild.name if guild else str(target_guild_id)
            self.clear_auto_reconnect(target_guild_id)
            try:
                if target_vc:
                    await target_vc.disconnect(force=True)
            except Exception as exc:
                logger.warning("Disconnect error: %s", exc)
            await ctx.send(f"👋 Đã thoát **{sname}** | Persistent: OFF", delete_after=5)
        else:
            await ctx.send("❌ Bot không online (hoặc nhập sai ID).", delete_after=5)

    @commands.command(name="leaveall", aliases=["lvall"])
    async def leave_all_voice(self, ctx):
        """Thoát tất cả."""
        try: await ctx.message.delete()
        except: pass
        vcs = list(self.bot.voice_clients)
        configured = list(self.auto_reconnect_channels)
        if not vcs and not configured:
            return await ctx.send("✅ Bot rảnh.", delete_after=5)
        msg = await ctx.send(f"🚪 Đang tắt {max(len(vcs), len(configured))} kết nối persistent...")
        for guild_id in configured:
            self.clear_auto_reconnect(guild_id)
        for vc in vcs:
            try:
                await vc.disconnect(force=True)
                await asyncio.sleep(0.5)
            except: pass
        await msg.edit(content="✅ Đã thoát hết | Persistent: OFF")

    @commands.command(name="vcstatus", aliases=["vcs"])
    async def voice_status(self, ctx):
        """Xem trạng thái voice connections"""
        try: await ctx.message.delete()
        except: pass

        if not self.bot.voice_clients:
            return await ctx.send("✅ Không có kết nối voice nào.", delete_after=5)

        lines = ["```ini", "[ 🎙️ VOICE STATUS ]", ""]
        for i, vc in enumerate(self.bot.voice_clients, 1):
            try:
                guild_id = vc.guild.id
                auto_reconnect = "ON 🔄" if guild_id in self.auto_reconnect_channels else "OFF"
                
                # Lấy mic/speaker status - CHECK NULL
                guild = vc.guild
                me = guild.me
                
                # Fix: Check nếu me.voice is None (bot đang disconnect)
                if me.voice is None:
                    mic_status = "N/A"
                    speaker_status = "N/A"
                else:
                    mic_status = "OFF 🔇" if me.voice.self_mute else "ON 🎤"
                    speaker_status = "OFF 🔇" if me.voice.self_deaf else "ON 🔊"
            
                # Lấy uptime
                uptime = "N/A"
                if guild_id in self.voice_timers:
                    diff = datetime.datetime.now() - self.voice_timers[guild_id]
                    hours, remainder = divmod(int(diff.total_seconds()), 3600)
                    minutes, seconds = divmod(remainder, 60)
                    uptime = f"{hours:02}:{minutes:02}:{seconds:02}"
                
                lines.append(f"{i}. {vc.channel.name}")
                lines.append(f"   Server        : {vc.guild.name}")
                lines.append(f"   Uptime        : {uptime}")
                lines.append(f"   Mic           : {mic_status}")
                lines.append(f"   Speaker       : {speaker_status}")
                lines.append(f"   Auto-Reconnect: {auto_reconnect}")
                lines.append(f"   Latency       : {round(vc.latency * 1000)}ms")
                lines.append("")
            except Exception as e:
                # Nếu có lỗi với voice client này, skip
                logger.warning(f"Error getting voice status: {e}")
                continue

        lines.append("```")
        await ctx.send("\n".join(lines), delete_after=30)

    @commands.command(name="mic", aliases=["togglemic", "tm"])
    async def toggle_mic(self, ctx, id: str = None):
        """Toggle mic ON/OFF"""
        try: await ctx.message.delete()
        except: pass

        # Tìm voice client
        target_vc = None
        if id and id.isdigit():
            sid = int(id)
            for vc in self.bot.voice_clients:
                if vc.guild.id == sid:
                    target_vc = vc
                    break
        else:
            # FIX: Check ctx.guild
            if ctx.guild:
                target_vc = ctx.guild.voice_client
            if not target_vc and len(self.bot.voice_clients) == 1:
                target_vc = self.bot.voice_clients[0]

        if not target_vc:
            return await ctx.send("❌ Bot không ở voice nào!", delete_after=5)

        # Toggle mic
        guild = target_vc.guild
        me = guild.me
        
        # Check nếu me.voice is None
        if me.voice is None:
            return await ctx.send("❌ Bot không ở voice hoặc đang disconnect!", delete_after=5)
        
        current_mute = me.voice.self_mute
        
        try:
            await guild.change_voice_state(
                channel=target_vc.channel,
                self_mute=not current_mute,
                self_deaf=me.voice.self_deaf
            )
            status = "OFF 🔇" if not current_mute else "ON 🎤"
            await ctx.send(f"🎤 Mic → {status} | {guild.name}", delete_after=5)
        except Exception as e:
            await ctx.send(f"❌ Lỗi: {e}", delete_after=5)

    @commands.command(name="speaker", aliases=["togglespeaker", "ts"])
    async def toggle_speaker(self, ctx, id: str = None):
        """Toggle speaker ON/OFF"""
        try: await ctx.message.delete()
        except: pass

        # Tìm voice client
        target_vc = None
        if id and id.isdigit():
            sid = int(id)
            for vc in self.bot.voice_clients:
                if vc.guild.id == sid:
                    target_vc = vc
                    break
        else:
            # FIX: Check ctx.guild
            if ctx.guild:
                target_vc = ctx.guild.voice_client
            if not target_vc and len(self.bot.voice_clients) == 1:
                target_vc = self.bot.voice_clients[0]

        if not target_vc:
            return await ctx.send("❌ Bot không ở voice nào!", delete_after=5)

        # Toggle speaker
        guild = target_vc.guild
        me = guild.me
        
        # Check nếu me.voice is None
        if me.voice is None:
            return await ctx.send("❌ Bot không ở voice hoặc đang disconnect!", delete_after=5)
        
        current_deaf = me.voice.self_deaf
        
        try:
            await guild.change_voice_state(
                channel=target_vc.channel,
                self_mute=me.voice.self_mute,
                self_deaf=not current_deaf
            )
            status = "OFF 🔇" if not current_deaf else "ON 🔊"
            await ctx.send(f"🔊 Speaker → {status} | {guild.name}", delete_after=5)
        except Exception as e:
            await ctx.send(f"❌ Lỗi: {e}", delete_after=5)

    @commands.command(name="setvoice", aliases=["sv"])
    async def set_voice(self, ctx, mic: str = "off", speaker: str = "on"):
        """Set mic/speaker state (off/on)"""
        try: await ctx.message.delete()
        except: pass

        # Parse args
        mic_state = mic.lower() == "on"
        speaker_state = speaker.lower() == "on"

        # Tìm voice client
        target_vc = None
        # FIX: Check ctx.guild
        if ctx.guild:
            target_vc = ctx.guild.voice_client
        if not target_vc and len(self.bot.voice_clients) == 1:
            target_vc = self.bot.voice_clients[0]

        if not target_vc:
            return await ctx.send("❌ Bot không ở voice nào!", delete_after=5)

        # Set voice state
        guild = target_vc.guild
        try:
            await guild.change_voice_state(
                channel=target_vc.channel,
                self_mute=not mic_state,
                self_deaf=not speaker_state
            )
            mic_icon = "🎤 ON" if mic_state else "🔇 OFF"
            speaker_icon = "🔊 ON" if speaker_state else "🔇 OFF"
            await ctx.send(f"✅ Mic: {mic_icon} | Speaker: {speaker_icon}", delete_after=5)
        except Exception as e:
            await ctx.send(f"❌ Lỗi: {e}", delete_after=5)

async def setup(bot):
    await bot.add_cog(Voice(bot))
