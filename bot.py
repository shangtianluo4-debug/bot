import discord
from discord.ext import commands
from discord import app_commands
from openai import OpenAI
import os
import json

TOKEN = os.getenv("DISCORD_TOKEN")
OPENAI_KEY = os.getenv("OPENAI_API_KEY")

client = OpenAI(api_key=OPENAI_KEY)

CREATOR_ID = 1442017307332182168

intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents)

# -------------------
# 資料
# -------------------

DATA_FILE = "data.json"

if not os.path.exists(DATA_FILE):
    with open(DATA_FILE, "w") as f:
        json.dump({
            "blacklist": [],
            "whitelist": [],
            "violations": {},
            "punish_channel": None
        }, f)

with open(DATA_FILE) as f:
    data = json.load(f)


def save():
    with open(DATA_FILE, "w") as f:
        json.dump(data, f)


# -------------------
# BOT READY
# -------------------

@bot.event
async def on_ready():
    await bot.tree.sync()
    print(f"{bot.user} 已啟動")


# -------------------
# AI偵測
# -------------------

@bot.event
async def on_message(message):

    if message.author.bot:
        return

    uid = str(message.author.id)

    if uid in data["whitelist"]:
        await bot.process_commands(message)
        return

    try:

        response = client.moderations.create(
            model="omni-moderation-latest",
            input=message.content
        )

        flagged = response.results[0].flagged

        if flagged:

            await message.delete()

            data["violations"][uid] = data["violations"].get(uid, 0) + 1
            save()

            if data["violations"][uid] >= 7:
                data["blacklist"].append(uid)
                save()

            if data["punish_channel"]:
                channel = bot.get_channel(data["punish_channel"])

                if channel:
                    await channel.send(
                        f"⚠️ {message.author.mention} 違規\n次數:{data['violations'][uid]}"
                    )

    except Exception as e:
        print("AI error", e)

    await bot.process_commands(message)


# -------------------
# 領域展開 無量空處
# -------------------

@bot.tree.command(name="domain", description="領域展開 · 無量空處")
@app_commands.describe(
    功能="黑名單/白名單/機器人狀態/後台統計",
    成員="指定成員"
)
async def domain(
    interaction: discord.Interaction,
    功能: str,
    成員: discord.Member = None
):

    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("需要管理員權限", ephemeral=True)
        return

    if 功能 == "機器人狀態":

        latency = round(bot.latency * 1000)

        embed = discord.Embed(
            title="領域展開 · 無量空處",
            description="無限資訊灌入大腦",
            color=0x6f00ff
        )

        embed.add_field(name="AI偵測", value="啟用", inline=True)
        embed.add_field(name="延遲", value=f"{latency}ms", inline=True)

        await interaction.response.send_message(embed=embed)

    elif 功能 == "黑名單":

        if 成員:
            data["blacklist"].append(str(成員.id))
            save()
            await interaction.response.send_message("已加入黑名單")

    elif 功能 == "白名單":

        if 成員:
            data["whitelist"].append(str(成員.id))
            save()
            await interaction.response.send_message("已加入白名單")

    elif 功能 == "後台統計":

        total = sum(data["violations"].values())

        embed = discord.Embed(
            title="後台統計",
            description=f"總違規次數 {total}",
            color=0xff0000
        )

        await interaction.response.send_message(embed=embed)


# -------------------
# 0.2秒領域展開
# -------------------

@bot.tree.command(name="domain02", description="0.2秒的領域展開")
@app_commands.describe(
    功能="違規排行榜/假冒說話/刪除訊息/設置懲罰頻道",
    成員="指定成員",
    訊息="訊息內容",
    數量="刪除數量"
)
async def mini_domain(
    interaction: discord.Interaction,
    功能: str,
    成員: discord.Member = None,
    訊息: str = None,
    數量: int = None
):

    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("需要管理員權限", ephemeral=True)
        return

    if 功能 == "刪除訊息":

        await interaction.channel.purge(limit=數量)
        await interaction.response.send_message(
            f"已刪除 {數量} 則訊息",
            ephemeral=True
        )

    elif 功能 == "設置懲罰頻道":

        data["punish_channel"] = interaction.channel.id
        save()

        await interaction.response.send_message("已設置懲罰頻道")

    elif 功能 == "違規排行榜":

        sorted_users = sorted(
            data["violations"].items(),
            key=lambda x: x[1],
            reverse=True
        )

        text = ""

        for uid, count in sorted_users[:10]:
            text += f"<@{uid}> : {count}次\n"

        embed = discord.Embed(
            title="違規排行榜",
            description=text,
            color=0xff0000
        )

        await interaction.response.send_message(embed=embed)

    elif 功能 == "假冒說話":

        prompt = f"模仿 {成員.display_name} 說: {訊息}"

        ai = client.responses.create(
            model="gpt-4.1-mini",
            input=prompt
        )

        await interaction.response.send_message("完成", ephemeral=True)

        await interaction.channel.send(ai.output_text)


# -------------------
# 虛式茈
# -------------------

@bot.tree.command(name="purple", description="虛式 · 茈")
async def purple(
    interaction: discord.Interaction,
    訊息: str
):

    if interaction.user.id != CREATOR_ID:
        await interaction.response.send_message(
            "只有創作者能使用",
            ephemeral=True
        )
        return

    await interaction.response.send_message("完成", ephemeral=True)

    await interaction.channel.send(訊息)


# -------------------

bot.run(TOKEN)

