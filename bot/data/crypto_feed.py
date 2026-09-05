import requests
import pandas as pd
from typing import Dict, Any, Optional

class CryptoFeed:
    """
    Binance Public REST API üzerinden Kripto verisi çeker.
    API anahtarı gerektirmez.
    """
    BASE_URL = "https://api.binance.com/api/v3"
    _cache = {}
    _cache_time = {}

    @classmethod
    def get_all_binance_market_tickers(cls) -> list:
        """
        Binance'de listelenen TÜM altcoinleri (650+ aktif USDT çifti) anlık fiyatları,
        24 saatlik değişimleri ve işlem hacimleri ile birlikte tek seferde getirir.
        30 saniyelik akıllı önbellek ile rate-limit koruması sağlar.
        """
        import time
        now = time.time()
        if "BINANCE" in cls._cache and (now - cls._cache_time.get("BINANCE", 0) < 30.0):
            return cls._cache["BINANCE"]

        url = f"{cls.BASE_URL}/ticker/24hr"
        try:
            resp = requests.get(url, timeout=12)
            resp.raise_for_status()
            tickers = resp.json()
            blacklist = ["USDCUSDT", "FDUSDUSDT", "TUSDUSDT", "EURUSDT", "USD1USDT", "RLUSDUSDT", "UUSDT"]
            valid = []
            for t in tickers:
                sym = t.get("symbol", "")
                px = float(t.get("lastPrice", 0.0))
                vol = float(t.get("quoteVolume", 0.0))
                if (
                    sym.endswith("USDT")
                    and sym not in blacklist
                    and px > 0.0
                    and vol > 1000.0  # Aktif ve likit çiftler
                    and not any(x in sym for x in ["UPUSDT", "DOWNUSDT", "BULLUSDT", "BEARUSDT"])
                ):
                    valid.append({
                        "exchange": "Binance",
                        "symbol": sym,
                        "asset": sym.replace("USDT", ""),
                        "price": px,
                        "change_24h": round(float(t.get("priceChangePercent", 0.0)), 2),
                        "volume_usd": round(vol, 2),
                        "high_24h": float(t.get("highPrice", 0.0)),
                        "low_24h": float(t.get("lowPrice", 0.0))
                    })
            valid.sort(key=lambda x: x["volume_usd"], reverse=True)
            cls._cache["BINANCE"] = valid
            cls._cache_time["BINANCE"] = now
            return valid
        except Exception as e:
            print(f"[CryptoFeed] Binance tickerları alınamadı: {e}")
            return cls._cache.get("BINANCE", [])

    @classmethod
    def get_all_okx_market_tickers(cls) -> list:
        """
        OKX Spot piyasasında listelenen tüm aktif USDT altcoinlerini getirir.
        """
        import time
        now = time.time()
        if "OKX" in cls._cache and (now - cls._cache_time.get("OKX", 0) < 30.0):
            return cls._cache["OKX"]

        url = "https://www.okx.com/api/v5/market/tickers?instType=SPOT"
        try:
            resp = requests.get(url, timeout=12)
            resp.raise_for_status()
            data = resp.json().get("data", [])
            valid = []
            for item in data:
                inst_id = item.get("instId", "")
                if not inst_id.endswith("-USDT"):
                    continue
                asset = inst_id.split("-")[0]
                sym = f"{asset}USDT"
                px = float(item.get("last", 0.0))
                open_24h = float(item.get("open24h", 0.0))
                vol = float(item.get("volCcy24h", 0.0))
                if px <= 0:
                    continue
                change_pct = round(((px - open_24h) / open_24h) * 100, 2) if open_24h > 0 else 0.0
                valid.append({
                    "exchange": "OKX",
                    "symbol": sym,
                    "asset": asset,
                    "price": px,
                    "change_24h": change_pct,
                    "volume_usd": round(vol, 2),
                    "high_24h": float(item.get("high24h", 0.0)),
                    "low_24h": float(item.get("low24h", 0.0))
                })
            valid.sort(key=lambda x: x["volume_usd"], reverse=True)
            cls._cache["OKX"] = valid
            cls._cache_time["OKX"] = now
            return valid
        except Exception as e:
            print(f"[CryptoFeed] OKX tickerları alınamadı: {e}")
            return cls._cache.get("OKX", [])

    @classmethod
    def get_all_mexc_market_tickers(cls) -> list:
        """
        MEXC Spot piyasasında listelenen 1600+ aktif USDT altcoinini getirir.
        """
        import time
        now = time.time()
        if "MEXC" in cls._cache and (now - cls._cache_time.get("MEXC", 0) < 30.0):
            return cls._cache["MEXC"]

        url = "https://api.mexc.com/api/v3/ticker/24hr"
        try:
            resp = requests.get(url, timeout=12)
            resp.raise_for_status()
            tickers = resp.json()
            blacklist = ["USDCUSDT", "FDUSDUSDT", "TUSDUSDT", "EURUSDT", "USD1USDT", "RLUSDUSDT", "UUSDT"]
            valid = []
            for t in tickers:
                sym = t.get("symbol", "")
                px = float(t.get("lastPrice", 0.0))
                vol = float(t.get("quoteVolume", 0.0))
                if (
                    sym.endswith("USDT")
                    and sym not in blacklist
                    and px > 0.0
                    and vol > 100.0
                    and not any(x in sym for x in ["3L", "3S", "4L", "4S", "5L", "5S"])
                ):
                    pct_raw = float(t.get("priceChangePercent", 0.0))
                    change_pct = round(pct_raw * 100.0, 2)
                    valid.append({
                        "exchange": "MEXC",
                        "symbol": sym,
                        "asset": sym.replace("USDT", ""),
                        "price": px,
                        "change_24h": change_pct,
                        "volume_usd": round(vol, 2),
                        "high_24h": float(t.get("highPrice", 0.0)),
                        "low_24h": float(t.get("lowPrice", 0.0))
                    })
            valid.sort(key=lambda x: x["volume_usd"], reverse=True)
            cls._cache["MEXC"] = valid
            cls._cache_time["MEXC"] = now
            return valid
        except Exception as e:
            print(f"[CryptoFeed] MEXC tickerları alınamadı: {e}")
            return cls._cache.get("MEXC", [])

    @classmethod
    def get_market_tickers(cls, exchange: str = "BINANCE") -> list:
        """Belirtilen borsanın tüm USDT spot paritelerini getirir."""
        ex = (exchange or "BINANCE").upper()
        if ex == "OKX":
            return cls.get_all_okx_market_tickers()
        elif ex == "MEXC":
            return cls.get_all_mexc_market_tickers()
        return cls.get_all_binance_market_tickers()

    @classmethod
    def get_ticker_24h(cls, symbol: str = "BTCUSDT") -> Dict[str, Any]:
        """24 saatlik fiyat değişimi, en yüksek, en düşük ve hacim verisi."""
        url = f"{cls.BASE_URL}/ticker/24hr?symbol={symbol}"
        try:
            resp = requests.get(url, timeout=10)
            resp.raise_for_status()
            data = resp.json()
            return {
                "symbol": symbol,
                "price": float(data.get("lastPrice", 0)),
                "change_24h": float(data.get("priceChangePercent", 0)),
                "high_24h": float(data.get("highPrice", 0)),
                "low_24h": float(data.get("lowPrice", 0)),
                "volume_24h": float(data.get("volume", 0)),
                "quote_volume_24h": float(data.get("quoteVolume", 0)),
            }
        except Exception as e:
            return {"symbol": symbol, "error": str(e), "price": 0.0, "change_24h": 0.0}

    @classmethod
    def get_klines(cls, symbol: str = "BTCUSDT", interval: str = "1h", limit: int = 100) -> pd.DataFrame:
        """
        Mum verilerini (Open, High, Low, Close, Volume) çeker.
        interval: 15m, 1h, 4h, 1d vb.
        """
        url = f"{cls.BASE_URL}/klines?symbol={symbol}&interval={interval}&limit={limit}"
        try:
            resp = requests.get(url, timeout=10)
            resp.raise_for_status()
            raw = resp.json()
            
            # Binance Klines Format:
            # [ [Open time, Open, High, Low, Close, Volume, Close time, ...], ... ]
            df = pd.DataFrame(raw, columns=[
                "open_time", "open", "high", "low", "close", "volume",
                "close_time", "quote_volume", "trades", "taker_buy_base", "taker_buy_quote", "ignore"
            ])
            
            df["timestamp"] = pd.to_datetime(df["open_time"], unit="ms")
            for col in ["open", "high", "low", "close", "volume"]:
                df[col] = df[col].astype(float)
                
            return df[["timestamp", "open", "high", "low", "close", "volume"]]
        except Exception as e:
            print(f"[CryptoFeed] Hata ({symbol}): {e}")
            return pd.DataFrame()

    @classmethod
    def get_top_volume_symbols(cls, limit: int = 15) -> list:
        """Piyasadaki en yüksek 24s hacimli USDT çiftlerini dinamik olarak getirir."""
        url = f"{cls.BASE_URL}/ticker/24hr"
        try:
            resp = requests.get(url, timeout=10)
            resp.raise_for_status()
            tickers = resp.json()
            # Stabil coinler ve kaldıraçlı tokenları ele
            blacklist = ["USDCUSDT", "FDUSDUSDT", "TUSDUSDT", "EURUSDT", "USD1USDT", "RLUSDUSDT", "UUSDT"]
            valid = [
                t for t in tickers 
                if t['symbol'].endswith('USDT') 
                and t['symbol'] not in blacklist
                and not any(x in t['symbol'] for x in ['UPUSDT', 'DOWNUSDT', 'BULLUSDT', 'BEARUSDT'])
            ]
            valid.sort(key=lambda x: float(x.get('quoteVolume', 0)), reverse=True)
            return [t['symbol'] for t in valid[:limit]]
        except Exception as e:
            print(f"[CryptoFeed] Hacim liderleri çekilemedi: {e}")
            return ["BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "BNBUSDT", "DOGEUSDT"]
