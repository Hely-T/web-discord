import discord
from discord.ext import commands
import asyncio
import random
import os
import datetime

class Quotes(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.active_tasks = {}
        self.quote_stats = {}
        self.base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.data_path = os.path.join(self.base_dir, "data", "quotes.txt")
        self.quotes_cache = []

    def clean_text(self, text):
        if not text: return ""
        if "]" in text: return text.split("]")[-1].strip()
        return text.strip()

    def load_quotes(self):
        self.quotes_cache = []
        if os.path.exists(self.data_path):
            try:
                with open(self.data_path, "r", encoding="utf-8") as f:
                    lines = f.readlines()
                for line in lines:
                    final = self.clean_text(line)
                    if final: self.quotes_cache.append(final)
            except: pass
        if not self.quotes_cache: self.quotes_cache = ["Example quote"]

    @commands.command(name='quotes')
    async def start_quotes(self, ctx, id: str = None, delay: float = 60.0):
        """Treo quotes ($quotes [id] [delay])."""
        try: await ctx.message.delete()
        except: pass
        
        self.load_quotes()
        
        target_id = ctx.channel.id
        if id and id.isdigit(): target_id = int(id)
        
        channel = self.bot.get_channel(target_id)
        if not channel:
            try: channel = await self.bot.fetch_channel(target_id)
            except: return await ctx.send("❌ Không tìm thấy kênh!", delete_after=5)

        if self.active_tasks.get(target_id):
            return await ctx.send("⚠️ Đang chạy rồi!", delete_after=5)

        self.active_tasks[target_id] = True
        self.quote_stats[target_id] = {'count': 0, 'start_time': datetime.datetime.now()}
        
        await ctx.send(f"📜 Quotes tại: `{channel.name}` | Delay: `{delay}s`")

        while self.active_tasks.get(target_id):
            try:
                txt = random.choice(self.quotes_cache)
                await channel.send(txt)
                self.quote_stats[target_id]['count'] += 1
                
                for _ in range(int(delay)):
                    if not self.active_tasks.get(target_id): break
                    await asyncio.sleep(1)
            except:
                self.active_tasks[target_id] = False
                break

    @commands.command(name='stop_quotes', aliases=['sq'])
    async def stop_quotes(self, ctx, id: str = None):
        """Dừng Quotes (Không cần ID nếu đang đứng tại chỗ)."""
        try: await ctx.message.delete()
        except: pass
        
        target_id = None

        # 1. Nếu nhập ID -> Dừng ID đó
        if id and id.isdigit():
            target_id = int(id)
        
        # 2. Nếu không nhập ID
        else:
            # Ưu tiên kênh hiện tại
            if self.active_tasks.get(ctx.channel.id):
                target_id = ctx.channel.id
            else:
                # Nếu hiện tại không chạy, kiểm tra xem có duy nhất 1 kênh nào đang chạy không
                active_list = [k for k, v in self.active_tasks.items() if v]
                if len(active_list) == 1:
                    target_id = active_list[0]
        
        # Xử lý lệnh dừng
        if target_id and self.active_tasks.get(target_id):
            self.active_tasks[target_id] = False
            self.quote_stats.pop(target_id, None)
            
            # Lấy tên kênh cho đẹp
            ch = self.bot.get_channel(target_id)
            name = ch.name if ch else str(target_id)
            
            await ctx.send(f"🛑 Đã dừng quotes tại: **{name}**", delete_after=5)
        else:
            await ctx.send("⚠️ Không tìm thấy tác vụ Quotes nào để dừng.", delete_after=5)

async def setup(bot):
    await bot.add_cog(Quotes(bot))