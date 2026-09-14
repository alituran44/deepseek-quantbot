import time
import json
import urllib.request
from typing import Dict, Any, Optional

class MacroMarketFeed:
    """
    Küresel Geleneksel Finans (TradFi) ve Makroekonomik Veri Besleyicisi.
    Yahoo Finance ve Frankfurter (Avrupa Merkez Bankası) üzerinden
    DXY (Dolar Endeksi), Nasdaq, Altın ve USD/TRY kurlarını çekerek
    Bitcoin için 'Makro Piyasa İklimi' ve dinamik kâr çarpanı üretir.
    """

    _cache: Dict[str, Any] = {}
    _cache_time: float = 0.0
    CACHE_DURATION: float = 45.0  # 45 saniyelik önbellek

    @classmethod
    def get_macro_climate(cls, force_refresh: bool = False) -> Dict[str, Any]:
        now = time.time()
        if not force_refresh and cls._cache and (now - cls._cache_time < cls.CACHE_DURATION):
            return cls._cache

        # 1. Frankfurter API (ECB Kurları)
        usd_try = 48.62
        eur_usd = 1.085
        try:
            req = urllib.request.Request(
                "https://api.frankfurter.app/latest?from=USD&to=TRY,EUR",
                headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0"}
            )
            with urllib.request.urlopen(req, timeout=5) as res:
                f_data = json.loads(res.read().decode("utf-8"))
                rates = f_data.get("rates", {})
                usd_try = float(rates.get("TRY", usd_try))
                eur_rate = float(rates.get("EUR", 0.92))
                if eur_rate > 0:
                    eur_usd = round(1.0 / eur_rate, 4)
        except Exception as e:
            print(f"[MacroMarketFeed] Frankfurter kur çekme uyarısı: {e}")

        # 2. Yahoo Finance (DXY, Nasdaq, Altın)
        tickers = {
            "DXY": "DX-Y.NYB",
            "NASDAQ": "^IXIC",
            "GOLD": "GC=F"
        }
        market_data: Dict[str, Dict[str, Any]] = {}

        for key, sym in tickers.items():
            try:
                url = f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}?interval=1d&range=5d"
                req = urllib.request.Request(
                    url,
                    headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
                )
                with urllib.request.urlopen(req, timeout=5) as res:
                    d = json.loads(res.read().decode("utf-8"))
                    meta = d["chart"]["result"][0]["meta"]
                    px = float(meta.get("regularMarketPrice", 0.0))
                    prev = float(meta.get("chartPreviousClose") or meta.get("previousClose") or px)
                    chg = round(((px - prev) / (prev + 1e-9)) * 100.0, 2) if prev > 0 else 0.0
                    market_data[key] = {
                        "price": px,
                        "change_24h": chg,
                        "symbol": sym
                    }
            except Exception as e:
                print(f"[MacroMarketFeed] Yahoo Finance {key} çekme uyarısı: {e}")
                # Varsayılan değerler
                defaults = {
                    "DXY": {"price": 99.40, "change_24h": -0.20, "symbol": "DX-Y.NYB"},
                    "NASDAQ": {"price": 26280.0, "change_24h": 0.80, "symbol": "^IXIC"},
                    "GOLD": {"price": 4350.0, "change_24h": 0.10, "symbol": "GC=F"}
                }
                market_data[key] = defaults.get(key, {"price": 0.0, "change_24h": 0.0, "symbol": sym})

        # 3. Makro İklim Skoru (0 - 100) Hesaplama
        # Bitcoin için kurallar:
        # - DXY düşüyorsa (ters korelasyon) -> ÇOK İYİ (+Puan)
        # - DXY fırlıyorsa -> TEHLİKE (-Puan, sahte kırılım riski)
        # - Nasdaq yeşilse -> Risk-On / Sermaye Akışı (+Puan)
        # - Altın güçlü ise -> Küresel likidite desteği (+Puan)

        dxy_chg = market_data["DXY"]["change_24h"]
        nasdaq_chg = market_data["NASDAQ"]["change_24h"]
        gold_chg = market_data["GOLD"]["change_24h"]

        score = 65.0  # Taban nötr puan

        # DXY Etkisi (En kritik çarpan)
        if dxy_chg <= -0.5:
            score += 22.0  # Dolar çöküyor, Bitcoin için roket yakıtı!
        elif dxy_chg < 0:
            score += 12.0
        elif dxy_chg >= 0.6:
            score -= 28.0  # Dolar fırlıyor, kriptoda çöküş/sahte kırılım riski!
        elif dxy_chg > 0.2:
            score -= 14.0

        # Nasdaq Etkisi (Wall Street Risk İştahı)
        if nasdaq_chg >= 1.5:
            score += 15.0
        elif nasdaq_chg > 0:
            score += 8.0
        elif nasdaq_chg <= -1.5:
            score -= 18.0
        elif nasdaq_chg < 0:
            score -= 8.0

        # Altın Etkisi
        if gold_chg > 0:
            score += 3.0
        else:
            score -= 2.0

        score = max(5.0, min(98.0, round(score, 1)))

        # 4. Rejim & Dinamik Kâr Çarpanı Belirleme
        if score >= 75.0:
            regime = "TURBO_BULL"
            regime_title = "🔥 TURBO BOĞA (Kâr Maksimize)"
            target_tp_pct = 35.0          # Normal %18 yerine %35 Kâr Hedefi!
            trailing_stop_pct = 5.0       # Zirveden %5 sarkınca sat
            budget_multiplier = 1.5       # $40 yerine $60 alım bütçesi
            allow_buying = True
            color = "#10b981"
            thesis = f"DXY düşüşte (%{dxy_chg}) ve Wall Street alıcı. Küresel likidite Bitcoin ve kriptoya akıyor; kâr hedefi +%35'e katlandı."
        elif score <= 42.0:
            regime = "DEFENSIVE"
            regime_title = "🛑 MAKRO KORUMA (Tuzak Kalkanı)"
            target_tp_pct = 12.0
            trailing_stop_pct = 2.5
            budget_multiplier = 0.5
            allow_buying = False          # Sahte kırılımları engellemek için yeni alımları dondur!
            color = "#ef4444"
            thesis = f"DXY zıpladı (+%{dxy_chg}) veya Wall Street kırmızıda. Sahte kırılım ve tuzak riskine karşı yeni alımlar askıya alındı."
        else:
            regime = "BALANCED"
            regime_title = "⚖️ DENGELİ PİYASA"
            target_tp_pct = 18.0          # Standart %18 Kâr Hedefi
            trailing_stop_pct = 4.0
            budget_multiplier = 1.0
            allow_buying = True
            color = "#0284c7"
            thesis = "Küresel göstergeler dengede; standart kırılım ve sıkışma kuralları (+%18 TP, -%2.5 SL) devrede."

        result = {
            "status": "SUCCESS",
            "score": score,
            "regime": regime,
            "regime_title": regime_title,
            "color": color,
            "allow_buying": allow_buying,
            "target_tp_pct": target_tp_pct,
            "trailing_stop_pct": trailing_stop_pct,
            "budget_multiplier": budget_multiplier,
            "thesis": thesis,
            "dxy": market_data["DXY"],
            "nasdaq": market_data["NASDAQ"],
            "gold": market_data["GOLD"],
            "usd_try_ecb": round(usd_try, 3),
            "eur_usd_ecb": round(eur_usd, 4),
            "updated_at": time.strftime("%H:%M:%S")
        }

        cls._cache = result
        cls._cache_time = now
        return result
