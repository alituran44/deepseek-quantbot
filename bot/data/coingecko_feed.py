import time
import requests
from typing import Dict, Any, List, Optional
from ..config import config

class CoinGeckoFeed:
    """
    CoinGecko API Entegrasyonu:
    - Kripto sektör kategorilerini (AI, Layer 1, DeFi, Meme, RWA) anlık 24s hacim & piyasa değeri değişimiyle çeker.
    - Anlık sektör rallilerini (hacim patlaması yaşayan temaları) tespit eder.
    - Trend altcoinleri listeler.
    - Ücretsiz / No Auth ve opsiyonel Demo Key ile 5 dakikalık akıllı önbelleğe sahiptir.
    """
    BASE_URL = "https://api.coingecko.com/api/v3"
    
    _categories_cache: List[Dict[str, Any]] = []
    _categories_cache_time: float = 0.0
    _trending_cache: Dict[str, Any] = {}
    _trending_cache_time: float = 0.0
    CACHE_TTL: float = 300.0  # 5 dakika önbellek

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = (api_key or config.COINGECKO_API_KEY).strip()

    def _get_headers(self) -> Dict[str, str]:
        headers = {
            "Accept": "application/json",
            "User-Agent": "DeepSeek-QuantBot/2.0 (CryptoPortfolio Intelligence)"
        }
        if self.api_key:
            headers["x-cg-demo-api-key"] = self.api_key
        return headers

    def get_top_categories(self, limit: int = 15) -> List[Dict[str, Any]]:
        """Piyasadaki en aktif kategorileri 24 saatlik getiri ve hacme göre sıralar."""
        now = time.time()
        if self._categories_cache and (now - self._categories_cache_time < self.CACHE_TTL):
            return self._categories_cache[:limit]

        try:
            resp = requests.get(
                f"{self.BASE_URL}/coins/categories",
                headers=self._get_headers(),
                timeout=10
            )
            if resp.status_code == 200:
                raw_data = resp.json()
                parsed = []
                for cat in raw_data:
                    parsed.append({
                        "id": cat.get("id", ""),
                        "name": cat.get("name", "Bilinmeyen Kategori"),
                        "market_cap": cat.get("market_cap") or 0.0,
                        "market_cap_change_24h": round(cat.get("market_cap_change_24h") or 0.0, 2),
                        "volume_24h": cat.get("volume_24h") or 0.0,
                        "top_3_coins": cat.get("top_3_coins", [])
                    })
                # Hacim ve getiriye göre sırala
                parsed.sort(key=lambda x: (x["volume_24h"], x["market_cap_change_24h"]), reverse=True)
                CoinGeckoFeed._categories_cache = parsed
                CoinGeckoFeed._categories_cache_time = now
                return parsed[:limit]
        except Exception:
            if self._categories_cache:
                return self._categories_cache[:limit]
        return []

    def get_trending(self) -> Dict[str, Any]:
        """CoinGecko üzerinde en çok aranan trend altcoinleri ve kategorileri çeker."""
        now = time.time()
        if self._trending_cache and (now - self._trending_cache_time < self.CACHE_TTL):
            return self._trending_cache

        try:
            resp = requests.get(
                f"{self.BASE_URL}/search/trending",
                headers=self._get_headers(),
                timeout=10
            )
            if resp.status_code == 200:
                data = resp.json()
                coins = []
                for item in data.get("coins", [])[:10]:
                    c = item.get("item", {})
                    coins.append({
                        "id": c.get("id"),
                        "name": c.get("name"),
                        "symbol": c.get("symbol", "").upper(),
                        "market_cap_rank": c.get("market_cap_rank"),
                        "thumb": c.get("thumb")
                    })
                categories = []
                for cat in data.get("categories", [])[:6]:
                    categories.append({
                        "name": cat.get("name"),
                        "market_cap_1h_change": round(cat.get("data", {}).get("market_cap_change_percentage_24h", {}).get("usd", 0.0), 2)
                    })

                res = {"trending_coins": coins, "trending_categories": categories}
                CoinGeckoFeed._trending_cache = res
                CoinGeckoFeed._trending_cache_time = now
                return res
        except Exception:
            if self._trending_cache:
                return self._trending_cache
        return {"trending_coins": [], "trending_categories": []}

    def get_sector_momentum_summary(self) -> Dict[str, Any]:
        """Bot karar motoru ve dashboard için özet sektör istihbaratı üretir."""
        categories = self.get_top_categories(limit=25)
        trending = self.get_trending()
        
        tracked_keywords = {
            "AI / DePIN": ["artificial-intelligence", "ai", "depin"],
            "Layer 1": ["layer-1", "smart-contract"],
            "DeFi": ["decentralized-finance-defi", "defi", "dex"],
            "Meme": ["meme-token", "memes"],
            "RWA (Gerçek Varlıklar)": ["real-world-assets-rwa", "rwa"]
        }
        
        sector_heats = []
        for label, kw_list in tracked_keywords.items():
            matched = next((c for c in categories if any(k in c["id"].lower() for k in kw_list)), None)
            if matched:
                sector_heats.append({
                    "sector": label,
                    "name": matched["name"],
                    "change_24h": matched["market_cap_change_24h"],
                    "volume_24h": matched["volume_24h"],
                    "is_hot": matched["market_cap_change_24h"] > 5.0
                })
        
        sorted_by_change = sorted(categories, key=lambda x: x["market_cap_change_24h"], reverse=True)
        top_gainer = sorted_by_change[0] if sorted_by_change else {}

        return {
            "top_categories": categories[:8],
            "tracked_sectors": sector_heats,
            "top_gainer_sector": top_gainer.get("name", "Genel Kripto"),
            "top_gainer_change": top_gainer.get("market_cap_change_24h", 0.0),
            "trending_coins": [c["symbol"] for c in trending.get("trending_coins", [])[:5]],
            "last_updated": int(self._categories_cache_time)
        }
