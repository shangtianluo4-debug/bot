import discord
from discord.ext import commands, tasks
from discord import app_commands
from datetime import datetime, timezone
import os, json, aiohttp

# ----------------------------
# 基本設定
# ----------------------------
TOKEN = os.getenv("DISCORD_TOKEN")
HF_KEY = os.getenv("HF_API_KEY")
OWNER_ID = int(os.getenv("OWNER_ID"))
DATA_FILE = "data.json"

intents = discord.Intents.default()
intents.messages = True
intents.message_content = True
intents.members = True
bot = commands.Bot(command_prefix="!", intents=intents)

# ----------------------------
# 檢查函數
# ----------------------------
def is_owner(interaction: discord.Interaction):
    return interaction.user.id == OWNER_ID

def is_developer(interaction: discord.Interaction):
    data = load_data()
    return interaction.user.id in data.get("開發者名單", [])

# ----------------------------
# 資料管理
# ----------------------------
def init_data():
    default_data = {
        "黑名單": [],
        "白名單": [],
        "開發者名單": [1442017307332182168],
        "日誌頻道": None,
        "懲罰日誌頻道": None,
        "驗證身分組": None,
        "驗證頻道": None,
        "未驗證身分組": None,
        "客服身分組": None,
        "工單分類": None,
        "工單紀錄": {},
        "違規次數": {},
        "bot_last_reset": ""
    }
    if not os.path.exists(DATA_FILE):
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(default_data, f, indent=4, ensure_ascii=False)
        return
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        try:
            data = json.load(f)
        except:
            data = {}
    changed = False
    for key, value in default_data.items():
        if key not in data:
            data[key] = value
            changed = True
    if changed:
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4, ensure_ascii=False)

def load_data():
    init_data()
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

# ----------------------------
# AI 文字違規偵測
# ----------------------------
async def 偵測文字違規(text):
    髒話 = ["幹","白癡","垃圾","智障","靠北","髒話"]
    for w in 髒話:
        if w in text.lower():
            return True, f"含髒話：{w}"
    if not HF_KEY:
        return False, ""
    headers = {"Authorization": f"Bearer {HF_KEY}"}
    payload = {"inputs": text}
    async with aiohttp.ClientSession() as session:
        try:
            async with session.post(
                "https://api-inference.huggingface.co/models/unitary/toxic-bert",
                headers=headers,
                json=payload
            ) as resp:
                res = await resp.json()
                if isinstance(res, dict) and "error" in res:
                    return False, ""
                for label in res[0]:
                    if label["score"] > 0.8 and label["label"].lower() in ["toxic","insult","threat","identity_hate"]:
                        return True, f"AI判定違規({label['label']})"
        except Exception as e:
            print("HF AI 偵測錯誤:", e)
            return False, ""
    return False, ""

# ----------------------------
# AI 圖片違規偵測
# ----------------------------
async def 偵測圖片違規(url):
    key = os.getenv("DEEPAI_API_KEY")
    if not key:
        return False
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                "https://api.deepai.org/api/nsfw-detector",
                headers={"api-key": key},
                json={"image": url}
            ) as resp:
                res = await resp.json()
                nsfw_score = res.get("output", {}).get("nsfw_score", 0)
                if nsfw_score > 0.8:
                    return True
    except Exception as e:
        print("DeepAI error:", e)
    return False

# ----------------------------
# 違規處理
# ----------------------------
async def 處理違規(user: discord.Member, guild: discord.Guild, 原因: str):
    data = load_data()
    uid = str(user.id)
    data["違規次數"][uid] = data["違規次數"].get(uid, 0) + 1

    if data["違規次數"][uid] == 1:
        原因 += "（首次警告）"
    elif data["違規次數"][uid] == 3:
        try:
            await user.timeout(duration=60)
            原因 += "（累積三次禁言60秒）"
        except Exception as e:
            print(f"禁言失敗: {e}")
    elif data["違規次數"][uid] >= 5 and user.id not in data["黑名單"]:
        data["黑名單"].append(user.id)
        原因 += "（累積五次自動封鎖）"

    save_data(data)

    # 發送懲罰頻道
    頻道ID = data.get("懲罰日誌頻道")
    if 頻道ID:
        channel = bot.get_channel(頻道ID)
        if channel:
            embed = discord.Embed(
                title="⚠ 違規通知",
                description=f"使用者 <@{user.id}> 違規：{原因}",
                color=0xff5555,
                timestamp=datetime.now(timezone.utc)
            )
            await channel.send(embed=embed)

    # 發送日誌頻道
    log_channel_id = data.get("日誌頻道")
    if log_channel_id:
        log_channel = bot.get_channel(log_channel_id)
        if log_channel:
            await log_channel.send(f"[LOG] {user} 違規: {原因} (累計 {data['違規次數'][uid]})")

# ----------------------------
# 每日重置違規
# ----------------------------
@tasks.loop(minutes=60)
async def 每日重置違規():
    data = load_data()
    today = str(datetime.now().date())
    if data.get("bot_last_reset") != today:
        data["違規次數"] = {}
        data["bot_last_reset"] = today
        save_data(data)
        log_channel_id = data.get("日誌頻道")
        if log_channel_id:
            log_channel = bot.get_channel(log_channel_id)
            if log_channel:
                await log_channel.send("📌 每日違規次數已重置")

# ----------------------------
# 訊息監控
# ----------------------------
@bot.event
async def on_message(message):
    if message.author.bot:
        return

    data = load_data()
    uid = message.author.id

    if uid in data["白名單"]:
        await bot.process_commands(message)
        return

    # 驗證系統
    verify_role_id = data.get("驗證身分組")
    if verify_role_id:
        verify_role = message.guild.get_role(verify_role_id)
        if verify_role and verify_role not in message.author.roles:
            try:
                await message.delete()
            except:
                pass
            return

    # 黑名單刪訊息
    if uid in data["黑名單"]:
        try:
            await message.delete()
        except:
            pass
        return

    # 文字違規
    違規, 原因 = await 偵測文字違規(message.content)
    if 違規:
        try:
            await message.delete()
        except:
            pass
        await 處理違規(message.author, message.guild, 原因)
        return

    # 圖片違規
    for att in message.attachments:
        if att.content_type and "image" in att.content_type:
            flag = await 偵測圖片違規(att.url)
            if flag:
                try:
                    await message.delete()
                except:
                    pass
                await 處理違規(message.author, message.guild, "疑似色情/不當圖片")
                return

    await bot.process_commands(message)

# ----------------------------
# 成員加入自動賦予身分組
# ----------------------------
@bot.event
async def on_member_join(member: discord.Member):
    data = load_data()
    role_id = data.get("自動賦予身分組")  # 你可以用指令設置這個欄位
    if role_id:
        role = member.guild.get_role(role_id)
        if role:
            try:
                await member.add_roles(role)
                # 可選：發送歡迎訊息
                welcome_channel_id = data.get("驗證頻道") or data.get("日誌頻道")
                if welcome_channel_id:
                    channel = member.guild.get_channel(welcome_channel_id)
                    if channel:
                        await channel.send(f"🎉 歡迎 {member.mention}！已自動賦予 {role.name} 身分組")
            except Exception as e:
                print(f"自動賦予身分組失敗: {e}")


# ----------------------------
# 身分
# ----------------------------
@bot.tree.command(name="設置自動身分組", description="設定新成員自動獲得的身分組")
@app_commands.check(is_owner)
@app_commands.describe(身分組="要自動賦予的身分組")
async def 設置自動身分組(interaction: discord.Interaction, 身分組: discord.Role):
    data = load_data()
    data["自動賦予身分組"] = 身分組.id
    save_data(data)
    await interaction.response.send_message(f"✅ 新成員將自動獲得身分組：{身分組.name}", ephemeral=True)
# ----------------------------
# 黑白名單管理
# ----------------------------
@bot.tree.command(name="查看黑白名單", description="查看伺服器黑白名單")
@app_commands.checks.has_permissions(administrator=True)
async def 查看黑白名單(interaction: discord.Interaction):
    data = load_data()
    wl = ", ".join([f"<@{i}>" for i in data["白名單"]]) or "無"
    bl = ", ".join([f"<@{i}>" for i in data["黑名單"]]) or "無"
    await interaction.response.send_message(f"白名單: {wl}\n黑名單: {bl}", ephemeral=True)

@bot.tree.command(name="黑名單加入", description="將成員加入黑名單")
@app_commands.checks.has_permissions(administrator=True)
@app_commands.describe(目標="選擇成員")
async def 黑名單加入(interaction: discord.Interaction, 目標: discord.Member):
    data = load_data()
    if 目標.id not in data["黑名單"]:
        data["黑名單"].append(目標.id)
        save_data(data)
    await interaction.response.send_message(f"✅ 已加入黑名單：<@{目標.id}>", ephemeral=True)

@bot.tree.command(name="黑名單移除", description="將成員從黑名單移除")
@app_commands.checks.has_permissions(administrator=True)
@app_commands.describe(目標="選擇成員")
async def 黑名單移除(interaction: discord.Interaction, 目標: discord.Member):
    data = load_data()
    if 目標.id in data["黑名單"]:
        data["黑名單"].remove(目標.id)
        save_data(data)
    await interaction.response.send_message(f"✅ 已移除黑名單：<@{目標.id}>", ephemeral=True)

@bot.tree.command(name="白名單加入", description="將成員加入白名單")
@app_commands.checks.has_permissions(administrator=True)
@app_commands.describe(目標="選擇成員")
async def 白名單加入(interaction: discord.Interaction, 目標: discord.Member):
    data = load_data()
    if 目標.id not in data["白名單"]:
        data["白名單"].append(目標.id)
        save_data(data)
    await interaction.response.send_message(f"✅ 已加入白名單：<@{目標.id}>", ephemeral=True)

@bot.tree.command(name="白名單移除", description="將成員從白名單移除")
@app_commands.checks.has_permissions(administrator=True)
@app_commands.describe(目標="選擇成員")
async def 白名單移除(interaction: discord.Interaction, 目標: discord.Member):
    data = load_data()
    if 目標.id in data["白名單"]:
        data["白名單"].remove(目標.id)
        save_data(data)
    await interaction.response.send_message(f"✅ 已移除白名單：<@{目標.id}>", ephemeral=True)

# ----------------------------
# 開發者名單管理
# ----------------------------
@bot.tree.command(name="設定開發者", description="新增開發者權限（只有創作者可用）")
@app_commands.check(is_owner)
@app_commands.describe(目標="選擇成員")
async def 設定開發者(interaction: discord.Interaction, 目標: discord.Member):
    data = load_data()
    if 目標.id not in data["開發者名單"]:
        data["開發者名單"].append(目標.id)
        save_data(data)
    await interaction.response.send_message(f"✅ 已賦予 <@{目標.id}> 開發者權限", ephemeral=True)

@bot.tree.command(name="查看開發者", description="查看所有開發者")
@app_commands.check(is_owner)
async def 查看開發者(interaction: discord.Interaction):
    data = load_data()
    devs = ", ".join([f"<@{i}>" for i in data["開發者名單"]]) or "無"
    await interaction.response.send_message(f"開發者名單：{devs}", ephemeral=True)

# ----------------------------
# 日誌頻道管理
# ----------------------------
@bot.tree.command(name="設置日誌頻道", description="設定日誌通知頻道")
@app_commands.check(is_owner)
@app_commands.describe(頻道="選擇頻道（可選）")
async def 設置日誌頻道(interaction: discord.Interaction, 頻道: discord.TextChannel = None):
    await interaction.response.defer(ephemeral=True)  # ✅ 立即延長
    data = load_data()
    設置頻道 = 頻道 or interaction.channel
    data["日誌頻道"] = 設置頻道.id
    save_data(data)
    await interaction.followup.send(f"✅ 已將日誌頻道設為：{設置頻道.mention}", ephemeral=True)


@bot.tree.command(name="設置懲罰日誌頻道", description="設定違規懲罰通知頻道")
@app_commands.check(is_owner)
@app_commands.describe(頻道="選擇頻道（可選）")
async def 設置懲罰日誌頻道(interaction: discord.Interaction, 頻道: discord.TextChannel = None):
    設置頻道 = 頻道 or interaction.channel
    if not 設置頻道:
        await interaction.response.send_message("❌ 找不到頻道", ephemeral=True)
        return
    data = load_data()
    data["懲罰日誌頻道"] = 設置頻道.id
    save_data(data)
    await interaction.response.send_message(f"✅ 懲罰日誌頻道設為：{設置頻道.mention}", ephemeral=True)

# ----------------------------
# 匿名發言（開發者）
# ----------------------------
@bot.tree.command(name="匿名發言", description="開發者匿名代發訊息")
@app_commands.check(is_developer)
@app_commands.describe(內容="要發送的內容", 頻道="要發送的頻道（可選）")
async def 匿名發言(interaction: discord.Interaction, 內容: str, 頻道: discord.TextChannel = None):
    發送頻道 = 頻道 or interaction.channel
    if not 發送頻道:
        await interaction.response.send_message("❌ 找不到頻道", ephemeral=True)
        return
    embed = discord.Embed(description=內容, color=0x5865F2)
    embed.set_author(name="系統訊息")
    await 發送頻道.send(embed=embed)
    await interaction.response.send_message("✅ 已發送", ephemeral=True)

# ----------------------------
# 驗證系統
# ----------------------------
@bot.tree.command(name="設置驗證身分組", description="設定驗證後給予的身分組")
@app_commands.check(is_owner)
@app_commands.describe(身分組="要給的身分組")
async def 設置驗證身分組(interaction: discord.Interaction, 身分組: discord.Role):
    data = load_data()
    data["驗證身分組"] = 身分組.id
    save_data(data)
    await interaction.response.send_message(f"✅ 驗證身分組設為：{身分組.name}", ephemeral=True)

@bot.tree.command(name="設置未驗證身分組", description="設定未驗證角色（驗證後會移除）")
@app_commands.check(is_owner)
@app_commands.describe(身分組="未驗證身分組")
async def 設置未驗證身分組(interaction: discord.Interaction, 身分組: discord.Role):
    data = load_data()
    data["未驗證身分組"] = 身分組.id
    save_data(data)
    await interaction.response.send_message(f"✅ 未驗證身分組設為：{身分組.name}", ephemeral=True)

@bot.tree.command(name="設置驗證頻道", description="設定驗證使用的頻道")
@app_commands.check(is_owner)
@app_commands.describe(頻道="驗證頻道")
async def 設置驗證頻道(interaction: discord.Interaction, 頻道: discord.TextChannel):
    data = load_data()
    data["驗證頻道"] = 頻道.id
    save_data(data)
    await interaction.response.send_message(f"✅ 驗證頻道設為：{頻道.mention}", ephemeral=True)

class 驗證按鈕(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="點我驗證", style=discord.ButtonStyle.green)
    async def verify(self, interaction: discord.Interaction, button: discord.ui.Button):
        data = load_data()
        role_id = data.get("驗證身分組")
        if not role_id:
            await interaction.response.send_message("❌ 尚未設置驗證身分組", ephemeral=True)
            return

        role = interaction.guild.get_role(role_id)
        if not role:
            await interaction.response.send_message("❌ 身分組不存在", ephemeral=True)
            return

        # ✅ 賦予驗證身分組
        await interaction.user.add_roles(role)

        # ✅ 移除未驗證身分組
        unverified_id = data.get("未驗證身分組")
        if unverified_id:
            unverified_role = interaction.guild.get_role(unverified_id)
            if unverified_role and unverified_role in interaction.user.roles:
                await interaction.user.remove_roles(unverified_role)

        await interaction.response.send_message(f"✅ 驗證成功！歡迎 {interaction.user.mention} 🎉", ephemeral=True)

@bot.tree.command(name="發送驗證", description="發送驗證按鈕")
@app_commands.check(is_owner)
async def 發送驗證(interaction: discord.Interaction):
    data = load_data()
    channel_id = data.get("驗證頻道")
    if not channel_id:
        await interaction.response.send_message("❌ 尚未設置驗證頻道", ephemeral=True)
        return
    channel = bot.get_channel(channel_id)
    if not channel:
        await interaction.response.send_message("❌ 找不到頻道", ephemeral=True)
        return
    embed = discord.Embed(title="🔐 驗證系統", description="點擊下方按鈕完成驗證", color=0x00ff99)
    await channel.send(embed=embed, view=驗證按鈕())
    await interaction.response.send_message("✅ 已發送驗證訊息", ephemeral=True)

# ----------------------------
# 客服與工單系統
# ----------------------------
@bot.tree.command(name="設置客服身分組", description="設定客服可查看工單")
@app_commands.check(is_owner)
@app_commands.describe(身分組="客服身分組")
async def 設置客服身分組(interaction: discord.Interaction, 身分組: discord.Role):
    data = load_data()
    data["客服身分組"] = 身分組.id
    save_data(data)
    await interaction.response.send_message(f"✅ 客服身分組設為：{身分組.name}", ephemeral=True)

class 工單按鈕(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="🎫 開啟工單", style=discord.ButtonStyle.green)
    async def open_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        data = load_data()
        uid = str(interaction.user.id)
        if uid in data["工單紀錄"]:
            await interaction.response.send_message("❌ 你已經有工單了！", ephemeral=True)
            return

        guild = interaction.guild
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            interaction.user: discord.PermissionOverwrite(view_channel=True, send_messages=True)
        }

        role_id = data.get("客服身分組")
        if role_id:
            role = guild.get_role(role_id)
            if role:
                overwrites[role] = discord.PermissionOverwrite(view_channel=True, send_messages=True)

        channel = await guild.create_text_channel(
            name=f"ticket-{interaction.user.name}",
            overwrites=overwrites
        )
        data["工單紀錄"][uid] = channel.id
        save_data(data)
        await channel.send(f"{interaction.user.mention} 🎫 工單已建立，請描述你的問題")
        await interaction.response.send_message(f"✅ 工單已建立：{channel.mention}", ephemeral=True)

@bot.tree.command(name="發送工單", description="發送工單按鈕")
@app_commands.check(is_owner)
async def 發送工單(interaction: discord.Interaction):
    embed = discord.Embed(title="🎫 客服系統", description="點擊下方按鈕建立工單", color=0x00ff99)
    await interaction.channel.send(embed=embed, view=工單按鈕())
    await interaction.response.send_message("✅ 已發送工單按鈕", ephemeral=True)

@bot.tree.command(name="關閉工單", description="關閉此工單")
@app_commands.checks.has_permissions(manage_channels=True)
async def 關閉工單(interaction: discord.Interaction):
    data = load_data()
    channel_id = interaction.channel.id
    user_id = None
    for uid, cid in data["工單紀錄"].items():
        if cid == channel_id:
            user_id = uid
            break
    if not user_id:
        await interaction.response.send_message("❌ 這不是工單頻道", ephemeral=True)
        return
    del data["工單紀錄"][user_id]
    save_data(data)
    await interaction.response.send_message("🗑️ 工單已關閉")
    await interaction.channel.delete()

@bot.tree.command(name="加入人員", description="加入人員到工單")
@app_commands.checks.has_permissions(manage_channels=True)
async def 加入人員(interaction: discord.Interaction, 成員: discord.Member):
    await interaction.channel.set_permissions(成員, view_channel=True, send_messages=True)
    await interaction.response.send_message(f"✅ 已加入 {成員.mention}")

@bot.tree.command(name="移除人員", description="移除人員")
@app_commands.checks.has_permissions(manage_channels=True)
async def 移除人員(interaction: discord.Interaction, 成員: discord.Member):
    await interaction.channel.set_permissions(成員, overwrite=None)
    await interaction.response.send_message(f"✅ 已移除 {成員.mention}")

# ----------------------------
# 成員加入自動賦予身分組
# ----------------------------
@bot.event
async def on_member_join(member: discord.Member):
    data = load_data()
    role_id = data.get("驗證身分組")  # 自動賦予驗證身分組
    if role_id:
        role = member.guild.get_role(role_id)
        if role:
            await member.add_roles(role)

# ----------------------------
# BOT 啟動事件
# ----------------------------
@bot.event
async def on_ready():
    await bot.tree.sync()
    每日重置違規.start()
    print(f"Logged in as {bot.user} (BOT 已啟動)")

# ----------------------------
# 啟動 BOT
# ----------------------------
bot.run(TOKEN)











