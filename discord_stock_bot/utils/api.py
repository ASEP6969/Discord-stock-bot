import yfinance as yf
import requests
import asyncio

async def fetch_stock_price(symbol: str) -> float:
    def _get():
        ticker = yf.Ticker(symbol)
        try:
            hist = ticker.history(period="1d")
            if not hist.empty:
                return float(hist['Close'].iloc[-1])
            info = ticker.info
            return info.get('regularMarketPrice') or info.get('currentPrice', 0.0)
        except:
            return 0.0
    return await asyncio.to_thread(_get)

async def fetch_stock_info(symbol: str) -> dict:
    def _get():
        ticker = yf.Ticker(symbol)
        info = ticker.info
        return {
            "name": info.get("shortName") or info.get("longName", symbol),
            "price": info.get("regularMarketPrice") or info.get("currentPrice", 0.0),
            "previous_close": info.get("previousClose", 0.0),
            "currency": info.get("currency", "USD"),
        }
    return await asyncio.to_thread(_get)

async def fetch_historical_prices(symbol: str, start: str, end: str):
    def _get():
        ticker = yf.Ticker(symbol)
        hist = ticker.history(start=start, end=end)
        if hist.empty:
            return [], []
        return hist['Close'].tolist(), hist.index.strftime('%Y-%m-%d').tolist()
    closes, dates = await asyncio.to_thread(_get)
    return closes, dates

async def get_usd_to_idr() -> float:
    def _get():
        resp = requests.get("https://api.exchangerate-api.com/v4/latest/USD", timeout=10)
        data = resp.json()
        return data['rates']['IDR']
    return await asyncio.to_thread(_get)
