import requests
from typing import Dict, Any, Optional
from ..config import config

class TelegramNotifier:
    """
    Telegram Bot API bildirim servisi.
    Token veya Chat ID tanımlı değilse zarifçe atlar ve konsola yazar.
    """
    def __init__(self):
        self.token = config.TELEGRAM_BOT_TOKEN
        self.chat_id = config.TELEGRAM_CHAT_ID
        self.enabled = bool(self.token and self.chat_id)

    def send_message(self, text: str) -> bool:
        """Telegram'a doğrudan metin mesajı gönderir."""
        if not self.enabled:
            # Token yoksa sadece konsola düş
            return False
            
        url = f"https://api.telegram.org/bot{self.token}/sendMessage"
        payload = {
            "chat_id": self.chat_id,
            "text": text,
            "parse_mode": "Markdown",
            "disable_web_page_preview": True
        }
        try:
            resp = requests.post(url, json=payload, timeout=8)
            return resp.status_code == 200
        except Exception as e:
            print(f"[TelegramNotifier] Gönderim hatası: {e}")
            return False

    def notify_signal(self, symbol: str, signal: Dict[str, Any], order_params: Optional[Dict[str, Any]] = None):
        """Yeni bir alım-satım tezi ve sinyali üretildiğinde bildirim atar."""
        action = signal.get("action", "HOLD")
        confidence = signal.get("confidence", 0.0) * 100
        thesis = signal.get("thesis_summary", "")
        entry = signal.get("entry_price", 0)
        sl = signal.get("stop_loss", 0)
        tp = signal.get("take_profit", 0)
        rr = signal.get("risk_reward_ratio", "N/A")
        source = signal.get("source", "DEEPSEEK_AI")

        if action == "HOLD":
            return

        icon = "🟢" if action == "BUY" else "🔴"
        action_tr = "ALIM SİNYALİ" if action == "BUY" else "SATIŞ SİNYALİ"

        msg = (
            f"{icon} *DEEPSEEK QUANT BOT: {action_tr}*\n\n"
            f"🎯 *Varlık:* `{symbol}`\n"
            f"⚡ *İşlem:* `{action}` | *Güven:* `%{confidence:.0f}`\n"
            f"📍 *Giriş Seviyesi:* `${entry:,.2f}`\n"
            f"🛡 *Stop-Loss (Zarar Durdur):* `${sl:,.2f}`\n"
            f"🎯 *Take-Profit (Hedef):* `${tp:,.2f}`\n"
            f"⚖️ *Risk/Ödül Oranı:* `{rr}`\n\n"
        )

        if order_params:
            pos_val = order_params.get("position_value_usd", 0)
            risk_val = order_params.get("risk_amount_usd", 0)
            msg += (
                f"💼 *Sanal Kasa Simülasyonu:*\n"
                f"• Pozisyon Büyüklüğü: `${pos_val:,.2f}`\n"
                f"• Riske Edilen Miktar: `${risk_val:,.2f}`\n\n"
            )

        msg += f"🧠 *DeepSeek Strateji Tezi:*\n_{thesis}_\n\n"
        msg += f"🤖 *Motor:* `{source}`"

        self.send_message(msg)

    def notify_trade_closed(self, trade: Dict[str, Any]):
        """Açık pozisyon kapandığında (SL veya TP tetiklendiğinde) bildirim atar."""
        symbol = trade.get("symbol")
        action = trade.get("action")
        pnl = trade.get("pnl_usd", 0)
        pnl_pct = trade.get("pnl_pct", 0)
        reason = trade.get("exit_reason", "")
        exit_px = trade.get("exit_price", 0)

        is_profit = pnl >= 0
        icon = "🎉" if is_profit else "⚠️"
        status_tr = "KÂR ALINDI (TP)" if "TAKE_PROFIT" in reason else ("STOP OLDU (SL)" if "STOP_LOSS" in reason else "KAPATILDI")

        msg = (
            f"{icon} *POZİSYON KAPANDI: {symbol}*\n\n"
            f"📌 *Durum:* `{status_tr}`\n"
            f"📊 *İşlem Yönü:* `{action}`\n"
            f"💵 *Çıkış Fiyatı:* `${exit_px:,.2f}`\n"
            f"📈 *Net Kâr / Zarar:* `${pnl:,.2f}` (`%{pnl_pct:+.2f}`)\n"
        )
        self.send_message(msg)
