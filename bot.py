import discord
from discord.ext import commands
from discord import app_commands, Interaction
from openai import OpenAI
import os
import json
import datetime

# -------------------------------
# 初始化
# -------------------------------
intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents)

# OpenAI Client
openai_api_key = os.getenv("OPENAI_API_KEY")
client = OpenAI(api_key=openai_api_key)

# 載入黑白名單資料
if os.path.exists("data.json"):
    with open("data.json", "r") as f:
        data = json.load(f)
else:
    data = {"whitelist": [], "blacklist": [], "violations": {}}

# 詐騙字詞清單
scam_words = ["discord.gift/", "nitro", "free money", "bit.ly/"]

# -------------------------------
# /say 指令
# -------------------------------
@bot.tree.command(name="say", description="機器人代替你發訊息")
@app_commands.describe(message="你想讓機器人說的內容")
async def say(interaction: Interaction, message: str):
    await interaction.response.send_message("訊息已發送！", ephemeral=True)
    await interaction.channel.send(message)

# -------------------------------
# 黑白名單管理指令
# -------------------------------
@bot.tree.command(name="whitelist", description="管理白名單")
@app_commands.describe(action="add 或 remove", member="要操作的使用者")
async def whitelist(interaction: Interaction, action: str, member: discord.Member):
    user_id = member.id
    if action.lower() == "add":
        if user_id not in data["whitelist"]:
            data["whitelist"].append(user_id)
            # 移除黑名單
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

    # 存檔
    with open("data.json", "w") as f:
        json.dump(data, f, indent=4)

@bot.tree.command(name="blacklist", description="管理黑名單")
@app_commands.describe(action="add 或 remove", member="要操作的使用者")
async def blacklist(interaction: Interaction, action: str, member: discord.Member):
    user_id = member.id
    if action.lower() == "add":
        if user_id not in data["blacklist"]:
            data["blacklist"].append(user_id)
            # 移除白名單
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

    # 存檔
    with open("data.json", "w") as f:
        json.dump(data, f, indent=4)

# -------------------------------
# 設置懲罰通知頻道
# -------------------------------
@bot.tree.command(name="set_punish_channel", description="設置懲罰通知發送頻道")
@app_commands.describe(channel="要用來接收懲罰通知的頻道")
async def set_punish_channel(interaction: Interaction, channel: discord.TextChannel):
    # 儲存頻道 ID
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

    # 找到懲罰頻道
    punish_channel = None
    if "punish_channel_id" in data:
        punish_channel = guild.get_channel(data["punish_channel_id"])
    if punish_channel:
        await punish_channel.send(f"{member.mention} 違規: {reason} (第 {data['violations'][user_id]} 次)")

    # 暫時禁言
    try:
        await member.edit(timed_out_until=datetime.datetime.utcnow() + datetime.timedelta(minutes=5))
    except:
        pass

    # 儲存資料
    with open("data.json", "w") as f:
        json.dump(data, f, indent=4)

# -------------------------------
# 訊息監控
# -------------------------------
@bot.event
async def on_message(message):
    if message.author.bot:
        return

    # 白名單無敵
    if message.author.id in data["whitelist"]:
        await bot.process_commands(message)
        return

    # 黑名單封鎖
    if message.author.id in data["blacklist"]:
        try:
            await message.delete()
        except:
            pass
        return

    text = message.content.lower()
    violation = False
    reason = ""

    # 詐騙偵測
    for word in scam_words:
        if word in text:
            violation = True
            reason = "詐騙連結"
            break

    # AI文字偵測
    if text and not violation:
        try:
            response = client.moderations.create(
                model="omni-moderation-latest",
                input=text
            )
            results = response["results"] if "results" in response else response.results
            if results[0]["flagged"]:
                violation = True
                reason = "不當語言"
        except Exception as e:
            print("Moderation API error:", e)

    # 圖片偵測
    if message.attachments and not violation:
        for attachment in message.attachments:
            if attachment.content_type and "image" in attachment.content_type:
                violation = True
                reason = "疑似不當圖片"
                break

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





