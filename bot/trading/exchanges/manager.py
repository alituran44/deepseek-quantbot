from typing import Dict, Any, List, Optional
from .base import BaseExchange
from ..binance_live import BinanceLiveExecutor
from .okx_live import OKXLiveExecutor
from .mexc_live import MEXCLiveExecutor
import ccxt

class MultiExchangeManager:
    """
    Çoklu Borsa Yöneticisi (Multi-Exchange Orchestrator).
    Kullanıcının Binance, OKX, MEXC vb. borsaları tek merkezden yönetmesini sağlar.
    """

    SUPPORTED_EXCHANGES = ["BINANCE", "OKX", "MEXC", "BYBIT", "GATEIO", "KUCOIN"]

    def __init__(self, active_exchange: str = "BINANCE"):
        self.active_exchange_id = active_exchange.upper()
        self._exchanges: Dict[str, Any] = {}
        
        # 1. Binance Birincil Motor
        self._binance = BinanceLiveExecutor()
        self._exchanges["BINANCE"] = self._binance
        
        # 2. OKX Motor
        self._okx = OKXLiveExecutor()
        self._exchanges["OKX"] = self._okx

        # 3. MEXC Motor
        self._mexc = MEXCLiveExecutor()
        self._exchanges["MEXC"] = self._mexc

    @property
    def active_exchange(self):
        """Şu anda aktif olan borsayı döner."""
        return self._exchanges.get(self.active_exchange_id, self._binance)

    def set_active_exchange(self, exchange_id: str) -> bool:
        """Kullanıcının aktif borsayı değiştirmesini sağlar."""
        ex = exchange_id.upper()
        if ex in self.SUPPORTED_EXCHANGES:
            self.active_exchange_id = ex
            return True
        return False

    def get_exchanges_status(self) -> List[Dict[str, Any]]:
        """Tüm desteklenen borsaların bağlantı ve yetki durumunu listeler."""
        return [
            {
                "id": "BINANCE",
                "name": "Binance Spot",
                "status": "CONNECTED" if self._binance.enabled else "DISCONNECTED",
                "active": self.active_exchange_id == "BINANCE",
                "is_configured": self._binance.enabled,
                "masked_key": f"{self._binance.api_key[:6]}...{self._binance.api_key[-6:]}" if self._binance.api_key else ""
            },
            {
                "id": "OKX",
                "name": "OKX Spot / Web3",
                "status": "CONNECTED" if self._okx.enabled else ("NEEDS_PASSPHRASE" if self._okx.needs_passphrase else "DISCONNECTED"),
                "active": self.active_exchange_id == "OKX",
                "is_configured": self._okx.configured,
                "masked_key": f"{self._okx.api_key[:6]}...{self._okx.api_key[-6:]}" if self._okx.api_key else ""
            },
            {
                "id": "MEXC",
                "name": "MEXC Spot",
                "status": "CONNECTED" if self._mexc.enabled else "DISCONNECTED",
                "active": self.active_exchange_id == "MEXC",
                "is_configured": self._mexc.configured,
                "masked_key": f"{self._mexc.api_key[:6]}...{self._mexc.api_key[-6:]}" if self._mexc.api_key else ""
            },
            {
                "id": "BYBIT",
                "name": "Bybit Spot / Derivatives",
                "status": "READY_FOR_API",
                "active": self.active_exchange_id == "BYBIT",
                "is_configured": False,
                "masked_key": ""
            },
            {
                "id": "GATEIO",
                "name": "Gate.io",
                "status": "READY_FOR_API",
                "active": self.active_exchange_id == "GATEIO",
                "is_configured": False,
                "masked_key": ""
            }
        ]

    def register_exchange_keys(self, exchange_id: str, api_key: str, secret_key: str, passphrase: str = "") -> tuple[bool, str]:
        """Yeni bir borsa API anahtarını kaydeder ve test eder."""
        ex_id = exchange_id.upper()
        if ex_id == "BINANCE":
            self._binance = BinanceLiveExecutor(api_key=api_key, secret_key=secret_key)
            self._exchanges["BINANCE"] = self._binance
            ok = self._binance.get_account_balances().get("success", False)
            return ok, "Binance anahtarları güncellendi." if ok else "Binance anahtar doğrulama başarısız."
        
        # CCXT Üzerinden Bybit, OKX vb.
        try:
            ex_class = getattr(ccxt, ex_id.lower(), None)
            if not ex_class:
                return False, f"{ex_id} borsası desteklenmiyor."
            
            config = {
                "apiKey": api_key,
                "secret": secret_key,
                "enableRateLimit": True,
            }
            if passphrase:
                config["password"] = passphrase
                
            client = ex_class(config)
            balance = client.fetch_balance()
            return True, f"{ex_id} bağlantısı başarıyla kuruldu!"
        except Exception as e:
            return False, f"{ex_id} bağlantı hatası: {e}"
