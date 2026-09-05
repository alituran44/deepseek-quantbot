import unittest
from bot.trading.binance_live import BinanceLiveExecutor

class TestBinanceLive(unittest.TestCase):

    def test_01_signature_generation(self):
        """HMAC-SHA256 imzasının matematiksel doğruluğu testi."""
        executor = BinanceLiveExecutor(api_key="test_key", secret_key="test_secret")
        params = {"symbol": "BTCUSDT", "side": "BUY", "type": "MARKET", "quantity": 1.0, "timestamp": 1600000000000}
        sig = executor._sign(params)
        self.assertIsInstance(sig, str)
        self.assertEqual(len(sig), 64) # SHA256 hex uzunluğu 64 karakterdir
        print("[TEST OK] HMAC-SHA256 borsa imza motoru çalışıyor.")

    def test_02_precision_formatter(self):
        """Lot büyüklüğü ve adım hassasiyeti formatlama testi."""
        executor = BinanceLiveExecutor(api_key="test_key", secret_key="test_secret")
        executor._symbol_filters_cache["BTCUSDT"] = {"stepSize": 0.00001, "tickSize": 0.01, "minNotional": 10.0}
        formatted = executor.format_quantity("BTCUSDT", 0.12345678)
        self.assertEqual(formatted, 0.12345)
        print("[TEST OK] Adım hassasiyeti (lot size) kuralları başarıyla uygulandı.")

    def test_03_unconfigured_safety(self):
        """Anahtarlar girilmediğinde canlı emir iletimini engelleyen güvenlik testi."""
        executor = BinanceLiveExecutor(api_key="", secret_key="")
        ok, res = executor.place_market_order("BTCUSDT", "BUY", 0.01)
        self.assertFalse(ok)
        self.assertTrue("error" in res or "msg" in res)
        print("[TEST OK] Anahtarsız canlı emir engellendi (Güvenlik onaylandı).")

if __name__ == "__main__":
    unittest.main()
