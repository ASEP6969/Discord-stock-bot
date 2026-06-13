import asyncpg
import os
from datetime import datetime

class Database:
    def __init__(self):
        self.pool = None

    async def connect(self):
        DATABASE_URL = os.getenv("DATABASE_URL")
        if not DATABASE_URL:
            raise ValueError("DATABASE_URL environment variable not set")
        self.pool = await asyncpg.create_pool(
            DATABASE_URL,
            min_size=1,
            max_size=5
        )
        await self._create_tables()

    async def _create_tables(self):
        async with self.pool.acquire() as conn:
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    user_id BIGINT PRIMARY KEY,
                    username TEXT,
                    daily_update INTEGER DEFAULT 0
                );
                CREATE TABLE IF NOT EXISTS transactions (
                    id SERIAL PRIMARY KEY,
                    user_id BIGINT,
                    symbol TEXT,
                    shares DOUBLE PRECISION,
                    buy_price_idr DOUBLE PRECISION,
                    total_cost_idr DOUBLE PRECISION,
                    exchange_rate DOUBLE PRECISION,
                    buy_date TEXT
                );
            """)

    async def add_user(self, user_id: int, username: str):
        async with self.pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO users (user_id, username) VALUES ($1, $2) "
                "ON CONFLICT (user_id) DO UPDATE SET username = $2",
                user_id, str(username)
            )

    async def set_daily_update(self, user_id: int, enabled: bool):
        async with self.pool.acquire() as conn:
            await conn.execute(
                "UPDATE users SET daily_update = $1 WHERE user_id = $2",
                int(enabled), user_id
            )

    async def add_transaction(self, user_id: int, symbol: str, shares: float,
                              buy_price_idr: float, total_cost_idr: float, exchange_rate: float):
        async with self.pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO transactions "
                "(user_id, symbol, shares, buy_price_idr, total_cost_idr, exchange_rate, buy_date) "
                "VALUES ($1, $2, $3, $4, $5, $6, $7)",
                user_id, symbol.upper(), shares, buy_price_idr, total_cost_idr, exchange_rate,
                datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
            )

    async def get_user_portfolio(self, user_id: int):
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT symbol, SUM(shares) as total_shares, SUM(total_cost_idr) as total_cost, "
                "MIN(buy_date) as first_buy "
                "FROM transactions WHERE user_id = $1 GROUP BY symbol",
                user_id
            )
            portfolio = []
            for row in rows:
                ex_rate_row = await conn.fetchrow(
                    "SELECT exchange_rate FROM transactions WHERE user_id = $1 AND symbol = $2 "
                    "ORDER BY buy_date ASC LIMIT 1",
                    user_id, row['symbol']
                )
                portfolio.append({
                    "symbol": row['symbol'],
                    "shares": float(row['total_shares']),
                    "total_cost_idr": float(row['total_cost']),
                    "exchange_rate": float(ex_rate_row['exchange_rate']) if ex_rate_row else 0,
                    "buy_date": row['first_buy']
                })
            return portfolio

    async def get_transaction_for_symbol(self, user_id: int, symbol: str):
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT SUM(shares) as total_shares, SUM(total_cost_idr) as total_cost, "
                "MIN(buy_date) as buy_date "
                "FROM transactions WHERE user_id = $1 AND symbol = $2 GROUP BY symbol",
                user_id, symbol.upper()
            )
            if not row:
                return None
            ex_row = await conn.fetchrow(
                "SELECT exchange_rate FROM transactions WHERE user_id = $1 AND symbol = $2 "
                "ORDER BY buy_date ASC LIMIT 1",
                user_id, symbol.upper()
            )
            return {
                "shares": float(row['total_shares']),
                "buy_price_idr": 0,
                "total_cost_idr": float(row['total_cost']),
                "exchange_rate": float(ex_row['exchange_rate']) if ex_row else 0,
                "buy_date": row['buy_date']
            }

    async def get_users_with_daily_update(self):
        async with self.pool.acquire() as conn:
            rows = await conn.fetch("SELECT user_id FROM users WHERE daily_update = 1")
            return [r['user_id'] for r in rows]

    async def close(self):
        if self.pool:
            await self.pool.close()
