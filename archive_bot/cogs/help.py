import discord
from discord.ext import commands

class Help(commands.Cog):
    """Hệ thống Help Menu V12: Enhanced Display"""
    
    def __init__(self, bot):
        self.bot = bot
        if self.bot.get_command("help"):
            self.bot.remove_command("help")

    @commands.command(name="help", aliases=["h", "menu"])
    async def help_cmd(self, ctx, *, cmd_name: str = None):
        """Xem danh sách toàn bộ lệnh"""
        try: await ctx.message.delete()
        except: pass
        
        prefix = ctx.prefix

        # Mapping tên nhóm với icons
        cogs_mapping = {
            "SpamSystem": "🔥 SPAM TOOLS",
            "Quotes":     "📜 AUTO QUOTES",
            "Voice":      "🎙️ VOICE MANAGER",
            "Status":     "📊 STATUS DASHBOARD",
            "utility":    "🛠️ UTILITIES",
            "Help":       "ℹ️ SYSTEM INFO"
        }

        # --- MENU TỔNG ---
        if not cmd_name:
            lines = ["```ini"]
            lines.append("╔══════════════════════════════════════════╗")
            lines.append("║      [ SELF-BOT ALL COMMANDS ]           ║")
            lines.append("╚══════════════════════════════════════════╝")
            lines.append("")

            for cog_name, cog in self.bot.cogs.items():
                commands_list = cog.get_commands()
                visible_cmds = [c for c in commands_list if not c.hidden]
                if not visible_cmds: continue

                header = cogs_mapping.get(cog_name, f"📁 {cog_name.upper()}")
                lines.append(f"[ {header} ]")
                
                for cmd in visible_cmds:
                    # Lấy mô tả
                    desc = cmd.help.strip().split("\n")[0] if cmd.help else "..."
                    # Lấy aliases
                    aliases = f"({', '.join(cmd.aliases)})" if cmd.aliases else ""
                    # Format command name + aliases
                    cmd_display = f"{prefix}{cmd.name} {aliases}".ljust(28)
                    lines.append(f"  {cmd_display} : {desc}")
                
                lines.append("")

            lines.append("─" * 44)
            lines.append(f"💡 Gõ {prefix}help <lệnh> để xem chi tiết")
            lines.append(f"💡 Gõ {prefix}help <nhóm> để xem lệnh trong nhóm")
            lines.append("```")
            await ctx.send("\n".join(lines))
            return

        # --- TÌM KIẾM CHI TIẾT ---
        cmd = self.bot.get_command(cmd_name)
        if cmd:
            lines = ["```yaml"]
            lines.append("╔══════════════════════════════════════════╗")
            lines.append(f"║  CHI TIẾT LỆNH: {cmd.name.upper():<24}  ║")
            lines.append("╚══════════════════════════════════════════╝")
            lines.append("")
            
            full_desc = cmd.help.strip() if cmd.help else "Chưa có mô tả."
            lines.append(f"📝 Mô tả   : {full_desc}")
            
            # Cú pháp với signature
            syntax = f"{prefix}{cmd.name}"
            if cmd.signature:
                syntax += f" {cmd.signature}"
            lines.append(f"⚙️  Cú pháp : {syntax}")
            
            # Aliases
            if cmd.aliases:
                lines.append(f"🔖 Viết tắt: {', '.join(cmd.aliases)}")
            
            # Thêm examples nếu có
            if cmd.name in ["setvoice", "sv"]:
                lines.append("")
                lines.append("📌 Ví dụ:")
                lines.append(f"   {prefix}setvoice off on  → Mic OFF, Speaker ON")
                lines.append(f"   {prefix}setvoice on off  → Mic ON, Speaker OFF")
                lines.append(f"   {prefix}setvoice on on   → Cả 2 ON")
            elif cmd.name in ["spam"]:
                lines.append("")
                lines.append("📌 Ví dụ:")
                lines.append(f"   {prefix}spam 60 Hello    → Spam 'Hello' mỗi 60s")
                lines.append(f"   {prefix}spam 123456 30 Hi → Spam ở channel 123456")
            elif cmd.name in ["joinvoice", "jv"]:
                lines.append("")
                lines.append("📌 Ví dụ:")
                lines.append(f"   {prefix}jv               → Join voice bạn đang ở")
                lines.append(f"   {prefix}jv 123456789     → Join voice ID cụ thể")
            
            lines.append("```")
            await ctx.send("\n".join(lines))
            return

        # --- TÌM NHÓM ---
        found_cog = None
        for name, cog in self.bot.cogs.items():
            if name.lower() == cmd_name.lower():
                found_cog = cog
                break
        
        if found_cog:
            lines = ["```ini"]
            header = cogs_mapping.get(found_cog.qualified_name, f"📁 {found_cog.qualified_name.upper()}")
            lines.append("╔══════════════════════════════════════════╗")
            lines.append(f"║  {header:<38}  ║")
            lines.append("╚══════════════════════════════════════════╝")
            lines.append("")
            
            for cmd in found_cog.get_commands():
                if not cmd.hidden:
                    desc = cmd.help.strip().split("\n")[0] if cmd.help else "..."
                    aliases = f"({', '.join(cmd.aliases)})" if cmd.aliases else ""
                    cmd_display = f"{prefix}{cmd.name} {aliases}".ljust(28)
                    lines.append(f"  {cmd_display} : {desc}")
            
            lines.append("")
            lines.append(f"💡 Gõ {prefix}help <lệnh> để xem chi tiết")
            lines.append("```")
            await ctx.send("\n".join(lines))
            return

        await ctx.send(f"❌ Không tìm thấy: **{cmd_name}**", delete_after=5)

    @commands.command(name="quickhelp", aliases=["qh"])
    async def quick_help(self, ctx):
        """Quick reference - Lệnh thông dụng"""
        try: await ctx.message.delete()
        except: pass
        
        prefix = ctx.prefix
        lines = ["```ini"]
        lines.append("╔══════════════════════════════════════════╗")
        lines.append("║        [ LỆNH THÔNG DỤNG ]               ║")
        lines.append("╚══════════════════════════════════════════╝")
        lines.append("")
        
        lines.append("[ 🎙️ VOICE ]")
        lines.append(f"  {prefix}jv <id>           : Join voice")
        lines.append(f"  {prefix}lv                : Leave voice")
        lines.append(f"  {prefix}mic               : Toggle mic")
        lines.append(f"  {prefix}speaker           : Toggle speaker")
        lines.append(f"  {prefix}vcs               : Voice status")
        lines.append("")
        
        lines.append("[ 🔥 SPAM ]")
        lines.append(f"  {prefix}spam <delay> <msg>: Spam text")
        lines.append(f"  {prefix}spamfile          : Spam từ file")
        lines.append(f"  {prefix}ss                : Stop spam")
        lines.append("")
        
        lines.append("[ 📜 QUOTES ]")
        lines.append(f"  {prefix}quotes <delay>    : Auto quotes")
        lines.append(f"  {prefix}sq                : Stop quotes")
        lines.append("")
        
        lines.append("[ 📊 SYSTEM ]")
        lines.append(f"  {prefix}status            : Xem status tổng")
        lines.append(f"  {prefix}reload            : Reload cogs")
        lines.append("")
        
        lines.append(f"💡 Gõ {prefix}help để xem toàn bộ lệnh")
        lines.append("```")
        await ctx.send("\n".join(lines))

async def setup(bot):
    await bot.add_cog(Help(bot))
