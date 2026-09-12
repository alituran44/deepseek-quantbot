import time
import requests
from typing import Dict, Any, List, Optional

class MarketIntelligence:
    """
    4 Harici Açık Kripto API'si Entegratörü:
    1. BtcTurk Public API: Binance TR vs BtcTurk TL Arbitraj Radarı
    2. CoinGecko Public API: Küresel Arama Trendleri & Hacim Patlamaları
    3. Mempool.space Public API: Bitcoin Ağ Sağlığı & Madenci Transfer Ücretleri
    4. DEX Aggregator API (DexScreener / Raydium / Uniswap): CEX vs DEX Fiyat Karşılaştırması
    """

    def __init__(self):
        self._cache: Dict[str, Any] = {}
        self._cache_times: Dict[str, float] = {}

    def _get_cached(self, key: str, ttl_seconds: float) -> Optional[Any]:
        if key in self._cache and (time.time() - self._cache_times.get(key, 0)) < ttl_seconds:
            return self._cache[key]
        return None

    def _set_cached(self, key: str, data: Any):
        self._cache[key] = data
        self._cache_times[key] = time.time()

    # -------------------------------------------------------------
    # Binance & Binance TR Fiyat Çekici (Doğrudan Açık Ticker)
    # -------------------------------------------------------------
    def get_binance_ticker_prices(self) -> Dict[str, float]:
        """Binance TR ve Global'den açık ticker fiyatlarını çeker (15 sn önbellekli)."""
        cached = self._get_cached("binance_tickers", 15.0)
        if cached:
            return cached

        tickers = {}
        try:
            url = "https://api.binance.me/api/v3/ticker/price"
            resp = requests.get(url, timeout=4)
            if resp.status_code == 200:
                for item in resp.json():
                    sym = item.get("symbol", "")
                    px = float(item.get("price", 0.0))
                    tickers[sym] = px
                    if sym.endswith("TRY"):
                        coin = sym[:-3]
                        tickers[f"{coin}_TRY"] = px
                        tickers[coin] = px
                    elif sym.endswith("USDT"):
                        coin = sym[:-4]
                        tickers[f"{coin}_USDT"] = px
            if tickers:
                self._set_cached("binance_tickers", tickers)
                return tickers
        except Exception:
            pass

        return self._cache.get("binance_tickers", {})

    # -------------------------------------------------------------
    # 1. BtcTurk Ticker & Arbitraj Radarı
    # -------------------------------------------------------------
    def get_btcturk_tickers(self) -> Dict[str, Any]:
        cached = self._get_cached("btcturk_tickers", 15.0)
        if cached:
            return cached

        url = "https://api.btcturk.com/api/v2/ticker"
        try:
            resp = requests.get(url, timeout=5)
            if resp.status_code == 200:
                raw_list = resp.json().get("data", [])
                lookup = {}
                for item in raw_list:
                    pair = item.get("pair", "")
                    lookup[pair] = {
                        "pair": pair,
                        "pair_normalized": item.get("pairNormalized", ""),
                        "last": float(item.get("last", 0.0)),
                        "bid": float(item.get("bid", 0.0)),
                        "ask": float(item.get("ask", 0.0)),
                        "high": float(item.get("high", 0.0)),
                        "low": float(item.get("low", 0.0)),
                        "volume": float(item.get("volume", 0.0)),
                        "daily_percent": float(item.get("dailyPercent", 0.0))
                    }
                res = {"success": True, "tickers": lookup}
                self._set_cached("btcturk_tickers", res)
                return res
        except Exception:
            pass

        return self._cache.get("btcturk_tickers", {"success": False, "tickers": {}})

    def calculate_turkey_arbitrage(self, binance_tr_prices: Optional[Dict[str, float]] = None) -> List[Dict[str, Any]]:
        """
        Binance TR ile BtcTurk arasındaki anlık TL fiyat farkını (arbitraj) hesaplar.
        """
        btcturk_data = self.get_btcturk_tickers()
        bt_tickers = btcturk_data.get("tickers", {})
        if not bt_tickers:
            return []

        # Eğer dışarıdan btr_prices verilmemişse veya eksikse açık Binance ticker'ından tamamla
        live_btr_tickers = self.get_binance_ticker_prices()
        merged_btr = dict(live_btr_tickers)
        if binance_tr_prices:
            merged_btr.update(binance_tr_prices)

        arbitrage_list = []
        watch_pairs = [
            ("BTC", "BTCTRY", "BTCTRY"),
            ("ETH", "ETHTRY", "ETHTRY"),
            ("SOL", "SOLTRY", "SOLTRY"),
            ("XRP", "XRPTRY", "XRPTRY"),
            ("NEAR", "NEATRY", "NEARTRY"),
            ("SUI", "SUITRY", "SUITRY"),
            ("AVAX", "AVAXTRY", "AVAXTRY"),
            ("DOGE", "DOGETRY", "DOGETRY"),
            ("PEPE", "PEPETRY", "PEPETRY"),
            ("USDT", "USDTTRY", "USDTTRY")
        ]

        for coin, bt_pair, btr_pair in watch_pairs:
            bt_info = bt_tickers.get(bt_pair)
            if not bt_info:
                continue

            bt_price = bt_info.get("last", 0.0)
            btr_price = (
                merged_btr.get(btr_pair)
                or merged_btr.get(f"{coin}_TRY")
                or merged_btr.get(f"{coin}TRY")
                or merged_btr.get(coin, 0.0)
            )

            if bt_price > 0 and btr_price > 0:
                spread = bt_price - btr_price
                spread_pct = (spread / btr_price) * 100.0
                abs_pct = abs(spread_pct)
                cheaper = "Binance TR" if btr_price < bt_price else "BtcTurk"
                pricier = "BtcTurk" if btr_price < bt_price else "Binance TR"
                rating = "YUKSEK" if abs_pct >= 1.0 else ("ORTA" if abs_pct >= 0.4 else "DUSUK")

                arbitrage_list.append({
                    "coin": coin,
                    "asset": coin,
                    "symbol": f"{coin}TRY",
                    "binance_price": round(btr_price, 4 if btr_price < 10 else 2),
                    "binance_tr_price": round(btr_price, 4 if btr_price < 10 else 2),
                    "btcturk_price": round(bt_price, 4 if bt_price < 10 else 2),
                    "spread_try": round(abs(spread), 4 if abs(spread) < 10 else 2),
                    "spread_pct": round(abs_pct, 2),
                    "abs_spread_pct": round(abs_pct, 2),
                    "raw_spread_pct": round(spread_pct, 2),
                    "cheaper": cheaper,
                    "cheaper_exchange": cheaper,
                    "expensive": pricier,
                    "pricier_exchange": pricier,
                    "arbitrage_rating": rating,
                    "opportunity": rating
                })

        arbitrage_list.sort(key=lambda x: x["abs_spread_pct"], reverse=True)
        return arbitrage_list

    # -------------------------------------------------------------
    # 2. CoinGecko Küresel Trend Kriptolar
    # -------------------------------------------------------------
    def get_coingecko_trending(self) -> List[Dict[str, Any]]:
        cached = self._get_cached("coingecko_trending", 90.0)
        if cached:
            return cached

        url = "https://api.coingecko.com/api/v3/search/trending"
        try:
            headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0"}
            resp = requests.get(url, headers=headers, timeout=5)
            if resp.status_code == 200:
                coins = resp.json().get("coins", [])
                trending_list = []
                for c in coins[:12]:
                    item = c.get("item", {})
                    data_obj = item.get("data", {})
                    price_usd = float(data_obj.get("price", 0.0) or 0.0)
                    price_chg = data_obj.get("price_change_percentage_24h", {})
                    chg_24h = 0.0
                    if isinstance(price_chg, dict):
                        chg_24h = float(price_chg.get("usd", 0.0) or 0.0)
                    elif isinstance(price_chg, (int, float)):
                        chg_24h = float(price_chg)

                    trending_list.append({
                        "id": item.get("id"),
                        "name": item.get("name"),
                        "symbol": item.get("symbol", "").upper(),
                        "market_cap_rank": item.get("market_cap_rank") or "-",
                        "thumb": item.get("thumb") or item.get("small"),
                        "price_usd": round(price_usd, 6 if price_usd < 1 else 2),
                        "price_btc": item.get("price_btc", 0.0),
                        "change_24h": round(chg_24h, 2),
                        "score": item.get("score", 0) + 1
                    })
                if trending_list:
                    self._set_cached("coingecko_trending", trending_list)
                    return trending_list
        except Exception:
            pass

        return self._cache.get("coingecko_trending", [])

    # -------------------------------------------------------------
    # 3. Mempool.space Bitcoin Ağ Sağlığı & Madenci Ücretleri
    # -------------------------------------------------------------
    def get_bitcoin_network_health(self) -> Dict[str, Any]:
        cached = self._get_cached("mempool_fees", 30.0)
        if cached:
            return cached

        url = "https://mempool.space/api/v1/fees/recommended"
        try:
            resp = requests.get(url, timeout=5)
            if resp.status_code == 200:
                data = resp.json()
                fast = data.get("fastestFee", 2)
                half = data.get("halfHourFee", 1)
                hour = data.get("hourFee", 1)
                min_fee = data.get("minimumFee", 1)
                eco = data.get("economyFee", min_fee)

                if fast <= 6:
                    status_text = "Çok Sakin / Minimum Komisyon"
                    status_level = "HEALTHY"
                    color = "var(--profit)"
                elif fast <= 20:
                    status_text = "Normal / Standart Yoğunluk"
                    status_level = "NORMAL"
                    color = "var(--profit)"
                elif fast <= 50:
                    status_text = "Orta Yoğunluk / Hafif Tıkanıklık"
                    status_level = "BUSY"
                    color = "var(--warning)"
                else:
                    status_text = "Aşırı Yoğun / Yüksek Madenci Ücreti"
                    status_level = "CONGESTED"
                    color = "var(--loss)"

                res = {
                    "success": True,
                    "fastestFee": fast,
                    "halfHourFee": half,
                    "hourFee": hour,
                    "economyFee": eco,
                    "minimumFee": min_fee,
                    "fastest_fee_sat_vb": fast,
                    "half_hour_fee_sat_vb": half,
                    "hour_fee_sat_vb": hour,
                    "minimum_fee_sat_vb": min_fee,
                    "congestion_status": status_level,
                    "status_level": status_level,
                    "status_text": status_text,
                    "network_status": status_text,
                    "status_color": color
                }
                self._set_cached("mempool_fees", res)
                return res
        except Exception:
            pass

        return self._cache.get("mempool_fees", {
            "success": True,
            "fastestFee": 3,
            "halfHourFee": 2,
            "hourFee": 1,
            "economyFee": 1,
            "minimumFee": 1,
            "fastest_fee_sat_vb": 3,
            "half_hour_fee_sat_vb": 2,
            "hour_fee_sat_vb": 1,
            "minimum_fee_sat_vb": 1,
            "congestion_status": "NORMAL",
            "status_level": "NORMAL",
            "status_text": "Ağ Normal (Düşük/Makul Komisyon)",
            "network_status": "Ağ Normal",
            "status_color": "var(--profit)"
        })

    # -------------------------------------------------------------
    # 4. DEX vs CEX Fiyat Kıyaslaması
    # -------------------------------------------------------------
    def get_dex_comparison(self, cex_prices_usd: Optional[Dict[str, float]] = None) -> List[Dict[str, Any]]:
        cached = self._get_cached("dex_comparison", 30.0)
        if cached:
            return cached

        binance_prices = self.get_binance_ticker_prices()
        merged_cex = dict(binance_prices)
        if cex_prices_usd:
            merged_cex.update(cex_prices_usd)

        targets = [
            {"symbol": "SOL", "name": "Solana", "contract": "So11111111111111111111111111111111111111112", "chain": "Solana"},
            {"symbol": "ETH", "name": "Ethereum", "contract": "0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2", "chain": "Ethereum"},
            {"symbol": "PEPE", "name": "Pepe", "contract": "0x6982508145454ce325ddbe47a25d4ec3d2311933", "chain": "Ethereum"},
            {"symbol": "SUI", "name": "Sui Network", "contract": "0x2::sui::SUI", "chain": "Sui"}
        ]

        results = []
        for t in targets:
            sym = t["symbol"]
            cex_px = (
                merged_cex.get(f"{sym}USDT")
                or merged_cex.get(f"{sym}_USDT")
                or merged_cex.get(sym, 0.0)
            )
            try:
                url = f"https://api.dexscreener.com/latest/dex/tokens/{t['contract']}"
                r = requests.get(url, timeout=3)
                if r.status_code == 200:
                    pairs = r.json().get("pairs", [])
                    if pairs:
                        top = pairs[0]
                        dex_px = float(top.get("priceUsd", 0.0) or 0.0)
                        dex_name = (top.get("dexId") or "DEX").capitalize()
                        
                        if dex_px > 0 and cex_px > 0:
                            diff = dex_px - cex_px
                            diff_pct = (diff / cex_px) * 100.0
                            abs_diff = abs(diff_pct)
                            
                            opp = "DENGELI"
                            if diff_pct <= -0.6:
                                opp = "DEX_UCUZ"
                            elif diff_pct >= 0.6:
                                opp = "CEX_UCUZ"

                            results.append({
                                "symbol": sym,
                                "asset": sym,
                                "chain": t["chain"],
                                "dex_name": dex_name,
                                "cex_price": round(cex_px, 6 if cex_px < 1 else 2),
                                "cex_price_usd": round(cex_px, 6 if cex_px < 1 else 2),
                                "dex_price": round(dex_px, 6 if dex_px < 1 else 2),
                                "dex_price_usd": round(dex_px, 6 if dex_px < 1 else 2),
                                "diff_pct": round(abs_diff, 2),
                                "raw_diff_pct": round(diff_pct, 2),
                                "opportunity": opp,
                                "premium_platform": "DEX Daha Pahalı" if diff > 0 else "CEX Daha Pahalı"
                            })
            except Exception:
                pass

        if results:
            self._set_cached("dex_comparison", results)
            return results

        return self._cache.get("dex_comparison", [])

    # -------------------------------------------------------------
    # Konsolide Özet Raporu
    # -------------------------------------------------------------
    def get_full_intelligence_summary(
        self,
        binance_tr_prices: Optional[Dict[str, float]] = None,
        cex_prices_usd: Optional[Dict[str, float]] = None
    ) -> Dict[str, Any]:
        arbitrage = self.calculate_turkey_arbitrage(binance_tr_prices)
        trending = self.get_coingecko_trending()
        mempool = self.get_bitcoin_network_health()
        dex = self.get_dex_comparison(cex_prices_usd)

        return {
            "status": "SUCCESS",
            "timestamp": int(time.time()),
            "data": {
                "arbitrage": arbitrage,
                "trending": trending,
                "mempool": mempool,
                "dex": dex
            },
            "arbitrage_radar": arbitrage,
            "trending_coins": trending,
            "network_health": mempool,
            "dex_comparison": dex
        }

market_intelligence = MarketIntelligence()
