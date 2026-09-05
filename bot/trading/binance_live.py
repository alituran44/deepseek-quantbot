import time
import hmac
import hashlib
import requests
from typing import Dict, Any, List, Optional, Tuple
from urllib.parse import urlencode
from ..config import config

class BinanceLiveExecutor:
    """
    Binance Gerçek Borsa (Live Execution) Motoru.
    HMAC-SHA256 imzalı REST API üzerinden güvenli emir iletimi,
    bakiye sorgusu ve Stop-Loss / Take-Profit (OCO) emirlerini yönetir.
    """
    
    BASE_URL_LIVE = "https://api.binance.com"
    BASE_URL_TESTNET = "https://testnet.binance.vision"

    def __init__(self, api_key: Optional[str] = None, secret_key: Optional[str] = None, testnet: bool = False):
        self.api_key = (api_key or config.BINANCE_API_KEY).strip()
        self.secret_key = (secret_key or config.BINANCE_SECRET_KEY).strip()
        self.testnet = testnet or config.BINANCE_TESTNET
        self.base_url = self.BASE_URL_TESTNET if self.testnet else self.BASE_URL_LIVE
        self.enabled = bool(self.api_key and self.secret_key)
        self._symbol_filters_cache: Dict[str, Dict[str, Any]] = {}

    def _get_timestamp(self) -> int:
        """Milisaniye cinsinden geçerli zaman damgası."""
        return int(time.time() * 1000)

    def _sign(self, params: Dict[str, Any]) -> str:
        """HMAC-SHA256 ile istek imzasını (signature) hesaplar."""
        query_string = urlencode(params)
        signature = hmac.new(
            self.secret_key.encode("utf-8"),
            query_string.encode("utf-8"),
            hashlib.sha256
        ).hexdigest()
        return signature

    def _request(self, method: str, endpoint: str, params: Optional[Dict[str, Any]] = None, signed: bool = False) -> Tuple[bool, Any]:
        """Binance REST API'sine imzalı veya imzasız HTTP isteği gönderir."""
        if not self.enabled and signed:
            return False, {"error": "Binance API Key ve Secret Key tanımlı değil."}

        url = f"{self.base_url}{endpoint}"
        headers = {"X-MBX-APIKEY": self.api_key} if self.api_key else {}
        params = params or {}

        if signed:
            params["timestamp"] = self._get_timestamp()
            params["recvWindow"] = 5000
            params["signature"] = self._sign(params)

        try:
            if method.upper() == "GET":
                resp = requests.get(url, headers=headers, params=params, timeout=10)
            elif method.upper() == "POST":
                resp = requests.post(url, headers=headers, params=params, timeout=10)
            elif method.upper() == "DELETE":
                resp = requests.delete(url, headers=headers, params=params, timeout=10)
            else:
                return False, {"error": f"Desteklenmeyen metod: {method}"}

            data = resp.json()
            if resp.status_code >= 400:
                return False, data
            return True, data
        except Exception as e:
            return False, {"error": str(e)}

    def get_account_balances(self) -> Dict[str, Any]:
        """
        Kullanıcının Binance cüzdanındaki serbest ve kilitli bakiyelerini çeker.
        """
        ok, res = self._request("GET", "/api/v3/account", signed=True)
        if not ok:
            return {"success": False, "error": res.get("msg", str(res))}

        balances = res.get("balances", [])
        free_usdt = 0.0
        active_assets = {}

        for b in balances:
            free = float(b.get("free", 0.0))
            locked = float(b.get("locked", 0.0))
            asset = b.get("asset", "")
            if free > 0 or locked > 0:
                active_assets[asset] = {"free": free, "locked": locked, "total": free + locked}
                if asset == "USDT":
                    free_usdt = free

        return {
            "success": True,
            "free_usdt": free_usdt,
            "assets": active_assets,
            "can_trade": res.get("canTrade", False)
        }

    def get_real_portfolio_summary(self) -> Dict[str, Any]:
        """
        Gerçek Binance hesabındaki TÜM varlıkları (Spot + Fonlama), serbest ve kilitli
        adetleri, canlı fiyatları ve toplam portföy değerini kuruşu kuruşuna,
        eksiksiz hesaplar. Hiçbir varlığı filtrelemez.
        """
        ok_spot, spot_res = self._request("GET", "/api/v3/account", signed=True)
        ok_fund, fund_res = self._request("POST", "/sapi/v1/asset/get-funding-asset", signed=True)

        if not ok_spot:
            return {
                "total_equity": 0.0,
                "cash_balance": 0.0,
                "open_positions": [],
                "recent_closed_trades": [],
                "total_pnl": 0.0,
                "total_pnl_pct": 0.0,
                "win_rate": 0.0,
                "total_trades": 0,
                "is_live": True,
                "error": spot_res.get("msg", str(spot_res))
            }

        from ..data.crypto_feed import CryptoFeed
        holdings = []
        total_equity = 0.0
        total_usdt = 0.0

        # 1. Spot Cüzdanındaki Varlıkları Tara
        for item in spot_res.get("balances", []):
            free = float(item.get("free", 0.0))
            locked = float(item.get("locked", 0.0))
            tot = free + locked
            if tot > 0:
                asset = item.get("asset", "").upper()
                if asset == "USDT":
                    px = 1.0
                    total_usdt += tot
                else:
                    try:
                        px = float(CryptoFeed.get_ticker_24h(f"{asset}USDT").get("price", 0.0))
                    except Exception:
                        px = 0.0
                val = tot * px
                total_equity += val
                holdings.append({
                    "id": f"spot_{asset.lower()}",
                    "symbol": asset if asset == "USDT" else f"{asset}USDT",
                    "asset": asset,
                    "action": "VARLIK (SPOT)",
                    "units": tot,
                    "free": free,
                    "locked": locked,
                    "entry_price": px,
                    "current_price": px,
                    "stop_loss": px * 0.95 if px > 0 else 0.0,
                    "take_profit": px * 1.10 if px > 0 else 0.0,
                    "position_value": val,
                    "unrealized_pnl": 0.0,
                    "unrealized_pnl_pct": 0.0,
                    "wallet_type": "Spot Cüzdanı",
                    "thesis": f"Binance Spot Cüzdanında {tot} {asset} mevcut."
                })

        # 2. Fonlama (Funding) Cüzdanındaki Varlıkları Tara
        if ok_fund and isinstance(fund_res, list):
            for item in fund_res:
                free = float(item.get("free", 0.0))
                locked = float(item.get("locked", 0.0))
                tot = free + locked
                if tot > 0:
                    asset = item.get("asset", "").upper()
                    if asset == "USDT":
                        px = 1.0
                        total_usdt += tot
                    else:
                        try:
                            px = float(CryptoFeed.get_ticker_24h(f"{asset}USDT").get("price", 0.0))
                        except Exception:
                            px = 0.0
                    val = tot * px
                    total_equity += val
                    holdings.append({
                        "id": f"fund_{asset.lower()}",
                        "symbol": asset if asset == "USDT" else f"{asset}USDT",
                        "asset": asset,
                        "action": "VARLIK (FONLAMA)",
                        "units": tot,
                        "free": free,
                        "locked": locked,
                        "entry_price": px,
                        "current_price": px,
                        "stop_loss": px * 0.95 if px > 0 else 0.0,
                        "take_profit": px * 1.10 if px > 0 else 0.0,
                        "position_value": val,
                        "unrealized_pnl": 0.0,
                        "unrealized_pnl_pct": 0.0,
                        "wallet_type": "Fonlama Cüzdanı",
                        "thesis": f"Binance Fonlama Cüzdanında {tot} {asset} mevcut."
                    })

        return {
            "total_equity": round(total_equity, 6),
            "cash_balance": round(total_usdt, 6),
            "open_positions": holdings,
            "recent_closed_trades": [],
            "total_pnl": 0.0,
            "total_pnl_pct": 0.0,
            "win_rate": 0.0,
            "total_trades": 0,
            "is_live": True,
            "live_assets": spot_res.get("balances", [])
        }

    def get_deposit_addresses(self) -> List[Dict[str, Any]]:
        """
        Binance API üzerinden kullanıcının resmi yatırma (deposit) cüzdan adreslerini çeker.
        """
        networks_to_check = [
            {"coin": "USDT", "network": "TRX", "name": "USDT (TRC-20 / Tron)", "desc": "En Düşük Komisyon & Hızlı"},
            {"coin": "USDT", "network": "BSC", "name": "USDT (BEP-20 / BNB Chain)", "desc": "Hızlı & Düşük Ağ Ücreti"},
            {"coin": "USDT", "network": "SOL", "name": "USDT (Solana Ağı)", "desc": "Ultra Hızlı"},
            {"coin": "USDT", "network": "ETH", "name": "USDT (ERC-20 / Ethereum)", "desc": "Standart Ethereum Ağı"},
            {"coin": "BTC", "network": "BTC", "name": "Bitcoin (BTC Native Ağı)", "desc": "Doğrudan Bitcoin Yatırma"},
            {"coin": "ETH", "network": "ETH", "name": "Ethereum (ERC-20)", "desc": "Doğrudan ETH Yatırma"}
        ]
        results = []
        for item in networks_to_check:
            ok, res = self._request("GET", "/sapi/v1/capital/deposit/address", params={"coin": item["coin"], "network": item["network"]}, signed=True)
            if ok and "address" in res:
                results.append({
                    "coin": item["coin"],
                    "network": item["network"],
                    "name": item["name"],
                    "desc": item["desc"],
                    "address": res["address"],
                    "tag": res.get("tag", ""),
                    "url": res.get("url", "")
                })
        return results

    def get_symbol_rules(self, symbol: str) -> Dict[str, Any]:
        """Borsadaki lot ve adım hassasiyeti (precision / filters) kurallarını getirir."""
        if symbol in self._symbol_filters_cache:
            return self._symbol_filters_cache[symbol]

        ok, res = self._request("GET", "/api/v3/exchangeInfo", params={"symbol": symbol})
        if not ok or "symbols" not in res:
            return {"stepSize": 0.0001, "tickSize": 0.01, "minNotional": 10.0}

        s_info = res["symbols"][0]
        step_size = 0.0001
        tick_size = 0.01
        min_notional = 10.0

        for f in s_info.get("filters", []):
            if f["filterType"] == "LOT_SIZE":
                step_size = float(f.get("stepSize", 0.0001))
            elif f["filterType"] == "PRICE_FILTER":
                tick_size = float(f.get("tickSize", 0.01))
            elif f["filterType"] in ["NOTIONAL", "MIN_NOTIONAL"]:
                min_notional = float(f.get("minNotional", 10.0))

        rules = {
            "stepSize": step_size,
            "tickSize": tick_size,
            "minNotional": min_notional,
            "baseAsset": s_info.get("baseAsset"),
            "quoteAsset": s_info.get("quoteAsset")
        }
        self._symbol_filters_cache[symbol] = rules
        return rules

    def format_quantity(self, symbol: str, quantity: float) -> float:
        """Adet miktarını borsa kuralına göre basamaklar."""
        rules = self.get_symbol_rules(symbol)
        step = rules.get("stepSize", 0.0001)
        if step <= 0:
            return quantity
        # Bilimsel gösterimden kaçınmak için 8 basamağa kadar formatla
        step_str = f"{step:.8f}".rstrip("0")
        decimals = len(step_str.split(".")[1]) if "." in step_str else 0
        factor = 10 ** decimals
        return int(quantity * factor) / factor

    def place_market_order(self, symbol: str, side: str, quantity: float) -> Tuple[bool, Dict[str, Any]]:
        """
        Gerçek Borsa Piyasa (MARKET) Alım veya Satım Emri.
        side: BUY veya SELL
        """
        qty_formatted = self.format_quantity(symbol, quantity)
        params = {
            "symbol": symbol.upper(),
            "side": side.upper(),
            "type": "MARKET",
            "quantity": qty_formatted
        }
        ok, res = self._request("POST", "/api/v3/order", params=params, signed=True)
        return ok, res

    def place_oco_order(
        self, 
        symbol: str, 
        side: str, 
        quantity: float, 
        take_profit_price: float, 
        stop_loss_price: float
    ) -> Tuple[bool, Dict[str, Any]]:
        """
        Gerçek Binance OCO (One-Cancels-the-Other) Emri.
        Tek seferde hem Kâr Al (TP) hem de Zarar Durdur (SL) emrini
        Binance'in kendi eşleştirme motoruna yazar.
        """
        qty_formatted = self.format_quantity(symbol, quantity)
        rules = self.get_symbol_rules(symbol)
        tick = rules["tickSize"]
        decimals = len(str(tick).split(".")[1]) if "." in str(tick) else 2
        
        tp_str = f"{take_profit_price:.{decimals}f}"
        sl_str = f"{stop_loss_price:.{decimals}f}"
        
        # Stop-Limit için tetiklenme sonrasındaki limit fiyat (hafif marj ile)
        limit_price = stop_loss_price * 0.995 if side.upper() == "SELL" else stop_loss_price * 1.005
        limit_str = f"{limit_price:.{decimals}f}"

        params = {
            "symbol": symbol.upper(),
            "side": side.upper(),
            "quantity": qty_formatted,
            "price": tp_str,
            "stopPrice": sl_str,
            "stopLimitPrice": limit_str,
            "stopLimitTimeInForce": "GTC"
        }
        ok, res = self._request("POST", "/api/v3/order/oco", params=params, signed=True)
        return ok, res

    def cancel_order(self, symbol: str, order_id: int) -> Tuple[bool, Dict[str, Any]]:
        """Açık emri iptal eder."""
        params = {"symbol": symbol.upper(), "orderId": order_id}
        return self._request("DELETE", "/api/v3/order", params=params, signed=True)
