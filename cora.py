import pandas as pd
import numpy as np
import yfinance as yf
import requests
import time

# ---------- Crypto Map & Search ----------
CRYPTO_MAP = {
    'BTC': 'bitcoin', 'ETH': 'ethereum', 'DOGE': 'dogecoin', 'XRP': 'ripple',
    'ADA': 'cardano', 'SOL': 'solana', 'MATIC': 'matic-network', 'DOT': 'polkadot',
    'SHIB': 'shiba-inu', 'AVAX': 'avalanche-2', 'LINK': 'chainlink',
    'UNI': 'uniswap', 'LTC': 'litecoin', 'TRX': 'tron', 'XLM': 'stellar',
    'BCH': 'bitcoin-cash', 'ALGO': 'algorand', 'ATOM': 'cosmos',
    'VET': 'vechain', 'ICP': 'internet-computer'
}

def search_crypto_id(symbol):
    try:
        r = requests.get(f"https://api.coingecko.com/api/v3/search?query={symbol}", timeout=8)
        if r.status_code == 200:
            for coin in r.json().get('coins', []):
                if coin.get('symbol', '').upper() == symbol.upper():
                    return coin['id']
    except:
        pass
    return None


def _fetch_uncached(ticker):
    """Quick live price fetch (no cache)."""
    query = ticker.strip().upper()
    price = None
    crypto_id = CRYPTO_MAP.get(query)
    if not crypto_id:
        crypto_id = search_crypto_id(query)
        if crypto_id:
            CRYPTO_MAP[query] = crypto_id
    if crypto_id:
        try:
            url = f"https://api.coingecko.com/api/v3/simple/price?ids={crypto_id}&vs_currencies=inr"
            resp = requests.get(url, timeout=5)
            if resp.status_code == 200:
                price = resp.json().get(crypto_id, {}).get('inr')
        except:
            pass
    else:
        yticker = query + '.NS'
        try:
            stock = yf.Ticker(yticker)
            df = stock.history(period="1d", interval="1m")
            if not df.empty:
                price = df['Close'].iloc[-1]
        except:
            pass
    return price


# ---------- Full indicator data fetch ----------
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
        if getattr(df.index, "tz", None) is not None:
            df.index = df.index.tz_localize(None)

        required = ['open', 'high', 'low', 'close', 'volume']
        if not all(c in df.columns for c in required):
            return None

        # Indicators
        df['ema20'] = df['close'].ewm(span=20, adjust=False).mean()
        df['ema50'] = df['close'].ewm(span=50, adjust=False).mean()
        df['vwap_num'] = df['volume'] * (df['high'] + df['low'] + df['close']) / 3
        df['date'] = df.index.date
        df['vwap'] = df.groupby('date')['vwap_num'].cumsum() / df.groupby('date')['volume'].cumsum()

        high_low = df['high'] - df['low']
        high_close = abs(df['high'] - df['close'].shift(1))
        low_close = abs(df['low'] - df['close'].shift(1))
        tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        df['atr'] = tr.ewm(alpha=1 / 14, adjust=False).mean()

        delta = df['close'].diff()
        gain = delta.clip(lower=0)
        loss = -delta.clip(upper=0)
        avg_gain = gain.ewm(alpha=1 / 14, adjust=False).mean()
        avg_loss = loss.ewm(alpha=1 / 14, adjust=False).mean()
        rs = avg_gain / avg_loss.replace(0, 1e-10)
        df['rsi'] = 100 - (100 / (1 + rs))

        plus_dm = (df['high'].diff()).clip(lower=0)
        minus_dm = (-df['low'].diff()).clip(lower=0)
        avg_plus_dm = plus_dm.ewm(alpha=1 / 14, adjust=False).mean()
        avg_minus_dm = minus_dm.ewm(alpha=1 / 14, adjust=False).mean()
        plus_di = 100 * (avg_plus_dm / df['atr'])
        minus_di = 100 * (avg_minus_dm / df['atr'])
        dx = 100 * abs(plus_di - minus_di) / (plus_di + minus_di + 1e-10)
        df['adx'] = dx.ewm(alpha=1 / 14, adjust=False).mean()

        df['vol_sma'] = df['volume'].rolling(20).mean()
        df['vol_ratio'] = df['volume'] / df['vol_sma']

        return df.dropna()
    except:
        return None


# ---------- Pattern Detection ----------
def detect_patterns(df):
    df = df.copy()
    n = len(df)
    current_price = df['close'].iloc[-1]
    is_penny = current_price < 100
    vol_threshold = 2.0 if is_penny else 1.3

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
        recent_min = [idx for idx in min_idx if i - 20 <= idx < i]
        recent_max = [idx for idx in max_idx if i - 20 <= idx < i]

        # W-Pattern
        if len(recent_min) >= 2:
            t1_idx = recent_min[-2]
            t2_idx = recent_min[-1]
            if t2_idx - t1_idx >= 4:
                t1 = df['low'].iloc[t1_idx]
                t2 = df['low'].iloc[t2_idx]
                if abs(t1 - t2) / max(t1, t2) < 0.025:
                    mid_closes = df['close'].iloc[t1_idx:t2_idx + 1]
                    if len(mid_closes) > 1:
                        neckline = mid_closes.max()
                        if df['close'].iloc[i] > neckline:
                            df.loc[df.index[i], 'chart_pattern'] = "W-Pattern (Double Bottom) 🚀"
                            rsi_now = df['rsi'].iloc[i]
                            vol_now = df['vol_ratio'].iloc[i]
                            if 45 <= rsi_now <= 65 and vol_now > vol_threshold:
                                df.loc[df.index[i], 'pattern_signal'] = "BUY (SURE PATTERN)"
                                df.loc[df.index[i], 'pattern_marker'] = "W"

        # M-Pattern
        if len(recent_max) >= 2:
            p1_idx = recent_max[-2]
            p2_idx = recent_max[-1]
            if p2_idx - p1_idx >= 4:
                p1 = df['high'].iloc[p1_idx]
                p2 = df['high'].iloc[p2_idx]
                if abs(p1 - p2) / max(p1, p2) < 0.025:
                    mid_closes = df['close'].iloc[p1_idx:p2_idx + 1]
                    if len(mid_closes) > 1:
                        neckline = mid_closes.min()
                        if df['close'].iloc[i] < neckline:
                            df.loc[df.index[i], 'chart_pattern'] = "M-Pattern (Double Top) 📉"
                            rsi_now = df['rsi'].iloc[i]
                            if rsi_now > 65:
                                df.loc[df.index[i], 'pattern_signal'] = "SELL (OVERBOUGHT)"
                                df.loc[df.index[i], 'pattern_marker'] = "M"

    last_signals = df['pattern_signal'].iloc[-3:].values
    bullish_pat = any(s.startswith("BUY") for s in last_signals)
    bearish_pat = any(s.startswith("SELL") for s in last_signals)

    last_chart = df['chart_pattern'].iloc[-1]
    pattern_desc = []
    if "W-Pattern" in last_chart: pattern_desc.append("W‑Pattern (Double Bottom)")
    if "M-Pattern" in last_chart: pattern_desc.append("M‑Pattern (Double Top)")
    pattern_str = ", ".join(pattern_desc) if pattern_desc else "कोई स्पष्ट चार्ट पैटर्न नहीं"
    last_candle = df['candle_pattern'].iloc[-1]
    return df, bullish_pat, bearish_pat, pattern_str, last_candle


# ---------- News Sentiment (mock) ----------
def fetch_news_sentiment(ticker):
    return 0.1, ["News sentiment engine in development"]


# ---------- 10x Signal Validation ----------
def validate_signal_10x(ticker, side, last, news_score, bullish_pat, bearish_pat, progress_callback=None):
    is_penny = last['close'] < 100
    vol_threshold = 2.0 if is_penny else 1.3

    for i in range(1, 11):
        if progress_callback:
            progress_callback(i)
        price = _fetch_uncached(ticker)
        if price is None:
            return False
        close = price
        vwap = last['vwap']
        ema20 = last['ema20']
        ema50 = last['ema50']
        rsi = last['rsi']
        adx = last['adx']
        vol_ratio = last['vol_ratio']

        if side == "BUY":
            tech_ok = (close > vwap and close > ema20 and ema20 > ema50 and
                       35 < rsi < 75 and adx > 15 and vol_ratio > vol_threshold and
                       news_score >= -0.2)
            pattern_ok = bullish_pat
            if not (tech_ok or pattern_ok):
                return False
        else:  # SELL
            tech_ok = (close < vwap and close < ema20 and ema20 < ema50 and
                       30 < rsi < 65 and adx > 15 and vol_ratio > vol_threshold and
                       news_score <= 0.2)
            pattern_ok = bearish_pat
            if not (tech_ok or pattern_ok):
                return False
        time.sleep(0.3)
    return True