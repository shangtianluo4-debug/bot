import aiosqlite
from config import DB

async def init_db():
    async with aiosqlite.connect(DB) as db:

        # 🎫 Ticket
        await db.execute("""
        CREATE TABLE IF NOT EXISTS tickets(
            guild_id INTEGER,
            user_id INTEGER,
            channel_id INTEGER,
            created_at TEXT
        )
        """)

        await db.execute("""
        CREATE TABLE IF NOT EXISTS ticket_settings(
            guild_id INTEGER PRIMARY KEY,
            category_id INTEGER,
            log_channel INTEGER
        )
        """)

        # 📊 Panel
        await db.execute("""
        CREATE TABLE IF NOT EXISTS panel(
            guild_id INTEGER PRIMARY KEY,
            channel_id INTEGER,
            message_id INTEGER
        )
        """)

        # 📜 Rules
        await db.execute("""
        CREATE TABLE IF NOT EXISTS rules(
            guild_id INTEGER,
            type TEXT,
            content TEXT
        )
        """)

        # 👑 Dev
        await db.execute("""
        CREATE TABLE IF NOT EXISTS developers(
            user_id INTEGER PRIMARY KEY
        )
        """)

        await db.execute("""
        CREATE TABLE IF NOT EXISTS dev_logs(
            user_id INTEGER,
            command TEXT,
            time TEXT
        )
        """)

        await db.commit()
