import time
import requests
from typing import Dict, Any, Optional

class HyperliquidFeed:
    """
    Hyperliquid DEX Vadeli Piyasa İstihbarat Servisi (No Auth / Tamamen Ücretsiz):
    - 230+ Kripto paranın anlık Fonlama Oranını (Funding Rate) çeker.
    - Açık Pozisyon (Open Interest / OI) miktarını ve değerini hesaplar.
    - Tasfiye & Squeeze Riski Tespiti:
        * Aşırı pozitif fonlama (> +0.04% 8s): Long Squeeze Riski (Tepeden alımı engeller)
        * Aşırı negatif fonlama (< -0.03% 8s): Short Squeeze Fırsatı (Ani yukarı patlama)
    """
    INFO_URL = "https://api.hyperliquid.xyz/info"
    _cache_data: Dict[str, Any] = {}
    _cache_time: float = 0.0
    CACHE_TTL: float = 45.0  # 45 saniye önbellek

    @classmethod
    def fetch_market_contexts(cls) -> Dict[str, Any]:
        """Tüm Hyperliquid evrenini ve türev piyasa durumunu tek çağrıda çeker."""
        now = time.time()
        if cls._cache_data and (now - cls._cache_time < cls.CACHE_TTL):
            return cls._cache_data

        try:
            resp = requests.post(
                cls.INFO_URL,
                json={"type": "metaAndAssetCtxs"},
                headers={"Content-Type": "application/json"},
                timeout=8
            )
            if resp.status_code == 200:
                data = resp.json()
                if isinstance(data, list) and len(data) >= 2:
                    universe = data[0].get("universe", [])
                    ctxs = data[1]
                    
                    market_map = {}
                    for i, coin_meta in enumerate(universe):
                        name = coin_meta.get("name", "").upper()
                        if i < len(ctxs):
                            ctx = ctxs[i]
                            funding = float(ctx.get("funding", 0.0))
                            oracle_px = float(ctx.get("oraclePx", 0.0))
                            oi_coins = float(ctx.get("openInterest", 0.0))
                            oi_usd = oi_coins * oracle_px
                            
                            # 8 saatlik ve yıllık fonlama oranı (%)
                            funding_8h_pct = round(funding * 8 * 100, 4)
                            funding_annual_pct = round(funding * 8 * 365 * 100, 2)
                            
                            # Squeeze Riski Sınıflandırması
                            if funding_8h_pct >= 0.04:
                                squeeze_status = "LONG_SQUEEZE_RISK"
                                squeeze_tr = "⚠️ Aşırı Long Yığılması (Düşüş Riski)"
                                risk_color = "var(--loss)"
                            elif funding_8h_pct <= -0.03:
                                squeeze_status = "SHORT_SQUEEZE_OPPORTUNITY"
                                squeeze_tr = "🚀 Short Squeeze Fırsatı (Ani Yukarı)"
                                risk_color = "var(--profit)"
                            else:
                                squeeze_status = "BALANCED"
                                squeeze_tr = "Dengeli Piyasa Yapısı"
                                risk_color = "var(--accent-cyan)"
                                
                            market_map[name] = {
                                "asset": name,
                                "oracle_price": oracle_px,
                                "funding_rate_8h_pct": funding_8h_pct,
                                "funding_rate_annual_pct": funding_annual_pct,
                                "open_interest_coins": oi_coins,
                                "open_interest_usd": round(oi_usd, 2),
                                "day_volume_usd": round(float(ctx.get("dayNtlVlm", 0.0)), 2),
                                "squeeze_status": squeeze_status,
                                "squeeze_tr": squeeze_tr,
                                "risk_color": risk_color
                            }
                    
                    cls._cache_data = market_map
                    cls._cache_time = now
                    return market_map
        except Exception:
            if cls._cache_data:
                return cls._cache_data
        return {}

    @classmethod
    def get_asset_perps_info(cls, symbol: str) -> Dict[str, Any]:
        """Belirtilen sembol için (örn: BTCUSDT veya BTC) fonlama oranı ve OI bilgilerini döner."""
        markets = cls.fetch_market_contexts()
        clean_asset = symbol.upper().replace("USDT", "").replace("BUSD", "").replace("USDC", "").strip()
        
        info = markets.get(clean_asset)
        if info:
            return info
            
        # Varsayılan nötr dönüş
        return {
            "asset": clean_asset,
            "oracle_price": 0.0,
            "funding_rate_8h_pct": 0.01,
            "funding_rate_annual_pct": 10.95,
            "open_interest_coins": 0.0,
            "open_interest_usd": 0.0,
            "day_volume_usd": 0.0,
            "squeeze_status": "BALANCED",
            "squeeze_tr": "Normal / Nötr",
            "risk_color": "var(--text-muted)"
        }
