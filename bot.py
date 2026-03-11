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
        json.dump({"whitelist": [], "blacklist": [], "violations": {}, "punish_channel": None}, f, ensure_ascii=False, indent=4)

def load_data():
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

# ----------------------------
# AI 偵測髒話文字
# ----------------------------
async def detect_text_violation(text):
    # 這裡使用簡單關鍵字 + Groq API 可改進
    violation = False
    reason = ""
    text = text.lower()
    bad_words = ["髒話1","髒話2","詐騙","違規詞"]  # 可擴充
    for word in bad_words:
        if word in text:
            violation = True
            reason = "不當文字"
            break
    return violation, reason

# ----------------------------
# AI 偵測圖片
# ----------------------------
async def detect_image_violation(url):
    headers = {"Authorization": f"Bearer {GROQ_KEY}"}
    payload = {"input": url}
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post("https://api.groq.ai/v1/moderation", headers=headers, json=payload) as resp:
                res = await resp.json()
                flagged = res.get("flagged", False)
                return flagged
    except Exception as e:
        print("Groq API error:", e)
        return False

# ----------------------------
# 違規處理
# ----------------------------
async def punish_user(user: discord.Member, guild: discord.Guild, reason: str):
    data = load_data()
    user_id = str(user.id)
    data["violations"][user_id] = data["violations"].get(user_id,0)+1
    # 達7次自動黑名單
    if data["violations"][user_id] >= 7 and user.id not in data["blacklist"]:
        data["blacklist"].append(user.id)
        reason += "（達7次自動封鎖）"
    save_data(data)

    # 發送懲罰通知
    channel_id = data.get("punish_channel")
    if channel_id:
        channel = bot.get_channel(channel_id)
        if channel:
            embed = discord.Embed(
                title="⚠ 違規通知",
                description=f"使用者 <@{user.id}> 違規：{reason}",
                color=0xff5555,
                timestamp=datetime.now(timezone.utc)
            )
            await channel.send(embed=embed)

# ----------------------------
# 訊息監控
# ----------------------------
@bot.event
async def on_message(message):
    if message.author.bot:
        return
    data = load_data()
    user_id = message.author.id

    # 白名單跳過
    if user_id in data["whitelist"]:
        await bot.process_commands(message)
        return

    # 黑名單直接刪除訊息
    if user_id in data["blacklist"]:
        try: await message.delete()
        except: pass
        return

    # AI 偵測文字
    violation, reason = await detect_text_violation(message.content)

    # AI 偵測圖片
    if not violation and message.attachments:
        for att in message.attachments:
            if att.content_type and "image" in att.content_type:
                flagged = await detect_image_violation(att.url)
                if flagged:
                    violation = True
                    reason = "疑似不當圖片"
                    break

    # 該刪則刪
    if violation:
        try: await message.delete()
        except: pass
        await punish_user(message.author, message.guild, reason)

    await bot.process_commands(message)

# ----------------------------
# /領域展開 · 無量空處
# ----------------------------
@bot.tree.command(name="domain", description="領域展開 · 無量空處")
@app_commands.checks.has_permissions(administrator=True)
async def domain(interaction: discord.Interaction, action: str, target_member: discord.Member=None):
    data = load_data()
    if action == "查看黑白名單":
        wl = ", ".join([f"<@{i}>" for i in data["whitelist"]]) or "無"
        bl = ", ".join([f"<@{i}>" for i in data["blacklist"]]) or "無"
        await interaction.response.send_message(f"白名單: {wl}\n黑名單: {bl}", ephemeral=True)
    elif action == "黑名單加入" and target_member:
        if target_member.id not in data["blacklist"]:
            data["blacklist"].append(target_member.id)
            save_data(data)
            await interaction.response.send_message(f"✅ 已加入黑名單：<@{target_member.id}>", ephemeral=True)
    elif action == "黑名單移除" and target_member:
        if target_member.id in data["blacklist"]:
            data["blacklist"].remove(target_member.id)
            save_data(data)
            await interaction.response.send_message(f"✅ 已移除黑名單：<@{target_member.id}>", ephemeral=True)
    elif action == "白名單加入" and target_member:
        if target_member.id not in data["whitelist"]:
            data["whitelist"].append(target_member.id)
            save_data(data)
            await interaction.response.send_message(f"✅ 已加入白名單：<@{target_member.id}>", ephemeral=True)
    elif action == "白名單移除" and target_member:
        if target_member.id in data["whitelist"]:
            data["whitelist"].remove(target_member.id)
            save_data(data)
            await interaction.response.send_message(f"✅ 已移除白名單：<@{target_member.id}>", ephemeral=True)
    elif action == "機器狀態":
        embed = discord.Embed(
            title="機器狀態",
            color=0x7a5cff,
            description=f"AI偵測: 正常\n延遲: {round(bot.latency*1000)}ms",
            timestamp=datetime.now(timezone.utc)
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

# ----------------------------
# /0.2秒領域展開
# ----------------------------
@bot.tree.command(name="domain02", description="0.2秒領域展開")
@app_commands.checks.has_permissions(administrator=True)
async def mini_domain(interaction: discord.Interaction, action: str, target_member: discord.Member=None, message: str=None, delete_count: int=0, target_channel: discord.TextChannel=None):
    data = load_data()
    if action == "假冒別人說話" and target_member and message:
        await interaction.response.send_message("✅ 已代發訊息", ephemeral=True)
        await interaction.channel.send(message)  # Bot 代發
    elif action == "刪除訊息" and delete_count > 0:
        deleted = await interaction.channel.purge(limit=delete_count)
        await interaction.response.send_message(f"✅ 已刪除 {len(deleted)} 則訊息", ephemeral=True)
    elif action == "設置違規頻道" and target_channel:
        data["punish_channel"] = target_channel.id
        save_data(data)
        await interaction.response.send_message(f"✅ 已設定 {target_channel.mention} 為違規通知頻道", ephemeral=True)
    elif action == "違規排行榜":
        sorted_users = sorted(data["violations"].items(), key=lambda x: x[1], reverse=True)
        desc = "\n".join([f"<@{u}>：{c}次" for u,c in sorted_users[:10]]) or "無違規紀錄"
        embed = discord.Embed(title="違規排行榜", description=desc, color=0x7a5cff, timestamp=datetime.now(timezone.utc))
        await interaction.response.send_message(embed=embed, ephemeral=True)

# ----------------------------
# /虛式茈（創作者專用）
# ----------------------------
@bot.tree.command(name="purple", description="虛式茈（創作者專用）")
async def purple(interaction: discord.Interaction, message: str):
    if interaction.user.id != OWNER_ID:
        await interaction.response.send_message("❌ 你不是創作者，無法使用此指令", ephemeral=True)
        return
    await interaction.response.send_message("✅ 已代發訊息", ephemeral=True)
    await interaction.channel.send(message)

# ----------------------------
# BOT 啟動
# ----------------------------
@bot.event
async def on_ready():
    await bot.tree.sync()
    print(f"Logged in as {bot.user} (五條悟 BOT 已啟動)")

bot.run(TOKEN)
