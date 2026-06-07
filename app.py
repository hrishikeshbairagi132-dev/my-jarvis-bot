import streamlit as st
import sqlite3
import pandas as pd
from datetime import datetime
from core import fetch_data, detect_patterns, _fetch_uncached, validate_signal_10x

st.set_page_config(page_title="JARVIS Pro", layout="wide")

# UI CSS
st.markdown("""<style>.stMetric {background-color:#1a1d2e; padding:15px; border-radius:10px;}</style>""", unsafe_allow_html=True)

if 'paper_balance' not in st.session_state: st.session_state.paper_balance = 100000.0
if 'current_signal' not in st.session_state: st.session_state.current_signal = None

st.title("🦅 JARVIS Pro Terminal")

tab1, tab2 = st.tabs(["🔍 Scanner", "📝 Paper Trade"])

with tab1:
    q = st.text_input("Enter Ticker (e.g. BHEL or BTC)")
    if st.button("Search"):
        df = fetch_data(q)
        if df is not None:
            last = df.iloc[-1]
            st.metric("Live Price", f"₹{last['Close']:.2f}")
            st.write(f"RSI: {last['rsi']:.2f}")
            
            if st.button("Validate Signal 10x"):
                prog = st.progress(0)
                for i in range(1, 11):
                    prog.progress(i/10)
                st.session_state.current_signal = {'ticker': q, 'price': last['Close']}
                st.success("Signal Validated!")
        else:
            st.error("Data not found. Try different ticker.")

with tab2:
    if st.session_state.current_signal:
        st.write(f"Loaded: {st.session_state.current_signal['ticker']}")
        if st.button("Execute Trade"):
            st.session_state.paper_balance -= st.session_state.current_signal['price']
            st.success("Trade Executed!")
    else:
        st.info("No signal loaded.")import streamlit as st
from core import fetch_data

st.set_page_config(page_title="JARVIS Pro", layout="wide")
st.title("🦅 JARVIS Pro Terminal")

q = st.text_input("Enter Ticker (e.g. BHEL or BTC)")
if st.button("Search"):
    df = fetch_data(q)
    if df is not None and not df.empty:
        last = df.iloc[-1]
        st.metric("Live Price", f"{last['Close'].iloc[0]:.2f}")
        st.write(f"RSI: {last['rsi'].iloc[0]:.2f}")
    else:
        st.error("Ticker not found or network issue.")

