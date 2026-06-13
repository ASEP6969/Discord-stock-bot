import discord
from discord.ext import commands, tasks
from discord import app_commands
from datetime import datetime, timedelta
import math
from utils.db import Database
from utils.api import (
    fetch_stock_price, fetch_stock_info,
    fetch_historical_prices, get_usd_to_idr
)

class StockCog(commands.Cog):
    def __init__(self, bot: commands.Bot, db: Database):
        self.bot = bot
        self.db = db
        self.daily_update_loop.start()

    def cog_unload(self):
        self.daily_update_loop.cancel()

    @app_commands.command(name="infosh", description="Lihat informasi harga saham dunia")
    @app_commands.describe(symbol="Simbol saham (contoh: AAPL, TSLA, BBCA.JK)")
    async def infosh(self, interaction: discord.Interaction, symbol: str):
        await interaction.response.defer()
        symbol = symbol.upper()
        try:
            info = await fetch_stock_info(symbol)
            price_usd = await fetch_stock_price(symbol)
            kurs = await get_usd_to_idr()
            price_idr = price_usd * kurs
            prev_close = info['previous_close']
            change = price_usd - prev_close
            change_pct = (change / prev_close * 100) if prev_close else 0

            embed = discord.Embed(
                title=f"{info['name']} ({symbol})",
                color=0x00ff00 if change >= 0 else 0xff0000
            )
            embed.add_field(name="Harga (USD)", value=f"${price_usd:,.2f}", inline=True)
            embed.add_field(name="Harga (IDR)", value=f"Rp{price_idr:,.2f}", inline=True)
            embed.add_field(name="Perubahan", value=f"{change:+.2f} ({change_pct:+.2f}%)", inline=True)
            embed.set_footer(text=f"Kurs USD/IDR: {kurs:,.0f} | Data real-time")
            await interaction.followup.send(embed=embed)
        except Exception as e:
            await interaction.followup.send(f"❌ Gagal mengambil data untuk `{symbol}`: {e}")

    @app_commands.command(name="shbuy", description="Beli saham dengan nominal Rupiah")
    @app_commands.describe(symbol="Simbol saham", amount_idr="Jumlah uang dalam Rupiah")
    async def shbuy(self, interaction: discord.Interaction, symbol: str, amount_idr: float):
        await interaction.response.defer()
        if amount_idr <= 0:
            await interaction.followup.send("❌ Nominal harus lebih dari 0.")
            return

        symbol = symbol.upper()
        user = interaction.user

        try:
            price_usd = await fetch_stock_price(symbol)
            if price_usd <= 0:
                await interaction.followup.send("❌ Simbol saham tidak valid atau data tidak tersedia.")
                return
            kurs = await get_usd_to_idr()
            price_idr = price_usd * kurs
            shares = amount_idr / price_idr
            await self.db.add_user(user.id, str(user))
            await self.db.add_transaction(
                user.id, symbol, shares, price_idr, amount_idr, kurs
            )

            embed = discord.Embed(title="✅ Pembelian Saham Berhasil", color=0x00ff00)
            embed.add_field(name="Saham", value=f"{symbol}", inline=True)
            embed.add_field(name="Jumlah Saham", value=f"{shares:,.4f} lembar", inline=True)
            embed.add_field(name="Harga per Saham (IDR)", value=f"Rp{price_idr:,.2f}", inline=True)
            embed.add_field(name="Total Biaya", value=f"Rp{amount_idr:,.2f}", inline=True)
            embed.set_footer(text="Simulasi dimulai. Gunakan /portfolio untuk melihat perkembangan.")
            await interaction.followup.send(embed=embed)
        except Exception as e:
            await interaction.followup.send(f"❌ Gagal memproses pembelian: {e}")

    @app_commands.command(name="portfolio", description="Lihat portofolio saham kamu")
    async def portfolio(self, interaction: discord.Interaction):
        await interaction.response.defer()
        user = interaction.user
        portfolio = await self.db.get_user_portfolio(user.id)
        if not portfolio:
            await interaction.followup.send("📭 Kamu belum memiliki saham. Gunakan `/shbuy` untuk membeli.")
            return

        embed = discord.Embed(title="📊 Portofolio Saham Kamu", color=0x3498db)
        total_value = 0
        total_cost = 0

        for item in portfolio:
            symbol = item['symbol']
            shares = item['shares']
            cost_idr = item['total_cost_idr']
            total_cost += cost_idr

            try:
                current_price_usd = await fetch_stock_price(symbol)
                current_price_idr = current_price_usd * item['exchange_rate']
                current_value = shares * current_price_idr
            except:
                current_price_idr = 0
                current_value = cost_idr

            total_value += current_value
            gain = current_value - cost_idr
            gain_pct = (gain / cost_idr * 100) if cost_idr else 0

            embed.add_field(
                name=f"{symbol}",
                value=f"🔹 Kepemilikan: {shares:,.4f} lembar\n"
                      f"🔹 Harga Beli (total): Rp{cost_idr:,.2f}\n"
                      f"🔹 Nilai Sekarang: Rp{current_value:,.2f}\n"
                      f"🔹 Gain/Loss: Rp{gain:+,.2f} ({gain_pct:+.2f}%)",
                inline=False
            )

        total_gain = total_value - total_cost
        embed.add_field(
            name="💰 Total Portofolio",
            value=f"Nilai Total: Rp{total_value:,.2f}\n"
                  f"Total Gain/Loss: Rp{total_gain:+,.2f}",
            inline=False
        )
        embed.set_footer(text="Update real-time dengan kurs saat beli pertama.")
        await interaction.followup.send(embed=embed)

    @app_commands.command(name="detail", description="Riwayat harian saham yang kamu miliki")
    @app_commands.describe(symbol="Simbol saham di portofolio")
    async def detail(self, interaction: discord.Interaction, symbol: str):
        await interaction.response.defer()
        user = interaction.user
        symbol = symbol.upper()
        tx = await self.db.get_transaction_for_symbol(user.id, symbol)
        if not tx:
            await interaction.followup.send(f"❌ Kamu tidak memiliki saham `{symbol}`.")
            return

        shares = tx['shares']
        exchange_rate = tx['exchange_rate']
        buy_date = datetime.strptime(tx['buy_date'], "%Y-%m-%d %H:%M:%S").date()
        end_date = datetime.utcnow().date()
        start_date = buy_date

        if start_date >= end_date:
            await interaction.followup.send("Belum ada data historis karena baru dibeli hari ini.")
            return

        try:
            closes, dates_str = await fetch_historical_prices(symbol, start_date.isoformat(), end_date.isoformat())
            if not closes:
                await interaction.followup.send("Tidak ada data historis.")
                return
        except Exception as e:
            await interaction.followup.send(f"❌ Gagal mengambil data historis: {e}")
            return

        # Hitung nilai IDR harian
        values = [shares * close * exchange_rate for close in closes]
        # Siapkan embed pagination
        pages = []
        chunk_size = 5
        for i in range(0, len(dates_str), chunk_size):
            embed = discord.Embed(title=f"📈 Riwayat {symbol} (sejak {start_date})", color=0x9b59b6)
            for j in range(i, min(i+chunk_size, len(dates_str))):
                date_lbl = dates_str[j]
                value_idr = values[j]
                embed.add_field(
                    name=date_lbl,
                    value=f"Nilai: Rp{value_idr:,.2f}",
                    inline=False
                )
            pages.append(embed)

        if len(pages) == 1:
            await interaction.followup.send(embed=pages[0])
        else:
            view = PaginatorView(pages)
            await interaction.followup.send(embed=pages[0], view=view)

    @app_commands.command(name="dailyupdate", description="Aktifkan/nonaktifkan update portofolio harian via DM")
    @app_commands.describe(status="on atau off")
    async def dailyupdate(self, interaction: discord.Interaction, status: str):
        await interaction.response.defer()
        user = interaction.user
        status = status.lower()
        if status not in ("on", "off"):
            await interaction.followup.send("❌ Gunakan `on` atau `off`.")
            return
        enabled = status == "on"
        await self.db.add_user(user.id, str(user))
        await self.db.set_daily_update(user.id, enabled)
        msg = "✅ Update harian **diaktifkan**." if enabled else "❌ Update harian **dinonaktifkan**."
        await interaction.followup.send(msg)

    @tasks.loop(hours=24)
    async def daily_update_loop(self):
        await self.bot.wait_until_ready()
        now = datetime.utcnow()
        if now.hour != 1:
            return
        user_ids = await self.db.get_users_with_daily_update()
        for uid in user_ids:
            user = self.bot.get_user(uid)
            if not user:
                continue
            portfolio = await self.db.get_user_portfolio(uid)
            if not portfolio:
                continue
            embed = discord.Embed(title="📊 Update Portofolio Harian", color=0x2ecc71,
                                  timestamp=datetime.utcnow())
            total_gain = 0
            for item in portfolio:
                symbol = item['symbol']
                shares = item['shares']
                cost_idr = item['total_cost_idr']
                ex_rate = item['exchange_rate']
                try:
                    price_today = await fetch_stock_price(symbol)
                    hist_closes, _ = await fetch_historical_prices(
                        symbol,
                        (datetime.utcnow() - timedelta(days=2)).strftime("%Y-%m-%d"),
                        datetime.utcnow().strftime("%Y-%m-%d")
                    )
                    yesterday_close = hist_closes[0] if len(hist_closes) >= 2 else price_today
                    today_close = hist_closes[-1]
                    value_today = shares * today_close * ex_rate
                    value_yesterday = shares * yesterday_close * ex_rate
                    change = value_today - value_yesterday
                    total_gain += change
                    embed.add_field(
                        name=symbol,
                        value=f"Harga: ${today_close:.2f}\nNilai: Rp{value_today:,.0f}\n"
                              f"Perubahan: Rp{change:+,.0f}",
                        inline=False
                    )
                except:
                    continue
            embed.add_field(name="Total Perubahan Hari Ini", value=f"Rp{total_gain:+,.0f}", inline=False)
            try:
                await user.send(embed=embed)
            except discord.Forbidden:
                pass

    @daily_update_loop.before_loop
    async def before_daily_update(self):
        await self.bot.wait_until_ready()

class PaginatorView(discord.ui.View):
    def __init__(self, pages):
        super().__init__(timeout=120)
        self.pages = pages
        self.current = 0

    @discord.ui.button(label="◀️ Sebelumnya", style=discord.ButtonStyle.gray)
    async def prev(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.current > 0:
            self.current -= 1
            await interaction.response.edit_message(embed=self.pages[self.current], view=self)

    @discord.ui.button(label="Selanjutnya ▶️", style=discord.ButtonStyle.gray)
    async def next(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.current < len(self.pages) - 1:
            self.current += 1
            await interaction.response.edit_message(embed=self.pages[self.current], view=self)
