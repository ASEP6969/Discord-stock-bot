import aiohttp
import asyncio
from datetime import datetime, timezone
import os

FINNHUB_KEY = os.getenv("FINNHUB_API_KEY")
BASE_URL = "https://finnhub.io/api/v1"

async def _finnhub_request(endpoint: str, params: dict = None):
    """Helper async untuk panggil Finnhub API."""
    url = f"{BASE_URL}/{endpoint}"
    if params is None:
        params = {}
    params["token"] = FINNHUB_KEY
    async with aiohttp.ClientSession() as session:
        async with session.get(url, params=params) as resp:
            if resp.status == 429:
                raise Exception("Finnhub rate limit tercapai, coba lagi nanti")
            return await resp.json()

async def fetch_stock_price(symbol: str) -> float:
    """Ambil harga terkini (USD)."""
    data = await _finnhub_request("quote", {"symbol": symbol.upper()})
    return float(data.get("c", 0.0))

async def fetch_stock_info(symbol: str) -> dict:
    """
    Ambil info dasar saham: nama, harga terbaru, previous close, mata uang.
    Gunakan dua panggilan (profile + quote) – masih aman dalam rate limit.
    """
    symbol = symbol.upper()
    # Jalankan kedua request bersamaan
    quote_task = _finnhub_request("quote", {"symbol": symbol})
    profile_task = _finnhub_request("stock/profile2", {"symbol": symbol})

    quote, profile = await asyncio.gather(quote_task, profile_task, return_exceptions=True)

    # Fallback jika salah satu gagal
    name = symbol
    currency = "USD"
    if not isinstance(profile, Exception) and profile:
        name = profile.get("name", symbol)
        currency = profile.get("currency", "USD")

    price = 0.0
    prev_close = 0.0
    if not isinstance(quote, Exception) and quote:
        price = float(quote.get("c", 0.0))
        prev_close = float(quote.get("pc", 0.0))

    return {
        "name": name,
        "price": price,
        "previous_close": prev_close,
        "currency": currency,
    }

async def fetch_historical_prices(symbol: str, start: str, end: str):
    """
    Ambil harga penutupan harian dalam rentang tanggal.
    start, end dalam format YYYY-MM-DD.
    Mengembalikan (list harga close, list string tanggal).
    """
    symbol = symbol.upper()
    # Konversi tanggal ke UNIX timestamp
    from_ts = int(datetime.strptime(start, "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp())
    to_ts = int(datetime.strptime(end, "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp())

    params = {
        "symbol": symbol,
        "resolution": "D",
        "from": from_ts,
        "to": to_ts,
    }
    data = await _finnhub_request("stock/candle", params)
    if data.get("s") != "ok":
        return [], []

    closes = data.get("c", [])
    timestamps = data.get("t", [])

    # Format tanggal dari timestamp
    dates = [datetime.utcfromtimestamp(ts).strftime("%Y-%m-%d") for ts in timestamps]

    return closes, dates

async def get_usd_to_idr() -> float:
    """Kurs USD ke IDR via Finnhub forex."""
    data = await _finnhub_request("forex/rates", {"base": "USD"})
    quote = data.get("quote", {})
    return float(quote.get("IDR", 0.0))
