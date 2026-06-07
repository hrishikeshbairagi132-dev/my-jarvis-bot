import streamlit as st
from core import fetch_data

st.set_page_config(page_title="JARVIS Pro", layout="wide")
st.title("🦅 JARVIS Pro Terminal")

q = st.text_input("Enter Ticker (e.g. BHEL or BTC)")

if st.button("Search"):
    df = fetch_data(q)
    if df is not None and not df.empty:
        # yfinance के नए वर्ज़न के लिए यह तरीका सबसे सही है
        last_close = df['Close'].iloc[-1]
        last_rsi = df['rsi'].iloc[-1]
        
        st.metric("Live Price", f"{float(last_close):.2f}")
        st.write(f"RSI: {float(last_rsi):.2f}")
    else:
        st.error("Ticker not found or network issue.")

st.markdown("---")
st.info("No signal loaded.")
