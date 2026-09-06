from typing import Dict, Any, Tuple
from ..config import config

class RiskGuard:
    """
    Sermaye koruma ve risk yönetimi filtresi.
    Hatalı, aşırı riskli veya kurallara uymayan emirleri engeller.
    """
    def __init__(self, max_risk_pct: float = None):
        profile = getattr(config, "AI_RISK_PROFILE", "AGGRESSIVE_ALPHA").upper()
        is_ultra = profile in ["ULTRA_DEGEN", "DEGEN_ALPHA", "DEGEN"]
        is_aggressive = is_ultra or profile == "AGGRESSIVE_ALPHA"
        
        if is_ultra:
            default_limit = 10.0
            self.max_open_positions = 15
            self.max_wallet_allocation_per_trade = 0.50  # Degen modda kasanın %50'sine kadar alım desteği
            self.min_rr_ratio = 1.2
        elif is_aggressive:
            default_limit = 5.0
            self.max_open_positions = 10
            self.max_wallet_allocation_per_trade = 0.40  # Yüksek inançlı işlemde %40'a kadar alım desteği
            self.min_rr_ratio = 1.4
        else:
            default_limit = 3.0
            self.max_open_positions = 6
            self.max_wallet_allocation_per_trade = 0.25
            self.min_rr_ratio = 1.6

        self.max_risk_pct = max_risk_pct or getattr(config, "MAX_RISK_PER_TRADE_PERCENT", default_limit)

    def validate_and_size_position(
        self, 
        signal: Dict[str, Any], 
        current_balance: float, 
        current_open_positions_count: int,
        open_positions: list = None
    ) -> Tuple[bool, str, Dict[str, Any]]:
        """
        Sinyali doğrular, risk kurallarından geçirir ve pozisyon büyüklüğünü hesaplar.
        Döndürür: (is_valid, reason, order_parameters)
        """
        action = signal.get("action", "HOLD").upper()
        if action == "HOLD":
            return False, "Sinyal nötr (HOLD)", {}
            
        if current_open_positions_count >= self.max_open_positions:
            return False, f"Maksimum açık pozisyon limitine ({self.max_open_positions}) ulaşıldı", {}
            
        entry = float(signal.get("entry_price", 0))
        sl = float(signal.get("stop_loss", 0))
        tp = float(signal.get("take_profit", 0))
        
        if entry <= 0 or sl <= 0 or tp <= 0:
            return False, "Geçersiz fiyat parametreleri (Entry, SL veya TP sıfır olamaz)", {}
            
        # Alım / Satım yönü doğrulaması
        if action == "BUY":
            if sl >= entry:
                return False, f"Alım işleminde Stop-Loss ({sl}) giriş fiyatından ({entry}) küçük olmalıdır", {}
            if tp <= entry:
                return False, f"Alım işleminde Take-Profit ({tp}) giriş fiyatından ({entry}) büyük olmalıdır", {}
            risk_per_unit = entry - sl
            reward_per_unit = tp - entry
        elif action == "SELL":
            if sl <= entry:
                return False, f"Satış işleminde Stop-Loss ({sl}) giriş fiyatından ({entry}) büyük olmalıdır", {}
            if tp >= entry:
                return False, f"Satış işleminde Take-Profit ({tp}) giriş fiyatından ({entry}) küçük olmalıdır", {}
            risk_per_unit = sl - entry
            reward_per_unit = entry - tp
        else:
            return False, f"Bilinmeyen eylem: {action}", {}
            
        # Risk / Ödül Oranı Testi
        rr_ratio = reward_per_unit / (risk_per_unit + 1e-9)
        min_rr = getattr(self, "min_rr_ratio", 1.4)
        if rr_ratio < min_rr:
            return False, f"Risk/Ödül oranı çok düşük ({rr_ratio:.2f} < {min_rr:.2f}). Kural gereği işlem reddedildi", {}
            
        # Pozisyon Büyüklüğü Hesaplama (Fixed Fractional Risk Sizing)
        # Riske edilecek miktar = Toplam Bakiye * Risk Yüzdesi (Örn: $10,000 * %2 = $200)
        risk_budget_usd = current_balance * (self.max_risk_pct / 100.0)
        
        # Kaç adet alınmalı: risk_budget_usd / risk_per_unit
        units = risk_budget_usd / risk_per_unit
        position_value_usd = units * entry
        
        # Tek işleme kasanın en fazla %25'i ayrılabilir tavan kontrolü
        max_position_value = current_balance * self.max_wallet_allocation_per_trade
        if position_value_usd > max_position_value:
            position_value_usd = max_position_value
            units = position_value_usd / entry
            risk_budget_usd = units * risk_per_unit

        # Sepet Sektör Bütçesi Kontrolü
        symbol = signal.get("symbol")
        if symbol and open_positions is not None:
            from .basket_manager import BasketManager
            headroom = BasketManager.get_sector_budget_headroom(symbol, current_balance, open_positions)
            if headroom < (current_balance * 0.04):
                return False, f"Sepet sektörü bütçe limitine ulaştı (Kalan: ${headroom:.2f})", {}
            if position_value_usd > headroom:
                position_value_usd = headroom
                units = position_value_usd / entry
                risk_budget_usd = units * risk_per_unit
            
        order_params = {
            "action": action,
            "entry_price": entry,
            "stop_loss": sl,
            "take_profit": tp,
            "units": round(units, 6),
            "position_value_usd": round(position_value_usd, 2),
            "risk_amount_usd": round(risk_budget_usd, 2),
            "risk_reward_ratio": round(rr_ratio, 2)
        }
        
        return True, "Risk onaylandı", order_params
