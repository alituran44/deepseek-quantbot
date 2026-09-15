import unittest
import os
from bot.config import config
from bot.trading.paper_wallet import PaperWallet
from bot.orchestrator import BotOrchestrator
from bot.trading.daily_breakout_radar import DailyBreakoutRadar

class TestFastScalpEngine(unittest.TestCase):
    def setUp(self):
        self.orchestrator = BotOrchestrator()
        self.wallet = PaperWallet()
        self.wallet.state["cash_balance"] = 50000.0
        self.wallet.state["open_positions"] = []

    def test_01_profit_strategy_config(self):
        """Kâr stratejisi konfigürasyonu ve varsayılan Fast Scalp değerleri."""
        self.assertEqual(config.FAST_SCALP_TP_PERCENT, 4.5)
        self.assertEqual(config.FAST_SCALP_SL_PERCENT, 1.8)
        self.assertEqual(config.FAST_SCALP_BREAKEVEN_PERCENT, 2.0)

    def test_02_switch_profit_strategy(self):
        """Orkestratör üzerinden mod değiştirme testi."""
        strat = self.orchestrator.set_profit_strategy("TREND")
        self.assertEqual(strat, "TREND")
        self.assertEqual(config.PROFIT_STRATEGY, "TREND")

        strat2 = self.orchestrator.set_profit_strategy("FAST_SCALP")
        self.assertEqual(strat2, "FAST_SCALP")
        self.assertEqual(config.PROFIT_STRATEGY, "FAST_SCALP")

    def test_03_fast_scalp_breakeven_lock(self):
        """Fast Scalp modunda +%2.0 kârda başabaş kilidi (+%0.5 kâr) testi."""
        config.PROFIT_STRATEGY = "FAST_SCALP"
        pos = self.wallet.open_position(
            symbol="BTCUSDT",
            action="BUY",
            entry_price=60000.0,
            stop_loss=58920.0, # -%1.8
            take_profit=62700.0, # +%4.5
            units=0.1,
            thesis="Scalp test"
        )
        self.assertIsNotNone(pos)
        
        # Fiyat +%2.1 kâra çıksın (61260.0)
        closed = self.wallet.check_and_update_prices({"BTCUSDT": 61260.0})
        self.assertEqual(len(closed), 0) # Henüz TP'ye ulaşmadı, açık kalmalı

        # Stop-loss başabaş seviyesine (60000 * 1.005 = 60300) taşınmış olmalı!
        updated_pos = next((p for p in self.wallet.open_positions if p["symbol"] == "BTCUSDT"), None)
        self.assertIsNotNone(updated_pos)
        self.assertTrue(updated_pos.get("is_risk_free"))
        self.assertAlmostEqual(updated_pos["stop_loss"], 60300.0, delta=1.0)

    def test_04_fast_scalp_take_profit_exit(self):
        """Fast Scalp modunda +%4.5 kârda anında nakit kilitleme (TP) testi."""
        config.PROFIT_STRATEGY = "FAST_SCALP"
        pos = self.wallet.open_position(
            symbol="ETHUSDT",
            action="BUY",
            entry_price=3000.0,
            stop_loss=2946.0, # -%1.8
            take_profit=3135.0, # +%4.5
            units=1.0,
            thesis="Scalp TP test"
        )
        # Fiyat hedefe ulaşsın: 3140.0
        closed = self.wallet.check_and_update_prices({"ETHUSDT": 3140.0})
        self.assertEqual(len(closed), 1)
        self.assertEqual(closed[0]["exit_reason"], "TAKE_PROFIT_HIT")
        self.assertGreater(closed[0]["pnl_usd"], 0.0)

    def test_05_fast_scalp_tight_stop_loss(self):
        """Fast Scalp modunda -%1.8'de sermayeyi korumak için sıkı stop testi."""
        config.PROFIT_STRATEGY = "FAST_SCALP"
        pos = self.wallet.open_position(
            symbol="SOLUSDT",
            action="BUY",
            entry_price=150.0,
            stop_loss=147.3, # -%1.8
            take_profit=156.75, # +%4.5
            units=2.0,
            thesis="Scalp SL test"
        )
        # Fiyat stop seviyesine insin: 147.0
        closed = self.wallet.check_and_update_prices({"SOLUSDT": 147.0})
        self.assertEqual(len(closed), 1)
        self.assertEqual(closed[0]["exit_reason"], "STOP_LOSS_HIT")

    def test_06_mega_runner_partial_tp1(self):
        """Mega Runner: +%12 kârda %40 nakit kilitleme ve Stop-Loss'u başabaşa çekme testi."""
        config.PROFIT_STRATEGY = "MEGA_RUNNER"
        pos = self.wallet.open_position(
            symbol="AVAXUSDT",
            action="BUY",
            entry_price=10.0,
            stop_loss=9.65, # -%3.5
            take_profit=16.0, # +%60
            units=100.0,
            thesis="Mega Runner test"
        )
        self.assertIsNotNone(pos)
        self.assertEqual(pos["initial_units"], 100.0)

        # Fiyat +%13 kâra çıksın (11.30) -> TP1 tetiklenmeli (+%12 seviyesi)
        closed = self.wallet.check_and_update_prices({"AVAXUSDT": 11.30})
        self.assertEqual(len(closed), 1)
        self.assertEqual(closed[0]["exit_reason"], "PARTIAL_TP1_HIT")
        self.assertAlmostEqual(closed[0]["units"], 40.0, delta=0.01) # 40 adet satıldı
        self.assertGreater(closed[0]["pnl_usd"], 0.0)

        # Kalan pozisyon 60 adet olmalı ve stop_loss 10.05 (başabaş +0.5%) olmalı
        updated_pos = next((p for p in self.wallet.open_positions if p["symbol"] == "AVAXUSDT"), None)
        self.assertIsNotNone(updated_pos)
        self.assertAlmostEqual(updated_pos["units"], 60.0, delta=0.01)
        self.assertTrue(updated_pos.get("tp1_hit"))
        self.assertTrue(updated_pos.get("is_risk_free"))
        self.assertAlmostEqual(updated_pos["stop_loss"], 10.05, delta=0.01)

    def test_07_mega_runner_partial_tp2(self):
        """Mega Runner: +%35 kârda ilave %35 nakit kilitleme ve Stop-Loss'u +%20'ye kilitleme testi."""
        config.PROFIT_STRATEGY = "MEGA_RUNNER"
        pos = self.wallet.open_position(
            symbol="NEARUSDT",
            action="BUY",
            entry_price=5.0,
            stop_loss=4.825, # -%3.5
            take_profit=8.0, # +%60
            units=100.0,
            thesis="Mega Runner TP2 test"
        )
        # Önce TP1 geçsin (5.60 = +%12)
        self.wallet.check_and_update_prices({"NEARUSDT": 5.60})
        
        # Sonra TP2 seviyesine (6.80 = +%36) ulaşsın
        closed2 = self.wallet.check_and_update_prices({"NEARUSDT": 6.80})
        self.assertEqual(len(closed2), 1)
        self.assertEqual(closed2[0]["exit_reason"], "PARTIAL_TP2_HIT")
        self.assertAlmostEqual(closed2[0]["units"], 35.0, delta=0.01) # 35 adet satıldı

        # Kalan Runner pozisyonu 25 adet (100 - 40 - 35 = 25) olmalı
        updated_pos = next((p for p in self.wallet.open_positions if p["symbol"] == "NEARUSDT"), None)
        self.assertIsNotNone(updated_pos)
        self.assertAlmostEqual(updated_pos["units"], 25.0, delta=0.01)
        self.assertTrue(updated_pos.get("tp2_hit"))
        # Stop-loss entry * 1.20 = 5.0 * 1.20 = 6.00 garantilenmiş kâr olmalı
        self.assertAlmostEqual(updated_pos["stop_loss"], 6.00, delta=0.01)

    def test_08_mega_runner_trailing_stop(self):
        """Mega Runner: +%40 üzerinde zirve takip eden geniş trailing stop testi."""
        config.PROFIT_STRATEGY = "MEGA_RUNNER"
        pos = self.wallet.open_position(
            symbol="RENDERUSDT",
            action="BUY",
            entry_price=10.0,
            stop_loss=9.65,
            take_profit=20.0,
            units=100.0,
            thesis="Mega Runner Trailing test"
        )
        # TP1 ve TP2 tetiklensin
        self.wallet.check_and_update_prices({"RENDERUSDT": 11.50}) # +15%
        self.wallet.check_and_update_prices({"RENDERUSDT": 14.00}) # +40%
        
        # Zirve 15.00'e (+%50) çıksın
        self.wallet.check_and_update_prices({"RENDERUSDT": 15.00})
        updated_pos = next((p for p in self.wallet.open_positions if p["symbol"] == "RENDERUSDT"), None)
        self.assertIsNotNone(updated_pos)
        # Trailing stop: 15.00 * 0.92 = 13.80 olmalı
        self.assertAlmostEqual(updated_pos["stop_loss"], 13.80, delta=0.05)

        # Fiyatta geri çekilme olsun: 13.70'e düşsün -> Trailing stop tetiklenip kalan Runner kapatılmalı
        closed = self.wallet.check_and_update_prices({"RENDERUSDT": 13.70})
        self.assertEqual(len(closed), 1)
        self.assertEqual(closed[0]["exit_reason"], "RUNNER_TRAILING_STOP_HIT")
        self.assertAlmostEqual(closed[0]["units"], 25.0, delta=0.01) # Kalan 25 adet kapatıldı
        self.assertGreater(closed[0]["pnl_usd"], 0.0) # Zirveden kârla çıktı

if __name__ == "__main__":
    unittest.main()

