import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf
import plotly.graph_objects as go
from datetime import datetime
import pytz
import csv
import os

# ---------- पेज सेटअप ----------
st.set_page_config(page_title="JARVIS V1.8 FINAL", layout="wide")
st.title("🦅 JARVIS V1.8 FINAL — No.1 Engine + सम्पूर्ण सुरक्षा")
st.markdown("*tz-safe • Crash-Proof Logging • Noise Filter • All Bugs Fixed*")

# ---------- साइडबार ----------
st.sidebar.header("⚙️ कंट्रोल पैनल")
ticker_input = st.sidebar.text_input("टिकर (TATAMOTORS, RELIANCE, BTC-USD):", "TATAMOTORS").upper().strip()
capital = st.sidebar.number_input("कुल पूंजी (₹):", min_value=100.0, value=25000.0, step=1000.0)
st.sidebar.markdown("---")
st.sidebar.info("🔒 yfinance लाइव डेटा • पूर्णतः क्रैश-प्रूफ")

# ---------- न्यूज़ सेंटीमेंट ----------
def fetch_news_sentiment(ticker):
    pos_words = ['growth','profit','surge','bullish','dividend','deal','win','order','success','buy',
                 'positive','rally','jump','upgrade','record','gain','boost','expansion','partnership']
    neg_words = ['loss','drop','slump','bearish','fine','fraud','decline','risk','fail','sell',
                 'negative','crash','downgrade','debt','investigation','layoff','cut','penalty']
    try:
        tick = yf.Ticker(ticker)
        news_items = tick.news
        if not news_items: return 0.0, []
        headlines, total_score, count = [], 0.0, 0
        for item in news_items[:5]:
            title = item.get('title', '')
            if not title: continue
            headlines.append(title)
            title_lower = title.lower()
            score = sum(0.3 for w in pos_words if w in title_lower) - sum(0.3 for w in neg_words if w in title_lower)
            total_score += score
            count += 1
        if count == 0: return 0.0, headlines
        return round(max(-1.0, min(1.0, total_score / count)), 2), headlines[:5]
    except:
        return 0.0, []

# ---------- डेटा फेचिंग (इंडिकेटर सहित, tz-safe) ----------
@st.cache_data(ttl=60)
def fetch_data(ticker):
    try:
        if not (ticker.endswith(".NS") or ticker.endswith(".BO") or "-" in ticker):
            ticker += ".NS"
        df = yf.Ticker(ticker).history(period="60d", interval="15m")
        if df.empty or len(df) < 60:
            return None

        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.droplevel(0)
        df.columns = [c.lower() for c in df.columns]

        # ✅ tz-safe इंडेक्स हैंडलिंग
        if getattr(df.index, "tz", None) is not None:
            df.index = df.index.tz_localize(None)

        required = ['open','high','low','close','volume']
        if not all(c in df.columns for c in required):
            return None

        # ---------- इंडिकेटर्स ----------
        df['ema20'] = df['close'].ewm(span=20, adjust=False).mean()
        df['ema50'] = df['close'].ewm(span=50, adjust=False).mean()

        # VWAP (डेली रीसेट)
        df['vwap_num'] = df['volume'] * (df['high'] + df['low'] + df['close']) / 3
        df['date'] = df.index.date
        df['vwap'] = df.groupby('date')['vwap_num'].cumsum() / df.groupby('date')['volume'].cumsum()

        # ATR (True Range, Wilder smoothing)
        high_low = df['high'] - df['low']
        high_close = abs(df['high'] - df['close'].shift(1))
        low_close = abs(df['low'] - df['close'].shift(1))
        tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        df['atr'] = tr.ewm(alpha=1/14, adjust=False).mean()

        # RSI (Wilder)
        delta = df['close'].diff()
        gain = delta.clip(lower=0)
        loss = -delta.clip(upper=0)
        avg_gain = gain.ewm(alpha=1/14, adjust=False).mean()
        avg_loss = loss.ewm(alpha=1/14, adjust=False).mean()
        rs = avg_gain / avg_loss.replace(0, 1e-10)
        df['rsi'] = 100 - (100 / (1 + rs))

        # ADX (Wilder)
        plus_dm = (df['high'].diff()).clip(lower=0)
        minus_dm = (-df['low'].diff()).clip(lower=0)
        avg_plus_dm = plus_dm.ewm(alpha=1/14, adjust=False).mean()
        avg_minus_dm = minus_dm.ewm(alpha=1/14, adjust=False).mean()
        plus_di = 100 * (avg_plus_dm / df['atr'])
        minus_di = 100 * (avg_minus_dm / df['atr'])
        dx = 100 * abs(plus_di - minus_di) / (plus_di + minus_di + 1e-10)
        df['adx'] = dx.ewm(alpha=1/14, adjust=False).mean()

        # Volume ratio
        df['vol_sma'] = df['volume'].rolling(20).mean()
        df['vol_ratio'] = df['volume'] / df['vol_sma']

        return df.dropna()
    except:
        return None

# ---------- पैटर्न डिटेक्शन (नॉइज़ फिल्टर, क्लोज-बेस्ड नेकलाइन) ----------
def detect_patterns(df):
    df = df.copy()
    n = len(df)

    current_price = df['close'].iloc[-1]
    is_penny = current_price < 100
    vol_threshold = 2.5 if is_penny else 1.2

    # कैंडलस्टिक पैटर्न
    body = abs(df['close'] - df['open'])
    candle_range = df['high'] - df['low']
    lower_shadow = np.minimum(df['open'], df['close']) - df['low']
    upper_shadow = df['high'] - np.maximum(df['open'], df['close'])

    df['candle_pattern'] = "No Pattern"
    df.loc[body <= (candle_range * 0.1), 'candle_pattern'] = "Doji ⏳"
    df.loc[(lower_shadow >= body * 2) & (upper_shadow <= body * 0.5), 'candle_pattern'] = "Hammer 🔨"
    is_green = df['close'] > df['open']
    was_red = df['close'].shift(1) < df['open'].shift(1)
    engulfing = (df['open'] <= df['close'].shift(1)) & (df['close'] >= df['open'].shift(1)) & (body > body.shift(1))
    df.loc[is_green & was_red & engulfing, 'candle_pattern'] = "Bullish Engulfing 📈"

    # स्थानीय न्यूनतम/उच्चतम
    roll_min = df['close'].rolling(5, center=True, min_periods=1).min()
    roll_max = df['close'].rolling(5, center=True, min_periods=1).max()
    tol = 0.015
    is_local_min = (df['close'] <= roll_min * (1 + tol))
    is_local_max = (df['close'] >= roll_max * (1 - tol))

    min_idx = np.where(is_local_min)[0]
    max_idx = np.where(is_local_max)[0]

    df['chart_pattern'] = "Scanning Trends..."
    df['pattern_signal'] = "HOLD"
    df['pattern_marker'] = ""

    for i in range(20, n):
        recent_min = [idx for idx in min_idx if i-20 <= idx < i]
        recent_max = [idx for idx in max_idx if i-20 <= idx < i]

        # W-पैटर्न
        if len(recent_min) >= 2:
            t1_idx = recent_min[-2]
            t2_idx = recent_min[-1]
            if t2_idx - t1_idx >= 4:   # नॉइज़ फिल्टर
                t1 = df['low'].iloc[t1_idx]
                t2 = df['low'].iloc[t2_idx]
                if abs(t1 - t2) / max(t1, t2) < 0.025:
                    mid_closes = df['close'].iloc[t1_idx:t2_idx+1]
                    if len(mid_closes) > 1:
                        neckline = mid_closes.max()   # क्लोज-बेस्ड नेकलाइन
                        if df['close'].iloc[i] > neckline:
                            df.loc[df.index[i], 'chart_pattern'] = "W-Pattern (Double Bottom) 🚀"
                            rsi_now = df['rsi'].iloc[i]
                            vol_now = df['vol_ratio'].iloc[i]
                            if 45 <= rsi_now <= 65 and vol_now > vol_threshold:
                                df.loc[df.index[i], 'pattern_signal'] = "BUY (SURE PATTERN)"
                                df.loc[df.index[i], 'pattern_marker'] = "W"

        # M-पैटर्न
        if len(recent_max) >= 2:
            p1_idx = recent_max[-2]
            p2_idx = recent_max[-1]
            if p2_idx - p1_idx >= 4:
                p1 = df['high'].iloc[p1_idx]
                p2 = df['high'].iloc[p2_idx]
                if abs(p1 - p2) / max(p1, p2) < 0.025:
                    mid_closes = df['close'].iloc[p1_idx:p2_idx+1]
                    if len(mid_closes) > 1:
                        neckline = mid_closes.min()
                        if df['close'].iloc[i] < neckline:
                            df.loc[df.index[i], 'chart_pattern'] = "M-Pattern (Double Top) 📉"
                            rsi_now = df['rsi'].iloc[i]
                            if rsi_now > 65:
                                df.loc[df.index[i], 'pattern_signal'] = "SELL (OVERBOUGHT)"
                                df.loc[df.index[i], 'pattern_marker'] = "M"

    # पिछली 3 कैंडल का बफर
    last_signals = df['pattern_signal'].iloc[-3:].values
    bullish_pat = any(s.startswith("BUY") for s in last_signals)
    bearish_pat = any(s.startswith("SELL") for s in last_signals)

    last_chart = df['chart_pattern'].iloc[-1]
    pattern_desc = []
    if "W-Pattern" in last_chart:
        pattern_desc.append("W‑Pattern (Double Bottom)")
    if "M-Pattern" in last_chart:
        pattern_desc.append("M‑Pattern (Double Top)")
    pattern_str = ", ".join(pattern_desc) if pattern_desc else "कोई स्पष्ट चार्ट पैटर्न नहीं"

    last_candle = df['candle_pattern'].iloc[-1]

    return df, bullish_pat, bearish_pat, pattern_str, last_candle

# ---------- ट्रेड लॉगिंग (क्रैश-प्रूफ) ----------
def log_trade(ticker, signal, price, sl, tp, qty, news_score, pattern):
    try:
        file_exists = os.path.exists('trade_log.csv')
        with open('trade_log.csv', 'a', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            if not file_exists:
                writer.writerow(['Time', 'Ticker', 'Signal', 'Price', 'SL', 'TP', 'Qty', 'News_Score', 'Pattern'])
            writer.writerow([
                datetime.now(pytz.timezone('Asia/Kolkata')).strftime('%Y-%m-%d %H:%M'),
                ticker, signal, price, sl, tp, qty, news_score, pattern
            ])
        return True
    except Exception:
        return False

# ---------- मुख्य एप ----------
if st.sidebar.button("🚀 विश्लेषण शुरू करें (V1.8 Final)", use_container_width=True):
    india_tz = pytz.timezone('Asia/Kolkata')
    now = datetime.now(india_tz)
    market_open = now.replace(hour=9, minute=15, second=0, microsecond=0)
    if now < market_open:
        st.warning("⏳ भारतीय बाज़ार 9:15 AM बजे खुलता है। कृपया प्रतीक्षा करें।")
        st.stop()

    df = fetch_data(ticker_input)
    if df is None or len(df) < 60:
        st.error("❌ डेटा लोड नहीं हो सका या पर्याप्त डेटा नहीं है। टिकर/इंटरनेट जाँचें।")
        st.stop()

    raw_ticker = ticker_input.replace(".NS","").replace(".BO","")
    news_score, headlines = fetch_news_sentiment(raw_ticker)

    df, bullish_pat, bearish_pat, pattern_str, last_candle = detect_patterns(df)
    last = df.iloc[-1]

    # ---------- सिग्नल लॉजिक ----------
    is_penny = last['close'] < 100
    vol_threshold = 2.0 if is_penny else 1.3

    tech_buy = (
        (last['close'] > last['vwap']) and
        (last['close'] > last['ema20']) and
        (last['ema20'] > last['ema50']) and
        (last['rsi'] > 35) and (last['rsi'] < 75) and
        (last['adx'] > 15) and
        (last['vol_ratio'] > vol_threshold) and
        (news_score >= -0.2)
    )

    tech_sell = (
        (last['close'] < last['vwap']) and
        (last['close'] < last['ema20']) and
        (last['ema20'] < last['ema50']) and
        (last['rsi'] > 30) and (last['rsi'] < 65) and
        (last['adx'] > 15) and
        (last['vol_ratio'] > vol_threshold) and
        (news_score <= 0.2)
    )

    if tech_buy and bullish_pat:
        signal = "BUY (तकनीकी + W‑पैटर्न)"
        strength = "मजबूत"
    elif tech_buy and not bullish_pat:
        signal = "BUY (तकनीकी)"
        strength = "सामान्य"
    elif tech_sell and bearish_pat:
        signal = "SELL (तकनीकी + M‑पैटर्न)"
        strength = "मजबूत"
    elif tech_sell and not bearish_pat:
        signal = "SELL (तकनीकी)"
        strength = "सामान्य"
    elif bullish_pat and not tech_buy and not tech_sell:
        signal = "BUY (W‑पैटर्न, सीमित जोखिम)"
        strength = "कमजोर (साइडवेज)"
    elif bearish_pat and not tech_buy and not tech_sell:
        signal = "SELL (M‑पैटर्न, सीमित जोखिम)"
        strength = "कमजोर (साइडवेज)"
    else:
        signal = "HOLD"
        strength = ""

    # ---------- जोखिम प्रबंधन ----------
    if "BUY" in signal or "SELL" in signal:
        risk_multiplier = 1.0
        if "कमजोर" in strength:
            risk_multiplier = 0.5
        risk_per_share = last['atr'] * 1.5
        if risk_per_share <= 0:
            st.error("⚠️ ATR शून्य है।")
            st.stop()
        qty_risk = int((capital * 0.02 * risk_multiplier) / risk_per_share)
        qty_capital = int(capital / last['close'])
        qty = min(qty_risk, qty_capital)
        if qty <= 0:
            signal = "HOLD"
        if "BUY" in signal:
            sl = last['close'] - risk_per_share
            tp = last['close'] + (last['atr'] * 3.0)
        else:
            sl = last['close'] + risk_per_share
            tp = last['close'] - (last['atr'] * 3.0)
    else:
        qty = sl = tp = 0.0

    # ---------- UI रेंडर ----------
    st.subheader("📰 लाइव न्यूज़ एनालिसिस")
    if headlines:
        emoji = "🟢" if news_score > 0.15 else ("🔴" if news_score < -0.15 else "⚪")
        st.markdown(f"**समग्र सेंटीमेंट:** {emoji} {news_score:.2f}")
        for i, h in enumerate(headlines):
            st.markdown(f"- {i+1}. {h}")
    else:
        st.info("कोई ताज़ा न्यूज़ उपलब्ध नहीं।")
    st.markdown("---")

    st.subheader("📐 चार्ट पैटर्न स्कैन")
    col_pat1, col_pat2 = st.columns(2)
    col_pat1.metric("चार्ट पैटर्न", pattern_str)
    col_pat2.metric("कैंडल पैटर्न", last_candle)
    st.markdown("---")

    if signal != "HOLD":
        if "BUY" in signal:
            st.success(f"🚀 **{signal}** | Qty: {qty} | SL: ₹{sl:.2f} | TP: ₹{tp:.2f} | News: {news_score:.2f}")
            log_trade(ticker_input, "BUY", last['close'], sl, tp, qty, news_score, pattern_str)
        else:
            st.error(f"📉 **{signal}** | Qty: {qty} | SL: ₹{sl:.2f} | TP: ₹{tp:.2f} | News: {news_score:.2f}")
            log_trade(ticker_input, "SELL", last['close'], sl, tp, qty, news_score, pattern_str)
    else:
        st.info("⏸️ HOLD — कोई उच्च-गुणवत्ता सिग्नल नहीं।")

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("वर्तमान मूल्य", f"₹{last['close']:.2f}")
    col2.metric("RSI", f"{last['rsi']:.1f}")
    col3.metric("ADX", f"{last['adx']:.1f}")
    col4.metric("ATR", f"₹{last['atr']:.2f}")

    st.subheader("📊 लाइव चार्ट (कैंडलस्टिक + VWAP + EMA20)")
    fig = go.Figure()
    fig.add_trace(go.Candlestick(x=df.index[-100:], open=df['open'].iloc[-100:],
                                 high=df['high'].iloc[-100:], low=df['low'].iloc[-100:],
                                 close=df['close'].iloc[-100:], name="मूल्य"))
    fig.add_trace(go.Scatter(x=df.index[-100:], y=df['vwap'].iloc[-100:],
                             line=dict(color='blue', width=1.5), name="VWAP"))
    fig.add_trace(go.Scatter(x=df.index[-100:], y=df['ema20'].iloc[-100:],
                             line=dict(color='orange', width=1.5), name="EMA20"))

    last_100 = df.iloc[-100:]
    marker_rows = last_100[last_100['pattern_marker'] != ""]
    if not marker_rows.empty:
        for idx, row in marker_rows.iterrows():
            marker = row['pattern_marker']
            if marker == "W":
                y_pos = row['low'] * 0.999
                fig.add_annotation(x=idx, y=y_pos, text="W", showarrow=True,
                                   arrowhead=1, bgcolor="green")
            elif marker == "M":
                y_pos = row['high'] * 1.001
                fig.add_annotation(x=idx, y=y_pos, text="M", showarrow=True,
                                   arrowhead=1, bgcolor="red")

    fig.update_layout(template="plotly_dark", height=500, xaxis_rangeslider_visible=False,
                      margin=dict(l=10, r=10, t=10, b=10))
    st.plotly_chart(fig, use_container_width=True)

    # ✅ सुरक्षित लॉग रीडिंग
    if os.path.exists('trade_log.csv'):
        st.subheader('📋 हाल के ट्रेड सिग्नल (लॉग)')
        try:
            log_df = pd.read_csv('trade_log.csv')
            st.dataframe(log_df.tail(5), use_container_width=True)
        except Exception:
            st.info("trade_log अभी सुरक्षित रूप से नहीं पढ़ा जा सका.")

    st.warning("⚠️ **अस्वीकरण:** यह केवल शैक्षिक उद्देश्यों के लिए है। पहले पेपर ट्रेडिंग करें।")