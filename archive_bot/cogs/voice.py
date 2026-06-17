import discord
from discord.ext import commands, tasks
import asyncio
import sys
import os
import ctypes.util
import datetime
import logging

logger = logging.getLogger("Voice")

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
        self.auto_reconnect_channels = {}  # {guild_id: channel_id}
        self.voice_monitor.start()

    def cog_unload(self):
        self.voice_monitor.cancel()

    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        """Handle voice state updates"""
        # Chỉ xử lý khi là bot user
        if member.id != self.bot.user.id:
            return
        
        # Bot bị disconnect khỏi voice
        if before.channel and not after.channel:
            guild_id = before.channel.guild.id
            logger.warning(f"⚠️ Bot bị disconnect từ {before.channel.name}")
            
            # Không xóa khỏi auto_reconnect - để auto-reconnect task xử lý
            # Monitor task sẽ tự động reconnect trong 1 phút

    @tasks.loop(minutes=1)
    async def voice_monitor(self):
        """Kiểm tra và reconnect voice connections bị disconnect"""
        try:
            for guild_id, channel_id in list(self.auto_reconnect_channels.items()):
                guild = self.bot.get_guild(guild_id)
                if not guild:
                    self.auto_reconnect_channels.pop(guild_id, None)
                    continue
                
                # Kiểm tra xem bot có còn trong voice không
                if not guild.voice_client:
                    # Thử reconnect
                    channel = guild.get_channel(channel_id)
                    if channel and isinstance(channel, discord.VoiceChannel):
                        try:
                            await channel.connect(self_mute=True, self_deaf=False, timeout=15.0)
                            logger.info(f"🔄 Auto-reconnected to {channel.name} in {guild.name}")
                            self.voice_timers[guild_id] = datetime.datetime.now()
                        except Exception as e:
                            logger.warning(f"⚠️ Failed to auto-reconnect: {e}")
        except Exception as e:
            logger.error(f"❌ Voice monitor error: {e}")

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
        """Vào voice với auto-reconnect."""
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

        try:
            guild_id = target_channel.guild.id
            self.voice_timers[guild_id] = datetime.datetime.now()
            
            # Lưu channel để auto-reconnect
            self.auto_reconnect_channels[guild_id] = target_channel.id
            
            # FIX: Check ctx.guild trước khi so sánh
            if ctx.guild and target_channel.guild.id != ctx.guild.id:
                await ctx.send(f"⚠️ Bot đang bay sang server **{target_channel.guild.name}**...", delete_after=5)

            current_vc = target_channel.guild.voice_client
            if current_vc:
                if current_vc.channel.id != target_channel.id:
                    await current_vc.move_to(target_channel)
                    await ctx.send(f"➡️ Chuyển: **{target_channel.name}** 🔄", delete_after=5)
                else:
                    await ctx.send(f"⚠️ Bot ở **{target_channel.name}** rồi. 🔄", delete_after=5)
            else:
                await target_channel.connect(self_mute=True, self_deaf=False, timeout=15.0)
                await ctx.send(f"✅ Đã vào: **{target_channel.name}** | Auto-reconnect: ON 🔄", delete_after=5)

        except asyncio.TimeoutError:
            await ctx.send("❌ Mạng lag (Timeout). Đang thử lại...", delete_after=5)
            # Thử lại 1 lần nữa
            try:
                await asyncio.sleep(2)
                await target_channel.connect(self_mute=True, self_deaf=False, timeout=20.0)
                await ctx.send(f"✅ Đã vào (retry): **{target_channel.name}**", delete_after=5)
            except:
                await ctx.send("❌ Không thể kết nối sau 2 lần thử.", delete_after=5)
        except Exception as e:
            await ctx.send(f"❌ Lỗi: `{e}`", delete_after=5)

    @commands.command(name="leavevoice", aliases=["lv", "leave"])
    async def leavevoice(self, ctx, id: str = None):
        """Thoát voice (Tự động tìm bot)."""
        try: await ctx.message.delete()
        except: pass

        target_vc = None
        
        # 1. Nếu có ID
        if id:
            clean_id = str(id).replace("<", "").replace(">", "").strip()
            if clean_id.isdigit():
                sid = int(clean_id)
                for vc in self.bot.voice_clients:
                    if vc.guild.id == sid or vc.channel.id == sid:
                        target_vc = vc
                        break
        # 2. Không có ID
        else:
            # FIX: Check ctx.guild trước khi dùng
            if ctx.guild:
                target_vc = ctx.guild.voice_client
            
            # Nếu server hiện tại không có bot, mà bot chỉ đang onl 1 chỗ duy nhất
            if not target_vc and len(self.bot.voice_clients) == 1:
                target_vc = self.bot.voice_clients[0]
        
        if target_vc:
            guild_id = target_vc.guild.id
            sname = target_vc.guild.name
            
            # Tắt auto-reconnect
            self.auto_reconnect_channels.pop(guild_id, None)
            self.voice_timers.pop(guild_id, None)
            
            try:
                await target_vc.disconnect(force=True)
            except Exception as e:
                logger.warning(f"Disconnect error: {e}")
            
            await ctx.send(f"👋 Đã thoát **{sname}** | Auto-reconnect: OFF", delete_after=5)
        else:
            await ctx.send("❌ Bot không online (hoặc nhập sai ID).", delete_after=5)

    @commands.command(name="leaveall", aliases=["lvall"])
    async def leave_all_voice(self, ctx):
        """Thoát tất cả."""
        try: await ctx.message.delete()
        except: pass
        vcs = list(self.bot.voice_clients)
        if not vcs: return await ctx.send("✅ Bot rảnh.", delete_after=5)

        msg = await ctx.send(f"🚪 Đang thoát {len(vcs)} server...")
        for vc in vcs:
            try:
                guild_id = vc.guild.id
                self.auto_reconnect_channels.pop(guild_id, None)
                self.voice_timers.pop(guild_id, None)
                await vc.disconnect(force=True)
                await asyncio.sleep(0.5)
            except: pass
        await msg.edit(content=f"✅ Đã thoát hết | Auto-reconnect: OFF")

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
