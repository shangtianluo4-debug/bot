import discord
from discord.ext import commands
import sqlite3
import asyncio
import os
import traceback

intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents)

# ======================
# 💾 DB（穩定版）
# ======================
conn = sqlite3.connect("data.db")

with conn:
    conn.execute("""
    CREATE TABLE IF NOT EXISTS members (
        user_id INTEGER PRIMARY KEY,
        role TEXT,
        approved_by INTEGER
    )
    """)

    conn.execute("""
    CREATE TABLE IF NOT EXISTS tickets (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        type TEXT
    )
    """)

# ======================
# ⚙️ 安全設定區
# ======================
config = {
    "ticket_category": None,
    "ticket_log": None,
    "rules_channel": None,
    "roles": {
        "member": None,
        "examiner": None
    }
}

DEVELOPER_ID = 123456789012345678  # ←一定要改

# ======================
# 🧠 安全函數
# ======================
def safe_get_channel(guild, channel_id):
    if not channel_id:
        return None
    return guild.get_channel(channel_id)

def safe_get_role(guild, role_id):
    if not role_id:
        return None
    return guild.get_role(role_id)

# ======================
# 🚀 Bot 啟動
# ======================
@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")
    await bot.tree.sync()

    # 🔥 UI 永久註冊（避免按鈕失效）
    bot.add_view(TicketView())

# ======================
# 🧯 全域錯誤保護
# ======================
@bot.event
async def on_error(event, *args, **kwargs):
    print("❌ Bot Error:")
    print(traceback.format_exc())

# ======================
# 🎫 Ticket UI（穩定版）
# ======================
class TicketView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="開單", style=discord.ButtonStyle.green)
    async def open(self, interaction: discord.Interaction, button: discord.ui.Button):

        category = safe_get_channel(interaction.guild, config["ticket_category"])

        if not category:
            return await interaction.response.send_message(
                "⚠️ 未設定客服分類",
                ephemeral=True
            )

        channel = await interaction.guild.create_text_channel(
            name=f"ticket-{interaction.user.id}",
            category=category
        )

        with conn:
            conn.execute(
                "INSERT INTO tickets (user_id, type) VALUES (?, ?)",
                (interaction.user.id, "general")
            )

        embed = discord.Embed(
            title="客服單已建立",
            description="請描述你的問題",
            color=0x2ecc71
        )

        await channel.send(embed=embed, view=CloseView())
        await interaction.response.send_message(f"已開單：{channel.mention}", ephemeral=True)

# ======================
# 🔒 關單（穩定版）
# ======================
class CloseView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="關閉客服單", style=discord.ButtonStyle.red)
    async def close(self, interaction: discord.Interaction, button: discord.ui.Button):

        await interaction.response.send_message("⏳ 5秒後關閉", ephemeral=True)

        log = safe_get_channel(interaction.guild, config["ticket_log"])

        if log:
            await log.send(
                embed=discord.Embed(
                    title="客服單關閉",
                    description=f"{interaction.channel.name}",
                    color=0xff0000
                )
            )

        await asyncio.sleep(5)

        try:
            await interaction.channel.delete()
        except:
            pass

# ======================
# 🏆 成員自動記錄（穩定版）
# ======================
@bot.event
async def on_member_update(before, after):

    try:
        role_id = config["roles"].get("member")
        if not role_id:
            return

        role = after.guild.get_role(role_id)
        if not role:
            return

        if role not in before.roles and role in after.roles:

            with conn:
                cursor = conn.execute(
                    "SELECT user_id FROM members WHERE user_id=?",
                    (after.id,)
                )
                if cursor.fetchone():
                    return

                conn.execute(
                    "INSERT INTO members VALUES (?, ?, ?)",
                    (after.id, "member", 0)
                )

            try:
                await after.send("🎉 你已通過戰隊考核")
            except:
                pass

    except Exception as e:
        print("member_update error:", e)

# ======================
# 👥 成員列表
# ======================
@bot.tree.command(name="members")
async def members(interaction: discord.Interaction):

    cursor = conn.execute("SELECT user_id FROM members")
    rows = cursor.fetchall()

    text = ""

    for r in rows:
        m = interaction.guild.get_member(r[0])
        if m:
            text += f"👤 {m.mention}\n"

    embed = discord.Embed(
        title="戰隊成員",
        description=text if text else "無資料",
        color=0xf1c40f
    )

    await interaction.response.send_message(embed=embed)

# ======================
# 📢 開發者公告（安全版）
# ======================
@bot.tree.command(name="broadcast")
async def broadcast(interaction: discord.Interaction, msg: str):

    if interaction.user.id != DEVELOPER_ID:
        return await interaction.response.send_message("❌ 無權限", ephemeral=True)

    embed = discord.Embed(
        title="📢 全域公告",
        description=msg,
        color=0xe74c3c
    )

    for g in bot.guilds:
        for c in g.text_channels:
            try:
                await c.send(embed=embed)
                break
            except:
                continue

    await interaction.response.send_message("已發送")

# ======================
# ⚙️ 設定指令（防呆版）
# ======================
@bot.tree.command(name="set_ticket_category")
async def set_ticket_category(interaction: discord.Interaction, category: discord.CategoryChannel):
    config["ticket_category"] = category.id
    await interaction.response.send_message("✔ 已設定")

@bot.tree.command(name="set_ticket_log")
async def set_ticket_log(interaction: discord.Interaction, channel: discord.TextChannel):
    config["ticket_log"] = channel.id
    await interaction.response.send_message("✔ 已設定")

@bot.tree.command(name="set_member_role")
async def set_member_role(interaction: discord.Interaction, role: discord.Role):
    config["roles"]["member"] = role.id
    await interaction.response.send_message("✔ 已設定")

# ======================
# 🚀 啟動
# ======================
bot.run(os.getenv("TOKEN"))










