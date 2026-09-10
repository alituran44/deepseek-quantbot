import time
import hmac
import hashlib
import requests
import urllib.parse
from decimal import Decimal
from typing import Dict, Any, List, Optional, Tuple
from .base import BaseExchange
from ...config import config

class BinanceTRLiveExecutor(BaseExchange):
    """
    Binance TR (trbinance.com) Resmi REST API Entegratoru.
    HMAC-SHA256 imzali Open API v1 protokolu uzerinden
    Turk Lirasi (TRY) ve USDT bakiyelerini okur, anlik portfoy hesaplar
    ve piyasa/limit alim-satim emirlerini iletir.
    """

    BASE_URL = "https://www.trbinance.com"

    def __init__(self, api_key: Optional[str] = None, secret_key: Optional[str] = None):
        self.api_key = (api_key or getattr(config, "BINANCE_TR_API_KEY", "")).strip()
        self.secret_key = (secret_key or getattr(config, "BINANCE_TR_SECRET_KEY", "")).strip()

    @property
    def exchange_id(self) -> str:
        return "BINANCE_TR"

    @property
    def is_configured(self) -> bool:
        return bool(self.api_key and self.secret_key)

    @property
    def configured(self) -> bool:
        return self.is_configured

    @property
    def enabled(self) -> bool:
        return self.is_configured

    def _sign(self, params: Dict[str, Any]) -> str:
        """HMAC-SHA256 ile imza uretir."""
        query_string = urllib.parse.urlencode(params)
        signature = hmac.new(
            self.secret_key.encode("utf-8"),
            query_string.encode("utf-8"),
            hashlib.sha256
        ).hexdigest()
        return signature

    def get_account_balances(self) -> Dict[str, Any]:
        """Binance TR Spot cuzdandaki tum serbest ve kilitli varliklari ceker."""
        if not self.enabled:
            return {"success": False, "msg": "Binance TR API anahtarlari tanimli degil.", "assets": {}}

        endpoint = "/open/v1/account/spot"
        params = {"timestamp": int(time.time() * 1000)}
        query_string = urllib.parse.urlencode(params)
        sig = self._sign(params)
        url = f"{self.BASE_URL}{endpoint}?{query_string}&signature={sig}"
        headers = {"X-MBX-APIKEY": self.api_key}

        try:
            resp = requests.get(url, headers=headers, timeout=8)
            if resp.status_code != 200:
                return {"success": False, "msg": f"HTTP {resp.status_code}: {resp.text}", "assets": {}}

            data = resp.json()
            if data.get("code") != 0:
                return {"success": False, "msg": data.get("msg", "Bilinmeyen hata"), "assets": {}}

            account_data = data.get("data", {})
            raw_assets = account_data.get("accountAssets", [])
            
            assets: Dict[str, Dict[str, float]] = {}
            free_usdt = 0.0
            free_try = 0.0

            for item in raw_assets:
                asset_name = item.get("asset", "").upper()
                free_amt = float(item.get("free", 0.0) or 0.0)
                locked_amt = float(item.get("locked", 0.0) or 0.0)
                total_amt = free_amt + locked_amt

                if total_amt > 0:
                    assets[asset_name] = {
                        "free": free_amt,
                        "locked": locked_amt,
                        "total": total_amt
                    }
                    if asset_name == "USDT":
                        free_usdt = free_amt
                    elif asset_name == "TRY":
                        free_try = free_amt

            return {
                "success": True,
                "free_usdt": free_usdt,
                "free_try": free_try,
                "assets": assets,
                "can_trade": bool(account_data.get("canTrade", 1))
            }
        except Exception as e:
            return {"success": False, "msg": f"Binance TR baglanti hatasi: {e}", "assets": {}}

    def get_real_portfolio_summary(self, usd_try_rate: float = 48.34) -> Dict[str, Any]:
        """
        Binance TR hesabindaki toplam portfoy degerini USD ve TRY cinsinden hesaplar.
        """
        if not self.enabled:
            return {
                "total_value_usd": 0.0,
                "total_value_try": 0.0,
                "cash_balance": 0.0,
                "free_usdt": 0.0,
                "free_try": 0.0,
                "unrealized_pnl": 0.0,
                "unrealized_pnl_pct": 0.0,
                "open_positions": [],
                "is_live": True,
                "exchange": "Binance TR",
                "configured": False,
                "live_assets": []
            }

        bal_info = self.get_account_balances()
        if not bal_info.get("success"):
            return {
                "total_value_usd": 0.0,
                "total_value_try": 0.0,
                "cash_balance": 0.0,
                "free_usdt": 0.0,
                "free_try": 0.0,
                "unrealized_pnl": 0.0,
                "unrealized_pnl_pct": 0.0,
                "open_positions": [],
                "is_live": True,
                "exchange": "Binance TR",
                "configured": True,
                "error": bal_info.get("msg"),
                "live_assets": []
            }

        assets = bal_info.get("assets", {})
        free_usdt = bal_info.get("free_usdt", 0.0)
        free_try = bal_info.get("free_try", 0.0)

        rate = usd_try_rate if usd_try_rate > 0 else 48.34

        total_value_usd = 0.0
        live_assets = []

        for asset, data in assets.items():
            tot = data.get("total", 0.0)
            if tot <= 0:
                continue

            current_px = 0.0
            if asset == "USDT":
                current_px = 1.0
                val_usd = tot
            elif asset == "TRY":
                current_px = round(1.0 / rate, 4)
                val_usd = tot / rate
            else:
                try:
                    px_resp = requests.get(f"https://data-api.binance.vision/api/v3/ticker/price?symbol={asset}USDT", timeout=3)
                    if px_resp.status_code == 200:
                        current_px = float(px_resp.json().get("price", 0.0))
                        val_usd = tot * current_px
                    else:
                        val_usd = 0.0
                except Exception:
                    val_usd = 0.0

            total_value_usd += val_usd

            live_assets.append({
                "asset": asset,
                "free": data.get("free", 0.0),
                "locked": data.get("locked", 0.0),
                "units": tot,
                "current_price": current_px,
                "value_usd": round(val_usd, 2),
                "value_try": round(val_usd * rate, 2),
                "exchange": "Binance TR"
            })

        total_value_try = total_value_usd * rate

        return {
            "total_value_usd": round(total_value_usd, 2),
            "total_value_try": round(total_value_try, 2),
            "cash_balance": round(total_value_usd, 2),
            "free_usdt": round(free_usdt, 2),
            "free_try": round(free_try, 2),
            "unrealized_pnl": 0.0,
            "unrealized_pnl_pct": 0.0,
            "open_positions": [],
            "is_live": True,
            "exchange": "Binance TR",
            "configured": True,
            "live_assets": live_assets
        }

    _step_size_cache: Dict[str, str] = {}

    def get_step_size(self, symbol: str) -> str:
        clean_sym = symbol.strip().upper()
        if clean_sym in self._step_size_cache:
            return self._step_size_cache[clean_sym]

        try:
            resp = requests.get(f"{self.BASE_URL}/open/v1/common/symbols", timeout=4)
            if resp.status_code == 200:
                data = resp.json().get("data", {}).get("list", [])
                for item in data:
                    s_name = item.get("symbol", "")
                    for f in item.get("filters", []):
                        if f.get("filterType") == "LOT_SIZE":
                            self._step_size_cache[s_name] = str(f.get("stepSize", "0.001"))
        except Exception:
            pass

        if clean_sym in self._step_size_cache:
            return self._step_size_cache[clean_sym]

        defaults = {
            "BTC_TRY": "0.00001",
            "ETH_TRY": "0.0001",
            "BNB_TRY": "0.001",
            "SOL_TRY": "0.001",
            "AVAX_TRY": "0.01",
            "XRP_TRY": "0.1",
            "DOGE_TRY": "1",
            "USDT_TRY": "1",
            "PEPE_TRY": "1",
        }
        return defaults.get(clean_sym, "0.001")

    def format_quantity(self, symbol: str, quantity: float) -> Tuple[float, str]:
        step_str = self.get_step_size(symbol)
        try:
            d_step = Decimal(step_str).normalize()
            exponent = d_step.as_tuple().exponent
            precision = max(0, -exponent) if exponent < 0 else 0

            d_qty = Decimal(str(quantity))
            stepped = (d_qty // Decimal(step_str)) * Decimal(step_str)
            fmt = f"{stepped:.{precision}f}"
            return float(fmt), fmt
        except Exception:
            val = round(quantity, 3)
            return val, str(val)

    def place_market_order(
        self, 
        symbol: str, 
        side: str, 
        quantity: Optional[float] = None, 
        quote_order_qty: Optional[float] = None
    ) -> Tuple[bool, Dict[str, Any]]:
        """
        Binance TR uzerinde anlik piyasa fiyatindan emir iletir.
        side: "BUY" (0) veya "SELL" (1)
        type: 2 (MARKET)
        quantity: Base varlik miktari (orn: XRP)
        quote_order_qty: Quote varlik tutari (orn: TRY ile dogrudan alim)
        """
        if not self.enabled:
            return False, {"error": "Binance TR API anahtarlari tanimli degil."}

        clean_sym = symbol.strip().upper()
        if "_" not in clean_sym:
            if clean_sym.endswith("USDT"):
                clean_sym = clean_sym.replace("USDT", "_TRY")
            elif clean_sym.endswith("TRY"):
                clean_sym = clean_sym.replace("TRY", "_TRY")
            else:
                clean_sym = f"{clean_sym}_TRY"

        numeric_side = 0 if side.upper() == "BUY" else 1

        params: Dict[str, Any] = {
            "symbol": clean_sym,
            "side": numeric_side,
            "type": 2,
            "timestamp": int(time.time() * 1000)
        }

        # BUY isleminde dogrudan TRY tutari (quoteOrderQty) ile alim onceliklidir
        if numeric_side == 0 and quote_order_qty is not None and float(quote_order_qty) > 0:
            params["quoteOrderQty"] = f"{float(quote_order_qty):.2f}"
        else:
            if quantity is None or float(quantity) <= 0:
                return False, {"error": f"Gecersiz islem miktari: {quantity}"}
            formatted_float, formatted_str = self.format_quantity(clean_sym, float(quantity))
            if formatted_float <= 0:
                return False, {"error": f"Gecersiz islem miktari: {quantity} -> {formatted_str}"}
            params["quantity"] = formatted_str

        query_string = urllib.parse.urlencode(params)
        sig = self._sign(params)
        url = f"{self.BASE_URL}/open/v1/orders"
        headers = {
            "X-MBX-APIKEY": self.api_key,
            "Content-Type": "application/x-www-form-urlencoded"
        }

        try:
            resp = requests.post(url, data=f"{query_string}&signature={sig}", headers=headers, timeout=8)
            res_data = resp.json()
            if resp.status_code == 200 and res_data.get("code") == 0:
                return True, res_data.get("data", {})
            err_msg = res_data.get("msg", "Emir iletilemedi")
            if "Insufficient balance" in err_msg or res_data.get("code") in [-2010, 2010]:
                err_msg = "Binance TR hesabınızda yetersiz serbest bakiye! Cüzdanınızdaki serbest TL veya coin miktarını aşan tutarda işlem yapılamaz."
            return False, {"error": err_msg, "code": res_data.get("code")}
        except Exception as e:
            return False, {"error": f"Binance TR emir hatasi: {e}"}

    def place_oco_order(self, symbol: str, side: str, quantity: float, take_profit_price: float, stop_loss_price: float) -> Tuple[bool, Dict[str, Any]]:
        return False, {"error": "Binance TR OCO emri su anda dogrudan piyasa emirleri ile yonetilmektedir."}

    def get_deposit_addresses(self) -> List[Dict[str, Any]]:
        return [
            {
                "coin": "TRY",
                "network": "Banka Havale / EFT / FAST",
                "address": "Ziraat Bankasi, Vakifbank, Fibabanka, Akbank, Is Bankasi ile 7/24 Aninda Masrafsiz TL Yatirma",
                "tag": "TR Binance Hesabim -> Yatirma -> TRY"
            },
            {
                "coin": "USDT",
                "network": "TRC20 / BEP20",
                "address": "trbinance.com uzerinden cuzdan adresinize erisebilirsiniz",
                "tag": "Binance TR -> Kripto Yatir"
            }
        ]
