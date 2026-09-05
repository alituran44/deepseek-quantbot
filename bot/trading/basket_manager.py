from typing import Dict, Any, List
from ..config import config

class BasketManager:
    """
    Kripto Sepet (Basket) Portföy Yöneticisi.
    Varlıkları tematik sektörlere ayırır, sermaye dağılımını dengeler
    ve tek bir sektöre aşırı yığılmayı önler.
    """
    
    @classmethod
    def get_symbol_sector(cls, symbol: str) -> str:
        """Sembolün ait olduğu sepet sektörünü belirler."""
        sym = symbol.upper()
        for sec_id, sec_data in config.BASKET_SECTORS.items():
            if sym in sec_data["symbols"]:
                return sec_id
        # Tanımlı değilse genel sınıflandırma
        if any(x in sym for x in ["BTC", "ETH"]):
            return "CORE"
        if any(x in sym for x in ["SOL", "SUI", "BNB", "AVAX", "ADA", "APT"]):
            return "LAYER1"
        if any(x in sym for x in ["TAO", "NEAR", "FET", "RENDER", "GRT", "WLD"]):
            return "AI_DEPIN"
        return "DEFI_MOMENTUM"

    @classmethod
    def calculate_basket_metrics(cls, wallet_summary: Dict[str, Any]) -> Dict[str, Any]:
        """
        Mevcut açık pozisyonların sepet sektörlerine göre dağılımını ve
        hedef ağırlıklara göre sapmalarını hesaplar.
        """
        total_equity = wallet_summary.get("total_equity", 10000.0)
        cash = wallet_summary.get("cash_balance", total_equity)
        open_positions = wallet_summary.get("open_positions", [])

        # Sektör toplamları
        sector_totals = {sec: 0.0 for sec in config.BASKET_SECTORS.keys()}
        sector_pnl = {sec: 0.0 for sec in config.BASKET_SECTORS.keys()}
        sector_positions_count = {sec: 0 for sec in config.BASKET_SECTORS.keys()}

        for pos in open_positions:
            sec = cls.get_symbol_sector(pos["symbol"])
            val = pos.get("position_value", 0.0) + pos.get("unrealized_pnl", 0.0)
            sector_totals[sec] += val
            sector_pnl[sec] += pos.get("unrealized_pnl", 0.0)
            sector_positions_count[sec] += 1

        sectors_report = []
        for sec_id, sec_data in config.BASKET_SECTORS.items():
            current_val = sector_totals[sec_id]
            current_pct = (current_val / total_equity * 100.0) if total_equity > 0 else 0.0
            target_pct = sec_data["target_pct"]
            delta_pct = round(current_pct - target_pct, 2)

            sectors_report.append({
                "id": sec_id,
                "name": sec_data["name"],
                "target_pct": target_pct,
                "current_pct": round(current_pct, 2),
                "current_val": round(current_val, 2),
                "unrealized_pnl": round(sector_pnl[sec_id], 2),
                "positions_count": sector_positions_count[sec_id],
                "status": "OVERWEIGHT" if delta_pct > 5.0 else ("UNDERWEIGHT" if delta_pct < -5.0 else "BALANCED")
            })

        cash_pct = round((cash / total_equity * 100.0) if total_equity > 0 else 100.0, 2)

        return {
            "total_basket_value": round(total_equity, 2),
            "cash_balance": round(cash, 2),
            "cash_pct": cash_pct,
            "sectors": sectors_report,
            "active_assets_count": len(open_positions)
        }

    @classmethod
    def get_sector_budget_headroom(cls, symbol: str, current_balance: float, open_positions: List[Dict[str, Any]]) -> float:
        """
        Belirli bir varlık için ait olduğu sepet sektörünün maksimum bütçesinden
        kalan boşluğu (USD) hesaplar.
        """
        sec = cls.get_symbol_sector(symbol)
        target_pct = config.BASKET_SECTORS.get(sec, {}).get("target_pct", 25.0)
        max_sector_pct = target_pct + 10.0 # En fazla %10 esneme toleransı
        
        max_budget = current_balance * (max_sector_pct / 100.0)
        
        current_invested = sum(
            p.get("position_value", 0.0) 
            for p in open_positions 
            if cls.get_symbol_sector(p["symbol"]) == sec
        )
        
        headroom = max_budget - current_invested
        return max(0.0, headroom)
