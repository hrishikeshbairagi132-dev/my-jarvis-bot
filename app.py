import streamlit as st
import yfinance as yf
import pandas as pd

# पेज की सेटिंग
st.set_page_config(page_title="Stock Analysis Dashboard", layout="wide")
st.title("📊 एडवांस स्टॉक एनालिसिस और न्यूज़ डैशबोर्ड")

# --- 1. SESSION STATE (मेमोरी) को सेट करना ---
# इससे ऐप रीलोड होने पर भी आपका डेटा डिलीट नहीं होगा
if "analysis_done" not in st.session_state:
    st.session_state["analysis_done"] = False
if "stock_data" not in st.session_state:
    st.session_state["stock_data"] = None
if "ticker_name" not in st.session_state:
    st.session_state["ticker_name"] = ""
if "news_data" not in st.session_state:
    st.session_state["news_data"] = []

# --- 2. SIDEBAR / INPUT PANEL ---
st.sidebar.header("कंट्रोल पैनल")
ticker_input = st.sidebar.text_input("भारतीय शेयर के लिए .NS लगाएं (जैसे: RELIANCE.NS)", "RELIANCE.NS").upper().strip()

# टाइम फ्रेम सेटिंग्स (सुरक्षित डिफॉल्ट्स)
period_choice = st.sidebar.selectbox("कितने दिनों का डेटा चाहिए?", ["1mo", "3mo", "6mo", "1y"])
interval_choice = st.sidebar.selectbox("एक कैंडल का समय (Interval)", ["15m", "30m", "60m", "1d"])

# --- 3. डेटा और न्यूज़ लाने वाले फंक्शन्स ---
def get_stock_data(ticker, period, interval):
    try:
        stock = yf.Ticker(ticker)
        df = stock.history(period=period, interval=interval)
        return df
    except Exception as e:
        return pd.DataFrame()

def get_stock_news(ticker):
    try:
        stock = yf.Ticker(ticker)
        # बिना किसी API Key के फ्री न्यूज़ पाने का तरीका
        return stock.news[:5] # सिर्फ टॉप 5 खबरें
    except Exception:
        return []

# --- 4. बटन क्लिक लॉजिक ---
if st.sidebar.button("Run Analysis", use_container_width=True):
    with st.spinner("डेटा और ताज़ा खबरें लोड हो रही हैं..."):
        df = get_stock_data(ticker_input, period_choice, interval_choice)
        news = get_stock_news(ticker_input)
        
        if df.empty:
            st.error(f"❌ '{ticker_input}' के लिए कोई डेटा नहीं मिला। कृपया टिकर का नाम जांचें।")
            st.session_state["analysis_done"] = False
        else:
            # सारा डेटा मेमोरी में सुरक्षित रख रहे हैं
            st.session_state["stock_data"] = df
            st.session_state["news_data"] = news
            st.session_state["ticker_name"] = ticker_input
            st.session_state["analysis_done"] = True
            st.success("✅ एनालिसिस पूरा हुआ!")

# --- 5. रिजल्ट डिस्प्ले पैनल (यह हमेशा स्क्रीन पर टिका रहेगा) ---
if st.session_state["analysis_done"]:
    df = st.session_state["stock_data"]
    news_list = st.session_state["news_data"]
    ticker = st.session_state["ticker_name"]
    
    st.header(f"📈 {ticker} का लाइव एनालिसिस")
    
    # दो कॉलम्स में स्क्रीन को बांटना
    col1, col2 = st.columns([2, 1])
    
    with col1:
        st.subheader("क्लोजिंग प्राइस चार्ट")
        st.line_chart(df['Close'])
        
        # डेटा टेबल
        with st.expander("पूरा डेटा टेबल देखें"):
            st.dataframe(df.tail(20))
            
    with col2:
        st.subheader("📰 ताज़ा खबरें (News Feed)")
        if not news_list:
            st.warning("इस स्टॉक के लिए फिलहाल कोई खबर नहीं मिली।")
        else:
            for item in news_list:
                title = item.get('title', 'No Title')
                link = item.get('link', '#')
                publisher = item.get('publisher', 'Unknown')
                
                st.markdown(f"**[{title}]({link})**")
                st.caption(f"पब्लिशर: {publisher}")
                st.markdown("---")

else:
    # फॉलबैक मैसेज (Fallback Message) जब तक बटन न दबे
    st.info("👈 बाईं तरफ टिकर नाम डालकर 'Run Analysis' बटन पर क्लिक करें।")

# --- 6. लाइव डिबग पैनल (सामने दिखेगा कि बैकएंड में क्या चल रहा है) ---
st.markdown("---")
with st.expander("🛠️ लाइव डिबग पैनल (Technical Check)"):
    st.write("**App State:**", "एनालिसिस एक्टिव है" if st.session_state["analysis_done"] else "रुका हुआ है")
    st.write("**मेमोरी में मौजूद टिकर:**", st.session_state["ticker_name"])
    if st.session_state["stock_data"] is not None:
        st.write("**डेटा रो (Rows) की संख्या:**", len(st.session_state["stock_data"]))
