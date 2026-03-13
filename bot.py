import discord
from discord.ext import commands, tasks
from discord import app_commands
from datetime import datetime, timezone, timedelta
import aiohttp
import json
import os
import asyncio

# ----------------------------
# 環境變數讀取
# ----------------------------
OWNER_ID_STR = os.getenv("OWNER_ID")
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
GROQ_KEY = os.getenv("GROQ_API_KEY")

if not OWNER_ID_STR:
    raise ValueError("⚠ 環境變數 OWNER_ID 未設定")
if not DISCORD_TOKEN:
    raise ValueError("⚠ 環境變數 DISCORD_TOKEN 未設定")

try:
    OWNER_ID = int(OWNER_ID_STR)
except ValueError:
    raise ValueError("⚠ OWNER_ID 必須是純數字 Discord ID")

# ----------------------------
# 基本設定
# ----------------------------
DATA_FILE = "data.json"
intents = discord.Intents.default()
intents.messages = True
intents.message_content = True
intents.members = True
bot = commands.Bot(command_prefix="!", intents=intents)

# ----------------------------
# 資料管理
# ----------------------------
if not os.path.exists(DATA_FILE):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump({
            "白名單": [],
            "黑名單": [],
            "違規次數": {},
            "懲罰頻道": None,
            "日誌": []
        }, f, ensure_ascii=False, indent=4)

def load_data():
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

def log_action(action):
    data = load_data()
    timestamp = datetime.now(timezone.utc).isoformat()
    data["日誌"].append(f"[{timestamp}] {action}")
    save_data(data)

# ----------------------------
# 檢查是否 BOT 創作者
# ----------------------------
def is_owner(interaction: discord.Interaction):
    return interaction.user.id == OWNER_ID
    
# ----------------------------
# 手動偵測不當詞語
# ----------------------------
async def 偵測文字違規(text):

    不當詞 = ["操你", "白癡", "智障"]

    for word in 不當詞:
        if word in text:
            return True, "不當文字"

    return False, ""

# ----------------------------
# AI 偵測文字違規 (關鍵字或 Groq)
# ----------------------------
async def 偵測文字違規(text):

    if not GROQ_KEY:
        return False, ""

    url = "https://api.groq.com/openai/v1/chat/completions"

    headers = {
        "Authorization": f"Bearer {GROQ_KEY}",
        "Content-Type": "application/json"
    }

    prompt = f"""
你是一個 Discord 管理機器人。
請判斷以下訊息是否違反社群規則。

違規類型：
- 仇恨言論
- 色情內容
- 詐騙
- 惡意辱罵
- 過度髒話

如果違規只回答：
違規:原因

如果沒有違規只回答：
正常

訊息：
{text}
"""

    payload = {
        "model": "llama3-8b-8192",
        "messages": [
            {"role": "user", "content": prompt}
        ],
        "temperature": 0
    }

    try:

        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, json=payload) as resp:

                result = await resp.json()
    return res.get("flagged", False)
            
                if content.startswith("違規"):
                    return True, content

    except Exception as e:
        print("Groq AI 偵測錯誤:", e)

    return False, ""
# ----------------------------
# AI 偵測圖片違規
# ----------------------------
async def 偵測圖片違規(url: str):

    可疑詞 = [
        "porn",
        "sex",
        "hentai",
        "xxx",
        "nsfw",
        "rule34",
        "18+"
    ]

    url_lower = url.lower()

    for word in 可疑詞:
        if word in url_lower:
            return True

    # 如果有 Groq AI 再進行 AI 判斷
    if GROQ_KEY:

        try:

            headers = {
                "Authorization": f"Bearer {GROQ_KEY}",
                "Content-Type": "application/json"
            }

            prompt = f"""
以下是一張圖片網址：
{url}

請判斷是否可能包含：
色情、裸露、成人內容

如果是請回答：
NSFW

如果不是請回答：
SAFE
"""

            payload = {
                "model": "llama3-8b-8192",
                "messages": [
                    {"role": "user", "content": prompt}
                ],
                "temperature": 0
            }

            async with aiohttp.ClientSession() as session:

                async with session.post(
                    "https://api.groq.com/openai/v1/chat/completions",
                    headers=headers,
                    json=payload
                ) as resp:

                    result = await resp.json()

                    content = result["choices"][0]["message"]["content"]

                    if "NSFW" in content:
                        return True

        except Exception as e:
            print("圖片 AI 偵測錯誤:", e)

    return False

# ----------------------------
#  廣告 / 詐騙連結偵測
# ----------------------------

async def 偵測詐騙連結(text: str):

    可疑關鍵字 = [
        "free nitro",
        "steam gift",
        "claim reward",
        "crypto invest",
        "airdrop",
        "免費nitro",
        "送你nitro",
        "投資加密",
    ]

    可疑網域 = [
        "bit.ly",
        "tinyurl",
        "grabify",
        "discord-nitro",
        "steamgift",
        "free-nitro",
        "nitro-drop"
    ]

    lower = text.lower()

    for word in 可疑關鍵字:
        if word in lower:
            return True

    for domain in 可疑網域:
        if domain in lower:
            return True

    return False
# ----------------------------
# 防刷訊息
# ----------------------------
user_message_times = {}

async def 檢查刷訊息(user_id):
    now = datetime.now(timezone.utc)
    if user_id not in user_message_times:
        user_message_times[user_id] = []
    user_message_times[user_id].append(now)
    # 保留 10 秒內訊息
    user_message_times[user_id] = [t for t in user_message_times[user_id] if now - t <= timedelta(seconds=10)]
    if len(user_message_times[user_id]) > 5:
        return True
    return False

# ----------------------------
# 違規處理
# ----------------------------
async def 處理違規(user: discord.Member, guild: discord.Guild, 原因: str):
    data = load_data()
    uid = str(user.id)
    data["違規次數"][uid] = data["違規次數"].get(uid, 0) + 1
    違規次數 = data["違規次數"][uid]

    頻道ID = data.get("懲罰頻道")
    channel = bot.get_channel(頻道ID) if 頻道ID else None

    if 違規次數 == 1:
        if channel:
            embed = discord.Embed(
                title="⚠ 違規警告",
                description=f"使用者 <@{user.id}> 第1次違規：{原因}",
                color=0xffaa00,
                timestamp=datetime.now(timezone.utc)
            )
            await channel.send(embed=embed)
    elif 違規次數 == 3:
        try:
            await user.timeout(duration=60, reason="累積3次違規")
        except Exception as e:
            print(f"禁言失敗: {e}")
        if channel:
            embed = discord.Embed(
                title="⛔ 禁言通知",
                description=f"使用者 <@{user.id}> 累積違規3次，已被禁言60秒\n原因：{原因}",
                color=0xff5555,
                timestamp=datetime.now(timezone.utc)
            )
            await channel.send(embed=embed)
    elif 違規次數 >= 5:
        if user.id not in data["黑名單"]:
            data["黑名單"].append(user.id)
        if channel:
            embed = discord.Embed(
                title="🛑 黑名單通知",
                description=f"使用者 <@{user.id}> 累積違規5次，已加入黑名單\n原因：{原因}",
                color=0x990000,
                timestamp=datetime.now(timezone.utc)
            )
            await channel.send(embed=embed)

    save_data(data)
    log_action(f"{user} 違規: {原因} (累計 {違規次數})")

# ----------------------------
# 每日午夜自動重置違規次數
# ----------------------------
@tasks.loop(hours=24)
async def reset_daily_violations():
    now = datetime.now()
    next_midnight = datetime.combine(now.date() + timedelta(days=1), datetime.min.time())
    wait_seconds = (next_midnight - now).total_seconds()
    await asyncio.sleep(wait_seconds)

    data = load_data()
    data["違規次數"] = {}
    save_data(data)
    
    頻道ID = data.get("懲罰頻道")
    channel = bot.get_channel(頻道ID) if 頻道ID else None
    if channel:
        embed = discord.Embed(
            title="📅 違規重置通知",
            description="已自動重置今日違規次數",
            color=0x00ff00,
            timestamp=datetime.now(timezone.utc)
        )
        await channel.send(embed=embed)
    log_action("每日午夜重置違規次數")

# ----------------------------
# 訊息監控
# ----------------------------
@bot.event
async def on_message(message):

    if message.author.bot:
        return

    data = load_data()
    uid = message.author.id

    # 白名單
    if uid in data["白名單"]:
        await bot.process_commands(message)
        return

    # 黑名單
    if uid in data["黑名單"]:
        try:
            await message.delete()
        except:
            pass
        return

    # ----------------
    # 詐騙連結偵測
    # ----------------
    if await 偵測詐騙連結(message.content):

        try:
            await message.delete()
        except:
            pass

        await 處理違規(
            message.author,
            message.guild,
            "疑似詐騙 / 廣告連結"
        )

        return

    # ----------------
    # 防刷訊息
    # ----------------
    if await 檢查刷訊息(uid):

        try:
            await message.delete()
        except:
            pass

        await 處理違規(
            message.author,
            message.guild,
            "刷訊息過快"
        )

        return

    # ----------------
    # 圖片偵測
    # ----------------
    if message.attachments:

        for att in message.attachments:

            if att.content_type and "image" in att.content_type:

                flag = await 偵測圖片違規(att.url)

                if flag:

                    try:
                        await message.delete()
                    except:
                        pass

                    await 處理違規(
                        message.author,
                        message.guild,
                        "疑似色情 / 不當圖片"
                    )

                    return

    # ----------------
    # AI文字偵測
    # ----------------
    違規, 原因 = await 偵測文字違規(message.content)

    if 違規:

        try:
            await message.delete()
        except:
            pass

        await 處理違規(
            message.author,
            message.guild,
            原因
        )

        return

    await bot.process_commands(message)
# ----------------------------
# /虛式茈 (保留原作者指令)
# ----------------------------
@bot.tree.command(name="虛式茈", description="讓機器人幫你說話 (僅作者可用)")
@app_commands.check(is_owner)
@app_commands.describe(內容="請輸入要說的內容")
async def purple(interaction: discord.Interaction, 內容: str):
    await interaction.response.send_message(內容)

# ----------------------------
# /領域展開 指令
# ----------------------------
功能選單 = [
    app_commands.Choice(name="查看黑白名單", value="查看黑白名單"),
    app_commands.Choice(name="黑名單加入", value="黑名單加入"),
    app_commands.Choice(name="黑名單移除", value="黑名單移除"),
    app_commands.Choice(name="白名單加入", value="白名單加入"),
    app_commands.Choice(name="白名單移除", value="白名單移除"),
    app_commands.Choice(name="機器人狀態", value="機器人狀態"),
]

@bot.tree.command(name="領域展開", description="領域展開 · 無量空處")
@app_commands.checks.has_permissions(administrator=True)
@app_commands.describe(功能="請選擇功能", 目標="選擇成員 (可選)")
@app_commands.choices(功能=功能選單)
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
# /0_2秒領域展開 指令
# ----------------------------
功能選單 = [
    app_commands.Choice(name="違規排行榜(本服)", value="違規排行榜本服"),
    app_commands.Choice(name="違規排行榜(全服)", value="違規排行榜全服"),
    app_commands.Choice(name="假冒別人說話", value="假冒說話"),
    app_commands.Choice(name="刪除訊息", value="刪除訊息"),
    app_commands.Choice(name="設置違規懲罰頻道", value="設置懲罰頻道"),
    app_commands.Choice(name="設置日誌頻道", value="設置日誌頻道")
]

@bot.tree.command(name="0_2秒領域展開", description="瞬間領域操作")
@app_commands.checks.has_permissions(administrator=True)
@app_commands.describe(
    功能="請選擇操作功能",
    目標="選擇成員 (假冒說話用)",
    數量="刪除訊息數量",
    頻道="選擇要設置的頻道"
)
@app_commands.choices(功能=功能選單)
async def mini_domain(
    interaction: discord.Interaction,
    功能: str,
    目標: discord.Member = None,
    數量: int = None,
    頻道: discord.TextChannel = None
):

    data = load_data()

    # ----------------
    # 違規排行榜
    # ----------------
    if 功能.startswith("違規排行榜"):

        embed = discord.Embed(
            title="📊 違規排行榜",
            color=0x7a5cff,
            timestamp=datetime.now(timezone.utc)
        )

        if 功能 == "違規排行榜本服":
            if data["違規次數"]:
                排行 = "\n".join(
                    [f"<@{uid}>：{cnt}" for uid, cnt in data["違規次數"].items()]
                )
            else:
                排行 = "無違規紀錄"

            embed.description = 排行

        else:
            embed.description = "全服排行榜功能未啟用"

        await interaction.response.send_message(embed=embed, ephemeral=True)

    # ----------------
    # 假冒說話
    # ----------------
    elif 功能 == "假冒說話":

        if not 目標:
            await interaction.response.send_message(
                "❌ 請選擇要假冒的成員",
                ephemeral=True
            )
            return

        await interaction.response.send_message(
            f"💬 機器人將代替 <@{目標.id}> 發言（內容由你輸入）",
            ephemeral=True
        )

    # ----------------
    # 刪除訊息
    # ----------------
    elif 功能 == "刪除訊息":

        if not 數量:
            await interaction.response.send_message(
                "❌ 請輸入要刪除的訊息數量",
                ephemeral=True
            )
            return

        deleted = await interaction.channel.purge(limit=min(數量, 100))

        await interaction.response.send_message(
            f"✅ 已刪除 {len(deleted)} 則訊息",
            ephemeral=True
        )

    # ----------------
    # 設置懲罰頻道
    # ----------------
    elif 功能 == "設置懲罰頻道":

        設置頻道 = 頻道 if 頻道 else interaction.channel

        data["懲罰頻道"] = 設置頻道.id
        save_data(data)

        await interaction.response.send_message(
            f"✅ 已設置 <#{設置頻道.id}> 為違規懲罰通知頻道",
            ephemeral=True
        )

    # ----------------
    # 設置日誌頻道
    # ----------------
    elif 功能 == "設置日誌頻道":

        設置頻道 = 頻道 if 頻道 else interaction.channel

        data["日誌頻道"] = 設置頻道.id
        save_data(data)

        await interaction.response.send_message(
            f"✅ 已設置 <#{設置頻道.id}> 為日誌頻道",
            ephemeral=True
        )
# ----------------------------
# /help 指令
# ----------------------------
@bot.tree.command(name="help", description="查看五條悟 BOT 功能介紹")
async def help_command(interaction: discord.Interaction):
    embed = discord.Embed(
        title="五條悟 BOT（ごじょう さとる）",
        description="「領域展開 · 無量空處」\n高階伺服器管理與 AI 偵測機器人",
        color=0x7a5cff
    )
    embed.add_field(
        name="領域展開 · 無量空處",
        value=( "管理員專用指令\n• 查看黑白名單\n• 黑名單加入 / 移除\n• 白名單加入 / 移除\n• 查看機器人狀態" ),
        inline=False
    )
    embed.add_field(
        name="0.2秒領域展開",
        value=( "快速管理工具\n• 違規排行榜（本服 / 全服）\n• 假冒別人說話\n• 刪除指定數量訊息\n• 設置違規懲罰通知頻道" ),
        inline=False
    )
    embed.add_field(
        name="虛式茈",
        value=( "僅 BOT 創作者可使用\n• 讓機器人代替發送訊息" ),
        inline=False
    )
    embed.add_field(
        name="AI 自動偵測系統",
        value=( "• 自動偵測違規文字\n• 自動偵測違規圖片\n• 自動刪除違規訊息\n• 違規達 5 次加入黑名單" ),
        inline=False
    )
    embed.set_footer(text="五條悟 BOT 系統")
    if bot.user:
        embed.set_thumbnail(url=bot.user.display_avatar.url)
    await interaction.response.send_message(embed=embed)


# ----------------------------
# BOT 啟動
# ----------------------------
@bot.event
async def on_ready():
    await bot.tree.sync()
    print(f"Logged in as {bot.user} (五條悟 BOT 已啟動)")
    if not reset_daily_violations.is_running():
        reset_daily_violations.start()

bot.run(DISCORD_TOKEN)















