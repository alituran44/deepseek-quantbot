import time
import requests
from typing import Dict, Any, Optional
from ..config import config

class MacroFeed:
    """
    Makro Risk Kalkanı & Fed İstihbarat Servisi (FRED + EconPulse):
    - ABD Dolar Endeksi (DXY), Fed Faiz Oranı (FEDFUNDS) ve ABD 10 Yıllık Tahvil Verilerini çeker.
    - Kripto piyasası için Makro Rejimi (RISK_ON / NEUTRAL / DEFENSIVE) hesaplar.
    - DXY fırladığında veya Fed faiz şoklarında botu otomatik savunma moduna geçirecek sinyalleri üretir.
    """
    _cache_data: Dict[str, Any] = {}
    _cache_time: float = 0.0
    CACHE_TTL: float = 600.0  # 10 dakika önbellek

    def __init__(self, fred_api_key: Optional[str] = None):
        self.fred_api_key = (fred_api_key or config.FRED_API_KEY).strip()

    def get_macro_regime(self) -> Dict[str, Any]:
        """Anlık makro ekonomik göstergeleri ve piyasa rejimini hesaplar."""
        now = time.time()
        if self._cache_data and (now - self._cache_time < self.CACHE_TTL):
            return self._cache_data

        dxy = self._fetch_dxy_price()
        ten_year_yield = self._fetch_10y_treasury()
        fed_rate = self._fetch_fed_funds_rate()

        # Makro Rejim Algoritması
        # DXY < 101 ve Düşük Tahvil Faizi = RISK_ON (Kripto İştahı Yüksek)
        # DXY > 104 = DEFENSIVE / RISK_OFF (Dolar Güçlü, Kriptoda Çöküş Riski)
        if dxy > 104.0 or ten_year_yield > 4.7:
            regime = "DEFENSIVE"
            regime_tr = "🛡️ Savunma Modu (Makro Risk Yüksek)"
            regime_color = "var(--loss)"
            cash_recommendation = "Nakit Oranını Artır (%35+)"
            stance = "BEARISH_HEADWIND"
        elif dxy < 101.5:
            regime = "RISK_ON"
            regime_tr = "⚡ Risk-On (Kripto İçin Pozitif Büyüme)"
            regime_color = "var(--profit)"
            cash_recommendation = "Agresif Sepet Genişlemesi"
            stance = "BULLISH_TAILWIND"
        else:
            regime = "NEUTRAL"
            regime_tr = "⚖️ Dengeli Makro Ortam"
            regime_color = "var(--accent-cyan)"
            cash_recommendation = "Standart Portföy Dengesi"
            stance = "NEUTRAL"

        result = {
            "dxy_index": round(dxy, 2),
            "us_10y_yield": round(ten_year_yield, 2),
            "fed_rate": round(fed_rate, 2),
            "regime": regime,
            "regime_tr": regime_tr,
            "regime_color": regime_color,
            "stance": stance,
            "cash_recommendation": cash_recommendation,
            "has_fred_key": bool(self.fred_api_key),
            "last_updated": int(now)
        }

        MacroFeed._cache_data = result
        MacroFeed._cache_time = now
        return result

    def _fetch_dxy_price(self) -> float:
        """Dolar Endeksini (DXY) çeker."""
        try:
            url = "https://query1.finance.yahoo.com/v8/finance/chart/DX-Y.NYB"
            resp = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=6)
            if resp.status_code == 200:
                data = resp.json()
                price = data["chart"]["result"][0]["meta"].get("regularMarketPrice")
                if price:
                    return float(price)
        except Exception:
            pass
        return 98.94  # Güvenli varsayılan

    def _fetch_10y_treasury(self) -> float:
        """ABD 10 Yıllık Tahvil Faizini (FRED DGS10 veya Yahoo) çeker."""
        if self.fred_api_key:
            try:
                url = f"https://api.stlouisfed.org/fred/series/observations?series_id=DGS10&api_key={self.fred_api_key}&file_type=json&limit=1&sort_order=desc"
                resp = requests.get(url, timeout=6)
                if resp.status_code == 200:
                    data = resp.json()
                    obs = data.get("observations", [])
                    if obs and obs[0].get("value") not in (".", None):
                        return float(obs[0]["value"])
            except Exception:
                pass

        try:
            url = "https://query1.finance.yahoo.com/v8/finance/chart/%5ETNX"
            resp = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=6)
            if resp.status_code == 200:
                data = resp.json()
                price = data["chart"]["result"][0]["meta"].get("regularMarketPrice")
                if price:
                    return float(price)
        except Exception:
            pass
        return 4.25

    def _fetch_fed_funds_rate(self) -> float:
        """St. Louis Fed FRED üzerinden veya doğrudan güncel Fed faiz oranını çeker."""
        if self.fred_api_key:
            try:
                url = f"https://api.stlouisfed.org/fred/series/observations?series_id=FEDFUNDS&api_key={self.fred_api_key}&file_type=json&limit=1&sort_order=desc"
                resp = requests.get(url, timeout=6)
                if resp.status_code == 200:
                    data = resp.json()
                    obs = data.get("observations", [])
                    if obs:
                        return float(obs[0].get("value", 4.50))
            except Exception:
                pass
        return 4.50  # Güncel ABD politika faiz aralığı
