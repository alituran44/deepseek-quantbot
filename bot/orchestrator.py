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
from .notifications.telegram_notifier import TelegramNotifier

from .trading.exchanges.okx_live import OKXLiveExecutor
from .trading.exchanges.mexc_live import MEXCLiveExecutor
from .data.coingecko_feed import CoinGeckoFeed
from .data.hyperliquid_feed import HyperliquidFeed
from .data.macro_feed import MacroFeed
from .trading.daily_breakout_radar import DailyBreakoutRadar

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
        self.okx_executor = OKXLiveExecutor()
        self.mexc_executor = MEXCLiveExecutor()
        self.radar = DailyBreakoutRadar()
        
        # Canlı USD/TRY döviz kuru önbelleği
        self._usd_try_rate: float = 48.09
        self._usd_try_cache_time: float = 0.0
        
        # Çoklu Borsa Özet Önbelleği (Dashboard anında <5ms yüklensin diye)
        self._exchange_cache_time: float = 0.0
        self._cached_binance_summary: Dict[str, Any] = {}
        self._cached_okx_summary: Dict[str, Any] = {}
        self._cached_mexc_summary: Dict[str, Any] = {}
        self._cached_binance_acc: Dict[str, Any] = {}

        # Son analiz önbelleği (Web paneli için)
        self.latest_analyses: Dict[str, Dict[str, Any]] = {}
        self.last_scan_time: Optional[str] = None
        self.is_scanning: bool = False
        self._scanner_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

    def get_usd_try_rate(self) -> float:
        """Canlı USDT/TRY kurunu Binance API üzerinden çeker (60 sn önbellekli)."""
        import time
        now = time.time()
        if now - self._usd_try_cache_time < 60.0:
            return self._usd_try_rate
        try:
            r = requests.get("https://api.binance.com/api/v3/ticker/price?symbol=USDTTRY", timeout=3)
            if r.ok:
                px = float(r.json().get("price", 48.09))
                if px > 0:
                    self._usd_try_rate = px
                    self._usd_try_cache_time = now
        except Exception:
            pass
        return self._usd_try_rate

    def get_registered_exchanges(self) -> List[Dict[str, Any]]:
        """Kayıtlı ve aktif borsaların (Binance, MEXC, OKX) listesini ve bakiyelerini döner."""
        exchanges = []
        if self.binance_executor.enabled:
            b_bal = self.binance_executor.get_account_balances()
            exchanges.append({
                "id": "BINANCE",
                "name": "Binance Spot",
                "enabled": True,
                "free_usdt": float(b_bal.get("free_usdt", 0.0)) if b_bal.get("success") else 0.0,
                "executor": self.binance_executor
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
                return found["executor"], found["id"], found["free_usdt"], f"{pref} borsasında yetersiz USDT bakiyesi (Mevcut: ${found['free_usdt']:.2f}, Gerekli: ${required_amount_usd:.2f})"
            return found["executor"], found["id"], found["free_usdt"], "OK"

        # AUTO: Akıllı Çoklu Borsa Seçimi
        qualified = [ex for ex in registered if ex["free_usdt"] >= required_amount_usd]
        if qualified:
            best = max(qualified, key=lambda x: x["free_usdt"])
            return best["executor"], best["id"], best["free_usdt"], "OK"

        best = max(registered, key=lambda x: x["free_usdt"])
        if required_amount_usd > 0 and best["free_usdt"] < required_amount_usd:
            return best["executor"], best["id"], best["free_usdt"], f"Kayıtlı borsalarda yetersiz USDT (En yüksek: {best['id']} ${best['free_usdt']:.2f})"
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
        thesis: str = ""
    ) -> tuple[bool, Dict[str, Any], str]:
        """
        Kayıtlı borsalar (Binance, MEXC, OKX) arasından seçilen borsada canlı emir iletir.
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
                ok, order_res = executor.place_market_order(symbol=symbol, side=action, quantity=units)
                if ok and action == "BUY" and stop_loss > 0 and take_profit > 0:
                    try:
                        executor.place_oco_order(
                            symbol=symbol,
                            side="SELL",
                            quantity=units,
                            take_profit_price=take_profit,
                            stop_loss_price=stop_loss
                        )
                    except Exception:
                        pass
            elif ex_id in ["MEXC", "OKX"]:
                ok, order_res = executor.place_market_order(symbol=symbol, side=action, amount=units)
            else:
                return False, {"msg": f"Desteklenmeyen borsa: {ex_id}"}, ex_id

            if ok:
                if action == "BUY":
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
        return analysis_payload

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

            self.last_scan_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            return {
                "status": "SUCCESS",
                "scanned_count": len(results),
                "closed_trades_count": len(closed_trades),
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

    def get_dashboard_state(self) -> Dict[str, Any]:
        """Web arayüzü için tüm sistem, çoklu borsa (Binance & OKX) ve döviz kurlarını derler."""
        sentiment = self.sentiment_feed.get_crypto_fear_and_greed()
        usd_try = self.get_usd_try_rate()
        
        now = time.time()
        if (now - self._exchange_cache_time > 10.0):
            binance_acc = {}
            if self.binance_executor.enabled:
                binance_acc = self.binance_executor.get_account_balances()
            self._cached_binance_acc = binance_acc
            self._cached_binance_summary = self.binance_executor.get_real_portfolio_summary()
            self._cached_okx_summary = self.okx_executor.get_real_portfolio_summary()
            self._cached_mexc_summary = self.mexc_executor.get_real_portfolio_summary()
            self._exchange_cache_time = now

        binance_acc = self._cached_binance_acc
        binance_summary = self._cached_binance_summary
        okx_summary = self._cached_okx_summary
        mexc_summary = self._cached_mexc_summary

        binance_usd = binance_summary.get("total_value_usd", 0.0)
        binance_try = round(binance_usd * usd_try, 2)
        okx_usd = okx_summary.get("total_value_usd", 0.0)
        okx_try = round(okx_usd * usd_try, 2)
        mexc_usd = mexc_summary.get("total_value_usd", 0.0)
        mexc_try = round(mexc_usd * usd_try, 2)

        # Çalışma Moduna Göre Portföy Verisi
        if config.TRADING_MODE == "LIVE":
            master_total_usd = binance_usd + okx_usd + mexc_usd
            master_total_try = round(master_total_usd * usd_try, 2)
            master_cash_usd = binance_summary.get("free_usdt", 0.0) + okx_summary.get("free_usdt", 0.0) + mexc_summary.get("free_usdt", 0.0)
            master_cash_try = round(master_cash_usd * usd_try, 2)

            combined_assets = []
            for a in binance_summary.get("live_assets", []):
                ac = dict(a)
                ac["exchange"] = "Binance"
                combined_assets.append(ac)
            for a in okx_summary.get("live_assets", []):
                ac = dict(a)
                ac["exchange"] = "OKX"
                combined_assets.append(ac)
            for a in mexc_summary.get("live_assets", []):
                ac = dict(a)
                ac["exchange"] = "MEXC"
                combined_assets.append(ac)

            wallet_summary = {
                "total_value": round(master_total_usd, 4 if master_total_usd < 1 else 2),
                "total_value_try": master_total_try,
                "cash_balance": round(master_cash_usd, 4 if master_cash_usd < 1 else 2),
                "cash_balance_try": master_cash_try,
                "unrealized_pnl": 0.0,
                "unrealized_pnl_pct": 0.0,
                "open_positions": binance_summary.get("open_positions", []) + okx_summary.get("open_positions", []) + mexc_summary.get("open_positions", []),
                "recent_closed_trades": [],
                "win_rate": 0.0,
                "total_trades": 0,
                "winning_trades": 0,
                "is_live": True,
                "live_assets": combined_assets
            }
        else:
            # SANAL KASA & ÖĞRENME VERİLERİ ($10,000 Sanal Simülasyon)
            wallet_summary = self.wallet.get_portfolio_summary()
            wallet_summary["is_live"] = False
            master_total_usd = wallet_summary.get("total_equity", 10000.0)
            master_total_try = round(master_total_usd * usd_try, 2)
            master_cash_usd = wallet_summary.get("cash_balance", 10000.0)
            master_cash_try = round(master_cash_usd * usd_try, 2)
            wallet_summary["total_value_try"] = master_total_try
            wallet_summary["cash_balance_try"] = master_cash_try

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
            "trading_mode": config.TRADING_MODE,
            "trading_exchange": getattr(config, "TRADING_EXCHANGE", "AUTO"),
            "available_trading_exchanges": [ex["id"] for ex in self.get_registered_exchanges()],
            "ai_risk_profile": getattr(config, "AI_RISK_PROFILE", "AGGRESSIVE_ALPHA"),
            "max_risk_per_trade_percent": getattr(config, "MAX_RISK_PER_TRADE_PERCENT", 5.0),
            "deepseek_model": config.DEEPSEEK_MODEL,
            "api_key_configured": bool(config.DEEPSEEK_API_KEY),
            "masked_deepseek_key": masked_deepseek_key,
            "usd_try_rate": usd_try,
            "master_treasury": {
                "total_usd": round(master_total_usd, 4 if master_total_usd < 1 else 2),
                "total_try": master_total_try,
                "cash_usd": round(master_cash_usd, 4 if master_cash_usd < 1 else 2),
                "cash_try": master_cash_try,
                "usd_try_rate": usd_try,
                "binance": {
                    "name": "Binance Spot",
                    "enabled": self.binance_executor.enabled,
                    "total_usd": binance_usd,
                    "total_try": binance_try,
                    "free_usdt": binance_summary.get("free_usdt", 0.0),
                    "assets": binance_summary.get("live_assets", [])
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
            "basket_sectors": config.BASKET_SECTORS
        }

# Global singleton orkestratör örneği
orchestrator = BotOrchestrator()
