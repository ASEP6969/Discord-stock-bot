import os
import asyncio
from dotenv import load_dotenv
import discord
from discord.ext import commands
from utils.db import Database
from cogs.stock import StockCog

load_dotenv()  # untuk development lokal, di Render env di-set lewat dashboard
TOKEN = os.getenv("DISCORD_BOT_TOKEN")

class MyBot(commands.Bot):
    def __init__(self, db: Database):
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(command_prefix="!", intents=intents)
        self.db = db

    async def setup_hook(self):
        await self.add_cog(StockCog(self, self.db))
        await self.tree.sync()
        print("Slash commands synced.")

async def main():
    db = Database()
    await db.connect()
    bot = MyBot(db)
    try:
        await bot.start(TOKEN)
    except KeyboardInterrupt:
        pass
    finally:
        await db.close()

if __name__ == "__main__":
    asyncio.run(main())
