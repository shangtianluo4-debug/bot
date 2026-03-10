import discord
from discord.ext import commands
from discord import app_commands, Interaction
from openai import OpenAI
import os
import json
import datetime
import time

# -------------------------------
# 初始化
# -------------------------------
intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents)

# OpenAI Client
openai_api_key = os.getenv("OPENAI_API_KEY")
client = OpenAI(api_key=openai_api_key)

# 載入資料
if os.path.exists("data.json"):
    with open("data.json", "r") as f:
        data = json.load(f)
else:
    data = {"whitelist": [], "blacklist": [], "violations": {}, "punish_channel_id": None}

# 詐騙字詞清單
scam_words = ["discord.gift/", "nitro", "free money", "bit.ly/"]

# 你的 Discord ID（/say 專用）
MY_USER_ID = 1442017307332182168  # <-- 改成你本人 ID

# -------------------------------
# 速率限制 (避免 429)
# -------------------------------
last_checked = {}  # user_id -> timestamp
COOLDOWN = 3  # 秒，同一使用者短時間內只檢測一次

# -------------------------------
# 權限檢查
# -------------------------------
def is_admin(interaction: Interaction):
    return interaction.user.guild_permissions.administrator

# -------------------------------
# /say 指令（僅限本人）
# -------------------------------
@bot.tree.command(name="say", description="機器人代替你發訊息（僅機器創作者本人可使用）")
@app_commands.describe(message="你想讓機器人說的內容")
async def say(interaction: Interaction, message: str):
    if interaction.user.id != MY_USER_ID:
        await interaction.response.send_message("你沒有權限使用這個指令！", ephemeral=True)
        return
    await interaction.response.send_message("訊息已發送！", ephemeral=True)
    await interaction.channel.send(message)

# -------------------------------
# 黑白名單管理（管理員專用）
# -------------------------------
@bot.tree.command(name="whitelist", description="管理白名單（需管理員）")
@app_commands.describe(action="add 或 remove", member="要操作的使用者")
async def whitelist(interaction: Interaction, action: str, member: discord.Member):
    if not is_admin(interaction):
        await interaction.response.send_message("你沒有權限使用此指令！", ephemeral=True)
        return
    user_id = member.id
    if action.lower() == "add":
        if user_id not in data["whitelist"]:
            data["whitelist"].append(user_id)
            if user_id in data["blacklist"]:
                data["blacklist"].remove(user_id)
            await interaction.response.send_message(f"{member} 已加入白名單", ephemeral=True)
        else:
            await interaction.response.send_message(f"{member} 已經在白名單", ephemeral=True)
    elif action.lower() == "remove":
        if user_id in data["whitelist"]:
            data["whitelist"].remove(user_id)
            await interaction.response.send_message(f"{member} 已從白名單移除", ephemeral=True)
        else:
            await interaction.response.send_message(f"{member} 不在白名單", ephemeral=True)
    else:
        await interaction.response.send_message("action 只能是 add 或 remove", ephemeral=True)
    with open("data.json", "w") as f:
        json.dump(data, f, indent=4)

@bot.tree.command(name="blacklist", description="管理黑名單（需管理員）")
@app_commands.describe(action="add 或 remove", member="要操作的使用者")
async def blacklist(interaction: Interaction, action: str, member: discord.Member):
    if not is_admin(interaction):
        await interaction.response.send_message("你沒有權限使用此指令！", ephemeral=True)
        return
    user_id = member.id
    if action.lower() == "add":
        if user_id not in data["blacklist"]:
            data["blacklist"].append(user_id)
            if user_id in data["whitelist"]:
                data["whitelist"].remove(user_id)
            await interaction.response.send_message(f"{member} 已加入黑名單", ephemeral=True)
        else:
            await interaction.response.send_message(f"{member} 已經在黑名單", ephemeral=True)
    elif action.lower() == "remove":
        if user_id in data["blacklist"]:
            data["blacklist"].remove(user_id)
            await interaction.response.send_message(f"{member} 已從黑名單移除", ephemeral=True)
        else:
            await interaction.response.send_message(f"{member} 不在黑名單", ephemeral=True)
    else:
        await interaction.response.send_message("action 只能是 add 或 remove", ephemeral=True)
    with open("data.json", "w") as f:
        json.dump(data, f, indent=4)

# -------------------------------
# 設置懲罰通知頻道（管理員專用）
# -------------------------------
@bot.tree.command(name="set_punish_channel", description="設置懲罰通知頻道（需管理員）")
@app_commands.describe(channel="要用來接收懲罰通知的頻道")
async def set_punish_channel(interaction: Interaction, channel: discord.TextChannel):
    if not is_admin(interaction):
        await interaction.response.send_message("你沒有權限使用此指令！", ephemeral=True)
        return
    data["punish_channel_id"] = channel.id
    with open("data.json", "w") as f:
        json.dump(data, f, indent=4)
    await interaction.response.send_message(f"已將懲罰通知頻道設為 {channel.mention}", ephemeral=True)

# -------------------------------
# 懲罰功能
# -------------------------------
async def punish(member, guild, reason):
    user_id = str(member.id)
    data["violations"][user_id] = data["violations"].get(user_id, 0) + 1

    # 違規達 7 次自動加入黑名單
    if data["violations"][user_id] >= 7:
        if member.id not in data["blacklist"]:
            data["blacklist"].append(member.id)

    # 發送懲罰通知
    punish_channel = None
    if "punish_channel_id" in data and data["punish_channel_id"]:
        punish_channel = guild.get_channel(data["punish_channel_id"])
    if punish_channel:
        await punish_channel.send(f"{member.mention} 違規: {reason} (第 {data['violations'][user_id]} 次)")

    # 暫時禁言 5 分鐘
    try:
        await member.edit(timed_out_until=datetime.datetime.utcnow() + datetime.timedelta(minutes=5))
    except:
        pass

    with open("data.json", "w") as f:
        json.dump(data, f, indent=4)

# -------------------------------
# 訊息監控
# -------------------------------
@bot.event
async def on_message(message):
    if message.author.bot:
        return

    now = time.time()
    user_id = message.author.id

    # 白名單無敵
    if user_id in data["whitelist"]:
        await bot.process_commands(message)
        return

    # 黑名單封鎖
    if user_id in data["blacklist"]:
        try: await message.delete()
        except: pass
        return

    # 檢查冷卻時間 (避免 429)
    if user_id in last_checked and now - last_checked[user_id] < COOLDOWN:
        await bot.process_commands(message)
        return
    last_checked[user_id] = now

    text = message.content
    violation = False
    reason = ""

    # 詐騙偵測
    for word in scam_words:
        if word.lower() in text.lower():
            violation = True
            reason = "詐騙連結"
            break

    # AI文字偵測
    if text and not violation:
        try:
            response = await client.moderations.create(
                model="omni-moderation-latest",
                input=text
            )
            results = response["results"] if "results" in response else response.results
            if results[0]["flagged"]:
                violation = True
                reason = "不當語言"
        except Exception as e:
            print("Moderation API error:", e)

    # AI圖片偵測
    if message.attachments and not violation:
        for attachment in message.attachments:
            if attachment.content_type and "image" in attachment.content_type:
                image_url = attachment.url
                try:
                    response = await client.moderations.create(
                        model="omni-moderation-latest",
                        input=f"檢查這張圖片是否含有不當或色情內容: {image_url}"
                    )
                    results = response["results"] if "results" in response else response.results
                    if results[0]["flagged"]:
                        violation = True
                        reason = "疑似不當圖片"
                        break
                except Exception as e:
                    print("Moderation API image error:", e)

    # 處理違規
    if violation:
        try:
            await message.delete()
        except:
            pass
        await punish(message.author, message.guild, reason)

    await bot.process_commands(message)

# -------------------------------
# 啟動 Bot
# -------------------------------
@bot.event
async def on_ready():
    await bot.tree.sync()
    print(f"Bot 已啟動: {bot.user}")

bot.run(os.getenv("DISCORD_TOKEN"))
