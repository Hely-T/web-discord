import discord
from discord.ext import commands
import datetime
import os

class Status(commands.Cog):
    """Hệ thống theo dõi tiến trình (Clean Version - No OwO)"""
    
    def __init__(self, bot):
        self.bot = bot
        self.start_time = datetime.datetime.now()

    def get_duration(self, start_time):
        if not start_time: return "00:00:00"
        diff = datetime.datetime.now() - start_time
        seconds = int(diff.total_seconds())
        days, seconds = divmod(seconds, 86400)
        hours, seconds = divmod(seconds, 3600)
        minutes, seconds = divmod(seconds, 60)
        if days > 0: return f"{days}d {hours:02}h {minutes:02}m"
        return f"{hours:02}:{minutes:02}:{seconds:02}"

    @commands.command(name="status", aliases=["st"])
    async def show_status(self, ctx):
        try: await ctx.message.delete()
        except: pass
        
        voice_cog = self.bot.get_cog("Voice")
        spam_cog = self.bot.get_cog("SpamSystem")
        quotes_cog = self.bot.get_cog("Quotes")

        lines = ["```ini", "[ 📊 MONITORING DASHBOARD ]"]
        
        # --- 1. SYSTEM INFO ---
        uptime = self.get_duration(self.start_time)
        ping = round(self.bot.latency * 1000)
        lines.append(f"[ SYSTEM ]\n• Uptime : {uptime}\n• Ping   : {ping}ms\n")

        # --- 2. VOICE STATUS ---
        lines.append(f"[ VOICE CONNECTIONS ]")
        if not self.bot.voice_clients:
            lines.append("• Không có kết nối nào.")
        else:
            for i, vc in enumerate(self.bot.voice_clients, 1):
                try:
                    # Lấy trạng thái Mic
                    vs = vc.guild.me.voice
                    mic = "ON" if vs and not vs.self_mute else "OFF"
                    
                    # Lấy thời gian treo
                    time_run = "N/A"
                    if voice_cog and hasattr(voice_cog, 'voice_timers'):
                        t = voice_cog.voice_timers.get(vc.guild.id)
                        time_run = self.get_duration(t)

                    lines.append(f"{i}. {vc.channel.name}")
                    lines.append(f"   Server : {vc.guild.name}")
                    lines.append(f"   Time   : {time_run} | Mic: {mic}")
                except: 
                    lines.append(f"{i}. {vc.channel.name} (Lỗi hiển thị)")
        lines.append("")

        # --- 3. RUNNING TASKS (Spam & Quotes) ---
        task_lines = []
        
        # Spam Tasks
        if spam_cog and hasattr(spam_cog, 'spam_stats'):
            for cid, data in spam_cog.spam_stats.items():
                if spam_cog.spam_tasks.get(cid):
                    ch = self.bot.get_channel(cid)
                    name = ch.name if ch else f"ID:{cid}"
                    task_lines.append(f"🔥 SPAM: {name}\n   Sent: {data.get('count',0)} | Last: {data.get('last_content','...')}")

        # Quotes Tasks
        if quotes_cog and hasattr(quotes_cog, 'quote_stats'):
            for cid, data in quotes_cog.quote_stats.items():
                if quotes_cog.active_tasks.get(cid):
                    ch = self.bot.get_channel(cid)
                    name = ch.name if ch else f"ID:{cid}"
                    task_lines.append(f"📜 QUOTES: {name}\n   Sent: {data.get('count',0)}")

        if task_lines:
            lines.append("[ RUNNING TASKS ]")
            lines.extend(task_lines)
            lines.append("")
        else:
            lines.append("[ TASKS ]\n• Không có tác vụ nào đang chạy.\n")

        lines.append("```")
        await ctx.send("\n".join(lines))

async def setup(bot):
    await bot.add_cog(Status(bot))