import discord
from discord.ext import commands
from discord import app_commands
from discord.ui import View, Button
import aiosqlite
import datetime
import io

DB = "pro.db"

# ================= DB INIT =================
async def init_ticket_db():
    async with aiosqlite.connect(DB) as db:
        await db.execute("""
        CREATE TABLE IF NOT EXISTS ticket_settings(
            guild_id INTEGER PRIMARY KEY,
            category_id INTEGER,
            log_channel INTEGER,
            open_msg TEXT
        )
        """)

        await db.execute("""
        CREATE TABLE IF NOT EXISTS tickets(
            guild_id INTEGER,
            user_id INTEGER,
            channel_id INTEGER,
            created_at TEXT
        )
        """)

        await db.commit()

# ================= 備份 =================
async def backup_channel(channel):
    messages = []

    async for msg in channel.history(limit=None, oldest_first=True):
        time = msg.created_at.strftime("%Y-%m-%d %H:%M")
        messages.append(f"[{time}] {msg.author}: {msg.content}")

    data = "\n".join(messages)

    return discord.File(
        io.BytesIO(data.encode()),
        filename=f"{channel.name}.txt"
    )

# ================= VIEW =================
class TicketView(View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="📩 開啟考核單", style=discord.ButtonStyle.green)
    async def open_ticket(self, interaction: discord.Interaction, button: Button):

        guild = interaction.guild
        user = interaction.user

        async with aiosqlite.connect(DB) as db:

            # 🔥 防重複開單
            cur = await db.execute("""
            SELECT * FROM tickets
            WHERE guild_id=? AND user_id=?
            """, (guild.id, user.id))

            if await cur.fetchone():
                return await interaction.response.send_message(
                    "❌ 你已經有開啟中的考核單",
                    ephemeral=True
                )

            # 設定
            cur = await db.execute("""
            SELECT category_id, open_msg FROM ticket_settings WHERE guild_id=?
            """, (guild.id,))
            data = await cur.fetchone()

        # 分類
        category = None
        if data and data[0]:
            category = guild.get_channel(data[0])

        if not isinstance(category, discord.CategoryChannel):
            category = await guild.create_category("考核單")

        # 建立頻道
        channel = await guild.create_text_channel(
            name=f"考核-{user.name}",
            category=category
        )

        # 權限（只有本人 + 管理員）
        await channel.set_permissions(guild.default_role, view_channel=False)
        await channel.set_permissions(user, view_channel=True, send_messages=True)

        # 訊息
        msg = data[1] if data and data[1] else "考官很快會回覆你"

        embed = discord.Embed(
            title="🎫 考核單已建立",
            description=msg,
            color=0x2ecc71
        )

        await channel.send(
            content=user.mention,
            embed=embed,
            view=CloseView()
        )

        # 記錄
        async with aiosqlite.connect(DB) as db:
            await db.execute("""
            INSERT INTO tickets VALUES (?,?,?,?)
            """, (guild.id, user.id, channel.id, str(datetime.datetime.now())))
            await db.commit()

        await interaction.response.send_message("✅ 已開啟考核單", ephemeral=True)


class CloseView(View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="🔒 關閉考核單", style=discord.ButtonStyle.red)
    async def close_ticket(self, interaction: discord.Interaction, button: Button):

        channel = interaction.channel
        guild = interaction.guild
        user = interaction.user

        async with aiosqlite.connect(DB) as db:
            cur = await db.execute("""
            SELECT user_id, created_at FROM tickets
            WHERE guild_id=? AND channel_id=?
            """, (guild.id, channel.id))
            data = await cur.fetchone()

        if not data:
            return await interaction.response.send_message("❌ 找不到資料", ephemeral=True)

        owner_id, created_at = data

        # 權限限制
        if user.id != owner_id and not user.guild_permissions.administrator:
            return await interaction.response.send_message("❌ 沒有權限", ephemeral=True)

        # 計算時間
        created_time = datetime.datetime.fromisoformat(created_at)
        duration = datetime.datetime.now() - created_time

        # 備份
        file = await backup_channel(channel)

        async with aiosqlite.connect(DB) as db:
            cur = await db.execute("""
            SELECT log_channel FROM ticket_settings WHERE guild_id=?
            """, (guild.id,))
            row = await cur.fetchone()

        if row and row[0]:
            log_ch = guild.get_channel(row[0])
            if log_ch:
                await log_ch.send(
                    content=f"🔒 關閉：{channel.name}\n⏱ 處理時間：{duration}",
                    file=file
                )

        # 刪除紀錄
        async with aiosqlite.connect(DB) as db:
            await db.execute("""
            DELETE FROM tickets WHERE channel_id=?
            """, (channel.id,))
            await db.commit()

        await interaction.response.send_message("❌ 已關閉", ephemeral=True)
        await channel.delete()


# ================= COG =================
class Ticket(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="考核單")
    async def panel(self, interaction: discord.Interaction):

        embed = discord.Embed(
            title="🎫 考核系統",
            description="點擊下方按鈕開單",
            color=0x3498db
        )

        await interaction.response.send_message(embed=embed, view=TicketView())

    @app_commands.command(name="設定考核系統")
    async def setup(self, interaction: discord.Interaction, log_channel: discord.TextChannel):

        async with aiosqlite.connect(DB) as db:
            await db.execute("""
            INSERT OR REPLACE INTO ticket_settings(guild_id, log_channel)
            VALUES (?,?)
            """, (interaction.guild.id, log_channel.id))
            await db.commit()

        await interaction.response.send_message("✅ 設定完成", ephemeral=True)


async def setup(bot):
    await init_ticket_db()
    await bot.add_cog(Ticket(bot))
