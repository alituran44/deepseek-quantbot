import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional
from ..config import config

class PaperWallet:
    """
    Sanal bakiye (Paper Trading) ve portföy yönetim motoru.
    İşlemleri kalıcı olarak data_storage/portfolio.json dosyasında saklar.
    """
    def __init__(self, storage_file: Optional[Path] = None):
        self.storage_file = storage_file or (config.DATA_DIR / "portfolio.json")
        self.state = self._load_state()

    def _load_state(self) -> Dict[str, Any]:
        """Kayıtlı durumu dosyadan okur veya başlangıç durumunu oluşturur."""
        if not self.storage_file.exists():
            repo_file = config.BASE_DIR / "data_storage" / "portfolio.json"
            if repo_file.exists() and repo_file.resolve() != self.storage_file.resolve():
                try:
                    import shutil
                    self.storage_file.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(repo_file, self.storage_file)
                except Exception as e:
                    print(f"[PaperWallet] Başlangıç portföy dosyası kopyalanamadı: {e}")

        if self.storage_file.exists():
            try:
                with open(self.storage_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                print(f"[PaperWallet] Dosya okuma hatası, sıfırlanıyor: {e}")
                
        initial_state = {
            "initial_balance": config.INITIAL_BALANCE,
            "cash_balance": config.INITIAL_BALANCE,
            "open_positions": [],
            "closed_trades": [],
            "last_updated": datetime.now().isoformat()
        }
        self._save_state(initial_state)
        return initial_state

    def _save_state(self, state: Optional[Dict[str, Any]] = None):
        """Durumu diske yazar."""
        if state is not None:
            self.state = state
        self.state["last_updated"] = datetime.now().isoformat()
        try:
            self.storage_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.storage_file, "w", encoding="utf-8") as f:
                json.dump(self.state, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"[PaperWallet] Durum kaydedilemedi: {e}")

    @property
    def cash_balance(self) -> float:
        return float(self.state.get("cash_balance", config.INITIAL_BALANCE))

    @property
    def open_positions(self) -> List[Dict[str, Any]]:
        return self.state.get("open_positions", [])

    @property
    def closed_trades(self) -> List[Dict[str, Any]]:
        return self.state.get("closed_trades", [])

    def open_position(
        self, 
        symbol: str, 
        action: str, 
        entry_price: float, 
        stop_loss: float, 
        take_profit: float, 
        units: float,
        thesis: str = "",
        exchange: str = "Paper",
        is_live_record: bool = False
    ) -> Dict[str, Any]:
        """Yeni bir pozisyon açar (Sanal veya Canlı Borsa Takip Kaydı)."""
        position_value = units * entry_price
        
        if not is_live_record and position_value > self.cash_balance:
            raise ValueError(f"Yetersiz nakit bakiye: İstenen ${position_value:.2f}, Mevcut ${self.cash_balance:.2f}")

        pos_id = str(uuid.uuid4())[:8]
        position = {
            "id": pos_id,
            "symbol": symbol,
            "exchange": exchange,
            "action": action.upper(),
            "entry_price": entry_price,
            "current_price": entry_price,
            "highest_price": entry_price,
            "lowest_price": entry_price,
            "stop_loss": stop_loss,
            "take_profit": take_profit,
            "units": units,
            "position_value": round(position_value, 2),
            "unrealized_pnl": 0.0,
            "unrealized_pnl_pct": 0.0,
            "open_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "thesis": thesis,
            "is_risk_free": False,
            "is_trailing_active": False,
            "sl_note": ""
        }

        if not is_live_record:
            self.state["cash_balance"] -= position_value
        self.state["open_positions"].append(position)
        self._save_state()
        return position

    def close_position(self, position_id: str, exit_price: float, exit_reason: str = "MANUAL") -> Optional[Dict[str, Any]]:
        """Açık pozisyonu kapatır ve gerçekleşen kâr/zararı hesaba yansıtır."""
        pos = None
        for p in self.state["open_positions"]:
            if p["id"] == position_id:
                pos = p
                break
                
        if not pos:
            return None

        self.state["open_positions"].remove(pos)

        entry_price = pos["entry_price"]
        units = pos["units"]
        action = pos["action"]

        if action == "BUY":
            pnl_usd = (exit_price - entry_price) * units
            pnl_pct = ((exit_price - entry_price) / entry_price) * 100
        else: # SELL / SHORT
            pnl_usd = (entry_price - exit_price) * units
            pnl_pct = ((entry_price - exit_price) / entry_price) * 100

        # Başlangıçta yatırılan pozisyon maliyeti + pnl geri nakite eklenir
        returned_cash = pos["position_value"] + pnl_usd
        self.state["cash_balance"] += returned_cash

        closed_trade = {
            "id": pos["id"],
            "symbol": pos["symbol"],
            "action": pos["action"],
            "entry_price": entry_price,
            "exit_price": exit_price,
            "stop_loss": pos["stop_loss"],
            "take_profit": pos["take_profit"],
            "units": units,
            "pnl_usd": round(pnl_usd, 2),
            "pnl_pct": round(pnl_pct, 2),
            "open_time": pos["open_time"],
            "close_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "exit_reason": exit_reason,
            "thesis": pos.get("thesis", "")
        }

        self.state["closed_trades"].insert(0, closed_trade)
        self._save_state()
        return closed_trade

    def check_and_update_prices(self, price_map: Dict[str, float]) -> List[Dict[str, Any]]:
        """
        Anlık fiyatlara göre pozisyonları günceller, Stop-Loss veya Take-Profit
        seviyesi tetiklenenleri otomatik olarak kapatır.
        """
        closed_events = []
        positions_to_close = []

        for pos in self.state["open_positions"]:
            symbol = pos["symbol"]
            if symbol not in price_map:
                continue

            current_price = price_map[symbol]
            pos["current_price"] = current_price
            entry = pos["entry_price"]
            units = pos["units"]
            action = pos["action"]

            # Anlık PnL
            if action == "BUY":
                # Zirve fiyat takibi
                prev_highest = pos.get("highest_price", entry)
                highest = max(prev_highest, current_price)
                pos["highest_price"] = highest

                unrealized = (current_price - entry) * units
                unrealized_pct = ((current_price - entry) / entry) * 100
                pos["unrealized_pnl"] = round(unrealized, 2)
                pos["unrealized_pnl_pct"] = round(unrealized_pct, 2)

                # 1. AKILLI BAŞABAŞ KİLİDİ: +%4 veya daha fazla kârda stop-loss'u başabaş (+%0.5 komisyon kârı) seviyesine taşı
                if unrealized_pct >= 4.0:
                    breakeven_sl = round(entry * 1.005, 4 if entry < 1 else 2)
                    if pos["stop_loss"] < breakeven_sl:
                        pos["stop_loss"] = breakeven_sl
                        pos["is_risk_free"] = True
                        pos["sl_note"] = "Başabaş Kilitlendi (Breakeven +0.5%)"

                # 2. AKILLI İZ SÜREN STOP (TRAILING STOP): Zirve kazancı +%8 veya üzerine çıktığında stop-loss'u zirvenin %4 altına kilitle
                peak_gain_pct = ((highest - entry) / entry) * 100
                if peak_gain_pct >= 8.0:
                    trailing_sl = round(highest * 0.96, 4 if entry < 1 else 2)
                    if trailing_sl > pos["stop_loss"]:
                        pos["stop_loss"] = trailing_sl
                        pos["is_trailing_active"] = True
                        pos["sl_note"] = f"İz Süren Stop Devrede (Zirve: {highest:.2f} - %4 Trailing: {trailing_sl})"

                # Stop-Loss / Trailing kontrolü
                if current_price <= pos["stop_loss"]:
                    reason = "TRAILING_STOP_HIT" if pos.get("is_trailing_active") else ("BREAKEVEN_STOP_HIT" if pos.get("is_risk_free") else "STOP_LOSS_HIT")
                    positions_to_close.append((pos["id"], current_price, reason))
                # Take-Profit kontrolü
                elif current_price >= pos["take_profit"]:
                    positions_to_close.append((pos["id"], current_price, "TAKE_PROFIT_HIT"))

            elif action == "SELL":
                # Dip fiyat takibi
                prev_lowest = pos.get("lowest_price", entry)
                lowest = min(prev_lowest, current_price)
                pos["lowest_price"] = lowest

                unrealized = (entry - current_price) * units
                unrealized_pct = ((entry - current_price) / entry) * 100
                pos["unrealized_pnl"] = round(unrealized, 2)
                pos["unrealized_pnl_pct"] = round(unrealized_pct, 2)

                # 1. AKILLI BAŞABAŞ KİLİDİ (Short): +%4 düşüşte stop-loss'u başabaş altına çek
                if unrealized_pct >= 4.0:
                    breakeven_sl = round(entry * 0.995, 4 if entry < 1 else 2)
                    if pos["stop_loss"] > breakeven_sl:
                        pos["stop_loss"] = breakeven_sl
                        pos["is_risk_free"] = True
                        pos["sl_note"] = "Başabaş Kilitlendi (Breakeven Short +0.5%)"

                # 2. AKILLI İZ SÜREN STOP (Short): Dip kazancı +%8 veya üzerine çıktığında stop-loss'u dip seviyesinin %4 üzerine kilitle
                peak_drop_pct = ((entry - lowest) / entry) * 100
                if peak_drop_pct >= 8.0:
                    trailing_sl = round(lowest * 1.04, 4 if entry < 1 else 2)
                    if trailing_sl < pos["stop_loss"]:
                        pos["stop_loss"] = trailing_sl
                        pos["is_trailing_active"] = True
                        pos["sl_note"] = f"İz Süren Stop Devrede (Dip: {lowest:.2f} - %4 Trailing: {trailing_sl})"

                if current_price >= pos["stop_loss"]:
                    reason = "TRAILING_STOP_HIT" if pos.get("is_trailing_active") else ("BREAKEVEN_STOP_HIT" if pos.get("is_risk_free") else "STOP_LOSS_HIT")
                    positions_to_close.append((pos["id"], current_price, reason))
                elif current_price <= pos["take_profit"]:
                    positions_to_close.append((pos["id"], current_price, "TAKE_PROFIT_HIT"))

        # SL / TP tetiklenenleri kapat
        for pos_id, exit_px, reason in positions_to_close:
            trade = self.close_position(pos_id, exit_px, reason)
            if trade:
                closed_events.append(trade)

        self._save_state()
        return closed_events

    _last_live_price_time: float = 0.0

    def update_live_prices(self):
        """Binance üzerinden açık pozisyonların anlık fiyatlarını çeker ve PnL'leri günceller."""
        open_pos = self.open_positions
        if not open_pos:
            return

        import time
        now = time.time()
        if now - getattr(self, "_last_live_price_time", 0.0) < 4.0:
            return

        symbols = list({p["symbol"] for p in open_pos if "symbol" in p})
        if not symbols:
            return

        try:
            import json, urllib.parse, requests
            encoded = urllib.parse.quote(json.dumps(symbols).replace(" ", ""))
            for base in ["https://data-api.binance.vision/api/v3", "https://api.binance.com/api/v3"]:
                try:
                    url = f"{base}/ticker/price?symbols={encoded}"
                    resp = requests.get(url, timeout=3.5)
                    if resp.status_code == 200:
                        data = resp.json()
                        price_map = {item["symbol"]: float(item["price"]) for item in data}
                        if price_map:
                            self.check_and_update_prices(price_map)
                            self._last_live_price_time = now
                            break
                except Exception:
                    continue
        except Exception:
            pass

    def get_portfolio_summary(self, auto_update: bool = True) -> Dict[str, Any]:
        """Portföy istatistiklerini ve metriklerini hesaplar."""
        if auto_update and self.open_positions:
            self.update_live_prices()

        cash = self.cash_balance
        open_positions = self.open_positions
        closed_trades = self.closed_trades

        unrealized_pnl = sum(p.get("unrealized_pnl", 0.0) for p in open_positions)
        positions_value = sum(p.get("position_value", 0.0) + p.get("unrealized_pnl", 0.0) for p in open_positions)
        total_equity = cash + positions_value

        initial = float(self.state.get("initial_balance", config.INITIAL_BALANCE))
        total_pnl = total_equity - initial
        total_pnl_pct = ((total_equity - initial) / initial) * 100 if initial > 0 else 0.0

        total_trades = len(closed_trades)
        winning_trades = [t for t in closed_trades if t.get("pnl_usd", 0) > 0]
        win_rate = (len(winning_trades) / total_trades * 100) if total_trades > 0 else 0.0

        gross_profit = sum(t.get("pnl_usd", 0) for t in winning_trades)
        gross_loss = abs(sum(t.get("pnl_usd", 0) for t in closed_trades if t.get("pnl_usd", 0) < 0))
        profit_factor = round(gross_profit / gross_loss, 2) if gross_loss > 0 else (99.0 if gross_profit > 0 else 0.0)

        return {
            "total_equity": round(total_equity, 2),
            "cash_balance": round(cash, 2),
            "positions_value": round(positions_value, 2),
            "unrealized_pnl": round(unrealized_pnl, 2),
            "total_realized_pnl": round(sum(t.get("pnl_usd", 0) for t in closed_trades), 2),
            "total_pnl": round(total_pnl, 2),
            "total_pnl_pct": round(total_pnl_pct, 2),
            "total_trades": total_trades,
            "win_rate": round(win_rate, 1),
            "profit_factor": profit_factor,
            "open_positions": open_positions,
            "recent_closed_trades": closed_trades[:15]
        }
