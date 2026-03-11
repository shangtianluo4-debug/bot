import discord
from discord.ext import commands
from discord import app_commands
from datetime import datetime, timezone
import json
import os
import aiohttp

# ----------------------------
# 基本設定
# ----------------------------
TOKEN = os.getenv("DISCORD_TOKEN")
GROQ_KEY = os.getenv("GROQ_API_KEY")
OWNER_ID = 1442017307332182168  # 你自己
DATA_FILE = "data.json"

intents = discord.Intents.default()
intents.messages = True
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# ----------------------------
# 資料管理
# ----------------------------
if not os.path.exists(DATA_FILE):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump({"白名單": [], "黑名單": [], "違規次數": {}, "懲罰頻道": None}, f, ensure_ascii=False, indent=4)

def load_data():
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

# ----------------------------
# AI 偵測髒話文字
# ----------------------------
async def 偵測文字違規(text):
    違規 = False
    原因 = ""
    text = text.lower()
    不當詞 = ["髒話1","髒話2","詐騙","違規詞"]  # 可擴充
    for word in 不當詞:
        if word in text:
            違規 = True
            原因 = "不當文字"
            break
    return 違規, 原因

# ----------------------------
# AI 偵測圖片
# ----------------------------
async def 偵測圖片違規(url):
    headers = {"Authorization": f"Bearer {GROQ_KEY}"}
    payload = {"input": url}
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post("https://api.groq.ai/v1/moderation", headers=headers, json=payload) as resp:
                res = await resp.json()
                return res.get("flagged", False)
    except Exception as e:
        print("Groq API 錯誤:", e)
        return False

# ----------------------------
# 違規處理
# ----------------------------
async def 處理違規(user: discord.Member, guild: discord.Guild, 原因: str):
    data = load_data()
    user_id = str(user.id)
    data["違規次數"][user_id] = data["違規次數"].get(user_id,0)+1

    # 達7次自動加入黑名單
    if data["違規次數"][user_id] >= 7 and user.id not in data["黑名單"]:
        data["黑名單"].append(user.id)
        原因 += "（達7次自動封鎖）"
    save_data(data)

    # 發送懲罰通知
    頻道ID = data.get("懲罰頻道")
    if 頻道ID:
        頻道 = bot.get_channel(頻道ID)
        if 頻道:
            embed = discord.Embed(
                title="⚠ 違規通知",
                description=f"使用者 <@{user.id}> 違規：{原因}",
                color=0xff5555,
                timestamp=datetime.now(timezone.utc)
            )
            await 頻道.send(embed=embed)

# ----------------------------
# 訊息監控
# ----------------------------
@bot.event
async def on_message(message):
    if message.author.bot:
        return
    data = load_data()
    user_id = message.author.id

    # 白名單跳過偵測
    if user_id in data["白名單"]:
        await bot.process_commands(message)
        return

    # 黑名單訊息刪除
    if user_id in data["黑名單"]:
        try: await message.delete()
        except: pass
        return

    # 偵測文字
    違規, 原因 = await 偵測文字違規(message.content)

    # 偵測圖片
    if not 違規 and message.attachments:
        for att in message.attachments:
            if att.content_type and "image" in att.content_type:
                flag = await 偵測圖片違規(att.url)
                if flag:
                    違規 = True
                    原因 = "疑似不當圖片"
                    break

    # 違規處理
    if 違規:
        try: await message.delete()
        except: pass
        await 處理違規(message.author, message.guild, 原因)

    await bot.process_commands(message)

# ----------------------------
# /領域展開 · 無量空處
# ----------------------------
@bot.tree.command(name="領域展開", description="領域展開 · 無量空處")
@app_commands.checks.has_permissions(administrator=True)
async def 領域展開(interaction: discord.Interaction, 功能: str, 目標: discord.Member=None):
    data = load_data()
    if 功能 == "查看黑白名單":
        wl = ", ".join([f"<@{i}>" for i in data["白名單"]]) or "無"
        bl = ", ".join([f"<@{i}>" for i in data["黑名單"]]) or "無"
        await interaction.response.send_message(f"白名單: {wl}\n黑名單: {bl}", ephemeral=True)
    elif 功能 == "黑名單加入" and 目標:
        if 目標.id not in data["黑名單"]:
            data["黑名單"].append(目標.id)
            save_data(data)
            await interaction.response.send_message(f"✅ 已加入黑名單：<@{目標.id}>", ephemeral=True)
    elif 功能 == "黑名單移除" and 目標:
        if 目標.id in data["黑名單"]:
            data["黑名單"].remove(目標.id)
            save_data(data)
            await interaction.response.send_message(f"✅ 已移除黑名單：<@{目標.id}>", ephemeral=True)
    elif 功能 == "白名單加入" and 目標:
        if 目標.id not in data["白名單"]:
            data["白名單"].append(目標.id)
            save_data(data)
            await interaction.response.send_message(f"✅ 已加入白名單：<@{目標.id}>", ephemeral=True)
    elif 功能 == "白名單移除" and 目標:
        if 目標.id in data["白名單"]:
            data["白名單"].remove(目標.id)
            save_data(data)
            await interaction.response.send_message(f"✅ 已移除白名單：<@{目標.id}>", ephemeral=True)
    elif 功能 == "機器人狀態":
        embed = discord.Embed(
            title="機器人狀態",
            color=0x7a5cff,
            description=f"AI偵測: 正常\n延遲: {round(bot.latency*1000)}ms",
            timestamp=datetime.now(timezone.utc)
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

# ----------------------------
# /0.2秒領域展開
# ----------------------------
@bot.tree.command(name="0_2秒領域展開", description="0.2秒領域展開")
@app_commands.checks.has_permissions(administrator=True)
async def 秒領域(interaction: discord.Interaction, 功能: str, 目標: discord.Member=None, 訊息: str=None, 刪除數量: int=0, 頻道: discord.TextChannel=None):
    data = load_data()
    if 功能 == "假冒別人說話" and 目標 and 訊息:
        await interaction.response.send_message("✅ 已代發訊息", ephemeral=True)
        await interaction.channel.send(訊息)
    elif 功能 == "刪除訊息" and 刪除數量 > 0:
        deleted = await interaction.channel.purge(limit=刪除數量)
        await interaction.response.send_message(f"✅ 已刪除 {len(deleted)} 則訊息", ephemeral=True)
    elif 功能 == "設置違規頻道" and 頻道:
        data["懲罰頻道"] = 頻道.id
        save_data(data)
        await interaction.response.send_message(f"✅ 已設定 {頻道.mention} 為違規通知頻道", ephemeral=True)
    elif 功能 == "違規排行榜":
        sorted_users = sorted(data["違規次數"].items(), key=lambda x: x[1], reverse=True)
        desc = "\n".join([f"<@{u}>：{c}次" for u,c in sorted_users[:10]]) or "無違規紀錄"
        embed = discord.Embed(title="違規排行榜", description=desc, color=0x7a5cff, timestamp=datetime.now(timezone.utc))
        await interaction.response.send_message(embed=embed, ephemeral=True)

# ----------------------------
# /虛式茈（創作者專用）
# ----------------------------
@bot.tree.command(name="虛式茈", description="虛式茈（創作者專用）")
async def 虛式茈(interaction: discord.Interaction, 訊息: str):
    if interaction.user.id != OWNER_ID:
        await interaction.response.send_message("❌ 你不是創作者，無法使用此指令", ephemeral=True)
        return
    await interaction.response.send_message("✅ 已代發訊息", ephemeral=True)
    await interaction.channel.send(訊息)

# ----------------------------
# BOT 啟動
# ----------------------------
@bot.event
async def on_ready():
    await bot.tree.sync()
    print(f"Logged in as {bot.user} (五條悟 BOT 已啟動)")

bot.run(TOKEN)
