import discord
from discord import app_commands, Interaction
from discord.ext import commands
import json, os, datetime

# -----------------------
# 基本設定
# -----------------------
TOKEN = os.getenv("DISCORD_TOKEN")
OWNER_ID = 123456789012345678  # ← 你的 Discord ID
bot = commands.Bot(command_prefix="!", intents=discord.Intents.all())

DATA_FILE = "data.json"

# -----------------------
# 資料存取
# -----------------------
def load_data():
    if not os.path.exists(DATA_FILE):
        return {"blacklist": [], "whitelist": [], "violations": {}, "punish_channel": None}
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

# -----------------------
# Owner 檢查
# -----------------------
def is_owner():
    async def predicate(interaction: Interaction):
        if interaction.user.id != OWNER_ID:
            await interaction.response.send_message("❌ 你無法使用此指令", ephemeral=True)
            return False
        return True
    return app_commands.check(predicate)

# -----------------------
# /domain
# -----------------------
@bot.tree.command(name="domain", description="領域展開 · 無量空處")
@app_commands.describe(action="操作選項：狀態/黑名單/黑名單成員/白名單/白名單成員/統計")
@app_commands.checks.has_permissions(administrator=True)
async def domain(interaction: Interaction, action: str):
    data = load_data()
    embed = discord.Embed(title="領域展開 · 無量空處", color=0x7a5cff, timestamp=datetime.datetime.utcnow())
    
    if action == "狀態":
        embed.add_field(name="AI偵測狀態", value="啟用", inline=True)
        embed.add_field(name="黑名單數量", value=str(len(data["blacklist"])), inline=True)
        embed.add_field(name="白名單數量", value=str(len(data["whitelist"])), inline=True)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    elif action == "黑名單":
        await interaction.response.send_message("請使用 `/domain` + 黑名單成員 來管理黑名單", ephemeral=True)

    elif action == "黑名單成員":
        members = [f"<@{uid}>" for uid in data["blacklist"]]
        embed.add_field(name="黑名單成員", value="\n".join(members) or "無", inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    elif action == "白名單":
        await interaction.response.send_message("請使用 `/domain` + 白名單成員 來管理白名單", ephemeral=True)

    elif action == "白名單成員":
        members = [f"<@{uid}>" for uid in data["whitelist"]]
        embed.add_field(name="白名單成員", value="\n".join(members) or "無", inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    elif action == "統計":
        embed.add_field(name="累積違規統計", value="\n".join([f"<@{uid}>：{cnt}次" for uid, cnt in data["violations"].items()]) or "無", inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    else:
        await interaction.response.send_message("請選擇有效的操作選項", ephemeral=True)

# -----------------------
# /domain 0.2
# -----------------------
@bot.tree.command(name="domain02", description="0.2秒領域展開")
@app_commands.describe(
    action="操作選項：違規排行榜/代替發言/刪除訊息/設置違規頻道",
    target_user="代替發言對象（選擇成員）",
    message="代替發言內容",
    delete_count="刪除訊息數量"
)
@app_commands.checks.has_permissions(administrator=True)
async def domain02(
    interaction: Interaction, 
    action: str, 
    target_user: discord.Member = None, 
    message: str = None, 
    delete_count: int = None
):
    data = load_data()
    embed = discord.Embed(title="0.2秒領域展開", color=0x7a5cff, timestamp=datetime.datetime.utcnow())

    # -------------------------
    # 違規排行榜
    # -------------------------
    if action == "違規排行榜":
        scope_value = "\n".join([f"<@{uid}>：{cnt}次" for uid, cnt in sorted(data["violations"].items(), key=lambda x: x[1], reverse=True)]) or "無違規紀錄"
        embed.add_field(name="違規排行榜", value=scope_value, inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return

    # -------------------------
    # 代替某人說話
    # -------------------------
    elif action == "代替發言":
        if not target_user or not message:
            await interaction.response.send_message("❌ 請指定使用者和訊息內容", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        # Bot 代替目標使用者發訊息，不顯示操作者
        await interaction.channel.send(message)
        await interaction.followup.send(f"✅ 已代替 <@{target_user.id}> 發言", ephemeral=True)
        return

    # -------------------------
    # 刪除訊息
    # -------------------------
    elif action == "刪除訊息":
        if not delete_count or delete_count < 1:
            await interaction.response.send_message("❌ 請指定要刪除的訊息數量", ephemeral=True)
            return
        deleted = await interaction.channel.purge(limit=delete_count)
        await interaction.response.send_message(f"✅ 已刪除 {len(deleted)} 則訊息", ephemeral=True)
        return

    # -------------------------
    # 設置違規懲罰通知頻道
    # -------------------------
    elif action == "設置違規頻道":
        data["punish_channel"] = interaction.channel.id
        save_data(data)
        await interaction.response.send_message(f"✅ 已將本頻道設為違規懲罰通知頻道", ephemeral=True)
        return

    else:
        await interaction.response.send_message("❌ 請選擇有效操作選項", ephemeral=True)

# -----------------------
# /purple
# -----------------------
@bot.tree.command(name="purple", description="虛式 · 茈：讓機器人幫你說話")
@is_owner()
async def purple(interaction: Interaction, message: str):
    await interaction.response.defer(ephemeral=True)
    await interaction.channel.send(message)

# -----------------------
# 啟動 BOT
# -----------------------
@bot.event
async def on_ready():
    print(f"已登入：{bot.user}")
    await bot.tree.sync()

bot.run(TOKEN)
