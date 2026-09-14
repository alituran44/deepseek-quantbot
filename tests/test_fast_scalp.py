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

if __name__ == "__main__":
    unittest.main()
