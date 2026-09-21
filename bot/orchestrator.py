import os
import json
import time
import threading
import requests
from typing import Dict, Any, List, Optional
from datetime import datetime
from .config import config
from .data.crypto_feed import CryptoFeed
from .data.sentiment_feed import SentimentFeed
from .indicators.technical import TechnicalAnalyzer
from .agent.harness_agent import DeepSeekQuantAgent
from .trading.risk_guard import RiskGuard
from .trading.paper_wallet import PaperWallet
from .trading.basket_manager import BasketManager
from .trading.binance_live import BinanceLiveExecutor
from .trading.exchanges.binance_tr_live import BinanceTRLiveExecutor
from .notifications.telegram_notifier import TelegramNotifier

from .trading.exchanges.okx_live import OKXLiveExecutor
from .trading.exchanges.mexc_live import MEXCLiveExecutor
from .data.coingecko_feed import CoinGeckoFeed
from .data.hyperliquid_feed import HyperliquidFeed
from .data.macro_feed import MacroFeed
from .data.macro_market_feed import MacroMarketFeed
from .trading.daily_breakout_radar import DailyBreakoutRadar
from .data.market_intelligence import market_intelligence

class BotOrchestrator:
    """
    Tüm bot bileşenlerini koordine eden ana orkestratör.
    Kripto piyasasını tarar, analiz eder, risk filtresinden geçirir,
    Binance, OKX & MEXC çoklu borsalarında işlem yürütür.
    """
    def __init__(self):
        self.crypto_feed = CryptoFeed()
        self.sentiment_feed = SentimentFeed()
        self.coingecko_feed = CoinGeckoFeed()
        self.hyperliquid_feed = HyperliquidFeed()
        self.macro_feed = MacroFeed()
        self.analyzer = TechnicalAnalyzer()
        self.agent = DeepSeekQuantAgent()
        self.risk_guard = RiskGuard()
        self.wallet = PaperWallet()
        self.notifier = TelegramNotifier()
        self.binance_executor = BinanceLiveExecutor()
        self.binance_tr_executor = BinanceTRLiveExecutor()
        self.okx_executor = OKXLiveExecutor()
        self.mexc_executor = MEXCLiveExecutor()
        self.radar = DailyBreakoutRadar()
        self.market_intelligence = market_intelligence
        
        # Canlı USD/TRY döviz kuru önbelleği
        self._usd_try_rate: float = 48.09
        self._usd_try_cache_time: float = 0.0
        
        # Çoklu Borsa Özet Önbelleği (Dashboard anında <5ms yüklensin diye)
        self._exchange_cache_time: float = 0.0
        self._cached_binance_summary: Dict[str, Any] = {}
        self._cached_binance_tr_summary: Dict[str, Any] = {}
        self._cached_okx_summary: Dict[str, Any] = {}
        self._cached_mexc_summary: Dict[str, Any] = {}
        self._cached_binance_acc: Dict[str, Any] = {}

        # Son analiz önbelleği (Web paneli için)
        self.latest_analyses_file = config.DATA_DIR / "latest_analyses.json"
        self.latest_analyses: Dict[str, Dict[str, Any]] = self._load_latest_analyses()
        self.last_scan_time: Optional[str] = datetime.now().strftime("%Y-%m-%d %H:%M:%S") if self.latest_analyses else None
        self.is_scanning: bool = False
        self._scanner_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

    def _load_latest_analyses(self) -> Dict[str, Any]:
        """Kayıtlı analizleri diskten yükler."""
        if not self.latest_analyses_file.exists():
            repo_file = config.BASE_DIR / "data_storage" / "latest_analyses.json"
            if repo_file.exists() and repo_file.resolve() != self.latest_analyses_file.resolve():
                try:
                    import shutil
                    self.latest_analyses_file.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(repo_file, self.latest_analyses_file)
                except Exception:
                    pass

        if self.latest_analyses_file.exists():
            try:
                with open(self.latest_analyses_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                print(f"[BotOrchestrator] Analizler yüklenemedi: {e}")
        return {}

    def _save_latest_analyses(self):
        """Analizleri diske kalıcı kaydeder."""
        try:
            self.latest_analyses_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.latest_analyses_file, "w", encoding="utf-8") as f:
                json.dump(self.latest_analyses, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"[BotOrchestrator] Analizler kaydedilemedi: {e}")

    def get_usd_try_rate(self) -> float:
        """Canlı USDT/TRY kurunu Binance API üzerinden çeker (60 sn önbellekli)."""
        import time
        now = time.time()
        if now - self._usd_try_cache_time < 60.0:
            return self._usd_try_rate
        for base in ["https://data-api.binance.vision/api/v3", "https://api.binance.com/api/v3"]:
            try:
                r = requests.get(f"{base}/ticker/price?symbol=USDTTRY", timeout=4)
                if r.ok:
                    px = float(r.json().get("price", 48.09))
                    if px > 0:
                        self._usd_try_rate = px
                        self._usd_try_cache_time = now
                        return px
            except Exception:
                continue
        return self._usd_try_rate

    def get_market_intelligence_summary(self) -> Dict[str, Any]:
        """BtcTurk Arbitraj, CoinGecko Trending, Mempool ve DEX özetini derler."""
        btr_prices = {}
        usd_rate = self.get_usd_try_rate() or 48.48
        for sym, data in self.latest_analyses.items():
            clean = sym.replace("USDT", "").replace("TRY", "").replace("_", "")
            px = data.get("current_price", 0.0)
            if px > 0:
                btr_prices[f"{clean}_TRY"] = px * usd_rate
                btr_prices[clean] = px * usd_rate

        cex_prices = {sym: d.get("current_price", 0.0) for sym, d in self.latest_analyses.items()}
        return self.market_intelligence.get_full_intelligence_summary(btr_prices, cex_prices)

    def get_registered_exchanges(self) -> List[Dict[str, Any]]:
        """Kayıtlı ve aktif borsaların (Binance, MEXC, OKX) listesini ve bakiyelerini döner."""
        exchanges = []
        if self.binance_executor.enabled:
            b_bal = self.binance_executor.get_account_balances()
            exchanges.append({
                "id": "BINANCE",
                "name": "Binance Spot (Global)",
                "enabled": True,
                "free_usdt": float(b_bal.get("free_usdt", 0.0)) if b_bal.get("success") else 0.0,
                "executor": self.binance_executor
            })
        if self.binance_tr_executor.enabled:
            tr_bal = self.binance_tr_executor.get_account_balances()
            usd_try = self.get_usd_try_rate() or 48.40
            free_u = float(tr_bal.get("free_usdt", 0.0)) if tr_bal.get("success") else 0.0
            free_t = float(tr_bal.get("free_try", 0.0)) if tr_bal.get("success") else 0.0
            total_u = round(free_u + (free_t / usd_try), 2)
            exchanges.append({
                "id": "BINANCE_TR",
                "name": "Binance TR (trbinance.com)",
                "enabled": True,
                "free_usdt": total_u,
                "raw_free_usdt": free_u,
                "free_try": free_t,
                "executor": self.binance_tr_executor
            })
        if self.mexc_executor.enabled:
            m_bal = self.mexc_executor.get_account_balances()
            exchanges.append({
                "id": "MEXC",
                "name": "MEXC Spot",
                "enabled": True,
                "free_usdt": float(m_bal.get("free_usdt", 0.0)) if m_bal.get("success") else 0.0,
                "executor": self.mexc_executor
            })
        if self.okx_executor.enabled:
            o_bal = self.okx_executor.get_account_balances()
            exchanges.append({
                "id": "OKX",
                "name": "OKX Spot",
                "enabled": True,
                "free_usdt": float(o_bal.get("free_usdt", 0.0)) if o_bal.get("success") else 0.0,
                "executor": self.okx_executor
            })
        return exchanges

    def select_execution_exchange(self, symbol: str, required_amount_usd: float = 0.0, preferred_exchange: Optional[str] = None) -> tuple[Optional[Any], str, float, str]:
        """
        Kayıtlı borsa API'leri arasından en uygun olanı seçer:
        1. Kullanıcı belirli bir borsa tercih ettiyse (preferred_exchange veya config.TRADING_EXCHANGE != 'AUTO'), onu kullanır.
        2. 'AUTO' ise: Kayıtlı ve serbest USDT bakiyesi yeterli olan borsayı otomatik seçer (Akıllı Yönlendirme).
        Döner: (executor, exchange_id, free_usdt, message)
        """
        registered = self.get_registered_exchanges()
        if not registered:
            return None, "", 0.0, "Kayıtlı ve doğrulanmış hiçbir borsa API anahtarı (Binance, MEXC, OKX) aktif değil."

        pref = (preferred_exchange or getattr(config, "TRADING_EXCHANGE", "AUTO")).upper()

        if pref != "AUTO":
            found = next((ex for ex in registered if ex["id"] == pref), None)
            if not found:
                return None, pref, 0.0, f"Seçilen {pref} borsasının API anahtarları tanımlı veya aktif değil."
            if required_amount_usd > 0 and found["free_usdt"] < required_amount_usd:
                if pref == "BINANCE_TR":
                    usd_try = self.get_usd_try_rate() or 48.40
                    free_tl = found.get("free_try", found["free_usdt"] * usd_try)
                    req_tl = required_amount_usd * usd_try
                    return None, found["id"], found["free_usdt"], f"Binance TR hesabınızda yetersiz TL bakiye (Mevcut: ₺{free_tl:.2f} TL, Gerekli: ₺{req_tl:.2f} TL)"
                return None, found["id"], found["free_usdt"], f"{pref} borsasında yetersiz USDT bakiyesi (Mevcut: ${found['free_usdt']:.2f}, Gerekli: ${required_amount_usd:.2f})"
            return found["executor"], found["id"], found["free_usdt"], "OK"

        # AUTO: Akıllı Çoklu Borsa Seçimi
        qualified = [ex for ex in registered if ex["free_usdt"] >= required_amount_usd]
        if qualified:
            best = max(qualified, key=lambda x: x["free_usdt"])
            return best["executor"], best["id"], best["free_usdt"], "OK"

        best = max(registered, key=lambda x: x["free_usdt"])
        if required_amount_usd > 0 and best["free_usdt"] < required_amount_usd:
            return None, best["id"], best["free_usdt"], f"Kayıtlı borsalarda yetersiz USDT (En yüksek: {best['id']} ${best['free_usdt']:.2f})"
        return best["executor"], best["id"], best["free_usdt"], "OK"

    def execute_live_order(
        self, 
        symbol: str, 
        action: str, 
        units: float, 
        entry_price: float, 
        stop_loss: float = 0.0, 
        take_profit: float = 0.0, 
        preferred_exchange: Optional[str] = None,
        thesis: str = "",
        quote_order_qty: Optional[float] = None
    ) -> tuple[bool, Dict[str, Any], str]:
        """
        Kayıtlı borsalar (Binance, MEXC, OKX, Binance TR) arasından seçilen borsada canlı emir iletir.
        Döner: (success, order_result, exchange_name)
        """
        needed_usd = units * entry_price
        executor, ex_id, free_usdt, msg = self.select_execution_exchange(
            symbol=symbol, 
            required_amount_usd=needed_usd if action == "BUY" else 0.0, 
            preferred_exchange=preferred_exchange
        )
        if not executor:
            return False, {"msg": msg}, ex_id or "NONE"

        try:
            if ex_id == "BINANCE":
                if action == "BUY" and quote_order_qty and quote_order_qty > 0:
                    ok, order_res = executor.place_market_order(symbol=symbol, side=action, quote_order_qty=quote_order_qty)
                else:
                    ok, order_res = executor.place_market_order(symbol=symbol, side=action, quantity=units)
                if ok and action == "BUY" and stop_loss > 0 and take_profit > 0:
                    try:
                        oco_qty = units
                        if order_res and isinstance(order_res, dict):
                            exec_qty = float(order_res.get("executedQty", 0.0) or order_res.get("origQty", 0.0) or 0.0)
                            if exec_qty > 0:
                                oco_qty = exec_qty
                        executor.place_oco_order(
                            symbol=symbol,
                            side="SELL",
                            quantity=oco_qty,
                            take_profit_price=take_profit,
                            stop_loss_price=stop_loss
                        )
                    except Exception:
                        pass
            elif ex_id == "BINANCE_TR":
                if action == "BUY" and quote_order_qty and quote_order_qty > 0:
                    ok, order_res = executor.place_market_order(symbol=symbol, side=action, quote_order_qty=quote_order_qty)
                else:
                    ok, order_res = executor.place_market_order(symbol=symbol, side=action, quantity=units)
            elif ex_id in ["MEXC", "OKX"]:
                ok, order_res = executor.place_market_order(symbol=symbol, side=action, amount=units)
            else:
                return False, {"msg": f"Desteklenmeyen borsa: {ex_id}"}, ex_id

            if ok:
                if action == "BUY":
                    if order_res and isinstance(order_res, dict):
                        exec_qty = float(order_res.get("executedQty", 0.0) or order_res.get("origQty", 0.0) or 0.0)
                        if exec_qty > 0:
                            units = exec_qty
                    self.wallet.open_position(
                        symbol=symbol,
                        action="BUY",
                        entry_price=entry_price,
                        stop_loss=stop_loss or (entry_price * 0.95),
                        take_profit=take_profit or (entry_price * 1.10),
                        units=units,
                        thesis=thesis or f"[CANLI {ex_id}]",
                        exchange=ex_id,
                        is_live_record=True
                    )
                elif action == "SELL":
                    clean = symbol.replace("USDT", "").replace("TRY", "").replace("_", "")
                    pos = next((p for p in self.wallet.open_positions if p.get("symbol") in [symbol, clean, f"{clean}USDT", f"{clean}_TRY"]), None)
                    if pos:
                        self.wallet.close_position(pos["id"], entry_price, exit_reason=f"CANLI_SATIS_{ex_id}")
                return True, order_res, ex_id
            else:
                return False, order_res, ex_id
        except Exception as e:
            return False, {"msg": str(e)}, ex_id

    def scan_asset(self, symbol: str) -> Dict[str, Any]:
        """Tek bir kripto varlığı analiz eder, sepet kuralına göre pozisyon açar/kapatır."""
        symbol = symbol.strip().upper()
        asset_type = "CRYPTO"

        # 1. Mum ve Fiyat Verisi Çek (Binance)
        df = self.crypto_feed.get_klines(symbol, interval="1h", limit=100)
        ticker = self.crypto_feed.get_ticker_24h(symbol)
        current_price = ticker.get("price", 0.0)
        change_24h = ticker.get("change_24h", 0.0)

        if df.empty or current_price <= 0:
            return {"symbol": symbol, "error": "Fiyat verisi alınamadı", "status": "FAILED"}

        # 2. Teknik Göstergeleri Hesapla
        indicators = self.analyzer.calculate_indicators(df)
        indicators["current_price"] = current_price
        indicators["change_24h"] = change_24h

        # 3. Piyasa Sentiment, Türev (Hyperliquid), Sektör (CoinGecko) ve Makro (FRED) Verileri
        sentiment = self.sentiment_feed.get_crypto_fear_and_greed()
        hyperliquid_info = self.hyperliquid_feed.get_asset_perps_info(symbol)
        sector_summary = self.coingecko_feed.get_sector_momentum_summary()
        macro_summary = self.macro_feed.get_macro_regime()

        # 4. Hibrit AI Ajanı Akıl Yürütme ve Karar (DeepSeek / Groq)
        signal = self.agent.analyze_market(
            symbol=symbol,
            asset_type=asset_type,
            indicators=indicators,
            sentiment=sentiment,
            hyperliquid_info=hyperliquid_info,
            sector_info=sector_summary,
            macro_info=macro_summary
        )
        signal["symbol"] = symbol
        signal["hyperliquid"] = hyperliquid_info
        signal["macro"] = macro_summary

        # 5. Risk Yönetimi ve Sepet Bütçesi Boyutlandırması
        current_balance = self.wallet.cash_balance
        target_executor = None
        target_ex_id = "PAPER"

        if config.TRADING_MODE == "LIVE":
            # Kayıtlı borsalardan (Binance, MEXC, OKX) uygun olanı seç
            cand_executor, cand_ex_id, free_usdt, sel_msg = self.select_execution_exchange(symbol=symbol, required_amount_usd=0.0)
            target_executor = cand_executor
            target_ex_id = cand_ex_id
            current_balance = free_usdt if cand_executor else 0.0

        is_valid_risk, risk_reason, order_params = self.risk_guard.validate_and_size_position(
            signal=signal,
            current_balance=current_balance,
            current_open_positions_count=len(self.wallet.open_positions),
            open_positions=self.wallet.open_positions
        )

        trade_executed = None
        # 6. Kasa / Canlı Çoklu Borsa İcrası
        if is_valid_risk:
            # CANLI ÇOKLU BORSA SPOT MODU (Binance, MEXC, OKX)
            if config.TRADING_MODE == "LIVE":
                if target_executor:
                    ok, order_res, used_ex = self.execute_live_order(
                        symbol=symbol,
                        action=order_params["action"],
                        units=order_params["units"],
                        entry_price=current_price,
                        stop_loss=order_params.get("stop_loss", 0.0),
                        take_profit=order_params.get("take_profit", 0.0),
                        preferred_exchange=target_ex_id,
                        thesis=f"[CANLI {target_ex_id}] {signal.get('thesis_summary', '')}"
                    )
                    if ok:
                        order_id = str(order_res.get("orderId") or order_res.get("id") or "")
                        trade_executed = {
                            "id": order_id,
                            "symbol": symbol,
                            "exchange": used_ex,
                            "action": order_params["action"],
                            "entry_price": current_price,
                            "units": order_params["units"],
                            "status": f"LIVE_{used_ex}_FILLED"
                        }
                        self.notifier.notify_signal(symbol, signal, order_params)
                    else:
                        risk_reason = f"{used_ex} canlı emir hatası: {order_res.get('msg', str(order_res))}"
                else:
                    risk_reason = "Canlı mod aktif fakat kayıtlı ve bakiyesi yeterli borsa API'si bulunamadı."

            # SANAL KASA (PAPER TRADING) MODU
            else:
                existing_pos = next((p for p in self.wallet.open_positions if p["symbol"] == symbol), None)
                if existing_pos:
                    if existing_pos["action"] != order_params["action"]:
                        closed = self.wallet.close_position(existing_pos["id"], current_price, exit_reason="AI_REVERSAL_SIGNAL")
                        if closed:
                            self.notifier.notify_trade_closed(closed)
                        existing_pos = None

                if not existing_pos:
                    try:
                        trade_executed = self.wallet.open_position(
                            symbol=symbol,
                            action=order_params["action"],
                            entry_price=order_params["entry_price"],
                            stop_loss=order_params["stop_loss"],
                            take_profit=order_params["take_profit"],
                            units=order_params["units"],
                            thesis=signal.get("thesis_summary", ""),
                            exchange="Paper"
                        )
                        self.notifier.notify_signal(symbol, signal, order_params)
                    except Exception as e:
                        risk_reason = f"Sepet emri açılamadı: {e}"

        sector = BasketManager.get_symbol_sector(symbol)
        
        # Kullanıcının bu kriptoya sahip olup olmadığını kontrol et (Tüm kayıtlı borsalar taranır)
        is_owned = False
        owned_units = 0.0
        owned_val = 0.0
        wallet_type = ""
        
        if config.TRADING_MODE == "LIVE":
            # Binance, MEXC, OKX konsolide varlıkları tara
            all_live_positions = (
                self._cached_binance_summary.get("open_positions", []) + 
                self._cached_mexc_summary.get("open_positions", []) + 
                self._cached_okx_summary.get("open_positions", [])
            )
            for p in all_live_positions:
                sym_clean = symbol.replace("USDT", "")
                if p.get("symbol") == symbol or p.get("asset") == sym_clean:
                    is_owned = True
                    owned_units = p.get("units", 0.0)
                    owned_val = p.get("position_value", 0.0)
                    wallet_type = f"{p.get('exchange', 'Borsa')} Spot"
                    break
        else:
            for p in self.wallet.open_positions:
                if p.get("symbol") == symbol:
                    is_owned = True
                    owned_units = p.get("units", 0.0)
                    owned_val = p.get("position_value", 0.0)
                    wallet_type = "Sanal Kasa"
                    break

        analysis_payload = {
            "symbol": symbol,
            "asset_type": asset_type,
            "sector": sector,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "current_price": current_price,
            "change_24h": change_24h,
            "is_owned": is_owned,
            "owned_units": owned_units,
            "owned_val": owned_val,
            "wallet_type": wallet_type,
            "indicators": indicators,
            "sentiment": sentiment,
            "signal": signal,
            "risk_validation": {
                "passed": is_valid_risk,
                "reason": risk_reason,
                "order_params": order_params
            },
            "trade_executed": trade_executed
        }

        self.latest_analyses[symbol] = analysis_payload
        self._save_latest_analyses()
        return analysis_payload

    def run_quick_scan(self, symbols: Optional[List[str]] = None) -> Dict[str, Any]:
        """
        Serverless ortamlar ve hızlı dashboard talepleri için
        sepet varlıklarını paralel olarak analiz eder, risk onaylı işlemleri yürütür.
        """
        from concurrent.futures import ThreadPoolExecutor
        
        target_symbols = list(symbols) if symbols else ["BTCUSDT", "ETHUSDT", "SOLUSDT", "NEARUSDT", "SUIUSDT"]
        # Açık pozisyonları da öncelikli olarak ekle
        for p in self.wallet.open_positions:
            s_sym = p.get("symbol", "")
            if s_sym and s_sym not in target_symbols:
                target_symbols.append(s_sym)

        target_symbols = target_symbols[:6]
        
        results = {}
        current_prices = {}
        with ThreadPoolExecutor(max_workers=min(len(target_symbols), 5)) as executor:
            scanned = list(executor.map(self.scan_asset, target_symbols))

        for res in scanned:
            sym = res.get("symbol")
            if sym:
                results[sym] = res
                if "current_price" in res and res["current_price"] > 0:
                    current_prices[sym] = res["current_price"]

        closed_trades = []
        if current_prices:
            closed_trades = self.wallet.check_and_update_prices(current_prices)
            for ct in closed_trades:
                self.notifier.notify_trade_closed(ct)
                # Eğer canlı moddaysa borsada da satış emrini ilet
                if config.TRADING_MODE == "LIVE":
                    c_sym = ct.get("symbol")
                    c_units = float(ct.get("units", 0.0))
                    c_px = float(ct.get("exit_price", 0.0))
                    c_reason = ct.get("exit_reason", "STOP_OR_TP")
                    if c_sym and c_units > 0:
                        try:
                            self.execute_live_order(
                                symbol=c_sym,
                                action="SELL",
                                units=c_units,
                                entry_price=c_px,
                                thesis=f"Otonom Kural Satışı ({c_reason})"
                            )
                        except Exception as e:
                            print(f"[Orchestrator] Canlı satış hatası: {e}")

        # Otonom Kırılım & Sıkışma Tetikleyicisi (Auto-Buy on Breakout)
        auto_trades = []
        if getattr(config, "AUTO_TRADE_BREAKOUTS", True):
            auto_trades = self.auto_trade_breakout_triggers()

        self.last_scan_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self._save_latest_analyses()
        return {
            "status": "SUCCESS",
            "scanned_count": len(results),
            "closed_trades_count": len(closed_trades),
            "auto_trades_executed": len(auto_trades),
            "timestamp": self.last_scan_time
        }

    def set_profit_strategy(self, strategy: str) -> str:
        """Kâr stratejisini ayarlar: 'FAST_SCALP' (Hızlı Para), 'TREND' (Trend / Ralli) veya 'MEGA_RUNNER' (Mega Kâr / Moonshot)."""
        valid = strategy.upper().strip()
        if valid in ["MOONSHOT", "RUNNER"]:
            valid = "MEGA_RUNNER"
        if valid not in ["FAST_SCALP", "TREND", "MEGA_RUNNER"]:
            valid = "FAST_SCALP"
        config.PROFIT_STRATEGY = valid
        os.environ["PROFIT_STRATEGY"] = valid
        try:
            from .config import update_env_file
            update_env_file("PROFIT_STRATEGY", valid)
        except Exception:
            pass
        print(f"[Orchestrator] Kâr Stratejisi Değiştirildi: {valid}")
        return valid

    def auto_trade_breakout_triggers(self) -> List[Dict[str, Any]]:
        """
        Radardaki patlama öncesi sıkışma (Pre-Pump Squeeze) ve kırılım adaylarını kontrol eder.
        Eğer fiyat kırılım tetikleyici direncini hacimle aştıysa otomatik ALIM yapar.
        
        FAST_SCALP (Hızlı Para):
        - +%4.5 Hızlı Take-Profit nakit kilidi
        - -%1.8 Sıkı Stop-Loss ile sermaye koruma
        - +%2.0 kârda başabaşa (giriş +%0.5) çekilerek risksiz işlem
        - +%3.0'da iz süren stop (zirvenin %1.5 altı)
        
        TREND (Trend / Ralli):
        - +%18 - +%35 Kâr hedefi
        - -%2.5 Stop-Loss
        - +%4.0 kârda başabaş, +%8.0'de iz süren stop

        MEGA_RUNNER (💎 Mega Kâr / Moonshot +%40 - +%150+):
        - +%12'de TP1: %40 Kâr Al ve Stop'u Başabaşa Kilitle (Sıfır Risk)
        - +%35'te TP2: %35 Büyük Kâr Al ve Stop'u +%20 Kâra Kilitle
        - +%40+'ta TP3: Kalan %25 için Geniş İz Süren Stop (Zirvenin %8 altı) ile Sonsuz Ralli Takibi
        """
        executed = []
        radar_summary = self.radar.get_summary()
        opportunities = radar_summary.get("opportunities") or radar_summary.get("top_opportunities") or getattr(self.radar, "opportunities", [])
        pre_pumps = radar_summary.get("pre_pump_opportunities", [])
        watchlist = radar_summary.get("watchlist", [])
        
        # 1. Açık pozisyondaki coinleri tespit et (aynı coin tekrar alınmasın)
        open_syms = set()
        active_positions_count = 0
        if config.TRADING_MODE == "LIVE":
            # Canlı modda sadece borsa üzerindeki gerçek aktif varlıkları dikkate al (kağıt cüzdandaki eski test kayıtları canlıyı engellemesin)
            if self.binance_executor.enabled:
                real_sum = self.binance_executor.get_real_portfolio_summary()
                for p in real_sum.get("open_positions", []):
                    s = p.get("symbol")
                    val = float(p.get("value_usd", p.get("position_value", 0.0)))
                    if s and s != "USDT":
                        # Yalnızca $5.00 ve üzeri varlıklar duplicate alımı engellesin (küsurat veya $1-$2 earn bakiyesi alımı tıkamasın)
                        if val >= 5.0:
                            open_syms.add(s)
                        if val >= 2.0:
                            active_positions_count += 1
        else:
            for p in self.wallet.open_positions:
                s = p.get("symbol")
                val = float(p.get("value_usd", p.get("position_value", 0.0)))
                if s:
                    if val >= 5.0:
                        open_syms.add(s)
                    if val >= 2.0:
                        active_positions_count += 1

        # RiskGuard'dan dinamik maksimum açık pozisyon sınırını al (Smart Aggressive: 12, Ultra Degen: 15)
        max_positions = getattr(self.risk_guard, "max_open_positions", 12)
        if active_positions_count >= max_positions:
            return executed

        # 🌐 Küresel Makro İklim Kontrolü (DXY, Nasdaq, ECB Döviz Kurları)
        macro_climate = MacroMarketFeed.get_macro_climate()
        regime = macro_climate.get("regime", "BALANCED")
        allow_buying = macro_climate.get("allow_buying", True)
        macro_tp_pct = macro_climate.get("target_tp_pct", 18.0)
        budget_mult = macro_climate.get("budget_multiplier", 1.0)
        regime_title = macro_climate.get("regime_title", "DENGELİ")

        current_strat = getattr(config, "PROFIT_STRATEGY", "FAST_SCALP").upper()
        is_fast_scalp = current_strat == "FAST_SCALP"
        is_mega_runner = current_strat == "MEGA_RUNNER"

        # 🛑 TUZAK KALKANI (DEFENSIVE REJİM):
        if not allow_buying or regime == "DEFENSIVE":
            if not is_fast_scalp and not is_mega_runner:
                print(f"[AutoTradeBreakout] 🛑 Makro Tuzak Kalkanı Devrede ({regime_title}): DXY/Nasdaq risk baskısı nedeniyle yeni kırılım alımları askıya alındı.")
                return executed
            elif is_fast_scalp:
                print(f"[AutoTradeBreakout] ⚡ Fast Scalp Korumalı Geçiş: Makro DEFENSIVE modda sadece aşırı dar sıkışmalı ($3M+ hacim) hızlı scalplar filtrelenerek değerlendirilecek.")
            else:
                print(f"[AutoTradeBreakout] 💎 Mega Runner Korumalı Geçiş: Makro DEFENSIVE modda sadece en yüksek akümülasyonlu ($3M+ hacim) potansiyelli coinler değerlendirilecek.")

        # Agresif Fırsat Avcısı: En yüksek skorlu aktif kırılımları (opportunities) en başa al
        high_conviction_opps = [o for o in opportunities if float(o.get("breakout_score", 0.0)) >= 70.0]
        candidates_to_check = high_conviction_opps[:8] + pre_pumps[:8] + [w for w in watchlist if w.get("status") == "TETİKTE BEKLİYOR"]
        
        # Canlı borsa serbest bakiyesini döngü öncesinde TEK SEFERDE al (64 gereksiz HTTP sorgusunu ve gecikmeyi sıfırlar)
        live_free_usdt = 0.0
        live_ex_id = "BINANCE"
        if config.TRADING_MODE == "LIVE":
            _, ex_id_found, free_u, _ = self.select_execution_exchange(symbol="BTCUSDT", required_amount_usd=0.0)
            live_free_usdt = free_u
            live_ex_id = ex_id_found or "BINANCE"
            if live_free_usdt < 10.0:
                return executed

        for cand in candidates_to_check:
            sym = cand.get("symbol")
            if not sym or sym in open_syms:
                continue

            px = float(cand.get("price", 0.0))
            if px <= 0:
                continue

            trigger_px = float(cand.get("trigger_price", 0.0))
            is_active_opp = cand.get("mode_type") == "BREAKOUT" or float(cand.get("breakout_score", 0.0)) >= 80.0
            
            if trigger_px <= 0:
                if is_active_opp:
                    trigger_px = px  # Zaten kırılım bölgesinde aktif koşan lider coin
                else:
                    continue

            vol = float(cand.get("volume_usd", 0.0))
            range_span = float(cand.get("range_span_pct", 5.0))

            # DEFENSIVE rejimdeysek ekstra sıkı kalite filtresi
            if regime == "DEFENSIVE":
                if range_span > 3.5 or (vol < 2000000.0 and not is_active_opp):
                    continue

            # Kırılım Şartı: Aktif breakout lideriyse veya anlık fiyat tetik direncini aştı mı?
            is_breakout_triggered = is_active_opp or (px >= trigger_px * 0.998)

            if is_breakout_triggered:
                entry_px = px
                cand_target_px = float(cand.get("target_price", 0.0))
                cand_stop_px = float(cand.get("stop_price", 0.0))
                score = float(cand.get("breakout_score", cand.get("squeeze_score", 85.0)))
                
                if is_fast_scalp:
                    # ⚡ Hızlı Scalp: +%4.5 Hızlı Nakit Kilidi (Turbo Boğada +%6.0)
                    tp_pct = 6.0 if regime == "TURBO_BULL" else getattr(config, "FAST_SCALP_TP_PERCENT", 4.5)
                    sl_pct = getattr(config, "FAST_SCALP_SL_PERCENT", 1.8)
                    gain_mult = 1.0 + (tp_pct / 100.0)
                    target_px = round(entry_px * gain_mult, 6 if entry_px < 1 else 4)
                    stop_px = round(entry_px * (1.0 - (sl_pct / 100.0)), 6 if entry_px < 1 else 4)
                    thesis_text = f"⚡ Otonom Hızlı Scalp ({score:.0f}% Skor): ${trigger_px} aşıldı. Hedef: +%{tp_pct} (${target_px}), Sıkı Stop: -%{sl_pct}, Başabaş: +%2.0"
                elif is_mega_runner:
                    # 💎 Mega Kâr / Moonshot: +%40 - +%150+ Kademeli Çıkış
                    tp1_pct = getattr(config, "MEGA_RUNNER_TP1_PERCENT", 12.0)
                    tp2_pct = getattr(config, "MEGA_RUNNER_TP2_PERCENT", 35.0)
                    sl_pct = getattr(config, "MEGA_RUNNER_SL_PERCENT", 3.5)
                    target_px = cand_target_px if cand_target_px > entry_px else round(entry_px * 1.60, 6 if entry_px < 1 else 4)
                    stop_px = cand_stop_px if (cand_stop_px > 0 and cand_stop_px < entry_px) else round(entry_px * (1.0 - (sl_pct / 100.0)), 6 if entry_px < 1 else 4)
                    target_gain_pct = round(((target_px - entry_px) / entry_px) * 100, 1)
                    thesis_text = f"💎 Otonom Mega Runner ({score:.0f}% Skor): Hedef: +%{target_gain_pct} (${target_px}), TP1: +%{tp1_pct}, TP2: +%{tp2_pct}, Moonshot Takibi"
                else:
                    # 🚀 Trend / Ralli: +%18 - +%35
                    gain_mult = 1.0 + (macro_tp_pct / 100.0)
                    target_px = cand_target_px if cand_target_px > entry_px else round(entry_px * gain_mult, 6 if entry_px < 1 else 4)
                    stop_px = cand_stop_px if (cand_stop_px > 0 and cand_stop_px < entry_px) else cand.get("stop_price", round(entry_px * 0.975, 4))
                    thesis_text = f"🚀 Otonom Makro Kırılım ({regime_title} - {score:.0f}% Skor): Hedef: +%{macro_tp_pct} (${target_px}), Stop: -%2.5"

                # Dinamik serbest nakit tespiti ve agresif sermaye dağılımı
                if config.TRADING_MODE == "LIVE":
                    if live_free_usdt < 10.0:
                        break
                    free_usdt = live_free_usdt
                    
                    # Agresif sermaye tahsisi: Serbest nakdi aktif kırılımlara dağıtır
                    if free_usdt <= 65.0:
                        trade_budget_usd = round(min(free_usdt * 0.60, 32.0), 2)
                        # Kalan miktar min emir sınırı (10$) altına düşecekse tek seferde tüm uygun nakdi kullan
                        if (free_usdt - trade_budget_usd) < 10.0:
                            trade_budget_usd = round(free_usdt * 0.94, 2)
                    else:
                        trade_budget_usd = round(min(free_usdt * 0.40, 50.0) * budget_mult, 2)
                    
                    trade_budget_usd = max(11.0, trade_budget_usd)
                    if trade_budget_usd > free_usdt:
                        trade_budget_usd = round(free_usdt * 0.95, 2)
                    
                    live_free_usdt = max(0.0, live_free_usdt - trade_budget_usd)
                else:
                    trade_budget_usd = round(40.0 * budget_mult, 2)

                if entry_px >= 1000:
                    units = round(trade_budget_usd / entry_px, 5)
                elif entry_px >= 10:
                    units = round(trade_budget_usd / entry_px, 2)
                elif entry_px >= 0.1:
                    units = round(trade_budget_usd / entry_px, 4)
                else:
                    units = round(trade_budget_usd / entry_px, 6)

                if units <= 0:
                    continue
                
                # CANLI veya SANAL emir ilet
                if config.TRADING_MODE == "LIVE":
                    ok, order_res, ex_name = self.execute_live_order(
                        symbol=sym,
                        action="BUY",
                        units=units,
                        entry_price=entry_px,
                        stop_loss=stop_px,
                        take_profit=target_px,
                        thesis=thesis_text,
                        quote_order_qty=trade_budget_usd
                    )
                    if ok:
                        open_syms.add(sym)
                        cand["trigger_status"] = "🔥 KIRILIM TETİKLENDİ - ALINDI"
                        executed.append({
                            "symbol": sym,
                            "action": "BUY",
                            "mode": "LIVE",
                            "exchange": ex_name,
                            "entry_price": entry_px,
                            "target_price": target_px,
                            "stop_price": stop_px,
                            "units": units
                        })
                else:
                    # Sanal Kasa (Paper)
                    try:
                        self.wallet.open_position(
                            symbol=sym,
                            action="BUY",
                            entry_price=entry_px,
                            stop_loss=stop_px,
                            take_profit=target_px,
                            units=units,
                            thesis=thesis_text,
                            exchange="Paper"
                        )
                        open_syms.add(sym)
                        cand["trigger_status"] = "🔥 KIRILIM TETİKLENDİ - ALINDI"
                        executed.append({
                            "symbol": sym,
                            "action": "BUY",
                            "mode": "PAPER",
                            "exchange": "Paper",
                            "entry_price": entry_px,
                            "target_price": target_px,
                            "stop_price": stop_px,
                            "units": units
                        })
                    except Exception as e:
                        print(f"[AutoTradeBreakout] Sanal emir açılamadı: {e}")

        return executed

    def run_full_scan(self) -> Dict[str, Any]:
        """Kullanıcının sahip olduğu varlıklar + Kripto sepetini tarar."""
        if self.is_scanning:
            return {"status": "ALREADY_SCANNING"}
            
        self.is_scanning = True
        try:
            results = {}
            current_prices = {}

            # Kullanıcının sahip olduğu tüm kriptoları listenin en başına al
            owned_symbols = []
            if config.TRADING_MODE == "LIVE" and self.binance_executor.enabled:
                real_summary = self.binance_executor.get_real_portfolio_summary()
                for p in real_summary.get("open_positions", []):
                    s_sym = p.get("symbol", "")
                    if s_sym and s_sym != "USDT":
                        owned_symbols.append(s_sym)
            else:
                for p in self.wallet.open_positions:
                    s_sym = p.get("symbol", "")
                    if s_sym:
                        owned_symbols.append(s_sym)

            # Dinamik hacim liderlerini de ekle
            dynamic_cryptos = self.crypto_feed.get_top_volume_symbols(limit=10)
            all_cryptos = list(dict.fromkeys(owned_symbols + config.CRYPTO_SYMBOLS + dynamic_cryptos))

            for sym in all_cryptos:
                res = self.scan_asset(sym)
                results[sym] = res
                if "current_price" in res:
                    current_prices[sym] = res["current_price"]

            # Açık pozisyonların Stop-Loss ve Take-Profit kontrolünü yap
            closed_trades = self.wallet.check_and_update_prices(current_prices)
            for ct in closed_trades:
                self.notifier.notify_trade_closed(ct)
                # Eğer canlı moddaysa borsada da satış emrini ilet
                if config.TRADING_MODE == "LIVE":
                    c_sym = ct.get("symbol")
                    c_units = float(ct.get("units", 0.0))
                    c_px = float(ct.get("exit_price", 0.0))
                    c_reason = ct.get("exit_reason", "STOP_OR_TP")
                    if c_sym and c_units > 0:
                        try:
                            self.execute_live_order(
                                symbol=c_sym,
                                action="SELL",
                                units=c_units,
                                entry_price=c_px,
                                thesis=f"Otonom Kural Satışı ({c_reason})"
                            )
                        except Exception as e:
                            print(f"[Orchestrator] Canlı satış hatası: {e}")

            # Otonom Kırılım & Sıkışma Tetikleyicisi
            auto_trades = []
            if getattr(config, "AUTO_TRADE_BREAKOUTS", True):
                auto_trades = self.auto_trade_breakout_triggers()

            self.last_scan_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            return {
                "status": "SUCCESS",
                "scanned_count": len(results),
                "closed_trades_count": len(closed_trades),
                "auto_trades_executed": len(auto_trades),
                "timestamp": self.last_scan_time
            }
        finally:
            self.is_scanning = False

    def start_background_scanner(self):
        """Belirlenen aralıklarla arka planda otomatik tarama yapan iş parçacığı."""
        if self._scanner_thread and self._scanner_thread.is_alive():
            return

        def _loop():
            print(f"[BotOrchestrator] Kripto sepet otomatik taraması başlatıldı (Aralık: {config.SCAN_INTERVAL_MINUTES} dk)")
            # İlk açılışta hemen bir tur tara
            self.run_full_scan()
            
            while not self._stop_event.is_set():
                sleep_seconds = config.SCAN_INTERVAL_MINUTES * 60
                for _ in range(int(sleep_seconds)):
                    if self._stop_event.is_set():
                        break
                    time.sleep(1)
                    
                if not self._stop_event.is_set():
                    self.run_full_scan()

        self._scanner_thread = threading.Thread(target=_loop, daemon=True)
        self._scanner_thread.start()

    def stop_background_scanner(self):
        """Arka plan taramasını durdurur."""
        self._stop_event.set()
        if self._scanner_thread:
            self._scanner_thread.join(timeout=3)

    def get_dashboard_state(self, mode: Optional[str] = None) -> Dict[str, Any]:
        """Web arayüzü için tüm sistem, çoklu borsa (Binance & OKX) ve döviz kurlarını derler."""
        sentiment = self.sentiment_feed.get_crypto_fear_and_greed()
        usd_try = self.get_usd_try_rate()
        
        now = time.time()
        if (now - self._exchange_cache_time > 45.0):
            from concurrent.futures import ThreadPoolExecutor

            def _fetch_binance():
                if not self.binance_executor.enabled:
                    return {}, {}
                b_sum = self.binance_executor.get_real_portfolio_summary()
                can_trade = bool(b_sum.get("can_trade", False))
                b_acc = {
                    "success": True,
                    "free_usdt": b_sum.get("free_usdt", 0.0),
                    "can_trade": can_trade,
                    "enable_spot": b_sum.get("enable_spot", False),
                    "permission_warning": b_sum.get("permission_warning"),
                    "assets": {a["asset"]: {"free": a.get("free", 0), "locked": a.get("locked", 0), "total": a.get("units", 0)} for a in b_sum.get("live_assets", [])}
                }
                return b_acc, b_sum

            def _fetch_binance_tr():
                return self.binance_tr_executor.get_real_portfolio_summary(usd_try_rate=usd_try) if self.binance_tr_executor.configured else {}

            def _fetch_okx():
                return self.okx_executor.get_real_portfolio_summary() if self.okx_executor.configured else {}

            def _fetch_mexc():
                return self.mexc_executor.get_real_portfolio_summary() if self.mexc_executor.configured else {}

            with ThreadPoolExecutor(max_workers=4) as executor:
                f_bin = executor.submit(_fetch_binance)
                f_bintr = executor.submit(_fetch_binance_tr)
                f_okx = executor.submit(_fetch_okx)
                f_mexc = executor.submit(_fetch_mexc)

                try:
                    res_acc, res_sum = f_bin.result(timeout=15)
                    if res_sum or not self._cached_binance_summary:
                        self._cached_binance_acc = res_acc
                        self._cached_binance_summary = res_sum
                except Exception as e:
                    print(f"[Orchestrator] Binance fetch exception: {e}")
                try:
                    res_bintr = f_bintr.result(timeout=15)
                    if res_bintr or not self._cached_binance_tr_summary:
                        self._cached_binance_tr_summary = res_bintr
                except Exception as e:
                    print(f"[Orchestrator] Binance TR fetch exception: {e}")
                try:
                    res_okx = f_okx.result(timeout=15)
                    if res_okx or not self._cached_okx_summary:
                        self._cached_okx_summary = res_okx
                except Exception as e:
                    print(f"[Orchestrator] OKX fetch exception: {e}")
                try:
                    res_mexc = f_mexc.result(timeout=15)
                    if res_mexc or not self._cached_mexc_summary:
                        self._cached_mexc_summary = res_mexc
                except Exception as e:
                    print(f"[Orchestrator] MEXC fetch exception: {e}")

            self._exchange_cache_time = now

        binance_acc = self._cached_binance_acc
        binance_summary = self._cached_binance_summary
        binance_tr_summary = self._cached_binance_tr_summary
        okx_summary = self._cached_okx_summary
        mexc_summary = self._cached_mexc_summary

        binance_usd = binance_summary.get("total_value_usd", binance_summary.get("total_equity", 0.0))
        binance_try = round(binance_usd * usd_try, 2)
        binance_tr_usd = binance_tr_summary.get("total_value_usd", 0.0)
        binance_tr_try = binance_tr_summary.get("total_value_try", round(binance_tr_usd * usd_try, 2))
        okx_usd = okx_summary.get("total_value_usd", 0.0)
        okx_try = round(okx_usd * usd_try, 2)
        mexc_usd = mexc_summary.get("total_value_usd", 0.0)
        mexc_try = round(mexc_usd * usd_try, 2)

        # Canlı borsa toplamları her zaman hesaplanır
        live_total_usd = binance_usd + binance_tr_usd + okx_usd + mexc_usd
        live_total_try = round(live_total_usd * usd_try, 2)
        live_cash_usd = binance_summary.get("free_usdt", binance_summary.get("cash_balance", 0.0)) + binance_tr_summary.get("cash_balance", 0.0) + okx_summary.get("free_usdt", 0.0) + mexc_summary.get("free_usdt", 0.0)
        live_cash_try = round(live_cash_usd * usd_try, 2)

        # Çalışma Moduna Göre Portföy Verisi - 100% Canlı Spot Kripto Portföyü
        active_mode = "LIVE"
        master_total_usd = live_total_usd
        master_total_try = live_total_try
        master_cash_usd = live_cash_usd
        master_cash_try = live_cash_try

        combined_assets = []
        for a in binance_summary.get("live_assets", []):
            units = float(a.get("units", a.get("free", 0)) or 0)
            if units > 0.00000001:
                ac = dict(a)
                ac["exchange"] = "Binance"
                ac["units"] = units
                combined_assets.append(ac)
        for a in binance_tr_summary.get("live_assets", []):
            units = float(a.get("units", a.get("free", 0)) or 0)
            if units > 0.00000001:
                ac = dict(a)
                ac["exchange"] = "Binance TR"
                ac["units"] = units
                combined_assets.append(ac)
        for a in okx_summary.get("live_assets", []):
            units = float(a.get("units", a.get("free", 0)) or 0)
            if units > 0.00000001:
                ac = dict(a)
                ac["exchange"] = "OKX"
                ac["units"] = units
                combined_assets.append(ac)
        for a in mexc_summary.get("live_assets", []):
            units = float(a.get("units", a.get("free", 0)) or 0)
            if units > 0.00000001:
                ac = dict(a)
                ac["exchange"] = "MEXC"
                ac["units"] = units
                combined_assets.append(ac)

        # Open positions lookup map
        pos_by_sym = {}
        for p in self.wallet.open_positions:
            s_clean = p.get("symbol", "").replace("USDT", "").replace("TRY", "").upper()
            pos_by_sym[s_clean] = p
            pos_by_sym[p.get("symbol", "").upper()] = p

        total_unrealized_pnl = 0.0

        # Her canlı varlık için Giriş Fiyatı, Anlık Fiyat ve Kâr/Zarar (PnL) zenginleştirmesi
        for ac in combined_assets:
            ast = ac.get("asset", "").upper()
            if ast.startswith("LD") and len(ast) > 3:
                ast = ast[2:]
                ac["asset"] = ast
            units = float(ac.get("units", ac.get("free", 0)) or 0)
            ac["units"] = units

            if ast in ["USDT", "TRY"]:
                cur_px = 1.0 if ast == "USDT" else round(1.0 / usd_try, 4)
                ac["entry_price"] = cur_px
                ac["current_price"] = cur_px
                ac["unrealized_pnl"] = 0.0
                ac["unrealized_pnl_pct"] = 0.0
                ac["stop_loss"] = 0.0
                ac["take_profit"] = 0.0
                val_usd = round(units * cur_px, 2)
                ac["value_usd"] = val_usd
                ac["position_value"] = val_usd
                ac["value_try"] = round(val_usd * usd_try, 2)
                continue
            
            matched_pos = pos_by_sym.get(ast) or pos_by_sym.get(f"{ast}USDT")
            analysis = self.latest_analyses.get(f"{ast}USDT") or self.latest_analyses.get(ast)
            
            cur_px = float(ac.get("current_price") or 0.0)
            if not cur_px and matched_pos:
                cur_px = float(matched_pos.get("current_price", 0.0))
            if not cur_px and analysis:
                cur_px = float(analysis.get("current_price", 0.0))
            if not cur_px and ast not in ["USDT", "TRY"]:
                try:
                    from .data.crypto_feed import CryptoFeed
                    t = CryptoFeed.get_ticker_24h(f"{ast}USDT")
                    if t and t.get("price"):
                        cur_px = float(t["price"])
                except Exception:
                    pass

            if matched_pos and matched_pos.get("entry_price"):
                entry_px = float(matched_pos.get("entry_price", cur_px))
                sl = float(matched_pos.get("stop_loss", 0.0))
                tp = float(matched_pos.get("take_profit", 0.0))
            else:
                chg_24 = float(analysis.get("change_24h", 0.0)) if (analysis and analysis.get("change_24h") is not None) else 0.0
                if cur_px > 0 and abs(chg_24) > 0.001:
                    entry_px = round(cur_px / (1.0 + (chg_24 / 100.0)), 6)
                else:
                    entry_px = cur_px
                sl = round(entry_px * 0.965, 4) if entry_px > 0 else 0.0
                tp = round(entry_px * 1.60, 4) if entry_px > 0 else 0.0

                # Canlı cüzdandaki bu varlığı kalıcı takip için open_positions'a kaydet
                if units > 0.00000001 and ast not in ["TRY", "USDT"]:
                    try:
                        self.wallet.open_position(
                            symbol=f"{ast}USDT",
                            action="BUY",
                            entry_price=entry_px,
                            stop_loss=sl,
                            take_profit=tp,
                            units=units,
                            thesis=f"[CANLI CÜZDAN KAYDI - {ac.get('exchange', 'Binance')}]",
                            exchange=ac.get("exchange", "Binance"),
                            is_live_record=True
                        )
                        pos_by_sym[ast] = {"entry_price": entry_px, "stop_loss": sl, "take_profit": tp}
                    except Exception:
                        pass
            
            ac["current_price"] = cur_px
            ac["entry_price"] = entry_px
            ac["stop_loss"] = sl
            ac["take_profit"] = tp

            val_usd = round(units * cur_px, 2)
            ac["value_usd"] = val_usd
            ac["position_value"] = val_usd
            ac["value_try"] = round(val_usd * usd_try, 2)
            
            if entry_px > 0 and cur_px > 0 and units > 0 and abs(cur_px - entry_px) > 0.000001:
                pnl_usd = (cur_px - entry_px) * units
                pnl_pct = ((cur_px - entry_px) / entry_px) * 100
            elif analysis and analysis.get("change_24h") is not None:
                pnl_pct = float(analysis.get("change_24h", 0.0))
                pnl_usd = (val_usd * pnl_pct) / 100.0
            else:
                pnl_usd = 0.0
                pnl_pct = 0.0
                
            ac["unrealized_pnl"] = round(pnl_usd, 2)
            ac["unrealized_pnl_pct"] = round(pnl_pct, 2)
            total_unrealized_pnl += ac["unrealized_pnl"]

        # Portföy toplam değerini doğrula
        calc_total_usd = sum(ac.get("value_usd", 0.0) for ac in combined_assets)
        if calc_total_usd > master_total_usd:
            master_total_usd = calc_total_usd
            master_total_try = round(master_total_usd * usd_try, 2)

        closed_trades = self.wallet.closed_trades
        total_trades = len(closed_trades)
        winning_trades = [t for t in closed_trades if t.get("pnl_usd", 0) > 0]
        win_rate = round((len(winning_trades) / total_trades * 100), 1) if total_trades > 0 else 0.0

        wallet_summary = {
            "total_value": round(master_total_usd, 4 if master_total_usd < 1 else 2),
            "total_value_try": master_total_try,
            "cash_balance": round(master_cash_usd, 4 if master_cash_usd < 1 else 2),
            "cash_balance_try": master_cash_try,
            "unrealized_pnl": round(total_unrealized_pnl, 2),
            "unrealized_pnl_pct": round((total_unrealized_pnl / master_total_usd * 100), 2) if master_total_usd > 0 else 0.0,
            "open_positions": binance_summary.get("open_positions", []) + binance_tr_summary.get("open_positions", []) + okx_summary.get("open_positions", []) + mexc_summary.get("open_positions", []),
            "recent_closed_trades": closed_trades[:30],
            "win_rate": win_rate,
            "total_trades": total_trades,
            "winning_trades": len(winning_trades),
            "is_live": True,
            "live_assets": combined_assets
        }

        basket_metrics = BasketManager.calculate_basket_metrics(wallet_summary)

        # Maskelenmiş Anahtarlar
        masked_binance_key = ""
        masked_binance_secret = ""
        if self.binance_executor.api_key:
            k = self.binance_executor.api_key
            masked_binance_key = f"{k[:8]}...{k[-8:]}" if len(k) > 16 else k
        if self.binance_executor.secret_key:
            s = self.binance_executor.secret_key
            masked_binance_secret = f"{s[:6]}...{s[-6:]}" if len(s) > 12 else s

        masked_binance_tr_key = ""
        masked_binance_tr_secret = ""
        if self.binance_tr_executor.api_key:
            btk = self.binance_tr_executor.api_key
            masked_binance_tr_key = f"{btk[:8]}...{btk[-8:]}" if len(btk) > 16 else btk
        if self.binance_tr_executor.secret_key:
            bts = self.binance_tr_executor.secret_key
            masked_binance_tr_secret = f"{bts[:6]}...{bts[-6:]}" if len(bts) > 12 else bts

        masked_okx_key = ""
        if self.okx_executor.api_key:
            ok = self.okx_executor.api_key
            masked_okx_key = f"{ok[:8]}...{ok[-8:]}" if len(ok) > 16 else ok

        masked_mexc_key = ""
        if self.mexc_executor.api_key:
            mk = self.mexc_executor.api_key
            masked_mexc_key = f"{mk[:6]}...{mk[-6:]}" if len(mk) > 12 else mk

        masked_deepseek_key = ""
        if config.DEEPSEEK_API_KEY:
            dk = config.DEEPSEEK_API_KEY
            masked_deepseek_key = f"{dk[:6]}...{dk[-6:]}" if len(dk) > 12 else dk

        return {
            "trading_mode": active_mode,
            "profit_strategy": getattr(config, "PROFIT_STRATEGY", "FAST_SCALP"),
            "fast_scalp_tp_percent": getattr(config, "FAST_SCALP_TP_PERCENT", 4.5),
            "fast_scalp_sl_percent": getattr(config, "FAST_SCALP_SL_PERCENT", 1.8),
            "fast_scalp_breakeven_percent": getattr(config, "FAST_SCALP_BREAKEVEN_PERCENT", 2.0),
            "mega_runner_tp1_percent": getattr(config, "MEGA_RUNNER_TP1_PERCENT", 12.0),
            "mega_runner_tp2_percent": getattr(config, "MEGA_RUNNER_TP2_PERCENT", 35.0),
            "mega_runner_trailing_start": getattr(config, "MEGA_RUNNER_TRAILING_START", 40.0),
            "mega_runner_sl_percent": getattr(config, "MEGA_RUNNER_SL_PERCENT", 3.5),
            "trading_exchange": getattr(config, "TRADING_EXCHANGE", "AUTO"),
            "available_trading_exchanges": [ex["id"] for ex in self.get_registered_exchanges()],
            "ai_risk_profile": getattr(config, "AI_RISK_PROFILE", "SMART_AGGRESSIVE"),
            "max_risk_per_trade_percent": getattr(config, "MAX_RISK_PER_TRADE_PERCENT", 20.0),
            "deepseek_model": config.DEEPSEEK_MODEL,
            "api_key_configured": bool(config.DEEPSEEK_API_KEY),
            "masked_deepseek_key": masked_deepseek_key,
            "usd_try_rate": usd_try,
            "master_treasury": {
                "total_usd": round(master_total_usd, 4 if master_total_usd < 1 else 2),
                "total_try": master_total_try,
                "cash_usd": round(master_cash_usd, 4 if master_cash_usd < 1 else 2),
                "cash_try": master_cash_try,
                "live_total_usd": round(live_total_usd, 4 if live_total_usd < 1 else 2),
                "live_total_try": live_total_try,
                "live_cash_usd": round(live_cash_usd, 4 if live_cash_usd < 1 else 2),
                "live_cash_try": live_cash_try,
                "usd_try_rate": usd_try,
                "binance": {
                    "name": "Binance Spot (Global)",
                    "enabled": self.binance_executor.enabled,
                    "total_usd": binance_usd,
                    "total_try": binance_try,
                    "free_usdt": binance_summary.get("free_usdt", 0.0),
                    "assets": binance_summary.get("live_assets", [])
                },
                "binance_tr": {
                    "name": "Binance TR (trbinance.com)",
                    "enabled": self.binance_tr_executor.enabled,
                    "configured": self.binance_tr_executor.configured,
                    "masked_key": masked_binance_tr_key,
                    "total_usd": binance_tr_usd,
                    "total_try": binance_tr_try,
                    "free_usdt": binance_tr_summary.get("free_usdt", 0.0),
                    "free_try": binance_tr_summary.get("free_try", 0.0),
                    "assets": binance_tr_summary.get("live_assets", [])
                },
                "okx": {
                    "name": "OKX Spot / Web3",
                    "enabled": self.okx_executor.enabled,
                    "configured": self.okx_executor.configured,
                    "needs_passphrase": self.okx_executor.needs_passphrase,
                    "masked_key": masked_okx_key,
                    "total_usd": okx_usd,
                    "total_try": okx_try,
                    "free_usdt": okx_summary.get("free_usdt", 0.0),
                    "assets": okx_summary.get("live_assets", [])
                },
                "mexc": {
                    "name": "MEXC Spot",
                    "enabled": self.mexc_executor.enabled,
                    "configured": self.mexc_executor.configured,
                    "masked_key": masked_mexc_key,
                    "total_usd": mexc_usd,
                    "total_try": mexc_try,
                    "free_usdt": mexc_summary.get("free_usdt", 0.0),
                    "assets": mexc_summary.get("live_assets", [])
                }
            },
            "binance_status": {
                "configured": self.binance_executor.enabled,
                "can_trade": binance_acc.get("can_trade", False) if self.binance_executor.enabled else False,
                "masked_key": masked_binance_key,
                "masked_secret": masked_binance_secret,
                "free_usdt": float(binance_acc.get("free_usdt", 0.0)) if binance_acc.get("success") else 0.0,
                "assets": binance_acc.get("assets", {}) if binance_acc.get("success") else {}
            },
            "binance_tr_status": {
                "configured": self.binance_tr_executor.configured,
                "enabled": self.binance_tr_executor.enabled,
                "masked_key": masked_binance_tr_key,
                "masked_secret": masked_binance_tr_secret,
                "free_usdt": binance_tr_summary.get("free_usdt", 0.0),
                "free_try": binance_tr_summary.get("free_try", 0.0),
                "total_usd": binance_tr_usd,
                "total_try": binance_tr_try,
                "assets": binance_tr_summary.get("live_assets", [])
            },
            "okx_status": {
                "configured": self.okx_executor.configured,
                "enabled": self.okx_executor.enabled,
                "needs_passphrase": self.okx_executor.needs_passphrase,
                "masked_key": masked_okx_key
            },
            "mexc_status": {
                "configured": self.mexc_executor.configured,
                "enabled": self.mexc_executor.enabled,
                "masked_key": masked_mexc_key
            },
            "last_scan_time": self.last_scan_time or "Henüz tarama yapılmadı",
            "is_scanning": self.is_scanning,
            "sentiment": sentiment,
            "macro_state": self.macro_feed.get_macro_regime(),
            "macro_climate": MacroMarketFeed.get_macro_climate(),
            "sector_momentum": self.coingecko_feed.get_sector_momentum_summary(),
            "groq_status": {
                "configured": bool(getattr(config, "GROQ_API_KEY", "")),
                "model": "llama-3.3-70b-versatile"
            },
            "coingecko_status": {
                "configured": True,
                "has_key": bool(getattr(config, "COINGECKO_API_KEY", ""))
            },
            "hyperliquid_status": {
                "configured": True,
                "status": "ONLINE"
            },
            "wallet": wallet_summary,
            "basket": basket_metrics,
            "analyses": list(self.latest_analyses.values()),
            "breakout_radar": self.radar.get_summary(),
            "crypto_symbols": config.CRYPTO_SYMBOLS,
            "basket_sectors": config.BASKET_SECTORS,
            "profit_strategy": getattr(config, "PROFIT_STRATEGY", "FAST_SCALP")
        }

    def get_macro_climate(self) -> Dict[str, Any]:
        """Yahoo Finance ve Frankfurter üzerinden küresel makro iklimi döner."""
        climate = dict(MacroMarketFeed.get_macro_climate())
        climate["profit_strategy"] = getattr(config, "PROFIT_STRATEGY", "FAST_SCALP")
        return climate

# Global singleton orkestratör örneği
orchestrator = BotOrchestrator()
