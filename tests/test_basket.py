import unittest
from bot.trading.basket_manager import BasketManager
from bot.trading.risk_guard import RiskGuard

class TestBasketManager(unittest.TestCase):

    def test_01_sector_categorization(self):
        """Kripto varlıkların doğru sepet sektörlerine atanması testi."""
        self.assertEqual(BasketManager.get_symbol_sector("BTCUSDT"), "CORE")
        self.assertEqual(BasketManager.get_symbol_sector("ETHUSDT"), "CORE")
        self.assertEqual(BasketManager.get_symbol_sector("SOLUSDT"), "LAYER1")
        self.assertEqual(BasketManager.get_symbol_sector("SUIUSDT"), "LAYER1")
        self.assertEqual(BasketManager.get_symbol_sector("TAOUSDT"), "AI_DEPIN")
        self.assertEqual(BasketManager.get_symbol_sector("NEARUSDT"), "AI_DEPIN")
        self.assertEqual(BasketManager.get_symbol_sector("DOGEUSDT"), "DEFI_MOMENTUM")
        self.assertEqual(BasketManager.get_symbol_sector("UNIUSDT"), "DEFI_MOMENTUM")
        print("[TEST OK] Tüm kriptolar doğru sepet sektörlerine atandı.")

    def test_02_basket_metrics(self):
        """Sepet sektör ağırlıklarının ve nakit oranının hesaplanması testi."""
        mock_wallet = {
            "total_equity": 10000.0,
            "cash_balance": 6000.0,
            "open_positions": [
                {"symbol": "BTCUSDT", "position_value": 2000.0, "unrealized_pnl": 100.0},
                {"symbol": "SOLUSDT", "position_value": 1000.0, "unrealized_pnl": -50.0},
                {"symbol": "TAOUSDT", "position_value": 1000.0, "unrealized_pnl": 50.0}
            ]
        }
        metrics = BasketManager.calculate_basket_metrics(mock_wallet)
        self.assertEqual(metrics["total_basket_value"], 10000.0)
        self.assertEqual(metrics["cash_pct"], 60.0)
        
        sectors_map = {s["id"]: s for s in metrics["sectors"]}
        self.assertAlmostEqual(sectors_map["CORE"]["current_pct"], 21.0, delta=0.5) # ($2100 / $10000)
        self.assertAlmostEqual(sectors_map["LAYER1"]["current_pct"], 9.5, delta=0.5)
        self.assertAlmostEqual(sectors_map["AI_DEPIN"]["current_pct"], 10.5, delta=0.5)
        print("[TEST OK] Sepet sektör yüzdeleri ve PnL dağılımı başarıyla hesaplandı.")

    def test_03_sector_budget_headroom(self):
        """Sektör bütçe tavanı ve serbest alan hesaplama testi."""
        open_positions = [
            {"symbol": "BTCUSDT", "position_value": 3000.0}
        ]
        # CORE için hedef %35 + %10 tolerans = %45 -> $10,000 * %45 = $4,500 maks bütçe.
        # Halihazırda $3,000 var -> Kalan bütçe: $1,500.
        headroom = BasketManager.get_sector_budget_headroom("ETHUSDT", current_balance=10000.0, open_positions=open_positions)
        self.assertAlmostEqual(headroom, 1500.0, delta=1.0)
        print("[TEST OK] Sektör bütçe tavanı doğrulaması başarılı.")

if __name__ == "__main__":
    unittest.main()
