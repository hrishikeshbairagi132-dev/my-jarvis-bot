import streamlit as st
import logging
import os
import sqlite3
import pandas as pd
import csv
import pytz
from datetime import datetime
from core import (
    fetch_data, detect_patterns, fetch_news_sentiment,
    validate_signal_10x, _fetch_uncached
)

# ---------- Logging ----------
log_file = "jarvis.log"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.FileHandler(log_file), logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

st.set_page_config(page_title="JARVIS Pro", page_icon="🦅", layout="wide", initial_sidebar_state="collapsed")

# ---------- Dark Theme CSS ----------
st.markdown("""
<style>
    body, .stApp { background-color: #0e1117; color: #e0e0e0; }
    .main > div { padding-top: 1rem; }
    [data-testid="stSidebar"] { background-color: #131722; }
    div[data-testid="stMetric"] { background-color: #1a1d2e; border-radius: 12px; padding: 10px; border: 1px solid #2a2f45; }
    div[data-testid="stMetricValue"] { font-size: 28px !important; font-weight: bold; color: #00ffcc; }
    .stButton>button { width: 100%; border-radius: 10px; background-color: #00ffcc; color: #0e1117; font-weight: bold; border: none; }
    .stTabs [data-baseweb="tab-list"] { gap: 2px; }
    .stTabs [data-baseweb="tab"] { background-color: #1a1d2e; border-radius: 8px 8px 0 0; padding: 10px 16px; color: #a0a0a0; }
    .stTabs [aria-selected="true"] { background-color: #00ffcc !important; color: #0e1117 !important; }
    [data-testid="stSidebar"] .stRadio > div { gap: 8px; }
    .search-result-card { background-color: #1a1d2e; border-radius: 12px; padding: 20px; margin: 10px 0; border: 1px solid #2a2f45; }
    .trade-card { background-color: #1a1d2e; border-radius: 8px; padding: 10px; margin: 5px 0; border: 1px solid #2a2f45; }
    .signal-validated { background-color: #00ffcc; color: #0e1117; padding: 15px; border-radius: 10px; font-weight: bold; text-align: center; }
</style>
""", unsafe_allow_html=True)

# ---------- Session State ----------
if 'settings' not in st.session_state:
    st.session_state.settings = {'risk_capital': 25000.0, 'default_ticker': 'TATAMOTORS', 'dark_mode': True, 'language': 'Hindi'}
if 'watchlist' not in st.session_state: st.session_state.watchlist = []
if 'chat_history' not in st.session_state: st.session_state.chat_history = []
if 'recent_searches' not in st.session_state: st.session_state.recent_searches = []
if 'paper_balance' not in st.session_state: st.session_state.paper_balance = 100000.0
if 'paper_positions' not in st.session_state: st.session_state.paper_positions = []
if 'paper_trade_history' not in st.session_state: st.session_state.paper_trade_history = []
if 'current_signal' not in st.session_state: st.session_state.current_signal = None

# ---------- Database Init ----------
conn = sqlite3.connect('alerts.db')
c = conn.cursor()
c.execute('''CREATE TABLE IF NOT EXISTS alerts
             (id INTEGER PRIMARY KEY AUTOINCREMENT,
              ticker TEXT NOT NULL, target_price REAL NOT NULL,
              direction TEXT NOT NULL, triggered INTEGER DEFAULT 0,
              created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
conn.commit(); conn.close()

# ---------- Utilities ----------
def log_event(evt, msg): logger.info(f"{evt}: {msg}")
def safe_rerun():
    if hasattr(st, 'rerun'): st.rerun()
    else: st.experimental_rerun()
def handle_error(e, ctx):
    logger.error(f"Error in {ctx}: {e}", exc_info=True)
    st.error(f"Something went wrong in {ctx}. Please try again.")

# ---------- Paper Trading ----------
def execute_paper_trade(ticker, side, quantity, price):
    if side == 'BUY':
        cost = quantity * price
        if st.session_state.paper_balance < cost:
            return False, "Insufficient virtual balance."
        st.session_state.paper_balance -= cost
        existing = [p for p in st.session_state.paper_positions if p['ticker'] == ticker]
        if existing:
            pos = existing[0]
            total_qty = pos['qty'] + quantity
            pos['buy_price'] = (pos['buy_price'] * pos['qty'] + price * quantity) / total_qty
            pos['qty'] = total_qty
        else:
            st.session_state.paper_positions.append({
                'ticker': ticker, 'qty': quantity, 'buy_price': price, 'current_price': price
            })
    else:
        pos_list = [p for p in st.session_state.paper_positions if p['ticker'] == ticker and p['qty'] >= quantity]
        if not pos_list: return False, "Not enough shares to sell."
        pos = pos_list[0]
        st.session_state.paper_balance += quantity * price
        pos['qty'] -= quantity
        if pos['qty'] == 0: st.session_state.paper_positions.remove(pos)
    st.session_state.paper_trade_history.append({
        'timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        'ticker': ticker, 'side': side, 'quantity': quantity, 'price': price,
        'total': quantity * price
    })
    return True, f"{side} {quantity} shares of {ticker} executed successfully."

def get_total_portfolio_value():
    total = st.session_state.paper_balance
    for pos in st.session_state.paper_positions:
        total += pos['qty'] * pos['current_price']
    return total

def refresh_positions():
    for pos in st.session_state.paper_positions:
        data = _fetch_uncached(pos['ticker'])
        if data: pos['current_price'] = data

# ---------- Navigation ----------
st.sidebar.title("🦅 JARVIS Pro")
nav = st.sidebar.radio("Navigate",
    ["📊 Dashboard", "🤖 AI Chat", "🔍 Market Scanner", "📰 News Intelligence",
     "📝 Paper Trading", "⭐ Watchlist", "🔔 Alerts", "⚙️ Settings"],
    index=0, label_visibility="collapsed")

try:
    if nav == "📊 Dashboard":
        st.title("Dashboard")
        total = get_total_portfolio_value()
        c1,c2,c3 = st.columns(3)
        c1.metric("Portfolio Value", f"₹{total:,.2f}")
        c2.metric("Cash", f"₹{st.session_state.paper_balance:,.2f}")
        c3.metric("Open Positions", len(st.session_state.paper_positions))
        st.info("Paper trading active. Use Market Scanner to analyse assets.")

    elif nav == "🤖 AI Chat":
        st.title("AI Chat Advisor")
        with st.form("chat"):
            q = st.text_input("Ask anything")
            if st.form_submit_button("Send") and q:
                st.session_state.chat_history.append({"role":"user","content":q})
                st.session_state.chat_history.append({"role":"assistant","content":"AI will answer fully in a future update."})
        for m in st.session_state.chat_history:
            st.markdown(f"**{'You' if m['role']=='user' else 'JARVIS'}:** {m['content']}")

    elif nav == "🔍 Market Scanner":
        st.title("Market Scanner")
        c1,c2 = st.columns([5,1])
        q = c1.text_input("Symbol (e.g. RELIANCE, BTC)", key="search")
        if c2.button("🔍 Search", use_container_width=True) and q:
            query = q.strip().upper()
            if query not in st.session_state.recent_searches:
                st.session_state.recent_searches.append(query)
                st.session_state.recent_searches = st.session_state.recent_searches[-20:]

            df = fetch_data(query)
            if df is None:
                st.error("Could not load data. Check ticker or network.")
            else:
                news_score, headlines = fetch_news_sentiment(query)
                df, bullish_pat, bearish_pat, pattern_str, last_candle = detect_patterns(df)
                last = df.iloc[-1]

                is_penny = last['close'] < 100
                vol_threshold = 2.0 if is_penny else 1.3

                tech_buy = (
                    (last['close'] > last['vwap']) and
                    (last['close'] > last['ema20']) and
                    (last['ema20'] > last['ema50']) and
                    (35 < last['rsi'] < 75) and
                    (last['adx'] > 15) and
                    (last['vol_ratio'] > vol_threshold) and
                    (news_score >= -0.2)
                )
                tech_sell = (
                    (last['close'] < last['vwap']) and
                    (last['close'] < last['ema20']) and
                    (last['ema20'] < last['ema50']) and
                    (30 < last['rsi'] < 65) and
                    (last['adx'] > 15) and
                    (last['vol_ratio'] > vol_threshold) and
                    (news_score <= 0.2)
                )

                st.subheader("📊 Signal Checklist")
                col1, col2, col3 = st.columns(3)
                col1.metric("Close > VWAP", "✅" if last['close'] > last['vwap'] else "❌")
                col1.metric("Close > EMA20", "✅" if last['close'] > last['ema20'] else "❌")
                col2.metric("EMA20 > EMA50", "✅" if last['ema20'] > last['ema50'] else "❌")
                col2.metric("RSI Range", "✅" if (35 < last['rsi'] < 75) else "❌")
                col3.metric("ADX > 15", "✅" if last['adx'] > 15 else "❌")
                col3.metric("Volume Boost", "✅" if last['vol_ratio'] > vol_threshold else "❌")
                st.metric("News Score OK", "✅" if (news_score >= -0.2) else "❌")
                st.write(f"**Chart Pattern:** {pattern_str}")

                if tech_buy and bullish_pat: sig_type = "BUY_STRONG"
                elif tech_buy: sig_type = "BUY_TECH"
                elif bullish_pat: sig_type = "BUY_PATTERN"
                elif tech_sell and bearish_pat: sig_type = "SELL_STRONG"
                elif tech_sell: sig_type = "SELL_TECH"
                elif bearish_pat: sig_type = "SELL_PATTERN"
                else: sig_type = "HOLD"

                if "BUY" in sig_type or "SELL" in sig_type:
                    if st.button("🔍 Validate Signal 10x"):
                        side = "BUY" if "BUY" in sig_type else "SELL"
                        progress_bar = st.progress(0)
                        status_text = st.empty()

                        def progress_callback(iter_num):
                            progress_bar.progress(iter_num / 10)
                            status_text.text(f"Validating Signal Stability: {iter_num}/10...")

                        with st.spinner("Running 10x stability test..."):
                            stable = validate_signal_10x(query, side, last, news_score,
                                                         bullish_pat, bearish_pat, progress_callback)
                        if stable:
                            sl = last['close'] - (last['atr']*1.5) if side=="BUY" else last['close'] + (last['atr']*1.5)
                            tp = last['close'] + (last['atr']*3.0) if side=="BUY" else last['close'] - (last['atr']*3.0)
                            st.session_state.current_signal = {
                                'ticker': query, 'side': side, 'price': last['close'], 'sl': sl, 'tp': tp
                            }
                            st.markdown('<div class="signal-validated">🚨 VALIDATED SIGNAL: 100% Confirmed</div>', unsafe_allow_html=True)
                            st.success(f"**{sig_type}** signal validated. SL: ₹{sl:.2f}, TP: ₹{tp:.2f}")
                        else:
                            st.warning("Signal Unstable – Dropped")
                        progress_bar.empty(); status_text.empty()

    elif nav == "📰 News Intelligence":
        st.title("News Intelligence"); st.info("Coming soon.")

    elif nav == "📝 Paper Trading":
        st.title("Paper Trading")
        with st.expander("Place Order", True):
            c1,c2,c3,c4 = st.columns(4)
            ticker = c1.text_input("Ticker", st.session_state.settings['default_ticker']).upper()
            side = c2.selectbox("Side", ["BUY","SELL"])
            qty = c3.number_input("Qty", min_value=1, value=1)

            if st.button("💡 Fill via JARVIS Signal"):
                if st.session_state.current_signal:
                    s = st.session_state.current_signal
                    ticker = s['ticker']
                    side = s['side']
                    price = s['price']
                    st.query_params(ticker=ticker, side=side, price=price)
                    st.info(f"Signal loaded: {ticker} {side} @ ₹{price:.2f}")
                else:
                    st.warning("No validated signal available. Run Scanner first.")

            try: curr = _fetch_uncached(ticker)
            except: curr = 0
            price = c4.number_input("Price (₹)", value=float(curr) if curr else 0.0, format="%.2f")
            if st.button("Execute Trade", use_container_width=True):
                if qty<=0 or price<=0: st.error("Invalid qty/price")
                else:
                    ok, msg = execute_paper_trade(ticker, side, qty, price)
                    if ok: st.success(msg); safe_rerun()
                    else: st.error(msg)

        st.markdown("---")
        col1,col2 = st.columns(2)
        with col1:
            st.subheader("Positions")
            if st.button("🔄 Refresh Prices"): refresh_positions()
            for pos in st.session_state.paper_positions:
                pnl = (pos['current_price'] - pos['buy_price']) * pos['qty']
                st.markdown(f"<div class='trade-card'><b>{pos['ticker']}</b> Qty:{pos['qty']} Entry:{pos['buy_price']:.2f} P&L: ₹{pnl:.2f}</div>", unsafe_allow_html=True)
            if not st.session_state.paper_positions: st.info("No open positions")
        with col2:
            st.subheader("History")
            if st.session_state.paper_trade_history:
                st.dataframe(pd.DataFrame(st.session_state.paper_trade_history).tail(10), use_container_width=True)
            else: st.info("No trades yet")

    elif nav == "⭐ Watchlist":
        st.title("Watchlist")
        new = st.text_input("Add ticker")
        if st.button("Add") and new:
            if new.upper() not in st.session_state.watchlist:
                st.session_state.watchlist.append(new.upper())
        for i,item in enumerate(st.session_state.watchlist):
            c1,c2 = st.columns([4,1])
            c1.write(f"• {item}")
            if c2.button("X", key=f"del{i}"): st.session_state.watchlist.pop(i); safe_rerun()

    elif nav == "🔔 Alerts":
        st.title("Price Alerts")
        with st.form("alert_form"):
            c1,c2,c3 = st.columns([2,2,1])
            alert_ticker = c1.text_input("Ticker", value=st.session_state.settings['default_ticker']).upper()
            alert_price = c2.number_input("Target Price (₹)", min_value=0.01, value=100.0, step=0.01)
            alert_dir = c3.selectbox("Direction", ["above", "below"])
            if st.form_submit_button("Set Alert"):
                if alert_ticker and alert_price > 0:
                    conn = sqlite3.connect('alerts.db')
                    c = conn.cursor()
                    c.execute("INSERT INTO alerts (ticker, target_price, direction) VALUES (?, ?, ?)",
                              (alert_ticker, alert_price, alert_dir))
                    conn.commit(); conn.close()
                    st.success(f"Alert set for {alert_ticker} when price goes {alert_dir} ₹{alert_price:.2f}!")
                else: st.error("Invalid input.")
        conn = sqlite3.connect('alerts.db')
        alerts_df = pd.read_sql_query("SELECT id, ticker, target_price, direction, triggered, created_at FROM alerts ORDER BY created_at DESC", conn)
        conn.close()
        if not alerts_df.empty:
            st.subheader("Your Active Alerts")
            for idx, row in alerts_df.iterrows():
                col1, col2, col3, col4 = st.columns([2,2,2,1])
                col1.write(f"**{row['ticker']}**")
                col2.write(f"{row['direction']} ₹{row['target_price']:.2f}")
                col3.write("🔔 Triggered" if row['triggered'] else "⏳ Waiting")
                if col4.button("Delete", key=f"del_alert_{row['id']}"):
                    conn = sqlite3.connect('alerts.db')
                    c = conn.cursor()
                    c.execute("DELETE FROM alerts WHERE id = ?", (row['id'],))
                    conn.commit(); conn.close()
                    st.success("Alert deleted."); safe_rerun()
        else: st.info("No alerts set.")

    elif nav == "⚙️ Settings":
        st.title("Settings")
        with st.form("set"):
            rc = st.number_input("Risk Capital", value=st.session_state.settings['risk_capital'])
            dt = st.text_input("Default Ticker", st.session_state.settings['default_ticker']).upper()
            lang = st.selectbox("Language", ["Hindi","English"], index=0)
            if st.form_submit_button("Save"):
                st.session_state.settings.update({'risk_capital':rc,'default_ticker':dt,'language':lang})
                st.success("Settings saved!")
        st.caption("App Version: 2.0.0 (Modular Core)")

except Exception as e:
    handle_error(e, "main app")
    st.stop()
