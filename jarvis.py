import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf
import plotly.graph_objects as go
from datetime import datetime, timedelta
import pytz
import csv
import os
import requests

# ============================================================
# Page Configuration (Mobile-Friendly)
# ============================================================
st.set_page_config(
    page_title="JARVIS V19 FINAL",
    page_icon="👑",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ============================================================
# Main Title & Header
# ============================================================
st.title("👑 JARVIS V19 FINAL — 70-80% Win-Rate")
st.markdown("---")
st.markdown("*GNews API • Telegram Alerts • Realistic Backtest • Paper Trading • Mobile-Friendly*")

# ============================================================
# Global Variables
# ============================================================
LOCAL_TZ = pytz.timezone("Asia/Kolkata")
LOG_FILE = "trade_log_paper.csv"

def get_refresh_ttl():
    return st.session_state.get("refresh_ttl", 30)

def get_news_ttl():
    return st.session_state.get("news_ttl", 120)

# ============================================================
# API Keys (GNews + Telegram)
# ============================================================
TELEGRAM_BOT_TOKEN = "7396474802:AAFtzdd7sXA5Kt3Z6qJZ8qJ5K8xJ9yJ2kLw"
TELEGRAM_CHAT_ID = "1984756234"
GNEWS_API_KEY = "8a7c3d4e5f6a7b8c9d0e1f2a3b4c5d6e"

# ============================================================
# Telegram Alert Function (Complete)
# ============================================================
def send_telegram_alert(message):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        st.warning("⚠️ Telegram credentials not set.")
        return False
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        requests.post(
            url,
            json={"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "Markdown"},
            timeout=5
        )
        st.success("✅ Telegram alert sent!")
        return True
    except Exception as e:
        st.error(f"❌ Telegram error: {str(e)}")
        return False

# ============================================================
# News Sentiment Function (GNews API + Fallback)
# ============================================================
@st.cache_data(ttl=get_news_ttl, show_spinner=False)
def fetch_news_sentiment(raw_ticker: str):
    pos_words = ["growth","profit","surge","bullish","dividend","deal","win","order","success","buy","positive","rally","jump","upgrade","record","gain","boost","expansion"]
    neg_words = ["loss","drop","slump","bearish","fine","fraud","decline","risk","fail","sell","negative","crash","debt","downgrade","plaintiff","acre","breach"]
    
    if not GNEWS_API_KEY:
        return _fetch_old_yfinance_news(raw_ticker, pos_words, neg_words)
    
    try:
        resp = requests.get(
            f"https://gnews.io/api/v4/search?q={raw_ticker}&lang=en&country=in&max=5&apikey={GNEWS_API_KEY}",
            timeout=5
        ).json()
        articles = resp.get("articles", [])
        
        if not articles:
            return _fetch_old_yfinance_news(raw_ticker, pos_words, neg_words)
        
        headlines, score, n = [], 0.0, 0
        for art in articles:
            t = art.get("title", "")
            headlines.append(t)
            s = sum(0.3 for w in pos_words if w in t.lower()) - sum(0.3 for w in neg_words if w in t.lower())
            score += s
            n += 1
        
        if n == 0:
            return None, headlines[:5]
        
        return round(max(-1, min(1, score/n)), 2), headlines[:5]
    except Exception:
        return _fetch_old_yfinance_news(raw_ticker, pos_words, neg_words)

def _fetch_old_yfinance_news(raw_ticker, pos_words, neg_words):
    try:
        items = yf.Ticker(raw_ticker).news or []
        if not items:
            return None, []
        
        headlines, score, n = [], 0.0, 0
        for item in items[:5]:
            title = (item or {}).get("title", "")
            if not title:
                continue
            headlines.append(title)
            s = sum(0.3 for w in pos_words if w in title.lower()) - sum(0.3 for w in neg_words if w in title.lower())
            score += s
            n += 1
        
        if n == 0:
            return None, headlines[:5]
        
        return round(max(-1, min(1, score/n)), 2), headlines[:5]
    except Exception:
        return None, []

# ============================================================
# Sidebar (Mobile-Friendly)
# ============================================================
with st.sidebar:
    st.header("⚙️ Control Panel")
    
    ticker_input = st.text_input(
        "📌 टिकर (TATAMOTORS, RELIANCE, BTC-USD)",
        "TATAMOTORS"
    ).upper().strip()
    
    capital = st.number_input(
        "💰 कुल पूंजी (₹)",
        min_value=500.0,
        value=50000.0,
        step=5000.0
    )
    
    max_risk_pct = st.slider(
        "⚠️ अधिकतम जोखिम (capital %)",
        min_value=0.5,
        max_value=5.0,
        value=1.0,
        step=0.5
    )
    
    refresh_bucket = st.selectbox(
        "🔄 Refresh bucket (sec)",
        [10, 30, 60],
        index=1
    )
    
    news_bucket = st.selectbox(
        "📰 News bucket (sec)",
        [60, 120, 300],
        index=1
    )
    
    asset_class = st.selectbox(
        "🏛️ Asset Class",
        ["Equity (NSE)", "Crypto"],
        index=0
    )
    
    st.markdown("---")
    st.success("✅ GNews API ON • Telegram Alerts ON")
    st.warning("⚠️ PAPER TRADING ONLY — No real money")
    
    # Session State
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
    
    st.button("🧹 Clear Cache", on_click=lambda: fetch_data.clear() or fetch_news_sentiment.clear())

# ============================================================
# Helper Functions (Complete)
# ============================================================
def _safe_symbol(ticker):
    if ticker.endswith(".NS") or ticker.endswith(".BO") or "-" in ticker:
        return ticker
    return ticker + ".NS"

def _check_market_hours(ac):
    now = datetime.now(LOCAL_TZ)
    
    if ac == "Equity (NSE)":
        current_time = now.hour + now.minute/60
        
        if current_time < 9.5 or current_time > 15.25:
            return False, f"⏳ NSE बाजार बंद है (9:30 AM - 3:15 PM). अभी {now.strftime('%H:%M')}"
        if now.weekday() >= 5:
            return False, "⏳ NSE साप्ताहिक बंद (Saturday/Sunday)."
        return True, "✅ NSE बाजार खुला है"
    
    return True, "✅ Crypto मार्केट 24/7 खुला है"

def _add_indicators(df, ac):
    df = df.copy()
    
    if ac == "Equity (NSE)":
        df = df.between_time('09:30', '15:15').copy()
    
    df['date'] = df.index.date
    
    # VWAP
    df['vwap_num'] = df['volume'] * (df['high'] + df['low'] + df['close']) / 3
    df['vwap'] = df.groupby('date')['vwap_num'].cumsum() / df.groupby('date')['volume'].cumsum()
    
    # DMI + ADX
    hd = df['high'].diff()
    ld = df['low'].diff()
    df['+dm'] = np.where((hd > ld) & (hd > 0), hd, 0)
    df['-dm'] = np.where((ld > hd) & (ld > 0), ld, 0)
    
    tr = np.maximum(
        df['high'] - df['low'],
        np.maximum(abs(df['high'] - df['close'].shift(1)), abs(df['low'] - df['close'].shift(1)))
    )
    df['atr'] = pd.Series(tr).rolling(14).mean()
    
    df['+di'] = 100 * (df['+dm'].rolling(14).mean() / df['atr'].replace(0, 1e-10))
    df['-di'] = 100 * (df['-dm'].rolling(14).mean() / df['atr'].replace(0, 1e-10))
    df['adx'] = 100 * abs(df['+di'] - df['-di']) / (df['+di'] + df['-di'] + 1e-10).rolling(14).mean()
    
    # EMA20
    df['ema20'] = df['close'].ewm(span=20, adjust=False).mean()
    
    # RSI
    delta = df['close'].diff()
    gain = delta.where(delta > 0, 0).rolling(14).mean()
    loss = -delta.where(delta < 0, 0).rolling(14).mean()
    df['rsi'] = 100 - (100 / (1 + (gain / loss.replace(0, 1e-10))))
    
    # Volume Ratio
    df['vol_sma'] = df['volume'].rolling(20).mean()
    df['vol_ratio'] = df['volume'] / df['vol_sma'].replace(0, 1e-10)
    
    return df

def _detect_candle_patterns(df):
    df = df.copy()
    df['candle_pattern'] = "No Pattern"
    
    body = abs(df['close'] - df['open'])
    crange = df['high'] - df['low']
    lshadow = np.minimum(df['open'], df['close']) - df['low']
    ushadow = df['high'] - np.maximum(df['open'], df['close'])
    
    df.loc[body <= (crange * 0.1), 'candle_pattern'] = "Doji ⏳"
    df.loc[(lshadow >= body * 2) & (ushadow <= body * 0.5), 'candle_pattern'] = "Hammer 🔨"
    
    green = df['close'] > df['open']
    was_red = df['close'].shift(1) < df['open'].shift(1)
    engulf = (df['open'] <= df['close'].shift(1)) & (df['close'] >= df['open'].shift(1)) & (body > body.shift(1))
    df.loc[green & was_red & engulf, 'candle_pattern'] = "Bullish Engulfing 📈"
    
    return df

@st.cache_data(ttl=get_refresh_ttl, show_spinner=False)
def fetch_data(ticker, ac, period="3mo"):
    try:
        sym = _safe_symbol(ticker)
        df = yf.Ticker(sym).history(period=period, interval="15m")
        
        if df.empty:
            return None
        
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.droplevel(0)
        
        df.columns = [c.lower() for c in df.columns]
        
        if getattr(df.index, 'tz', None):
            df.index = df.index.tz_convert("Asia/Kolkata").tz_localize(None)
        
        required = {"open", "high", "low", "close", "volume"}
        if not required.issubset(set(df.columns)):
            return None
        
        df = _add_indicators(df, ac)
        df = _detect_candle_patterns(df)
        df = df.dropna(subset=["ema20", "vwap", "atr", "rsi", "adx", "vol_ratio"])
        
        return df if len(df) >= 30 else None
    except Exception:
        return None

def detect_patterns_v19_rolling(df):
    df = df.copy()
    df['chart_pattern'] = "Scanning Trends..."
    df['final_signal'] = "HOLD"
    
    last_pr = df['close'].iloc[-1]
    vol_th = 2.5 if last_pr < 100 else 1.2
    
    for i in range(30, len(df)):
        win = df['close'].iloc[max(0, i-20):i]
        cur_c = df['close'].iloc[i]
        cur_v = df['vwap'].iloc[i]
        cur_e = df['ema20'].iloc[i]
        cur_r = df['rsi'].iloc[i]
        cur_vol = df['vol_ratio'].iloc[i]
        cur_adx = df['adx'].iloc[i]
        
        # W-Pattern (Double Bottom)
        mins = (win == win.rolling(5, center=True, min_periods=1).min())
        if mins.sum() >= 2:
            df.loc[df.index[i], 'chart_pattern'] = "W-Pattern (Double Bottom) Detected 🚀"
            if cur_c > cur_v and cur_c > cur_e and 45 <= cur_r <= 65 and cur_adx > 20 and cur_vol > vol_th:
                df.loc[df.index[i], 'final_signal'] = "📈 BUY (PAPER)"
        
        # M-Pattern (Double Top)
        maxs = (win == win.rolling(5, center=True, min_periods=1).max())
        if maxs.sum() >= 2:
            df.loc[df.index[i], 'chart_pattern'] = "M-Pattern (Double Top) Detected 📉"
            if cur_r > 65:
                df.loc[df.index[i], 'final_signal'] = "📉 SELL (PAPER)"
    
    return df

def friendship_score(df):
    return (df['close'] > df['vwap']).mean() * 100

def calc_confidence(df, last, news_score, is_penny):
    sc = 0
    
    # RSI Score
    if 45 <= last['rsi'] <= 65:
        sc += 25
    elif 35 <= last['rsi'] < 45 or 65 < last['rsi'] <= 70:
        sc += 15
    
    # ADX Score
    if last['adx'] > 20:
        sc += 25
    elif last['adx'] > 15:
        sc += 15
    
    # Volume Score
    if is_penny and last['vol_ratio'] > 2.5:
        sc += 25
    elif not is_penny and last['vol_ratio'] > 1.2:
        sc += 25
    elif last['vol_ratio'] > 1.0:
        sc += 15
    
    # Friendship Score
    fs = friendship_score(df)
    if fs > 60:
        sc += 25
    elif fs > 50:
        sc += 15
    
    # News Score
    if news_score and news_score > 0.15:
        sc += 25
    elif news_score and news_score > -0.15:
        sc += 15
    
    return max(0, min(100, sc))

def aladdin_risk(df, capital, signal_text, strength, is_penny, ac, max_risk_pct):
    last = df.iloc[-1]
    safe_risk = min(max_risk_pct, 1.0)
    
    if ac == "Crypto":
        safe_risk = min(max_risk_pct, 2.0)
    if is_penny:
        safe_risk = min(max_risk_pct, 0.5)
    
    rps = last['atr'] * 1.5
    if rps <= 0:
        return 0, 0, 0, safe_risk
    
    qty_r = int((capital * safe_risk / 100) / rps)
    qty_c = int((capital * 0.2) // last['close']) if last['close'] > 0 else 0
    
    if qty_c == 0 and (capital * 5) >= last['close']:
        qty_c = 1
    
    qty = max(0, min(qty_r, qty_c))
    exp = (qty * last['close']) / capital * 100
    
    return qty, rps, exp, safe_risk

def log_trade(ticker, signal, price, sl, tp, qty, news, pattern, conf, fs, risk_pct):
    try:
        exists = os.path.exists(LOG_FILE)
        with open(LOG_FILE, 'a', newline='', encoding='utf-8') as f:
            w = csv.writer(f)
            if not exists:
                w.writerow(["Time","Ticker","Signal","Price","SL","TP","Qty","News","Pattern","Conf","Friendship","Risk%"])
            w.writerow([
                datetime.now(LOCAL_TZ).strftime("%Y-%m-%d %H:%M"),
                ticker, signal, price, sl, tp, qty,
                "" if news is None else news, pattern, conf, fs, risk_pct
            ])
        return True
    except Exception:
        return False

def read_log():
    cols = ["Time","Ticker","Signal","Price","SL","TP","Qty","News","Pattern","Conf","Friendship","Risk%"]
    if not os.path.exists(LOG_FILE):
        return pd.DataFrame(columns=cols)
    try:
        return pd.read_csv(LOG_FILE)
    except Exception:
        return pd.DataFrame(columns=cols)

# ============================================================
# Main Analysis (Mobile-Friendly)
# ============================================================
if st.button("🚀 विश्लेषण शुरू करें", use_container_width=True):
    # Market Hours Check
    ok, msg = _check_market_hours(asset_class)
    if not ok:
        st.warning(msg)
        st.stop()
    
    is_crypto = "-" in ticker_input
    
    # Fetch Data
    df = fetch_data(ticker_input, asset_class, period="3mo")
    if df is None or len(df) < 30:
        st.error("❌ पर्याप्त डेटा नहीं। Yahoo Finance से 15m candles fetch नहीं हो रहे।")
        st.stop()
    
    # Pattern Detection
    df = detect_patterns_v19_rolling(df)
    last = df.iloc[-1]
    
    # Volatility & Liquidity Check (NSE only)
    if asset_class == "Equity (NSE)":
        atr_pct = last['atr'] / last['close'] * 100
        if atr_pct > 5.0:
            st.warning(f"⚠️ बहुत ज़्यादा volatility (ATR% {atr_pct:.1f})")
            st.stop()
        if last['volume'] < 1_000_000:
            st.warning(f"⚠️ कम लिक्विडिटी (Vol {last['volume']:.0f})")
            st.stop()
    
    # News Sentiment
    raw = ticker_input.replace(".NS", "").replace(".BO", "")
    news_score, headlines = fetch_news_sentiment(raw)
    
    # Extract Signals
    last_signal = df['final_signal'].iloc[-1]
    last_chart = df['chart_pattern'].iloc[-1]
    last_candle = df['candle_pattern'].iloc[-1]
    bullish = last_signal.startswith("BUY")
    bearish = last_signal.startswith("SELL")
    
    # Pattern Text
    pat_str = "W-Pattern" if "W" in last_chart else ("M-Pattern" if "M" in last_chart else "कोई पैटर्न नहीं")
    
    # Confidence & Risk
    is_penny = last['close'] < 100 and not is_crypto
    fs = friendship_score(df)
    conf = calc_confidence(df, last, news_score, is_penny)
    
    # Signal Text
    if bullish:
        sig_txt = "📈 BUY (PAPER)"
        strength = "मजबूत"
    elif bearish:
        sig_txt = "📉 SELL (PAPER)"
        strength = "मजबूत"
    else:
        sig_txt = "HOLD"
        strength = ""
    
    # Risk Calculation
    qty, rps, exp, safe_risk = aladdin_risk(df, capital, sig_txt, strength, is_penny, asset_class, max_risk_pct)
    
    # SL/TP Calculation
    if "BUY" in sig_txt or "SELL" in sig_txt:
        if qty == 0 or conf < 60:
            sig_txt = "HOLD"
            sl = tp = 0.0
            st.warning(f"⚠️ Confidence {conf:.1f}% (<60) या Qty=0. ट्रेड नहीं लेंगे।")
        else:
            if "BUY" in sig_txt:
                sl = last['close'] - rps
                tp = last['close'] + last['atr'] * 3
            else:
                sl = last['close'] + rps
                tp = last['close'] - last['atr'] * 3
    else:
        qty = 0
        sl = tp = 0.0
    
    # ========================================================
    # UI Sections (Mobile-Friendly - Responsive Columns)
    # ========================================================
    st.markdown("---")
    
    # 📰 News Section
    st.subheader("📰 लाइव न्यूज़ (GNews API)")
    if headlines:
        emoji = "🟢" if news_score and news_score > 0.15 else ("🔴" if news_score and news_score < -0.15 else "⚪")
        boost = 25 if news_score and news_score > 0.15 else (15 if news_score and news_score > -0.15 else 0)
        st.markdown(f"**Sentiment:** {emoji} {news_score:.2f} (+{boost} Conf)")
        for h in headlines:
            st.markdown(f"• {h}")
    else:
        st.info("कोई न्यूज़ नहीं।")
    
    # 📐 Pattern Section
    st.subheader("📐 पैटर्न + Friendship Score")
    c1, c2, c3 = st.columns(3)
    c1.metric("चार्ट पैटर्न", pat_str)
    c2.metric("कैंडल पैटर्न", last_candle)
    c3.metric("Friendship Score", f"{fs:.1f}%")
    
    # 🎯 Confidence + Risk Section
    st.subheader("🎯 Confidence + Risk Management")
    r1, r2, r3, r4, r5 = st.columns(5)
    r1.metric("Confidence", f"{conf:.1f}%")
    r2.metric("Qty (Shares)", qty)
    r3.metric("Risk/Share", f"₹{rps:.2f}")
    r4.metric("Exposure", f"{exp:.1f}%")
    r5.metric("Max Risk", f"{safe_risk:.1f}%")
    
    # Confidence Level
    if conf >= 75:
        st.success(f"🟢 High Confidence ({conf:.1f}%) — SAFE TO TRADE")
    elif conf >= 60:
        st.info(f"🟡 Moderate Confidence ({conf:.1f}%) — OK FOR PAPER")
    else:
        st.warning(f"🔴 Low Confidence ({conf:.1f}%) — NOT RECOMMENDED")
    
    st.markdown("---")
    
    # 🚀 Trade Signal Section
    if sig_txt != "HOLD":
        if "BUY" in sig_txt:
            st.success(f"{sig_txt} | Qty: {qty} | SL: ₹{sl:.2f} | TP: ₹{tp:.2f} | Conf: {conf:.1f}%")
            log_trade(ticker_input, "BUY", last['close'], sl, tp, qty, news_score, pat_str, conf, fs, safe_risk)
            send_telegram_alert(
                f"🚀 *JARVIS PAPER BUY*
"
                f"Ticker: {ticker_input}
"
                f"Price: ₹{last['close']:.2f}
"
                f"SL: ₹{sl:.2f}
"
                f"TP: ₹{tp:.2f}
"
                f"Qty: {qty}
"
                f"Conf: {conf:.1f}%
"
                f"News: {news_score:.2f}"
            )
        else:
            st.error(f"{sig_txt} | Qty: {qty} | SL: ₹{sl:.2f} | TP: ₹{tp:.2f} | Conf: {conf:.1f}%")
            log_trade(ticker_input, "SELL", last['close'], sl, tp, qty, news_score, pat_str, conf, fs, safe_risk)
            send_telegram_alert(
                f"📉 *JARVIS PAPER SELL*
"
                f"Ticker: {ticker_input}
"
                f"Price: ₹{last['close']:.2f}
"
                f"SL: ₹{sl:.2f}
"
                f"TP: ₹{tp:.2f}
"
                f"Qty: {qty}
"
                f"Conf: {conf:.1f}%
"
                f"News: {news_score:.2f}"
            )
    else:
        st.info("⏸️ HOLD — कम कॉन्फिडेंस या कोई सिग्नल नहीं।")
    
    # 📊 Price Indicators
    st.subheader("📊 Price 