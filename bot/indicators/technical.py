import pandas as pd
import numpy as np
from typing import Dict, Any, Optional

class TechnicalAnalyzer:
    """
    Pandas ve NumPy tabanlı, harici C kütüphanesi gerektirmeyen,
    hızlı ve hassas teknik gösterge hesaplayıcı.
    """
    
    @staticmethod
    def calculate_indicators(df: pd.DataFrame) -> Dict[str, Any]:
        """
        OHLCV (Open, High, Low, Close, Volume) DataFrame alıp
        tüm majör teknik indikatörleri hesaplar ve özetler.
        """
        if df.empty or len(df) < 20:
            return {
                "error": "Yetersiz veri (En az 20 mum gereklidir)",
                "summary": "NEUTRAL"
            }
        
        df = df.copy()
        close = df['close']
        high = df['high']
        low = df['low']
        volume = df['volume']
        
        # 1. Hareketli Ortalamalar (EMA 20, EMA 50, EMA 200)
        df['ema_20'] = close.ewm(span=20, adjust=False).mean()
        df['ema_50'] = close.ewm(span=50, adjust=False).mean() if len(df) >= 50 else close.ewm(span=len(df), adjust=False).mean()
        df['ema_200'] = close.ewm(span=200, adjust=False).mean() if len(df) >= 200 else close.ewm(span=len(df), adjust=False).mean()
        
        # 2. RSI (14)
        delta = close.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / (loss + 1e-9)
        df['rsi'] = 100 - (100 / (1 + rs))
        
        # 3. MACD (12, 26, 9)
        ema_12 = close.ewm(span=12, adjust=False).mean()
        ema_26 = close.ewm(span=26, adjust=False).mean()
        df['macd'] = ema_12 - ema_26
        df['macd_signal'] = df['macd'].ewm(span=9, adjust=False).mean()
        df['macd_hist'] = df['macd'] - df['macd_signal']
        
        # 4. Bollinger Bantları (20, 2)
        df['bb_mid'] = close.rolling(window=20).mean()
        df['bb_std'] = close.rolling(window=20).std()
        df['bb_upper'] = df['bb_mid'] + (df['bb_std'] * 2)
        df['bb_lower'] = df['bb_mid'] - (df['bb_std'] * 2)
        
        # 5. ATR (Average True Range - 14)
        tr1 = high - low
        tr2 = (high - close.shift()).abs()
        tr3 = (low - close.shift()).abs()
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        df['atr'] = tr.rolling(window=14).mean()
        
        # 6. Hacim Ortalaması (20)
        df['vol_sma_20'] = volume.rolling(window=20).mean()
        last_vol_sma = df['vol_sma_20'].iloc[-1]
        vol_surge = bool((volume.iloc[-1] / (last_vol_sma + 1e-9)) > 1.5) if not pd.isna(last_vol_sma) else False
        
        # Son değerler
        last = df.iloc[-1]
        prev = df.iloc[-2] if len(df) > 1 else last
        
        current_price = float(last['close'])
        rsi_val = round(float(last['rsi']), 2) if not pd.isna(last['rsi']) else 50.0
        macd_val = round(float(last['macd']), 4) if not pd.isna(last['macd']) else 0.0
        macd_sig = round(float(last['macd_signal']), 4) if not pd.isna(last['macd_signal']) else 0.0
        macd_hist = round(float(last['macd_hist']), 4) if not pd.isna(last['macd_hist']) else 0.0
        
        ema_20 = round(float(last['ema_20']), 2) if not pd.isna(last['ema_20']) else current_price
        ema_50 = round(float(last['ema_50']), 2) if not pd.isna(last['ema_50']) else current_price
        ema_200 = round(float(last['ema_200']), 2) if not pd.isna(last['ema_200']) else current_price
        
        bb_upper = round(float(last['bb_upper']), 2) if not pd.isna(last['bb_upper']) else current_price
        bb_lower = round(float(last['bb_lower']), 2) if not pd.isna(last['bb_lower']) else current_price
        bb_mid = round(float(last['bb_mid']), 2) if not pd.isna(last['bb_mid']) else current_price
        
        atr_val = round(float(last['atr']), 2) if not pd.isna(last['atr']) else (current_price * 0.02)
        
        # Trend ve Sinyal Sentezi
        bullish_score = 0
        bearish_score = 0
        
        # RSI koşulları
        if rsi_val < 30:
            bullish_score += 2  # Aşırı satım (Reversal potansiyeli)
        elif rsi_val > 70:
            bearish_score += 2  # Aşırı alım
        elif rsi_val > 50:
            bullish_score += 1
        else:
            bearish_score += 1
            
        # MACD koşulları
        if macd_val > macd_sig:
            bullish_score += 2
            if macd_hist > prev['macd_hist']:
                bullish_score += 1  # Momentum artıyor
        else:
            bearish_score += 2
            if macd_hist < prev['macd_hist']:
                bearish_score += 1
                
        # EMA trend koşulları
        if current_price > ema_20 > ema_50:
            bullish_score += 2
        elif current_price < ema_20 < ema_50:
            bearish_score += 2
            
        # Bollinger bant pozisyonu
        if current_price <= bb_lower:
            bullish_score += 1  # Dip bant tepkisi
        elif current_price >= bb_upper:
            bearish_score += 1  # Tepe bant direnci
            
        # Genel özet karar
        if bullish_score >= bearish_score + 3:
            trend_summary = "STRONG_BULLISH"
        elif bullish_score > bearish_score:
            trend_summary = "BULLISH"
        elif bearish_score >= bullish_score + 3:
            trend_summary = "STRONG_BEARISH"
        elif bearish_score > bullish_score:
            trend_summary = "BEARISH"
        else:
            trend_summary = "NEUTRAL"
            
        # Dinamik Destek ve Dirençler (Pivotlar)
        window = min(len(df), 30)
        recent_highs = df['high'].tail(window)
        recent_lows = df['low'].tail(window)
        
        resistance = round(float(recent_highs.max()), 2)
        support = round(float(recent_lows.min()), 2)
        
        return {
            "current_price": current_price,
            "rsi": rsi_val,
            "rsi_status": "OVERSOLD (<30)" if rsi_val <= 30 else ("OVERBOUGHT (>70)" if rsi_val >= 70 else "NORMAL"),
            "macd": {
                "macd": macd_val,
                "signal": macd_sig,
                "histogram": macd_hist,
                "cross": "BULLISH_CROSS" if macd_val > macd_sig else "BEARISH_CROSS"
            },
            "moving_averages": {
                "ema_20": ema_20,
                "ema_50": ema_50,
                "ema_200": ema_200,
                "price_vs_ema20": "ABOVE" if current_price >= ema_20 else "BELOW",
                "price_vs_ema50": "ABOVE" if current_price >= ema_50 else "BELOW",
                "price_vs_ema200": "ABOVE" if current_price >= ema_200 else "BELOW"
            },
            "bollinger_bands": {
                "upper": bb_upper,
                "middle": bb_mid,
                "lower": bb_lower,
                "position": "NEAR_LOWER" if current_price <= bb_lower * 1.01 else ("NEAR_UPPER" if current_price >= bb_upper * 0.99 else "MIDDLE")
            },
            "volatility": {
                "atr": atr_val,
                "atr_percent": round((atr_val / current_price) * 100, 2),
                "volume_surge": bool(vol_surge)
            },
            "key_levels": {
                "support": support,
                "resistance": resistance
            },
            "scores": {
                "bullish_score": int(bullish_score),
                "bearish_score": int(bearish_score)
            },
            "summary": trend_summary
        }
