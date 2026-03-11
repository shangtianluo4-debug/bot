import discord
from discord.ext import commands
from discord import app_commands, Interaction
from openai import OpenAI
import os
import json

# ----------------------
# 初始化
# ----------------------
intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents)
client = OpenAI(
    api_key=os.getenv("GROQ_API_KEY"),
    base_url="https://api.groq.com/openai/v1"
)

OWNER_ID = 123456789012345678  # 你的 Discord ID
DATA_FILE = "data.json"

# ----------------------
# 輔助函數
# ----------------------
def load_data():
    if not os.path.exists(DATA_FILE):
        return {"blacklist": [], "whitelist": [], "violations": {}, "punish_channel": None}
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

data = load_data()

async def punish(member: discord.Member, reason: str):
    data = load_data()
    # 違規次數 +1
    data["violations"][str(member.id)] = data["violations"].get(str(member.id), 0) + 1
    save_data(data)

    # 發送懲罰通知
    channel_id = data.get("punish_channel")
    if channel_id:
        channel = bot.get_channel(channel_id)
        if channel:
            embed = discord.Embed(
                title="⚠ 咒術警告",
                description=f"使用者：{member.mention}\n原因：{reason}\n累積次數：{data['violations'][str(member.id)]}",
                color=0xff5555
            )
            await channel.send(embed=embed)

    # 違規達7次自動黑名單
    if data["violations"][str(member.id)] >= 7:
        if member.id not in data["blacklist"]:
            data["blacklist"].append(member.id)
            save_data(data)
            if channel_id:
                embed = discord.Embed(
                    title="⚫ 無量空處吞噬",
                    description=f"{member.mention} 已被列入黑名單",
                    color=0x5500ff
                )
                await channel.send(embed=embed)

# ----------------------
# 領域展開 /domain
# ----------------------
@bot.tree.command(name="domain", description="領域展開 · 無量空處")
@app_commands.checks.has_permissions(administrator=True)
async def domain(interaction: Interaction, action: str = None):
    data = load_data()
    embed = discord.Embed(title="領域展開 · 無量空處", color=0x7a5cff)
    if action == "status":
        embed.add_field(name="AI偵測狀態", value="啟用", inline=True)
        embed.add_field(name="黑名單數量", value=str(len(data["blacklist"])), inline=True)
        embed.add_field(name="白名單數量", value=str(len(data["whitelist"])), inline=True)
        await interaction.response.send_message(embed=embed, ephemeral=True)
    elif action == "blacklist":
        embed.add_field(name="黑名單", value="\n".join([f"<@{uid}>" for uid in data["blacklist"]]) or "無", inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)
    elif action == "whitelist":
        embed.add_field(name="白名單", value="\n".join([f"<@{uid}>" for uid in data["whitelist"]]) or "無", inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)
    else:
        await interaction.response.send_message("請選擇 action: status / blacklist / whitelist", ephemeral=True)

# ----------------------
# 0.2秒領域 /domain02
# ----------------------
@bot.tree.command(name="domain02", description="0.2秒的領域展開")
@app_commands.checks.has_permissions(administrator=True)
async def domain02(interaction: Interaction, action: str = None, member: discord.Member = None, amount: int = 1, channel: discord.TextChannel = None, message: str = None):
    data = load_data()
    # 違規排行榜
    if action == "leaderboard":
        sorted_list = sorted(data["violations"].items(), key=lambda x: x[1], reverse=True)[:10]
        embed = discord.Embed(title="🏆 違規排行榜", color=0xffaa00)
        embed.description = "\n".join([f"<@{uid}> — {cnt}次" for uid, cnt in sorted_list]) or "無紀錄"
        await interaction.response.send_message(embed=embed)
    # 假冒說話
    elif action == "mimic" and member and message:
        prompt = f"用最自然方式說：{message}"
        try:
            ai = client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[{"role": "user", "content": prompt}]
            )
            text = ai.choices[0].message.content
        except Exception as e:
            print("AI error:", e)
            text = message  # 當AI掛掉就直接發原文
        await interaction.response.send_message("完成", ephemeral=True)
        await interaction.channel.send(text)
    # 刪除訊息
    elif action == "purge":
        deleted = await interaction.channel.purge(limit=amount)
        await interaction.response.send_message(f"已刪除 {len(deleted)} 則訊息", ephemeral=True)
    # 設置懲罰頻道
    elif action == "punish_channel" and channel:
        data["punish_channel"] = channel.id
        save_data(data)
        await interaction.response.send_message(f"懲罰通知頻道設置完成：{channel.mention}", ephemeral=True)
    else:
        await interaction.response.send_message("action: leaderboard / mimic / purge / punish_channel", ephemeral=True)

# ----------------------
# 虛式茈 /purple
# ----------------------
@bot.tree.command(name="purple", description="虛式 · 茈：讓機器人幫你說話")
@app_commands.checks.is_owner()
async def purple(interaction: Interaction, message: str):
    await interaction.response.defer(ephemeral=True)
    await interaction.channel.send(message)

# ----------------------
# 訊息監控
# ----------------------
@bot.event
async def on_message(message):
    if message.author.bot:
        return

    data = load_data()

    # 白名單無敵
    if message.author.id in data["whitelist"]:
        await bot.process_commands(message)
        return

    violation = False
    reason = ""

    # 關鍵字偵測
    bad_words = ["幹", "操", "白癡", "智障"]
    for word in bad_words:
        if word in message.content:
            violation = True
            reason = "不當言語"

    # AI偵測（簡單防止Groq爆配額）
    if not violation and message.content:
        prompt = f"判斷這句話是否違規，只回答safe或violation:\n{message.content}"
        try:
            ai = client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[{"role": "user", "content": prompt}]
            )
            result = ai.choices[0].message.content.lower()
            if "violation" in result:
                violation = True
                reason = "AI判定違規"
        except Exception as e:
            print("AI error:", e)

    if violation:
        await message.delete()
        await punish(message.author, reason)

    await bot.process_commands(message)

# ----------------------
# 啟動 Bot
# ----------------------
@bot.event
async def on_ready():
    print(f"{bot.user} 已上線")
    try:
        synced = await bot.tree.sync()
        print(f"已同步 {len(synced)} 條指令")
    except Exception as e:
        print("同步指令錯誤:", e)

bot.run(os.getenv("DISCORD_TOKEN"))

