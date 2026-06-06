import os
import csv
from datetime import datetime

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import pytz
import requests
import streamlit as st
import yfinance as yf

st.set_page_config(
    page_title="JARVIS Trading Dashboard",
    page_icon="👑",
    layout="wide",
    initial_sidebar_state="expanded",
)

LOCAL_TZ = pytz.timezone("Asia/Kolkata")
LOG_FILE = "trade_log_paper.csv"


def get_refresh_ttl():
    return st.session_state.get("refresh_ttl", 30)


def get_news_ttl():
    return st.session_state.get("news_ttl", 120)


try:
    TELEGRAM_BOT_TOKEN = st.secrets["TELEGRAM_BOT_TOKEN"]
    TELEGRAM_CHAT_ID = st.secrets["TELEGRAM_CHAT_ID"]
    GNEWS_API_KEY = st.secrets["GNEWS_API_KEY"]
except Exception:
    TELEGRAM_BOT_TOKEN = ""
    TELEGRAM_CHAT_ID = ""
    GNEWS_API_KEY = ""


def safe_symbol(ticker):
    ticker = ticker.upper().strip()
    if ticker.endswith(".NS") or ticker.endswith(".BO") or "-" in ticker:
        return ticker
    return ticker + ".NS"


def send_telegram_alert(message):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return False
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        requests.post(
            url,
            json={"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "Markdown"},
            timeout=10,
        )
        return True
    except Exception:
        return False


@st.cache_data(ttl=get_news_ttl, show_spinner=False)
def fetch_news_sentiment(raw_ticker):
    pos_words = [
        "growth", "profit", "surge", "bullish", "dividend", "deal", "win",
        "success", "buy", "positive", "rally", "jump", "upgrade", "record",
        "gain", "boost", "expansion"
    ]
    neg_words = [
        "loss", "drop", "slump", "bearish", "fraud", "decline", "risk",
        "fail", "sell", "negative", "crash", "debt", "downgrade", "breach"
    ]

    if not GNEWS_API_KEY:
        return None, []

    try:
        url = (
            "https://gnews.io/api/v4/search"
            f"?q={raw_ticker}&lang=en&country=in&max=5&apikey={GNEWS_API_KEY}"
        )
        data = requests.get(url, timeout=10).json()
        articles = data.get("articles", [])
        headlines = []
        score = 0.0

        for art in articles[:5]:
            title = art.get("title", "")
            if not title:
                continue
            headlines.append(title)
            low = title.lower()
            score += sum(0.3 for w in pos_words if w in low)
            score -= sum(0.3 for w in neg_words if w in low)

        if not headlines:
            return None, []

        return round(max(-1, min(1, score / max(1, len(headlines)))), 2), headlines
    except Exception:
        return None, []


def add_indicators(df):
    df = df.copy()
    df["date"] = df.index.date

    df["vwap_num"] = df["volume"] * (df["high"] + df["low"] + df["close"]) / 3
    df["vwap"] = df.groupby("date")["vwap_num"].cumsum() / df.groupby("date")["volume"].cumsum()

    delta = df["close"].diff()
    gain = delta.where(delta > 0, 0).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    rs = gain / loss.replace(0, 1e-10)
    df["rsi"] = 100 - (100 / (1 + rs))

    df["ema20"] = df["close"].ewm(span=20, adjust=False).mean()

    hd = df["high"].diff()
    ld = df["low"].diff()
    df["+dm"] = np.where((hd > ld) & (hd > 0), hd, 0)
    df["-dm"] = np.where((ld > hd) & (ld > 0), ld, 0)

    tr = pd.concat(
        [
            (df["high"] - df["low"]),
            (df["high"] - df["close"].shift(1)).abs(),
            (df["low"] - df["close"].shift(1)).abs(),
        ],
        axis=1,
    ).max(axis=1)

    df["atr"] = tr.rolling(14).mean()
    df["+di"] = 100 * (df["+dm"].rolling(14).mean() / df["atr"].replace(0, 1e-10))
    df["-di"] = 100 * (df["-dm"].rolling(14).mean() / df["atr"].replace(0, 1e-10))
    df["adx"] = (df["+di"] - df["-di"]).abs().rolling(14).mean()

    df["vol_sma"] = df["volume"].rolling(20).mean()
    df["vol_ratio"] = df["volume"] / df["vol_sma"].replace(0, 1e-10)

    return df


def detect_candle_patterns(df):
    df = df.copy()
    df["candle_pattern"] = "No Pattern"

    body = (df["close"] - df["open"]).abs()
    crange = (df["high"] - df["low"]).replace(0, 1e-10)
    lshadow = np.minimum(df["open"], df["close"]) - df["low"]
    ushadow = df["high"] - np.maximum(df["open"], df["close"])

    df.loc[body <= crange * 0.1, "candle_pattern"] = "Doji"
    df.loc[(lshadow >= body * 2) & (ushadow <= body * 0.5), "candle_pattern"] = "Hammer"

    green = df["close"] > df["open"]
    prev_red = df["close"].shift(1) < df["open"].shift(1)
    engulf = (
        (df["open"] <= df["close"].shift(1)) &
        (df["close"] >= df["open"].shift(1)) &
        (body > body.shift(1))
    )
    df.loc[green & prev_red & engulf, "candle_pattern"] = "Bullish Engulfing"

    return df


@st.cache_data(ttl=get_refresh_ttl, show_spinner=False)
def fetch_data(ticker, period="3mo"):
    try:
        sym = safe_symbol(ticker)
        df = yf.Ticker(sym).history(period=period, interval="15m")
        if df is None or df.empty:
            return None

        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.droplevel(0)

        df.columns = [c.lower() for c in df.columns]

        if getattr(df.index, "tz", None):
            df.index = df.index.tz_convert("Asia/Kolkata").tz_localize(None)

        required = {"open", "high", "low", "close", "volume"}
        if not required.issubset(set(df.columns)):
            return None

        df = add_indicators(df)
        df = detect_candle_patterns(df)
        df = df.dropna(subset=["vwap", "rsi", "ema20", "atr", "adx", "vol_ratio"])

        return df if len(df) >= 30 else None
    except Exception:
        return None


def detect_signal(df):
    last = df.iloc[-1]
    buy = (
        last["close"] > last["vwap"]
        and last["close"] > last["ema20"]
        and 45 <= last["rsi"] <= 65
        and last["vol_ratio"] > 1.0
    )
    sell = (
        last["close"] < last["vwap"]
        and last["close"] < last["ema20"]
        and last["rsi"] > 65
    )
    if buy:
        return "BUY"
    if sell:
        return "SELL"
    return "HOLD"


def calc_qty(capital, price, atr, risk_pct):
    if price <= 0 or atr <= 0:
        return 0, 0, 0
    risk_amount = capital * (risk_pct / 100.0)
    risk_per_share = atr * 1.5
    qty = int(risk_amount / risk_per_share)
    max_affordable = int((capital * 0.2) / price)
    qty = max(0, min(qty, max_affordable))
    exposure = (qty * price / capital) * 100 if capital > 0 else 0
    return qty, risk_per_share, exposure


def log_trade(row):
    exists = os.path.exists(LOG_FILE)
    with open(LOG_FILE, "a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if not exists:
            w.writerow(["Time", "Ticker", "Signal", "Price", "SL", "TP", "Qty", "News", "Pattern", "Conf"])
        w.writerow(row)


def read_log():
    cols = ["Time", "Ticker", "Signal", "Price", "SL", "TP", "Qty", "News", "Pattern", "Conf"]
    if not os.path.exists(LOG_FILE):
        return pd.DataFrame(columns=cols)
    try:
        return pd.read_csv(LOG_FILE)
    except Exception:
        return pd.DataFrame(columns=cols)


st.title("JARVIS Trading Dashboard")
st.caption("Paper trading only")

with st.sidebar:
    ticker_input = st.text_input("Ticker", "TATAMOTORS").upper().strip()
    capital = st.number_input("Capital", min_value=500.0, value=50000.0, step=1000.0)
    risk_pct = st.slider("Risk %", min_value=0.5, max_value=5.0, value=1.0, step=0.5)
    refresh_bucket = st.selectbox("Refresh TTL", [10, 30, 60], index=1)
    news_bucket = st.selectbox("News TTL", [60, 120, 300], index=1)

    if "refresh_ttl" not in st.session_state:
        st.session_state.refresh_ttl = refresh_bucket
    if "news_ttl" not in st.session_state:
        st.session_state.news_ttl = news_bucket

    if st.session_state.refresh_ttl != refresh_bucket:
        st.session_state.refresh_ttl = refresh_bucket
        fetch_data.clear()

    if st.session_state.news_ttl != news_bucket:
        st.session_state.news_ttl = news_bucket
        fetch_news_sentiment.clear()

    st.button("Clear Cache", on_click=lambda: (fetch_data.clear(), fetch_news_sentiment.clear()))

if st.button("Run Analysis", use_container_width=True):
    df = fetch_data(ticker_input, period="3mo")

    if df is None or df.empty:
        st.error("No data received from Yahoo Finance.")
        st.stop()

    last = df.iloc[-1]
    signal = detect_signal(df)
    news_score, headlines = fetch_news_sentiment(ticker_input.replace(".NS", "").replace(".BO", ""))

    conf = 50
    if signal == "BUY":
        conf += 20
    if signal == "SELL":
        conf += 15
    if last["rsi"] > 60:
        conf += 10
    if last["vol_ratio"] > 1.2:
        conf += 10
    if news_score is not None and news_score > 0.15:
        conf += 10

    conf = min(100, conf)
    qty, rps, exposure = calc_qty(capital, float(last["close"]), float(last["atr"]), risk_pct)

    if signal == "BUY":
        sl = float(last["close"] - rps)
        tp = float(last["close"] + 3 * last["atr"])
    elif signal == "SELL":
        sl = float(last["close"] + rps)
        tp = float(last["close"] - 3 * last["atr"])
    else:
        sl = 0.0
        tp = 0.0
        qty = 0

    st.subheader("Signal")
    st.write(signal)

    st.subheader("Price Stats")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Price", f"₹{last['close']:.2f}")
    c2.metric("RSI", f"{last['rsi']:.1f}")
    c3.metric("ADX", f"{last['adx']:.1f}")
    c4.metric("ATR", f"₹{last['atr']:.2f}")

    st.subheader("Risk")
    r1, r2, r3 = st.columns(3)
    r1.metric("Qty", qty)
    r2.metric("Risk/Share", f"₹{rps:.2f}")
    r3.metric("Exposure", f"{exposure:.1f}%")

    st.subheader("News")
    if headlines:
        for h in headlines:
            st.write(f"- {h}")
    else:
        st.write("No news available.")

    st.subheader("Chart")
    view = df.tail(200)
    fig = go.Figure()
    fig.add_trace(go.Candlestick(
        x=view.index,
        open=view["open"],
        high=view["high"],
        low=view["low"],
        close=view["close"],
        name="Price",
    ))
    fig.add_trace(go.Scatter(x=view.index, y=view["vwap"], name="VWAP"))
    fig.add_trace(go.Scatter(x=view.index, y=view["ema20"], name="EMA20"))
    fig.update_layout(template="plotly_dark", height=500, xaxis_rangeslider_visible=False)
    st.plotly_chart(fig, use_container_width=True)

    if signal != "HOLD" and qty > 0:
        msg = f"""JARVIS PAPER {signal}
Ticker: {ticker_input}
Price: ₹{last['close']:.2f}
SL: ₹{sl:.2f}
TP: ₹{tp:.2f}
Qty: {qty}
Conf: {conf:.1f}%"""
        send_telegram_alert(msg)
        log_trade([
            datetime.now(LOCAL_TZ).strftime("%Y-%m-%d %H:%M"),
            ticker_input,
            signal,
            float(last["close"]),
            sl,
            tp,
            qty,
            news_score if news_score is not None else "",
            "Technical",
            conf,
        ])

    st.success(f"Done. Confidence: {conf:.1f}%")

st.subheader("Recent Trades")
st.dataframe(read_log().tail(10), use_container_width=True)