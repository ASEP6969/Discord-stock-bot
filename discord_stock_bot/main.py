import os
import asyncio
from dotenv import load_dotenv
import discord
from discord.ext import commands
from aiohttp import web

from utils.db import Database
from cogs.stock import StockCog

load_dotenv()
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

async def handle(request):
    return web.Response(text="Bot is alive")

async def run_web():
    app = web.Application()
    app.router.add_get('/', handle)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', 8080)
    await site.start()
    print("Web server started on port 8080")

async def main():
    db = Database()
    await db.connect()
    bot = MyBot(db)

    # Jalankan web server di background
    web_task = asyncio.create_task(run_web())

    try:
        await bot.start(TOKEN)
    except KeyboardInterrupt:
        pass
    finally:
        await db.close()
        web_task.cancel()

if __name__ == "__main__":
    asyncio.run(main())
