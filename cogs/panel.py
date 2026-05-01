import discord
from discord.ext import commands, tasks
from discord import app_commands
import aiosqlite
import time
import psutil

DB = "pro.db"

async def init_panel_db():
    async with aiosqlite.connect(DB) as db:
        await db.execute("""
        CREATE TABLE IF NOT EXISTS panel_config(
            guild_id INTEGER PRIMARY KEY,
            channel_id INTEGER,
            message_id INTEGER,
            auto_update INTEGER DEFAULT 0
        )
        """)
        await db.commit()


class Panel(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.start_time = time.time()
        self.loop.start()

    def cog_unload(self):
        self.loop.cancel()

    @app_commands.command(name="系統面板")
    async def create(self, interaction: discord.Interaction):

        await interaction.response.send_message("📊 建立中...", ephemeral=True)

        embed = await self.build(interaction.guild)
        msg = await interaction.channel.send(embed=embed)

        async with aiosqlite.connect(DB) as db:
            await db.execute("""
            INSERT OR REPLACE INTO panel_config
            VALUES (?,?,?,1)
            """, (interaction.guild.id, interaction.channel.id, msg.id))
            await db.commit()

        await interaction.followup.send("✅ 完成")

    async def build(self, guild):

        bot = self.bot

        latency = round(bot.latency * 1000)
        uptime = int(time.time() - self.start_time)
        users = len(set(bot.get_all_members()))

        process = psutil.Process()
        mem_used = round(process.memory_info().rss / 1024 / 1024, 2)
        mem_total = round(psutil.virtual_memory().total / 1024 / 1024, 2)

        modules = len(bot.cogs)

        tickets = 0
        try:
            async with aiosqlite.connect(DB) as db:
                cur = await db.execute("SELECT COUNT(*) FROM tickets")
                tickets = (await cur.fetchone())[0]
        except:
            pass

        embed = discord.Embed(
            title="📊 機器人系統狀態報告",
            color=0x00bcd4
        )

        embed.description = (
            f"🤖｜機器人名稱：{bot.user}\n"
            f"📊｜目前狀態：🟢線上\n"
            f"🌐｜伺服器數量：{len(bot.guilds)}\n"
            f"👥｜服務用戶數：{users}\n\n"
            f"📡｜系統延遲：{latency}ms\n"
            f"⚡｜執行速度：{uptime}s\n"
            f"🧠｜核心模組：正常\n"
            f"💾｜記憶體使用：{mem_used}MB / {mem_total}MB\n\n"
            f"🔐｜安全系統：啟用中\n"
            f"📋｜功能模組：{modules}\n"
            f"🎫｜總開單數：{tickets}"
        )

        return embed

    @tasks.loop(seconds=15)
    async def loop(self):

        await self.bot.wait_until_ready()

        async with aiosqlite.connect(DB) as db:
            rows = await (await db.execute("""
            SELECT guild_id, channel_id, message_id, auto_update FROM panel_config
            """)).fetchall()

        for gid, cid, mid, auto in rows:

            if not auto:
                continue

            guild = self.bot.get_guild(gid)
            if not guild:
                continue

            channel = guild.get_channel(cid)
            if not channel:
                continue

            try:
                msg = await channel.fetch_message(mid)
                embed = await self.build(guild)
                await msg.edit(embed=embed)
            except:
                pass


async def setup(bot):
    await init_panel_db()
    await bot.add_cog(Panel(bot))
