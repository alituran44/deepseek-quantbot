from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional

class BaseExchange(ABC):
    """
    Çoklu Borsa Desteği için Soyut Borsa Arayüzü (Exchange Interface).
    Binance, Bybit, OKX, KuCoin vb. tüm borsa adaptörleri bu sınıfı miras alır.
    """

    @property
    @abstractmethod
    def exchange_id(self) -> str:
        """Borsa kimliği (örn: BINANCE, BYBIT, OKX)."""
        pass

    @property
    @abstractmethod
    def is_configured(self) -> bool:
        """API anahtarlarının geçerli ve tanımlı olup olmadığını döner."""
        pass

    @abstractmethod
    def get_account_balances(self) -> Dict[str, Any]:
        """Cüzdandaki serbest ve kilitli varlıkları çeker."""
        pass

    @abstractmethod
    def get_real_portfolio_summary(self) -> Dict[str, Any]:
        """Gerçek cüzdan varlıkları, USD karşılıkları ve toplam portföy değerini döner."""
        pass

    @abstractmethod
    def place_market_order(self, symbol: str, side: str, quantity: float) -> tuple[bool, Dict[str, Any]]:
        """Piyasa fiyatından alım veya satım emri iletir."""
        pass

    @abstractmethod
    def place_oco_order(self, symbol: str, side: str, quantity: float, take_profit_price: float, stop_loss_price: float) -> tuple[bool, Dict[str, Any]]:
        """Stop-Loss ve Take-Profit (OCO) emri kurar."""
        pass

    @abstractmethod
    def get_deposit_addresses(self) -> List[Dict[str, Any]]:
        """Kripto yatırma cüzdan adreslerini döner."""
        pass
