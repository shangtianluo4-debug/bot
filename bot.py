import discord
from discord.ext import commands
from discord import app_commands
from openai import OpenAI

TOKEN = "你的DISCORD_TOKEN"

client = OpenAI()

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

blacklist = set()
whitelist = set()

# Bot啟動
@bot.event
async def on_ready():
    await bot.tree.sync()
    print(f"已登入 {bot.user}")

# -------------------
# !say 偽裝說話
# -------------------
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

# -------------------
# /scan_text
# -------------------
@bot.tree.command(name="scan_text", description="AI偵測文字")
async def scan_text(interaction: discord.Interaction, text: str):

    response = client.moderations.create(
        model="omni-moderation-latest",
        input=text
    )

    flagged = response.results[0].flagged

    if flagged:
        await interaction.response.send_message("⚠️ 偵測到不當語言")
    else:
        await interaction.response.send_message("✅ 沒有問題")

# -------------------
# /scan_image
# -------------------
@bot.tree.command(name="scan_image", description="AI偵測圖片")
async def scan_image(interaction: discord.Interaction, image: discord.Attachment):

    # 示範回覆
    await interaction.response.send_message(
        "🖼️ 圖片已提交AI檢查（示範版本）"
    )

# -------------------
# /blacklist
# -------------------
@bot.tree.command(name="blacklist", description="加入黑名單")
async def blacklist_cmd(interaction: discord.Interaction, member: discord.Member):

    blacklist.add(member.id)

    await interaction.response.send_message(
        f"{member.display_name} 已加入黑名單"
    )

# -------------------
# /whitelist
# -------------------
@bot.tree.command(name="whitelist", description="加入白名單")
async def whitelist_cmd(interaction: discord.Interaction, member: discord.Member):

    whitelist.add(member.id)

    await interaction.response.send_message(
        f"{member.display_name} 已加入白名單"
    )

bot.run(TOKEN)