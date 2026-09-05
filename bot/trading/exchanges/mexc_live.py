import ccxt
from typing import Dict, Any, List, Optional
from ...config import config

class MEXCLiveExecutor:
    """
    MEXC Borsa Entegratörü (CCXT & MEXC Spot v3 REST API).
    Spot cüzdanındaki tüm kriptoları Satoshi hassasiyetiyle okur, 
    USD değerlerini hesaplar ve al-sat emirleri iletir.
    """

    def __init__(self, api_key: str = None, secret_key: str = None):
        self.api_key = api_key or getattr(config, "MEXC_API_KEY", "")
        self.secret_key = secret_key or getattr(config, "MEXC_SECRET_KEY", "")
        self._client = None
        self._init_client()

    def _init_client(self):
        if self.api_key and self.secret_key:
            try:
                self._client = ccxt.mexc({
                    "apiKey": self.api_key,
                    "secret": self.secret_key,
                    "enableRateLimit": True,
                    "options": {
                        "defaultType": "spot"
                    }
                })
            except Exception as e:
                print(f"[MEXCLiveExecutor] İstemci başlatma hatası: {e}")
                self._client = None
        else:
            self._client = None

    @property
    def configured(self) -> bool:
        """API Key ve Secret tanımlı mı?"""
        return bool(self.api_key and self.secret_key)

    @property
    def enabled(self) -> bool:
        """API Key ve Secret eksiksiz tanımlı ve istemci aktif mi?"""
        return bool(self._client is not None and self.configured)

    def get_account_balances(self) -> Dict[str, Any]:
        """MEXC Spot bakiyelerini tam hassasiyetle çeker."""
        if not self.enabled:
            return {"success": False, "msg": "MEXC API anahtarları tanımlı değil.", "assets": {}}

        try:
            bal = self._client.fetch_balance()
            total_assets = {}
            free_usdt = float(bal.get("free", {}).get("USDT", 0.0) or 0.0)
            
            for asset, amount in bal.get("total", {}).items():
                amt = float(amount or 0.0)
                if amt > 0:
                    free_amt = float(bal.get("free", {}).get(asset, 0.0) or 0.0)
                    locked_amt = float(bal.get("used", {}).get(asset, 0.0) or 0.0)
                    total_assets[asset] = {
                        "free": free_amt,
                        "locked": locked_amt,
                        "total": amt
                    }

            return {
                "success": True,
                "free_usdt": free_usdt,
                "assets": total_assets
            }
        except Exception as e:
            return {"success": False, "msg": f"MEXC Bakiye Hatası: {e}", "assets": {}}

    def get_real_portfolio_summary(self) -> Dict[str, Any]:
        """MEXC'deki gerçek bakiye, tüm coinler ve USD değerini döner."""
        if not self.enabled:
            return {
                "total_value_usd": 0.0,
                "cash_balance": 0.0,
                "free_usdt": 0.0,
                "unrealized_pnl": 0.0,
                "unrealized_pnl_pct": 0.0,
                "open_positions": [],
                "is_live": True,
                "exchange": "MEXC",
                "configured": self.configured,
                "live_assets": []
            }

        bal_info = self.get_account_balances()
        if not bal_info.get("success"):
            return {
                "total_value_usd": 0.0,
                "cash_balance": 0.0,
                "free_usdt": 0.0,
                "unrealized_pnl": 0.0,
                "unrealized_pnl_pct": 0.0,
                "open_positions": [],
                "is_live": True,
                "exchange": "MEXC",
                "configured": self.configured,
                "live_assets": []
            }

        assets_dict = bal_info.get("assets", {})
        free_usdt = float(bal_info.get("free_usdt", 0.0))
        total_val_usd = free_usdt
        live_assets = []
        positions = []

        for asset, details in assets_dict.items():
            total_qty = details["total"]
            if total_qty <= 0:
                continue

            if asset in ["USDT", "USDC", "USD"]:
                price = 1.0
                usd_val = total_qty
            else:
                try:
                    ticker = self._client.fetch_ticker(f"{asset}/USDT")
                    price = float(ticker.get("last", 0.0) or 0.0)
                except Exception:
                    price = 0.0
                usd_val = total_qty * price

            total_val_usd += (usd_val if asset not in ["USDT", "USDC", "USD"] else 0.0)

            live_assets.append({
                "asset": asset,
                "free": details["free"],
                "locked": details["locked"],
                "total": total_qty,
                "price": price,
                "usd_value": usd_val,
                "exchange": "MEXC"
            })

            if asset not in ["USDT", "USDC", "USD"] and usd_val > 0.0001:
                positions.append({
                    "id": f"mexc-{asset.lower()}",
                    "symbol": f"{asset}USDT",
                    "action": "BUY",
                    "entry_price": price,
                    "current_price": price,
                    "stop_loss": round(price * 0.95, 4 if price < 1 else 2),
                    "take_profit": round(price * 1.15, 4 if price < 1 else 2),
                    "units": total_qty,
                    "position_value": round(usd_val, 4 if usd_val < 1 else 2),
                    "unrealized_pnl": 0.0,
                    "unrealized_pnl_pct": 0.0,
                    "open_time": "MEXC Cüzdanı",
                    "exchange": "MEXC",
                    "thesis": f"MEXC Hesabınızdaki Gerçek Varlık ({asset})"
                })

        return {
            "total_value_usd": round(total_val_usd, 4 if total_val_usd < 1 else 2),
            "cash_balance": round(free_usdt, 4 if free_usdt < 1 else 2),
            "free_usdt": round(free_usdt, 4 if free_usdt < 1 else 2),
            "unrealized_pnl": 0.0,
            "unrealized_pnl_pct": 0.0,
            "open_positions": positions,
            "is_live": True,
            "exchange": "MEXC",
            "configured": self.configured,
            "live_assets": live_assets
        }

    def get_deposit_addresses(self) -> Dict[str, Any]:
        """MEXC kripto yatırma adreslerini döner."""
        if not self.enabled:
            return {"success": False, "msg": "MEXC bağlantısı aktif değil.", "addresses": []}

        results = []
        networks = [
            {"coin": "USDT", "netWork": "TRX", "name": "USDT (TRC-20 / Tron)", "desc": "En Düşük Komisyon"},
            {"coin": "USDT", "netWork": "ETH", "name": "USDT (ERC-20 / Ethereum)", "desc": "Ethereum Ana Ağı"},
            {"coin": "USDT", "netWork": "BSC", "name": "USDT (BEP-20 / BNB Chain)", "desc": "Hızlı & Düşük Masraf"},
            {"coin": "BTC", "netWork": "BTC", "name": "Bitcoin (BTC Native)", "desc": "Doğrudan Bitcoin"},
            {"coin": "MX", "netWork": "MX", "name": "MEXC Token (MX Native)", "desc": "MEXC Ekosistem Tokeni"}
        ]

        permission_error = False
        error_message = ""

        for item in networks:
            try:
                addr_info = self._client.fetch_deposit_address(item["coin"], {"netWork": item["netWork"]})
                if addr_info and addr_info.get("address"):
                    results.append({
                        "exchange": "MEXC",
                        "coin": item["coin"],
                        "network": item["netWork"],
                        "name": item["name"],
                        "desc": item["desc"],
                        "address": addr_info["address"],
                        "tag": addr_info.get("tag", ""),
                        "url": ""
                    })
            except Exception as e:
                err_str = str(e)
                if "700007" in err_str or "permission" in err_str.lower():
                    permission_error = True
                    error_message = "MEXC API anahtarınızda 'Yatırma Adresleri Okuma' izni henüz açık değil. MEXC panelinden API yönetimine giderek izinleri güncelleyebilirsiniz."
                    break
                pass

        if permission_error and not results:
            return {
                "success": False,
                "msg": error_message,
                "permission_needed": True,
                "addresses": []
            }

        return {
            "success": True,
            "msg": "Adresler başarıyla listelendi.",
            "permission_needed": False,
            "addresses": results
        }

    def place_market_order(self, symbol: str, side: str, amount: float) -> tuple[bool, Dict[str, Any]]:
        """MEXC üzerinde piyasa fiyatından al-sat yapar."""
        if not self.enabled:
            return False, {"msg": "MEXC bağlantısı aktif değil."}
        try:
            ccxt_sym = symbol if "/" in symbol else f"{symbol.replace('USDT', '')}/USDT"
            order = self._client.create_market_order(ccxt_sym, side.lower(), amount)
            return True, order
        except Exception as e:
            return False, {"msg": str(e)}
