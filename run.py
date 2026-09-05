"""
DeepSeek-QuantBot Ana Çalıştırma Betiği
"""
import sys
import uvicorn
import argparse
from bot.config import config

BANNER = r"""
================================================================================
  ____                 ____            _        ___                  _   ____        _   
 |  _ \  ___  ___ _ __/ ___|  ___  ___| | __   / _ \ _   _  __ _ _ _| |_| __ )  ___ | |_ 
 | | | |/ _ \/ _ \ '_ \___ \ / _ \/ _ \ |/ /  | | | | | | |/ _` | '_| __|  _ \ / _ \| __|
 | |_| |  __/  __/ |_) |__) |  __/  __/   <   | |_| | |_| | (_| | | | |_| |_) | (_) | |_ 
 |____/ \___|\___| .__/____/ \___|\___|_|\_\   \__\_\\__,_|\__,_|_|  \__|____/ \___/ \__|
                 |_|                                                                     
                  DeepSeek Harness Destekli Finansal Analiz & Paper Trading
================================================================================
"""

def main():
    parser = argparse.ArgumentParser(description="DeepSeek-QuantBot Dashboard & Trading Server")
    parser.add_argument("--host", default=config.HOST, help="Sunucu dinleme adresi (Varsayılan: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=config.PORT, help="Sunucu portu (Varsayılan: 8000)")
    parser.add_argument("--reload", action="store_true", help="Geliştirme modu (Auto-reload)")
    args = parser.parse_args()

    print(BANNER)
    print(f"[*] Çatı: DeepSeek Harness & Python SDK")
    print(f"[*] Mod: {config.TRADING_MODE} (Sanal Kasa Başlangıç: ${config.INITIAL_BALANCE:,.2f})")
    print(f"[*] DeepSeek Model: {config.DEEPSEEK_MODEL}")
    print(f"[*] API Anahtarı: {'Tanımlı' if config.DEEPSEEK_API_KEY else 'Tanımlı Değil (Deterministik Algoritmik Motor Devrede)'}")
    print(f"[*] Telegram Bildirimi: {'Aktif' if config.TELEGRAM_BOT_TOKEN and config.TELEGRAM_CHAT_ID else 'Devre Dışı'}")
    print(f"[*] Kripto Sepet Kapsamı: {', '.join(config.CRYPTO_SYMBOLS)}")
    print(f"[*] Sepet Sektörleri: {', '.join(s['name'] for s in config.BASKET_SECTORS.values())}")
    print(f"[*] Web Kontrol Paneli: http://{args.host}:{args.port}")
    print("=" * 80)

    uvicorn.run(
        "web.app:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        log_level="info"
    )

if __name__ == "__main__":
    main()
