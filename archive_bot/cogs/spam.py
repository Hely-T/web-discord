import discord
from discord.ext import commands
import asyncio
import random
import os
import datetime

class SpamSystem(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.spam_tasks = {}
        self.spam_stats = {}
        self.base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.data_path = os.path.join(self.base_dir, "data", "spam.txt")
        self.spam_cache = []

    # (Giữ nguyên các hàm phụ trợ load_data, get_global_channel, smart_wait...) 
    # - Tôi lược bớt hàm phụ để tập trung vào lệnh chính

    async def get_global_channel(self, channel_id):
        if not str(channel_id).isdigit(): return None
        try: return await self.bot.fetch_channel(int(channel_id))
        except: return None

    async def smart_wait(self, channel_id, seconds):
        jitter = random.uniform(0.5, 3.5)
        for _ in range(int((seconds + jitter) * 10)):
            if not self.spam_tasks.get(channel_id): return False
            await asyncio.sleep(0.1)
        return True

    # Cập nhật logic parse arguments
    async def parse_args(self, ctx, arg1, arg2, content):
        target = ctx.channel
        delay = 60.0
        msg = ""
        
        # Logic check ID
        clean1 = str(arg1).replace("<#","").replace(">","") if arg1 else ""
        if clean1.isdigit() and len(clean1) > 15:
            ch = await self.get_global_channel(clean1)
            if ch:
                target = ch
                # Arg2 là delay, content là msg
                if arg2 and str(arg2).replace('.','').isdigit():
                    delay = float(arg2)
                    msg = content
                else:
                    msg = f"{arg2} {content}" if arg2 and content else (arg2 or content)
        else:
            # Arg1 là delay hoặc msg
            if clean1.replace('.','').isdigit() and len(clean1) < 10:
                delay = float(clean1)
                msg = f"{arg2} {content}" if arg2 and content else (arg2 or content)
            else:
                msg = f"{arg1} {arg2} {content}".replace("None", "").strip()
                
        return target, delay, msg

    @commands.command(name='spam')
    async def spam_text(self, ctx, id_or_msg: str = None, delay: str = None, *, content: str = None):
        """Spam tin nhắn ($spam <id> <delay> <nd>)."""
        try: await ctx.message.delete()
        except: pass
        
        # Tái sử dụng logic parse args nhưng viết lại gọn
        channel, wait_time, text = await self.parse_args(ctx, id_or_msg, delay, content)
        
        if not text: return await ctx.send("❌ Thiếu nội dung!", delete_after=5)
        if self.spam_tasks.get(channel.id): return await ctx.send("⚠️ Đang chạy rồi!", delete_after=5)

        self.spam_tasks[channel.id] = True
        self.spam_stats[channel.id] = {'count': 0, 'start_time': datetime.datetime.now(), 'type': 'Text', 'last_content': text[:20]}
        
        await ctx.send(f"🌱 Spam tại: `{channel.name}` | Delay: `{wait_time}s`")
        
        while self.spam_tasks.get(channel.id):
            try:
                final = f"{text} `[{random.randint(1000,9999)}]`"
                await channel.send(final)
                self.spam_stats[channel.id]['count'] += 1
                if not await self.smart_wait(channel.id, wait_time): break
            except:
                self.spam_tasks[channel.id] = False
                break

    @commands.command(name='spamfile')
    async def spam_file(self, ctx, id: str = None, delay: str = None):
        """Spam từ file spam.txt ($spamfile [id] [delay])."""
        try: await ctx.message.delete()
        except: pass
        
        # Load data
        if not os.path.exists(self.data_path): return await ctx.send("❌ Thiếu file data/spam.txt")
        with open(self.data_path, "r", encoding="utf-8") as f:
            self.spam_cache = [l.strip() for l in f.readlines() if l.strip()]

        channel, wait_time, _ = await self.parse_args(ctx, id, delay, "")
        
        if self.spam_tasks.get(channel.id): return await ctx.send("⚠️ Đang chạy rồi!", delete_after=5)

        self.spam_tasks[channel.id] = True
        self.spam_stats[channel.id] = {'count': 0, 'start_time': datetime.datetime.now(), 'type': 'File', 'last_content': 'File'}

        await ctx.send(f"🌱 Spam File tại: `{channel.name}` | Delay: `{wait_time}s`")

        while self.spam_tasks.get(channel.id):
            try:
                txt = random.choice(self.spam_cache)
                if random.choice([True, False]): txt += " ."
                await channel.send(txt)
                self.spam_stats[channel.id]['count'] += 1
                if not await self.smart_wait(channel.id, wait_time): break
            except:
                self.spam_tasks[channel.id] = False
                break

    @commands.command(name='stopspam', aliases=['ss'])
    async def stop_spam(self, ctx, id: str = None):
        """Dừng spam ($ss [id])."""
        try: await ctx.message.delete()
        except: pass
        
        tid = int(id) if id and id.isdigit() else ctx.channel.id
        
        if self.spam_tasks.get(tid):
            self.spam_tasks[tid] = False
            self.spam_stats.pop(tid, None)
            await ctx.send(f"🛑 Đã dừng `{tid}`.", delete_after=5)
        else:
            # Nếu không nhập ID, dừng cái đang chạy duy nhất
            active = [k for k,v in self.spam_tasks.items() if v]
            if not id and len(active) == 1:
                self.spam_tasks[active[0]] = False
                self.spam_stats.pop(active[0], None)
                await ctx.send(f"🛑 Đã dừng `{active[0]}`.", delete_after=5)
            else:
                await ctx.send("⚠️ Kênh không chạy.", delete_after=3)

    @commands.command(name='stopallspam', aliases=['ssa'])
    async def stop_all(self, ctx):
        """Dừng tất cả spam."""
        try: await ctx.message.delete()
        except: pass
        for k in self.spam_tasks: self.spam_tasks[k] = False
        self.spam_stats.clear()
        await ctx.send("🛑 Đã dừng toàn bộ.", delete_after=5)

async def setup(bot):
    await bot.add_cog(SpamSystem(bot))