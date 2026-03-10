import discord
from discord.ext import commands
from discord import app_commands
from openai import OpenAI
import os
import json
import datetime

TOKEN = os.getenv("DISCORD_TOKEN")
OPENAI_KEY = os.getenv("OPENAI_API_KEY")

client = OpenAI(api_key=OPENAI_KEY)

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)

DATA_FILE = "data.json"

# ------------------
# 資料
# ------------------

if os.path.exists(DATA_FILE):
    with open(DATA_FILE) as f:
        data = json.load(f)
else:
    data = {
        "blacklist": [],
        "whitelist": [],
        "warnings": {},
        "log_channel": None
    }

def save():
    with open(DATA_FILE, "w") as f:
        json.dump(data, f)

# ------------------
# Bot啟動
# ------------------

@bot.event
async def on_ready():
    await bot.tree.sync()
    print(f"Bot 已上線 {bot.user}")

# ------------------
# !say 偽裝說話
# ------------------

@bot.command()
async def say(ctx, member: discord.Member, *, text):

    webhook = await ctx.channel.create_webhook(name=member.display_name)

    await webhook.send(
        content=text,
        username=member.display_name,
        avatar_url=member.display_avatar.url
    )

    await webhook.delete()
    await ctx.message.delete()

# ------------------
# 設置log頻道
# ------------------

@bot.tree.command(name="setlog",description="設置違規懲罰訊息頻道")
async def setlog(interaction: discord.Interaction, channel: discord.TextChannel):

    data["log_channel"] = channel.id
    save()

    await interaction.response.send_message("懲罰頻道設定成功")

# ------------------
# 黑名單
# ------------------

@bot.tree.command(name="blacklist",description="將成員加入黑名單")
async def blacklist(interaction: discord.Interaction, member: discord.Member):

    role = discord.utils.get(interaction.guild.roles, name="Blacklisted")

    if not role:
        role = await interaction.guild.create_role(name="Blacklisted")

        for channel in interaction.guild.channels:
            await channel.set_permissions(role, view_channel=False)

    await member.add_roles(role)

    data["blacklist"].append(member.id)
    save()

    await interaction.response.send_message("已加入黑名單")

# ------------------
# 白名單
# ------------------

@bot.tree.command(name="whitelist",description="將成員加入白名單")
async def whitelist(interaction: discord.Interaction, member: discord.Member):

    data["whitelist"].append(member.id)
    save()

    await interaction.response.send_message("已加入白名單")

# ------------------
# 詐騙關鍵字
# ------------------

scam_words = [
    "free nitro",
    "discord nitro",
    "steam giveaway",
    "bit.ly",
    "grabify",
    "airdrop"
]

# ------------------
# 違規處理
# ------------------

async def punish(member, guild, reason):

    uid = str(member.id)

    if uid not in data["warnings"]:
        data["warnings"][uid] = 0

    data["warnings"][uid] += 1
    warn = data["warnings"][uid]

    save()

    log_channel = None

    if data["log_channel"]:
        log_channel = bot.get_channel(data["log_channel"])

    # 3次禁言
    if warn == 3:
        await member.timeout(datetime.timedelta(minutes=10))

    # 5次禁言
    if warn == 5:
        await member.timeout(datetime.timedelta(hours=1))

    # 7次黑名單
    if warn >= 7:

        role = discord.utils.get(guild.roles, name="Blacklisted")

        if not role:
            role = await guild.create_role(name="Blacklisted")

            for channel in guild.channels:
                await channel.set_permissions(role, view_channel=False)

        await member.add_roles(role)

        data["blacklist"].append(member.id)
        save()

    if log_channel:
        await log_channel.send(
            f"{member} 違規\n原因: {reason}\n違規次數: {warn}"
        )

@bot.event
async def on_message(message):

    if message.author.bot:
        return

    # 白名單無敵
    if message.author.id in data["whitelist"]:
        await bot.process_commands(message)
        return

    text = message.content.lower()
    violation = False
    reason = ""

    # 詐騙偵測
    for word in scam_words:
        if word in text:
            violation = True
            reason = "詐騙連結"
            break  # 一旦偵測到就不用再檢查文字

    # AI文字偵測
    if text and not violation:
        try:
            response = client.moderations.create(
                model="omni-moderation-latest",
                input=text
            )
            # 兼容新版 SDK
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
        await message.delete()
        await punish(message.author, message.guild, reason)

    # 最後一定要處理指令
    await bot.process_commands(message)
bot.run(TOKEN)

