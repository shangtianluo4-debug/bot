import discord
from discord.ext import commands
import os
from dotenv import load_dotenv

# ===== keep alive (Render用) =====
from flask import Flask
from threading import Thread

app = Flask('')

@app.route('/')
def home():
    return "Bot is alive!"

def run():
    app.run(host='0.0.0.0', port=10000)

def keep_alive():
    t = Thread(target=run)
    t.start()

# ===== bot =====
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")

intents = discord.Intents.all()

bot = commands.Bot(
    command_prefix="!",
    intents=intents
)

# ===== 載入所有 Cog =====
async def load_cogs():
    cogs = [
        "cogs.ticket",
        "cogs.panel",
        "cogs.rank",
        "cogs.rules",
        "cogs.backup",
        "cogs.dev",
        "cogs.devlog",
        "cogs.help"
    ]

    for cog in cogs:
        try:
            await bot.load_extension(cog)
            print(f"✅ 載入 {cog}")
        except Exception as e:
            print(f"❌ 載入失敗 {cog}: {e}")

@bot.event
async def on_ready():
    print(f"🔥 已登入 {bot.user}")
    await bot.tree.sync()

async def main():
    await load_cogs()
    await bot.start(TOKEN)

keep_alive()
import asyncio
asyncio.run(main())









