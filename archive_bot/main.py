import os
import sys
import json
import logging
import asyncio
import discord
from discord.ext import commands

# --- CẤU HÌNH LOGGING ---
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger("SelfBot")
logging.getLogger('discord').setLevel(logging.ERROR)
logging.getLogger('werkzeug').setLevel(logging.ERROR)

# --- THỬ IMPORT KEEP ALIVE (ANTI-OFFLINE) ---
try:
    from keep_alive import keep_alive
    HAS_KEEP_ALIVE = True
except ImportError:
    HAS_KEEP_ALIVE = False
    logger.warning("⚠️ Không tìm thấy file keep_alive.py!")

# --- LOAD CONFIG ---
def load_config():
    try:
        with open("config.json", 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        logger.critical(f"❌ Lỗi đọc config: {e}")
        return None

config = load_config()
if not config:
    sys.exit(1)

TOKEN = config.get('token')
PREFIX = config.get('prefix', '$')

# --- THIẾT LẬP BOT ---
class SelfBot(commands.Bot):
    def __init__(self):
        super().__init__(
            command_prefix=PREFIX,
            self_bot=True,
            help_command=None,
            case_insensitive=True
        )

    async def on_ready(self):
        print("="*30)
        print(f"✅  BOT ONLINE: {self.user.name}")
        print(f"🆔  ID: {self.user.id}")
        print(f"🚀  Prefix: {self.command_prefix}")
        if HAS_KEEP_ALIVE:
            print(f"🌐  Webserver: ĐANG CHẠY")
        print("="*30)
        await self.load_cogs()

    async def on_error(self, event, *args, **kwargs):
        """Global error handler để bắt các lỗi voice protocol"""
        exc_type, exc_value, exc_traceback = sys.exc_info()
        
        # Bỏ qua lỗi _MissingSentinel voice protocol
        if exc_type.__name__ == 'AttributeError' and '_MissingSentinel' in str(exc_value):
            logger.debug(f"Ignored voice protocol error: {exc_value}")
            return
        
        # Log các lỗi khác
        logger.error(f"Error in {event}: {exc_type.__name__}: {exc_value}")

    async def on_voice_state_update(self, member, before, after):
        """Theo dõi voice state changes"""
        # Chỉ xử lý khi là bot user
        if member.id != self.user.id:
            return
        
        # Detect bị disconnect
        if before.channel and not after.channel:
            logger.warning(f"⚠️ Bot bị disconnect từ {before.channel.name}")

    async def load_cogs(self):
        if not os.path.exists("cogs"):
            os.makedirs("cogs")
        
        for filename in os.listdir("cogs"):
            if filename.endswith(".py") and not filename.startswith("_"):
                cog_name = f"cogs.{filename[:-3]}"
                try:
                    await self.load_extension(cog_name)
                    logger.info(f"🔹 Loaded: {filename[:-3]}")
                except Exception as e:
                    logger.error(f"❌ Lỗi load {filename}: {e}")

bot = SelfBot()

# --- COMMAND: RELOAD COGS ---
@bot.command(name="reload", aliases=["rl"])
async def reload_cog(ctx, cog_name: str = None):
    """Reload một cog hoặc tất cả cogs"""
    try:
        await ctx.message.delete()
    except:
        pass
    
    if not cog_name:
        # Reload all cogs
        reloaded = []
        for filename in os.listdir("cogs"):
            if filename.endswith(".py") and not filename.startswith("_"):
                cog = f"cogs.{filename[:-3]}"
                try:
                    await bot.reload_extension(cog)
                    reloaded.append(filename[:-3])
                except Exception as e:
                    logger.error(f"Failed to reload {cog}: {e}")
        
        if reloaded:
            await ctx.send(f"🔄 Reloaded: {', '.join(reloaded)}", delete_after=5)
        else:
            await ctx.send("❌ Không có cog nào được reload.", delete_after=5)
    else:
        # Reload specific cog
        cog = f"cogs.{cog_name}"
        try:
            await bot.reload_extension(cog)
            await ctx.send(f"✅ Reloaded: {cog_name}", delete_after=5)
        except Exception as e:
            await ctx.send(f"❌ Lỗi: {e}", delete_after=5)

# --- CHẠY BOT ---
if __name__ == "__main__":
    if not TOKEN:
        logger.critical("❌ Thiếu Token trong config!")
        sys.exit(1)

    # 1. Chạy Webserver giữ bot sống
    if HAS_KEEP_ALIVE:
        print("🌍 Đang khởi động Webserver...")
        keep_alive()

    # 2. Chạy Bot với improved error handling
    try:
        bot.run(TOKEN.strip(), log_handler=None)  # Disable default discord.py logging
    except KeyboardInterrupt:
        logger.info("👋 Bot stopped by user")
    except Exception as e:
        logger.critical(f"❌ Bot bị tắt đột ngột: {e}")
