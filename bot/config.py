import os
from pathlib import Path
from dotenv import load_dotenv

# Base directory
BASE_DIR = Path(__file__).resolve().parent.parent

# Load .env
load_dotenv(BASE_DIR / ".env")

class Config:
    BASE_DIR = BASE_DIR
    DATA_DIR = Path("/tmp/data_storage") if os.getenv("VERCEL") else (BASE_DIR / "data_storage")
    try:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass
    
    # DeepSeek Configuration
    DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "").strip()
    DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-reasoner").strip()
    DEEPSEEK_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com").strip()
    
    # DSH (DeepSeek Harness) Home directory
    DSH_HOME = os.getenv("DSH_HOME", "/tmp/.dsh_home" if os.getenv("VERCEL") else str(BASE_DIR / ".dsh_home")).strip()
    
    # Security / Admin Shield
    ADMIN_PIN = os.getenv("ADMIN_PIN", "1923").strip()

    # Trading Configuration
    TRADING_MODE = os.getenv("TRADING_MODE", "PAPER").upper()
    TRADING_EXCHANGE = os.getenv("TRADING_EXCHANGE", "AUTO").upper() # AUTO, BINANCE, MEXC, OKX
    INITIAL_BALANCE = float(os.getenv("INITIAL_BALANCE", "10000.0"))
    MAX_RISK_PER_TRADE_PERCENT = float(os.getenv("MAX_RISK_PER_TRADE_PERCENT", "5.0"))
    AI_RISK_PROFILE = os.getenv("AI_RISK_PROFILE", "AGGRESSIVE_ALPHA").upper() # AGGRESSIVE_ALPHA, BALANCED, CONSERVATIVE

    # Binance Live Exchange Configuration
    BINANCE_API_KEY = os.getenv("BINANCE_API_KEY", "").strip()
    BINANCE_SECRET_KEY = os.getenv("BINANCE_SECRET_KEY", "").strip()
    BINANCE_TESTNET = os.getenv("BINANCE_TESTNET", "false").lower() in ["true", "1", "yes"]

    # OKX Live Exchange Configuration
    OKX_API_KEY = os.getenv("OKX_API_KEY", "").strip()
    OKX_SECRET_KEY = os.getenv("OKX_SECRET_KEY", "").strip()
    OKX_PASSPHRASE = os.getenv("OKX_PASSPHRASE", "").strip()

    # MEXC Live Exchange Configuration
    MEXC_API_KEY = os.getenv("MEXC_API_KEY", "").strip()
    MEXC_SECRET_KEY = os.getenv("MEXC_SECRET_KEY", "").strip()
    
    # 4 Kritik İstihbarat & Alfa API Yapılandırması
    GROQ_API_KEY = os.getenv("GROQ_API_KEY", "").strip()
    COINGECKO_API_KEY = os.getenv("COINGECKO_API_KEY", "").strip()
    FRED_API_KEY = os.getenv("FRED_API_KEY", "").strip()
    
    # Telegram Configuration
    TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    
    # Kripto Sepet İzleme Listesi
    CRYPTO_SYMBOLS = [
        s.strip().upper() 
        for s in os.getenv("CRYPTO_SYMBOLS", "BTCUSDT,ETHUSDT,SOLUSDT,XRPUSDT,BNBUSDT,DOGEUSDT,SUIUSDT,NEARUSDT,TAOUSDT,ENAUSDT,ARBUSDT,ADAUSDT,LINKUSDT,AVAXUSDT").split(",") 
        if s.strip()
    ]
    
    # Kripto Sepet Sektör Tanımları & Hedef Ağırlıkları
    BASKET_SECTORS = {
        "CORE": {
            "name": "Çekirdek Varlıklar (Core)",
            "target_pct": 35.0,
            "symbols": ["BTCUSDT", "ETHUSDT"]
        },
        "LAYER1": {
            "name": "Katman-1 Blokzincirleri",
            "target_pct": 25.0,
            "symbols": ["SOLUSDT", "SUIUSDT", "BNBUSDT", "AVAXUSDT", "ADAUSDT"]
        },
        "AI_DEPIN": {
            "name": "Yapay Zeka & DePIN",
            "target_pct": 25.0,
            "symbols": ["TAOUSDT", "NEARUSDT", "FETUSDT", "RENDERUSDT"]
        },
        "DEFI_MOMENTUM": {
            "name": "DeFi & Momentum",
            "target_pct": 15.0,
            "symbols": ["UNIUSDT", "LINKUSDT", "ENAUSDT", "ARBUSDT", "DOGEUSDT", "PEPEUSDT"]
        }
    }
    
    # Scheduling & Server
    SCAN_INTERVAL_MINUTES = int(os.getenv("SCAN_INTERVAL_MINUTES", "15"))
    PORT = int(os.getenv("PORT", "8080"))
    HOST = os.getenv("HOST", "127.0.0.1")

config = Config()

def update_env_file(updates: dict):
    """Verilen anahtar-değer çiftlerini .env dosyasına kalıcı olarak yazar."""
    env_path = BASE_DIR / ".env"
    if not env_path.exists():
        return
    try:
        with open(env_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
            
        new_lines = []
        seen = set()
        for line in lines:
            stripped = line.strip()
            if stripped and not stripped.startswith("#") and "=" in stripped:
                k = stripped.split("=")[0].strip()
                if k in updates:
                    new_lines.append(f"{k}={updates[k]}\n")
                    seen.add(k)
                    continue
            new_lines.append(line)
            
        for k, v in updates.items():
            if k not in seen:
                new_lines.append(f"{k}={v}\n")
                
        with open(env_path, "w", encoding="utf-8") as f:
            f.writelines(new_lines)
    except Exception as e:
        print(f"[Config] .env güncellenirken hata: {e}")
