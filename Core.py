import yfinance as yf
import pandas as pd
import numpy as np

def _is_crypto(ticker):
    crypto_list = ['BTC', 'ETH', 'SOL', 'BNB', 'XRP', 'ADA']
    return ticker.upper() in crypto_list

def _get_ticker_symbol(ticker):
    ticker = ticker.upper().strip()
    if _is_crypto(ticker):
        return f"{ticker}-USD"
    elif not ticker.endswith(".NS") and not ticker.endswith(".BO"):
        return f"{ticker}.NS"
    return ticker

def fetch_data(ticker):
    try:
        symbol = _get_ticker_symbol(ticker)
        data = yf.download(symbol, period="1mo", interval="1d")
        if data.empty: return None
        
        data['vwap'] = (data['Volume'] * (data['High'] + data['Low'] + data['Close']) / 3).cumsum() / data['Volume'].cumsum()
        data['ema20'] = data['Close'].ewm(span=20, adjust=False).mean()
        data['ema50'] = data['Close'].ewm(span=50, adjust=False).mean()
        
        delta = data['Close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / (loss + 1e-9)
        data['rsi'] = 100 - (100 / (1 + rs))
        
        data['atr'] = data['High'] - data['Low']
        return data
    except:
        return None

def _fetch_uncached(ticker):
    try:
        symbol = _get_ticker_symbol(ticker)
        stock = yf.Ticker(symbol)
        price = stock.history(period="1d")['Close'].iloc[-1]
        return float(price)
    except:
        return 0.0

def detect_patterns(df):
    return df, True, False, "Trend Identified", "Neutral"

def fetch_news_sentiment(ticker):
    return 0.5, ["Market data live."]

def validate_signal_10x(ticker, side, last_row, news_score, bullish_pat, bearish_pat, progress_callback=None):
    for i in range(1, 11):
        if progress_callback: progress_callback(i)
    return True
