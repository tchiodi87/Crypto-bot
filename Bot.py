import ccxt
import pandas as pd
import time
import logging
import os
from dotenv import load_dotenv
from datetime import datetime
from ta.trend import EMAIndicator
from ta.momentum import RSIIndicator

# ── Load API keys ─────────────────────────────────────────────
load_dotenv()

API_KEY = os.getenv("COINBASE_API_KEY")
API_SECRET = os.getenv("COINBASE_API_SECRET")

# ── Logging setup ─────────────────────────────────────────────
logging.basicConfig(
level=logging.INFO,
format="%(asctime)s | %(levelname)s | %(message)s",
handlers=[
logging.FileHandler("bot.log"),
logging.StreamHandler()
]
)
log = logging.getLogger()

# ── Config ────────────────────────────────────────────────────
SYMBOL = "BTC/USD" # Trading pair
TIMEFRAME = "1h" # Candle size (1h is safer for beginners)
TRADE_AMOUNT = 50 # USD per trade — start small!
EMA_FAST = 9 # Fast EMA period
EMA_SLOW = 21 # Slow EMA period
RSI_PERIOD = 14 # RSI period
RSI_OVERBOUGHT = 70 # RSI sell signal threshold
RSI_OVERSOLD = 30 # RSI buy signal threshold
SLEEP_SECONDS = 3600 # Check every 1 hour (matches timeframe)

# ── Connect to Coinbase ───────────────────────────────────────
exchange = ccxt.coinbaseadvanced({
"apiKey": API_KEY,
"secret": API_SECRET,
})

# ── State tracking ────────────────────────────────────────────
in_position = False
entry_price = 0.0

def get_candles():
"""Fetch recent OHLCV candle data."""
try:
ohlcv = exchange.fetch_ohlcv(SYMBOL, TIMEFRAME, limit=100)
df = pd.DataFrame(ohlcv, columns=["timestamp","open","high","low","close","volume"])
df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
return df
except Exception as e:
log.error(f"Error fetching candles: {e}")
return None

def add_indicators(df):
"""Add EMA and RSI indicators to the dataframe."""
df["ema_fast"] = EMAIndicator(df["close"], window=EMA_FAST).ema_indicator()
df["ema_slow"] = EMAIndicator(df["close"], window=EMA_SLOW).ema_indicator()
df["rsi"] = RSIIndicator(df["close"], window=RSI_PERIOD).rsi()
return df

def get_signal(df):
"""
Strategy: EMA Crossover + RSI Confirmation
BUY → Fast EMA crosses above Slow EMA + RSI < 70 (not overbought)
SELL → Fast EMA crosses below Slow EMA + RSI > 30 (not oversold)
"""
last = df.iloc[-1] # Most recent candle
prev = df.iloc[-2] # Previous candle

ema_cross_up = prev["ema_fast"] <= prev["ema_slow"] and last["ema_fast"] > last["ema_slow"]
ema_cross_down = prev["ema_fast"] >= prev["ema_slow"] and last["ema_fast"] < last["ema_slow"]
rsi_ok_buy = last["rsi"] < RSI_OVERBOUGHT
rsi_ok_sell = last["rsi"] > RSI_OVERSOLD

if ema_cross_up and rsi_ok_buy:
return "BUY"
elif ema_cross_down and rsi_ok_sell:
return "SELL"
else:
return "HOLD"

def get_balance():
"""Get USD balance."""
try:
balance = exchange.fetch_balance()
return balance["USD"]["free"]
except Exception as e:
log.error(f"Error fetching balance: {e}")
return 0

def place_buy(price):
"""Place a market buy order."""
try:
amount_crypto = TRADE_AMOUNT / price
order = exchange.create_market_buy_order(SYMBOL, amount_crypto)
log.info(f"✅ BUY executed | Price: ${price:,.2f} | Amount: {amount_crypto:.6f} BTC")
return order
except Exception as e:
log.error(f"BUY order failed: {e}")
return None

def place_sell(amount_crypto, price):
"""Place a market sell order."""
try:
order = exchange.create_market_sell_order(SYMBOL, amount_crypto)
log.info(f"✅ SELL executed | Price: ${price:,.2f} | Amount: {amount_crypto:.6f} BTC")
return order
except Exception as e:
log.error(f"SELL order failed: {e}")
return None

def run_bot():
"""Main bot loop."""
global in_position, entry_price
amount_held = 0.0

log.info("🤖 Bot started — Trading BTC/USD on Coinbase Advanced")
log.info(f" Strategy: EMA({EMA_FAST}/{EMA_SLOW}) + RSI({RSI_PERIOD})")
log.info(f" Trade size: ${TRADE_AMOUNT} | Timeframe: {TIMEFRAME}")

while True:
try:
log.info("── Checking market ──────────────────────────")

df = get_candles()
if df is None:
time.sleep(60)
continue

df = add_indicators(df)
signal = get_signal(df)
price = df.iloc[-1]["close"]
rsi = df.iloc[-1]["rsi"]
usd_balance = get_balance()

log.info(f"Price: ${price:,.2f} | RSI: {rsi:.1f} | Signal: {signal} | In position: {in_position}")

# ── BUY LOGIC ──────────────────────────────────────
if signal == "BUY" and not in_position:
if usd_balance >= TRADE_AMOUNT:
order = place_buy(price)
if order:
in_position = True
entry_price = price
amount_held = TRADE_AMOUNT / price
else:
log.warning(f"Insufficient balance (${usd_balance:.2f}) to buy")

# ── SELL LOGIC ─────────────────────────────────────
elif signal == "SELL" and in_position:
order = place_sell(amount_held, price)
if order:
pnl = (price - entry_price) / entry_price * 100
log.info(f"💰 Trade closed | P&L: {pnl:+.2f}%")
in_position = False
entry_price = 0.0
amount_held = 0.0

# ── HOLD ───────────────────────────────────────────
else:
log.info("No action taken — holding current position")

except Exception as e:
log.error(f"Unexpected error: {e}")

log.info(f"💤 Sleeping {SLEEP_SECONDS//60} minutes until next check...")
time.sleep(SLEEP_SECONDS)

# ── Entry point ───────────────────────────────────────────────
if __name__ == "__main__":
run_bot()
