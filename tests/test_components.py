import unittest
import pandas as pd
import numpy as np
from bot.data.crypto_feed import CryptoFeed
from bot.data.sentiment_feed import SentimentFeed
from bot.indicators.technical import TechnicalAnalyzer
from bot.trading.risk_guard import RiskGuard
from bot.trading.paper_wallet import PaperWallet
from bot.agent.harness_agent import DeepSeekQuantAgent
from pathlib import Path
import tempfile
import os

class TestQuantBotComponents(unittest.TestCase):
    
    def test_01_crypto_feed(self):
        """Binance Public API'den veri çekme testi."""
        ticker = CryptoFeed.get_ticker_24h("BTCUSDT")
        self.assertIn("price", ticker)
        self.assertGreater(ticker["price"], 0)
        
        df = CryptoFeed.get_klines("BTCUSDT", interval="1h", limit=30)
        self.assertFalse(df.empty)
        self.assertIn("close", df.columns)
        self.assertIn("volume", df.columns)
        print(f"[TEST 1 OK] BTC Fiyatı: ${ticker['price']:,.2f}")

    def test_02_sentiment_feed(self):
        """Fear and Greed Endeksi çekme testi."""
        fng = SentimentFeed.get_crypto_fear_and_greed()
        self.assertIn("value", fng)
        self.assertGreaterEqual(fng["value"], 0)
        self.assertLessEqual(fng["value"], 100)
        print(f"[TEST 2 OK] Fear & Greed: {fng['value']} ({fng['label_tr']})")

    def test_03_technical_indicators(self):
        """Teknik indikatör motorunun matematiksel hesaplama testi."""
        # 50 barlık sentetik yükseliş trendi verisi üret
        dates = pd.date_range("2026-01-01", periods=50, freq="h")
        prices = np.linspace(100, 150, 50) + np.random.normal(0, 1, 50)
        df = pd.DataFrame({
            "timestamp": dates,
            "open": prices - 0.5,
            "high": prices + 1.5,
            "low": prices - 1.5,
            "close": prices,
            "volume": np.random.uniform(1000, 5000, 50)
        })
        
        res = TechnicalAnalyzer.calculate_indicators(df)
        self.assertIn("rsi", res)
        self.assertIn("macd", res)
        self.assertIn("moving_averages", res)
        self.assertIn("bollinger_bands", res)
        self.assertIn("volatility", res)
        self.assertIn("summary", res)
        print(f"[TEST 3 OK] RSI: {res['rsi']}, Trend Skoru: {res['summary']}")

    def test_04_risk_guard(self):
        """Risk koruma ve sermaye boyutlandırma testi."""
        guard = RiskGuard(max_risk_pct=2.0)
        
        # Geçerli BUY sinyali
        valid_buy = {
            "action": "BUY",
            "entry_price": 100.0,
            "stop_loss": 95.0, # $5 risk
            "take_profit": 115.0, # $15 ödül (1:3 RR)
        }
        passed, reason, params = guard.validate_and_size_position(valid_buy, current_balance=10000.0, current_open_positions_count=0)
        self.assertTrue(passed)
        self.assertEqual(params["risk_reward_ratio"], 3.0)
        # 10.000$'ın %25 tavanı = 2.500$ pozisyon büyüklüğü -> 25 adet -> 25 * $5 risk = $125 risk
        self.assertAlmostEqual(params["position_value_usd"], 2500.0, delta=1.0)
        self.assertAlmostEqual(params["risk_amount_usd"], 125.0, delta=1.0)
        
        # Geçersiz Stop-Loss (Entry'den yüksek)
        invalid_sl = {
            "action": "BUY",
            "entry_price": 100.0,
            "stop_loss": 105.0,
            "take_profit": 120.0
        }
        passed, reason, _ = guard.validate_and_size_position(invalid_sl, current_balance=10000.0, current_open_positions_count=0)
        self.assertFalse(passed)
        
        # Düşük Risk/Ödül oranı (1:1.0)
        bad_rr = {
            "action": "BUY",
            "entry_price": 100.0,
            "stop_loss": 90.0,
            "take_profit": 105.0
        }
        passed, reason, _ = guard.validate_and_size_position(bad_rr, current_balance=10000.0, current_open_positions_count=0)
        self.assertFalse(passed)
        print("[TEST 4 OK] RiskGuard kuralları başarıyla doğrulandı")

    def test_05_paper_wallet(self):
        """Sanal kasa ve işlem defteri testi."""
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tf:
            temp_path = Path(tf.name)
            
        try:
            wallet = PaperWallet(storage_file=temp_path)
            self.assertEqual(wallet.cash_balance, 10000.0)
            
            # Pozisyon aç
            pos = wallet.open_position(
                symbol="BTCUSDT",
                action="BUY",
                entry_price=60000.0,
                stop_loss=58000.0,
                take_profit=66000.0,
                units=0.05,
                thesis="Test alımı"
            )
            self.assertEqual(len(wallet.open_positions), 1)
            self.assertEqual(wallet.cash_balance, 10000.0 - (60000.0 * 0.05)) # $7000
            
            # Take-Profit vurulduğunda otomatik çıkış testi
            closed = wallet.check_and_update_prices({"BTCUSDT": 66500.0})
            self.assertEqual(len(closed), 1)
            self.assertEqual(closed[0]["exit_reason"], "TAKE_PROFIT_HIT")
            self.assertGreater(closed[0]["pnl_usd"], 0)
            self.assertEqual(len(wallet.open_positions), 0)
            print(f"[TEST 5 OK] PaperWallet TP ile kapandı. Kâr: ${closed[0]['pnl_usd']:.2f}")
        finally:
            if temp_path.exists():
                os.remove(temp_path)

    def test_06_agent_fallback(self):
        """DeepSeek Quant Agent deterministik kural motoru testi."""
        agent = DeepSeekQuantAgent()
        indicators = {
            "current_price": 65000.0,
            "summary": "STRONG_BULLISH",
            "rsi": 55.0,
            "volatility": {"atr": 1000.0},
            "key_levels": {"support": 63500.0, "resistance": 68000.0}
        }
        sentiment = {"value": 65, "label_tr": "Açgözlülük"}
        
        res = agent._rule_based_fallback("BTCUSDT", indicators, sentiment)
        self.assertEqual(res["action"], "BUY")
        self.assertIn("thesis_summary", res)
        self.assertLess(res["stop_loss"], 65000.0)
        self.assertGreater(res["take_profit"], 65000.0)
        print(f"[TEST 6 OK] Ajan Çıktısı: {res['action']} (SL: {res['stop_loss']}, TP: {res['take_profit']})")

if __name__ == "__main__":
    unittest.main()
