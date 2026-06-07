import sqlite3
import time
import logging
import os
from dotenv import load_dotenv
import requests
from core import (
    fetch_data, detect_patterns, fetch_news_sentiment, validate_signal_10x,
    _fetch_uncached
)

load_dotenv()
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
    raise ValueError("Please set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID environment variables.")

DB_PATH = "alerts.db"
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s",
                    handlers=[logging.FileHandler("alert_engine.log"), logging.StreamHandler()])
logger = logging.getLogger("AlertEngine")

def send_telegram_message(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "HTML"}
    try:
        resp = requests.post(url, json=payload, timeout=10)
        if resp.status_code != 200:
            logger.error(f"Telegram send failed: {resp.text}")
    except Exception as e:
        logger.error(f"Telegram exception: {e}")

def check_alerts():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT id, ticker, target_price, direction FROM alerts WHERE triggered = 0")
    alerts = c.fetchall()
    conn.close()

    for alert_id, ticker, target, direction in alerts:
        df = fetch_data(ticker)
        if df is None:
            logger.warning(f"Could not load data for {ticker}, skipping alert {alert_id}")
            continue

        news_score, _ = fetch_news_sentiment(ticker)
        df, bullish_pat, bearish_pat, pattern_str, _ = detect_patterns(df)
        last = df.iloc[-1]

        live_price = _fetch_uncached(ticker)
        if live_price is None:
            continue
        if direction == 'above' and live_price < target:
            continue
        if direction == 'below' and live_price > target:
            continue

        side = 'BUY' if direction == 'above' else 'SELL'

        stable = validate_signal_10x(ticker, side, last, news_score, bullish_pat, bearish_pat)
        if not stable:
            logger.info(f"Alert {alert_id} for {ticker} failed algo stability test.")
            continue

        final_price = _fetch_uncached(ticker)
        if final_price is None:
            continue

        if direction == 'above':
            msg = (f"🚀 <b>100% Confirmed Alert: {ticker}</b>\n"
                   f"Price above ₹{target:,.2f} & all 7 rules + patterns valid.\n"
                   f"Current: ₹{final_price:,.2f}")
        else:
            msg = (f"📉 <b>100% Confirmed Alert: {ticker}</b>\n"
                   f"Price below ₹{target:,.2f} & all 7 rules + patterns valid.\n"
                   f"Current: ₹{final_price:,.2f}")

        send_telegram_message(msg)
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("UPDATE alerts SET triggered = 1 WHERE id = ?", (alert_id,))
        conn.commit()
        conn.close()
        logger.info(f"Alert {alert_id} for {ticker} triggered and sent.")

if __name__ == "__main__":
    logger.info("Alert Engine started with 10x multi-condition validation.")
    while True:
        try:
            check_alerts()
        except Exception as e:
            logger.error(f"Error in main loop: {e}")
        time.sleep(30)