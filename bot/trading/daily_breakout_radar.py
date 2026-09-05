import json
import time
import os
from pathlib import Path
from typing import Dict, Any, List, Optional
from bot.data.crypto_feed import CryptoFeed

DATA_DIR = Path("/tmp/data_storage") if os.getenv("VERCEL") else (Path(__file__).resolve().parent.parent.parent / "data_storage")
WATCHLIST_FILE = DATA_DIR / "radar_watchlist.json"

class DailyBreakoutRadar:
    """
    Kayıtlı tüm borsaları (Binance, MEXC, OKX) tarayarak
    günlük yükselme eğilimi gösterecek coinleri tespit eden,
    takip eden ve kâr/zarar performansını raporlayan motor.
    """
    def __init__(self):
        self.crypto_feed = CryptoFeed()
        self.opportunities: List[Dict[str, Any]] = []
        self.watchlist: Dict[str, Dict[str, Any]] = {}
        self.last_scan_time: float = 0.0
        self.market_report: Dict[str, Any] = {
            "summary": "Piyasa taranıyor...",
            "dominant_exchange": "Binance / MEXC / OKX",
            "avg_potential": "+14.5%",
            "top_pick": None
        }
        self._ensure_storage()
        self.load_watchlist()

    def _ensure_storage(self):
        try:
            DATA_DIR.mkdir(parents=True, exist_ok=True)
            if not WATCHLIST_FILE.exists():
                with open(WATCHLIST_FILE, "w", encoding="utf-8") as f:
                    json.dump({}, f)
        except Exception as e:
            print(f"[DailyBreakoutRadar] Storage dizini oluşturulamadı: {e}")

    def load_watchlist(self):
        """Kayıtlı takip listesini diskten yükler."""
        if WATCHLIST_FILE.exists():
            try:
                with open(WATCHLIST_FILE, "r", encoding="utf-8") as f:
                    self.watchlist = json.load(f)
            except Exception as e:
                print(f"[DailyBreakoutRadar] Takip listesi okunamadı: {e}")
                self.watchlist = {}

    def save_watchlist(self):
        """Takip listesini diske kalıcı kaydeder."""
        try:
            DATA_DIR.mkdir(parents=True, exist_ok=True)
            with open(WATCHLIST_FILE, "w", encoding="utf-8") as f:
                json.dump(self.watchlist, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"[DailyBreakoutRadar] Takip listesi kaydedilemedi: {e}")

    def toggle_track(self, symbol: str, coin_data: Optional[Dict[str, Any]] = None) -> bool:
        """Bir coini takip listesine ekler veya listeden çıkarır."""
        sym = symbol.upper().strip()
        if sym in self.watchlist:
            del self.watchlist[sym]
            self.save_watchlist()
            return False  # Artık takipte değil
        else:
            # Yeni takip kaydı oluştur
            source = coin_data or {}
            price = source.get("price", 0.0)
            if price <= 0:
                # Fiyatı fırsat listesinden bul
                match = next((op for op in self.opportunities if op["symbol"] == sym), None)
                if match:
                    source = match
                    price = match["price"]

            self.watchlist[sym] = {
                "symbol": sym,
                "asset": sym.replace("USDT", ""),
                "exchanges": source.get("exchanges", ["Binance"]),
                "tracked_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                "initial_price": price,
                "current_price": price,
                "pnl_pct": 0.0,
                "target_price": source.get("target_price", round(price * 1.12, 4)),
                "stop_price": source.get("stop_price", round(price * 0.95, 4)),
                "target_gain_pct": source.get("target_gain_pct", 12.0),
                "breakout_score": source.get("breakout_score", 85),
                "status": "TAKİPTE",
                "thesis": source.get("thesis", "Günlük yükseliş kırılımı ve hacim ivmesi takip ediliyor.")
            }
            self.save_watchlist()
            return True  # Takibe alındı

    def scan_all_exchanges(self) -> Dict[str, Any]:
        """
        Binance, MEXC ve OKX borsalarındaki tüm aktif çiftleri tarar.
        Günlük yükseliş eğilimi gösteren en yüksek potansiyelli coinleri skorlar.
        """
        now = time.time()
        # 1. Tickerları topla
        binance_tickers = self.crypto_feed.get_all_binance_market_tickers() or []
        mexc_tickers = self.crypto_feed.get_all_mexc_market_tickers() or []
        okx_tickers = self.crypto_feed.get_all_okx_market_tickers() or []

        # 2. Sembol bazında borsaları ve en yüksek hacimli veriyi eşleştir
        coins_map: Dict[str, Dict[str, Any]] = {}

        def process_ticker(t: Dict[str, Any], exchange_name: str):
            sym = t.get("symbol", "").upper().strip()
            if not sym or not sym.endswith("USDT"):
                return
            
            # Stabil coin filtreleri
            if any(sc in sym for sc in ["USDC", "FDUSD", "TUSD", "EUR", "USD1", "RLUSD", "DAI", "BUSD"]):
                return

            px = float(t.get("price", 0.0))
            vol = float(t.get("volume_usd", 0.0))
            chg = float(t.get("change_24h", 0.0))
            h24 = float(t.get("high_24h", px))
            l24 = float(t.get("low_24h", px))

            if px <= 0 or vol < 1000:
                return

            if sym not in coins_map:
                coins_map[sym] = {
                    "symbol": sym,
                    "asset": t.get("asset", sym.replace("USDT", "")),
                    "price": px,
                    "change_24h": chg,
                    "volume_usd": vol,
                    "high_24h": h24,
                    "low_24h": l24,
                    "exchanges": [exchange_name],
                    "exchange_details": {exchange_name: {"price": px, "volume": vol}}
                }
            else:
                entry = coins_map[sym]
                if exchange_name not in entry["exchanges"]:
                    entry["exchanges"].append(exchange_name)
                entry["volume_usd"] += vol  # Konsolide hacim
                entry["exchange_details"][exchange_name] = {"price": px, "volume": vol}
                # Fiyat olarak likiditesi en yüksek olanı koru
                if vol > entry.get("_top_vol", 0.0):
                    entry["price"] = px
                    entry["change_24h"] = chg
                    entry["high_24h"] = max(entry["high_24h"], h24)
                    entry["low_24h"] = min(entry["low_24h"], l24) if l24 > 0 else entry["low_24h"]
                    entry["_top_vol"] = vol

        for t in binance_tickers:
            process_ticker(t, "Binance")
        for t in mexc_tickers:
            process_ticker(t, "MEXC")
        for t in okx_tickers:
            process_ticker(t, "OKX")

        candidates = []
        for sym, c in coins_map.items():
            vol = c["volume_usd"]
            chg = c["change_24h"]
            px = c["price"]
            h24 = c["high_24h"]
            l24 = c["low_24h"]

            # Likidite filtresi: En az 750,000 USD 24s işlem hacmi
            if vol < 750000.0:
                continue

            # Günlük yükselme ivmesi kriterleri:
            # 1. 24 saatlik değişim pozitif (+%2.0 ile +%25.0 arası) -> Ralli aşırı şişmemiş, taze
            # 2. Günün zirvesine yakınlık (Range Position): Alıcıların günlük mumu yukarıda tuttuğunu gösterir
            # 3. Birden fazla borsada listelenme avantajı
            if 2.0 <= chg <= 25.0 and h24 > l24:
                range_pct = (px - l24) / (h24 - l24 + 1e-9)
                if range_pct >= 0.60:  # Mumun üst %40'lık diliminde seyrediyor
                    # Skorlama Motoru (0 - 100)
                    score = 65.0
                    # Zirveye yakınlık katkısı (maks +15 puan)
                    score += range_pct * 15.0
                    
                    # Hacim derinliği katkısı (maks +10 puan)
                    if vol > 10000000.0:
                        score += 10.0
                    elif vol > 3000000.0:
                        score += 6.0
                    elif vol > 1000000.0:
                        score += 3.0

                    # Çoklu borsa listelenme gücü (Binance + MEXC/OKX) (maks +10 puan)
                    if len(c["exchanges"]) >= 3:
                        score += 10.0
                    elif len(c["exchanges"]) == 2:
                        score += 6.0

                    # Değişim tatlılığı (+%4 ile +%12 arası en ideal kırılım bölgesi)
                    if 4.0 <= chg <= 14.0:
                        score += 8.0
                    elif 14.0 < chg <= 20.0:
                        score += 4.0

                    score = min(round(score, 1), 97.0)

                    # Hedef ve stop seviyeleri
                    target_pct = round(max(8.0, min(24.0, (100 - score) * 0.4 + chg * 0.5)), 1)
                    target_px = round(px * (1 + target_pct / 100.0), 6 if px < 1 else 4)
                    stop_px = round(max(l24, px * 0.94), 6 if px < 1 else 4)

                    # Türkçe Gerekçe ve Yapay Zeka Tezi
                    reasons = []
                    if range_pct >= 0.85:
                        reasons.append("24s zirve kırılımı testinde")
                    elif range_pct >= 0.70:
                        reasons.append("Günlük tepe bölgesinde konsolide oluyor")

                    if vol > 5000000.0:
                        reasons.append(f"${round(vol/1e6, 1)}M güçlü kurumsal hacim")
                    else:
                        reasons.append("Artan alıcı iştahı")

                    if len(c["exchanges"]) > 1:
                        reasons.append(f"{'/'.join(c['exchanges'])} arbitraj/likidite desteği")

                    thesis = " • ".join(reasons)

                    candidates.append({
                        "symbol": sym,
                        "asset": c["asset"],
                        "price": px,
                        "change_24h": chg,
                        "volume_usd": vol,
                        "range_pct": round(range_pct * 100, 1),
                        "exchanges": c["exchanges"],
                        "breakout_score": score,
                        "target_gain_pct": target_pct,
                        "target_price": target_px,
                        "stop_price": stop_px,
                        "thesis": thesis,
                        "is_tracked": sym in self.watchlist
                    })

        # Skoruna göre sırala
        candidates.sort(key=lambda x: x["breakout_score"], reverse=True)
        self.opportunities = candidates[:25]  # En iyi 25 yükseliş adayı
        self.last_scan_time = now

        # Takip listesindeki coinlerin anlık fiyat ve PnL'lerini güncelle
        self._sync_watchlist_prices(coins_map)

        # Günlük Pazar Raporu Özeti Derle
        top_pick = self.opportunities[0] if self.opportunities else None
        avg_target = round(sum(o["target_gain_pct"] for o in self.opportunities[:8]) / max(1, len(self.opportunities[:8])), 1) if self.opportunities else 12.5

        self.market_report = {
            "summary": f"Binance, MEXC ve OKX'te toplam {len(coins_map)} parite tarandı. {len(self.opportunities)} yüksek potansiyelli yükseliş fırsatı radara alındı.",
            "dominant_exchange": "Binance + MEXC + OKX Konsolide",
            "avg_potential": f"+%{avg_target}",
            "top_pick": top_pick["symbol"] if top_pick else "BTCUSDT",
            "top_pick_score": top_pick["breakout_score"] if top_pick else 90.0,
            "top_pick_thesis": top_pick["thesis"] if top_pick else "Piyasa lideri akümülasyon bölgesinde.",
            "total_scanned_pairs": len(coins_map),
            "opportunity_count": len(self.opportunities)
        }

        return {
            "status": "SUCCESS",
            "opportunities": self.opportunities,
            "watchlist": list(self.watchlist.values()),
            "market_report": self.market_report,
            "last_scan_time": time.strftime("%H:%M:%S", time.localtime(now))
        }

    def _sync_watchlist_prices(self, coins_map: Dict[str, Dict[str, Any]]):
        """Takip listesindeki coinlerin fiyatını ve kâr/zararını günceller."""
        has_changes = False
        for sym, item in list(self.watchlist.items()):
            if sym in coins_map:
                curr_px = coins_map[sym]["price"]
                init_px = item.get("initial_price", curr_px)
                if init_px > 0:
                    pnl = round(((curr_px - init_px) / init_px) * 100.0, 2)
                else:
                    pnl = 0.0
                item["current_price"] = curr_px
                item["pnl_pct"] = pnl
                # Durum güncellemesi
                if curr_px >= item.get("target_price", curr_px * 2):
                    item["status"] = "HEDEF GÖRÜLDÜ ✅"
                elif curr_px <= item.get("stop_price", 0):
                    item["status"] = "STOP SEVİYESİNDE ⚠️"
                elif pnl > 0:
                    item["status"] = f"YÜKSELİŞTE (+%{pnl})"
                else:
                    item["status"] = "TAKİPTE"
                has_changes = True
        if has_changes:
            self.save_watchlist()

    def get_summary(self) -> Dict[str, Any]:
        """Web paneli ve periyodik state için hafif özet döner."""
        if not self.opportunities:
            self.scan_all_exchanges()

        return {
            "opportunity_count": len(self.opportunities),
            "tracked_count": len(self.watchlist),
            "top_opportunities": self.opportunities[:10],
            "watchlist": list(self.watchlist.values()),
            "market_report": self.market_report,
            "last_scan_time": time.strftime("%H:%M:%S", time.localtime(self.last_scan_time)) if self.last_scan_time else "Bekleniyor"
        }
