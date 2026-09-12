import os
import hmac
import hashlib
from pathlib import Path
from fastapi import FastAPI, Request, BackgroundTasks
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from typing import Optional, Dict, Any

from bot.config import config, update_env_file
from bot.orchestrator import orchestrator

app = FastAPI(title="DeepSeek-QuantBot Dashboard", version="1.0.0")

WEB_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(WEB_DIR / "templates"))

# Statik dosyaları bağla
app.mount("/static", StaticFiles(directory=str(WEB_DIR / "static")), name="static")

def get_expected_token() -> str:
    """HMAC-SHA256 ile ADMIN_PIN tabanlı güvenli oturum tokeni üretir."""
    pin = getattr(config, "ADMIN_PIN", "1923").strip()
    return hmac.new(pin.encode("utf-8"), b"quant_shield_session_v1", hashlib.sha256).hexdigest()

def is_request_authenticated(request: Request) -> bool:
    """İsteğin geçerli bir oturum tokeni (Header veya Cookie) taşıyıp taşımadığını doğrular."""
    pin = getattr(config, "ADMIN_PIN", "1923").strip()
    if not pin:
        return True

    expected = get_expected_token()

    # 1. Authorization: Bearer <token>
    auth_hdr = request.headers.get("Authorization", "")
    if auth_hdr.startswith("Bearer "):
        token = auth_hdr[7:].strip()
        if hmac.compare_digest(token, expected):
            return True

    # 2. X-Admin-Token header
    x_token = request.headers.get("X-Admin-Token", "").strip()
    if x_token and hmac.compare_digest(x_token, expected):
        return True

    # 3. quant_admin_token cookie
    cookie_token = request.cookies.get("quant_admin_token", "").strip()
    if cookie_token and hmac.compare_digest(cookie_token, expected):
        return True

    return False

@app.middleware("http")
async def security_and_cache_middleware(request: Request, call_next):
    """Yetkilendirme kalkanı ve önbellek kontrol middleware'i."""
    path = request.url.path

    # Herkese açık rotalar
    is_public = (
        path == "/" or
        path.startswith("/static") or
        path.startswith("/api/auth") or
        path == "/favicon.ico"
    )

    # Vercel Cron için /api/scan istisnası
    if path == "/api/scan" and (request.headers.get("x-vercel-cron") or request.headers.get("X-Vercel-Cron")):
        is_public = True

    if not is_public and path.startswith("/api"):
        if not is_request_authenticated(request):
            return JSONResponse(
                status_code=401,
                content={"status": "UNAUTHORIZED", "message": "Yetkisiz erişim. Lütfen PIN kodunuzu girin."}
            )

    response = await call_next(request)
    if path.startswith("/static") or path == "/":
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    return response

class AuthLoginRequest(BaseModel):
    pin: str

class ScanRequest(BaseModel):
    symbol: Optional[str] = None

class CloseTradeRequest(BaseModel):
    position_id: str
    exit_price: float

class ManualOrderRequest(BaseModel):
    symbol: str
    action: str  # BUY veya SELL
    amount_usd: Optional[float] = 0.0
    amount_try: Optional[float] = None
    currency: Optional[str] = "USD"
    exchange: Optional[str] = "AUTO"
    mode: Optional[str] = None  # LIVE veya PAPER

class SetEntryPriceRequest(BaseModel):
    symbol: str
    entry_price: float
    currency: Optional[str] = "TRY"

class SingleCoinAnalysisRequest(BaseModel):
    symbol: str

class ConfigUpdateRequest(BaseModel):
    deepseek_api_key: Optional[str] = None
    deepseek_model: Optional[str] = None
    trading_mode: Optional[str] = None
    trading_exchange: Optional[str] = None
    ai_risk_profile: Optional[str] = None
    admin_pin: Optional[str] = None
    telegram_token: Optional[str] = None
    telegram_chat_id: Optional[str] = None
    binance_api_key: Optional[str] = None
    binance_secret_key: Optional[str] = None
    binance_tr_api_key: Optional[str] = None
    binance_tr_secret_key: Optional[str] = None
    okx_api_key: Optional[str] = None
    okx_secret_key: Optional[str] = None
    okx_passphrase: Optional[str] = None
    mexc_api_key: Optional[str] = None
    mexc_secret_key: Optional[str] = None
    groq_api_key: Optional[str] = None
    coingecko_api_key: Optional[str] = None
    fred_api_key: Optional[str] = None
    max_risk_per_trade_percent: Optional[float] = None

@app.on_event("startup")
async def startup_event():
    """Uygulama açılışında arka plan tarayıcısını tetikler (Serverless harici ortamlarda)."""
    if not os.getenv("VERCEL"):
        orchestrator.start_background_scanner()

@app.on_event("shutdown")
def shutdown_event():
    """Uygulama kapanışında tarayıcıyı nazikçe durdurur."""
    if not os.getenv("VERCEL"):
        orchestrator.stop_background_scanner()

@app.post("/api/auth/login")
async def auth_login(req: AuthLoginRequest):
    """Kullanıcının girdiği 4 haneli PIN kodunu doğrular ve güvenli oturum tokeni döner."""
    pin = (req.pin or "").strip()
    expected_pin = getattr(config, "ADMIN_PIN", "1923").strip()
    
    if not expected_pin or pin == expected_pin:
        token = get_expected_token()
        resp = JSONResponse(content={"status": "SUCCESS", "message": "Oturum başarıyla açıldı.", "token": token})
        resp.set_cookie(
            key="quant_admin_token",
            value=token,
            max_age=7 * 24 * 3600,
            httponly=False,
            samesite="lax",
            path="/"
        )
        return resp
    return JSONResponse(status_code=401, content={"status": "ERROR", "message": "Hatalı PIN kodu! Lütfen tekrar deneyin."})

@app.get("/api/auth/check")
def auth_check(request: Request):
    """Mevcut oturumun geçerli olup olmadığını kontrol eder."""
    return JSONResponse(content={"authenticated": is_request_authenticated(request)})

@app.post("/api/auth/logout")
def auth_logout():
    """Oturumu sonlandırır ve kilit ekranına döndürür."""
    resp = JSONResponse(content={"status": "SUCCESS", "message": "Oturum kilitlendi."})
    resp.delete_cookie(key="quant_admin_token", path="/")
    return resp

@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    """Ana Dashboard Sayfası."""
    is_auth = is_request_authenticated(request)
    req_mode = request.query_params.get("mode") or request.cookies.get("deepseek_trading_mode") or config.TRADING_MODE or "LIVE"
    if is_auth:
        state = orchestrator.get_dashboard_state(mode=req_mode)
        state["is_locked"] = False
    else:
        # Kilitliyken hassas portföy ve bakiye bilgilerini HTML içine gömme
        state = {
            "is_locked": True,
            "last_scan_time": "",
            "trading_mode": req_mode,
            "trading_exchange": getattr(config, "TRADING_EXCHANGE", "AUTO"),
            "ai_risk_profile": getattr(config, "AI_RISK_PROFILE", "SMART_AGGRESSIVE"),
            "wallet": {"total_equity": 0.0, "cash_balance": 0.0, "open_positions": [], "is_live": False},
            "master_treasury": {"total_usd": 0.0, "cash_usd": 0.0, "binance": {}, "binance_tr": {}, "okx": {}, "mexc": {}},
            "watchlist": [],
            "radar_watchlist": []
        }
    return templates.TemplateResponse(request=request, name="index.html", context={"state": state, "is_authenticated": is_auth})

@app.get("/api/state")
def get_state(mode: Optional[str] = None):
    """Dashboard verisini anlık JSON olarak döndürür."""
    return JSONResponse(content=orchestrator.get_dashboard_state(mode=mode))

@app.api_route("/api/scan", methods=["GET", "POST"])
async def trigger_scan(request: Request, bg_tasks: BackgroundTasks):
    """Manuel veya Vercel Cron otomatik piyasa taraması tetikler."""
    symbol = None
    if request.method == "POST":
        try:
            body = await request.json()
            symbol = body.get("symbol")
        except Exception:
            pass

    if symbol:
        res = orchestrator.scan_asset(symbol)
        return JSONResponse(content=res)
    else:
        if os.getenv("VERCEL"):
            res = orchestrator.run_quick_scan()
            return JSONResponse(content=res)
        else:
            bg_tasks.add_task(orchestrator.run_full_scan)
            return JSONResponse(content={"status": "STARTED", "message": "Piyasa taraması arka planda başlatıldı."})

@app.post("/api/trade/close")
async def close_trade(req: CloseTradeRequest):
    """Açık bir pozisyonu manuel olarak kapatır."""
    res = orchestrator.wallet.close_position(req.position_id, req.exit_price, exit_reason="MANUAL_CLOSE")
    if res:
        orchestrator.notifier.notify_trade_closed(res)
        return JSONResponse(content={"status": "SUCCESS", "trade": res})
    return JSONResponse(status_code=404, content={"status": "ERROR", "message": "Pozisyon bulunamadı."})

@app.post("/api/trade/order")
async def execute_manual_order(req: ManualOrderRequest):
    """Kullanıcının kart detay penceresinden tek tıkla canlı veya sanal alım-satım yapmasını sağlar."""
    sym = req.symbol.strip().upper()
    action = req.action.strip().upper()
    req_exchange = (req.exchange or "AUTO").strip().upper()
    order_mode = (req.mode or config.TRADING_MODE or "PAPER").strip().upper()
    if order_mode not in ["LIVE", "PAPER"]:
        order_mode = config.TRADING_MODE or "PAPER"

    usd_try_rate = orchestrator.get_usd_try_rate() or 48.40
    currency = (req.currency or "USD").strip().upper()

    # Binance TR seçildiğinde veya TRY para birimi belirtildiğinde
    if req_exchange == "BINANCE_TR":
        if currency == "TRY" or (req.amount_try is not None and req.amount_try > 0) or (req.amount_usd and req.amount_usd > 100):
            currency = "TRY"

    if currency == "TRY":
        amt_try = float(req.amount_try if (req.amount_try is not None and req.amount_try > 0) else (req.amount_usd or 0.0))
        amt_usd = amt_try / usd_try_rate
    else:
        amt_usd = float(req.amount_usd or 0.0)
        amt_try = amt_usd * usd_try_rate

    ticker = orchestrator.crypto_feed.get_ticker_24h(sym)
    px = ticker.get("price", 0.0)
    if px <= 0:
        return JSONResponse(status_code=400, content={"status": "ERROR", "message": f"{sym} için güncel fiyat alınamadı."})
        
    units = amt_usd / px if px > 0 else 0.0
    clean_sym = sym.replace("USDT", "").replace("TRY", "").replace("_", "")

    if order_mode == "LIVE":
        # 1. Borsa API ve Doğrulama Kontrolleri (Çoklu Borsa & Binance TR)
        executor, ex_id, free_usdt, sel_msg = orchestrator.select_execution_exchange(
            symbol=sym, 
            required_amount_usd=amt_usd if action == "BUY" else 0.0, 
            preferred_exchange=req_exchange
        )
        if not executor:
            return JSONResponse(status_code=400, content={"status": "ERROR", "message": sel_msg})

        if action == "BUY":
            if ex_id == "BINANCE_TR" or currency == "TRY":
                b_bal = executor.get_account_balances()
                free_try = float(b_bal.get("free_try", 0.0))
                if free_try < 10.0:
                    return JSONResponse(status_code=400, content={
                        "status": "ERROR", 
                        "message": f"❌ Binance TR Serbest TL Bakiyesi Yetersiz! Cüzdanınızda serbest ₺{free_try:.2f} TL bulunuyor. Binance TR minimum işlem tutarı ₺10 TL'dir. Lütfen hesabınıza TL yatırın veya mevcut varlıklarınızdan satış yapın."
                    })
                if amt_try > free_try:
                    return JSONResponse(status_code=400, content={
                        "status": "ERROR", 
                        "message": f"❌ Binance TR Serbest TL Bakiyesi Yetersiz! Cüzdanınızda serbest ₺{free_try:.2f} TL bulunuyor, ancak istenen alım tutarı ₺{amt_try:.2f} TL. Lütfen tutarı ₺{free_try:.2f} TL veya altına çekin."
                    })
                if amt_try < 10.0:
                    return JSONResponse(status_code=400, content={"status": "ERROR", "message": "Binance TR minimum işlem tutarı ₺10 TL olmalıdır."})
            else:
                if amt_usd < 1.0:
                    return JSONResponse(status_code=400, content={"status": "ERROR", "message": "Minimum işlem tutarı $1.00 USD olmalıdır."})
        elif action == "SELL":
            b_bal = executor.get_account_balances()
            assets = b_bal.get("assets", {})
            coin_info = assets.get(clean_sym, {})
            free_coin = float(coin_info.get("free", 0.0))
            if free_coin <= 0:
                return JSONResponse(status_code=400, content={
                    "status": "ERROR", 
                    "message": f"❌ {ex_id} cüzdanınızda satılabilir {clean_sym} bulunmuyor (Mevcut Bakiye: 0.00 {clean_sym})."
                })
            px_in_try = px if (px > 50 and not sym.startswith("USDT")) else (px * usd_try_rate)
            coin_total_val_try = free_coin * px_in_try
            if amt_try >= (coin_total_val_try * 0.95):
                units = free_coin
            else:
                calc_units = amt_try / px_in_try if px_in_try > 0 else free_coin
                units = min(calc_units, free_coin)

        # Canlı Emri Gerçekleştir
        if ex_id == "BINANCE_TR" and action == "BUY":
            b_bal = executor.get_account_balances()
            free_try = float(b_bal.get("free_try", 0.0))
            if amt_try >= (free_try * 0.98):
                quote_qty = round(free_try * 0.985, 2)
            else:
                quote_qty = round(amt_try, 2)
        else:
            quote_qty = None

        ok, res, used_ex = orchestrator.execute_live_order(
            symbol=sym,
            action=action,
            units=units,
            entry_price=px,
            stop_loss=px * 0.95,
            take_profit=px * 1.10,
            preferred_exchange=req_exchange,
            thesis=f"[KULLANICI MANUEL CANLI EMİR - {req_exchange} - {currency}]",
            quote_order_qty=quote_qty
        )
        if ok:
            action_tr = "Alım" if action == "BUY" else "Satım"
            if used_ex == "BINANCE_TR" or currency == "TRY":
                msg = f"⚡ {used_ex} Canlı {action_tr} Emri Gerçekleşti! ({units:.4f} {clean_sym} - ₺{amt_try:.2f} TL / ~${amt_usd:.2f})"
            else:
                msg = f"⚡ {used_ex} Canlı {action_tr} Emri Gerçekleşti! ({units:.4f} {clean_sym} - ~${amt_usd:.2f})"
            return JSONResponse(content={
                "status": "SUCCESS", 
                "message": msg, 
                "order": res, 
                "exchange": used_ex
            })
        else:
            return JSONResponse(status_code=400, content={
                "status": "ERROR", 
                "message": f"❌ {used_ex} Canlı İşlem Hatası: {res.get('msg') or res.get('error') or str(res)}"
            })
    else:
        # Sanal Kasa İşlemi
        if action == "BUY":
            cash = orchestrator.wallet.cash_balance
            if req.amount_usd > cash:
                return JSONResponse(status_code=400, content={
                    "status": "ERROR", 
                    "message": f"Sanal kasanızda yetersiz nakit bakiye! (Mevcut: ${cash:.2f}, İstenen: ${req.amount_usd:.2f})"
                })

            trade = orchestrator.wallet.open_position(
                symbol=sym,
                action="BUY",
                entry_price=px,
                stop_loss=px * 0.95,
                take_profit=px * 1.10,
                units=units,
                thesis=f"[KULLANICI KARTINDAN MANUEL SANAL ALIM - {req_exchange}]",
                exchange="Paper"
            )
            return JSONResponse(content={
                "status": "SUCCESS", 
                "message": f"🧪 Sanal Alım Yapıldı: {units:.4f} {sym} (~${req.amount_usd:.2f}) sanal kasanıza eklendi.", 
                "trade": trade
            })
        else:
            pos = next((p for p in orchestrator.wallet.open_positions if p.get("symbol") in [sym, clean_sym, f"{clean_sym}USDT"]), None)
            if pos:
                closed = orchestrator.wallet.close_position(pos["id"], px, exit_reason="MANUAL_CARD_SELL")
                pnl = closed.get("pnl_usd", 0.0) if closed else 0.0
                pnl_pct = closed.get("pnl_pct", 0.0) if closed else 0.0
                pnl_sign = "+" if pnl >= 0 else ""
                return JSONResponse(content={
                    "status": "SUCCESS", 
                    "message": f"🧪 Sanal Satım Tamamlandı: {sym} pozisyonu kapatıldı (Realize K/Z: {pnl_sign}${pnl:.2f} | {pnl_sign}%{pnl_pct:.2f})", 
                    "trade": closed
                })
            return JSONResponse(status_code=400, content={
                "status": "ERROR", 
                "message": f"ℹ️ Sanal kasanızda satılacak açık {sym} pozisyonu bulunmuyor. Satış yapabilmek için önce 'Hızlı Al' yapmalısınız."
            })

@app.post("/api/portfolio/set-entry-price")
async def set_portfolio_entry_price(req: SetEntryPriceRequest):
    """Kullanıcının varlığı kaça aldığını (Giriş Maliyetini) manuel belirlemesini ve sabitlemesini sağlar."""
    sym = req.symbol.strip().upper().replace("USDT", "").replace("TRY", "").replace("_", "")
    usd_rate = orchestrator.get_usd_try_rate() or 48.48
    price = float(req.entry_price or 0.0)
    if price <= 0:
        return JSONResponse(status_code=400, content={"status": "ERROR", "message": "Lütfen geçerli bir fiyat girin."})
    
    price_usd = (price / usd_rate) if req.currency.upper() == "TRY" else price

    found = False
    for p in orchestrator.wallet.open_positions:
        p_sym = p.get("symbol", "").replace("USDT", "").replace("TRY", "").replace("_", "").upper()
        if p_sym == sym:
            p["entry_price"] = price_usd
            p["stop_loss"] = round(price_usd * 0.95, 4)
            p["take_profit"] = round(price_usd * 1.10, 4)
            found = True
            break
            
    if not found:
        orchestrator.wallet.open_position(
            symbol=f"{sym}USDT",
            action="BUY",
            entry_price=price_usd,
            stop_loss=round(price_usd * 0.95, 4),
            take_profit=round(price_usd * 1.10, 4),
            units=1.0,
            thesis="[KULLANICI MANUEL GİRİŞ MALİYETİ]",
            exchange="Binance TR",
            is_live_record=True
        )
    orchestrator.wallet._save_state()
    return JSONResponse(content={
        "status": "SUCCESS", 
        "message": f"✅ {sym} alış maliyeti {price:.2f} {req.currency} olarak güncellendi ve kilitlendi."
    })

@app.post("/api/mode/toggle")
async def toggle_mode(request: Request):
    """Sanal Kasa (PAPER) ile Canlı Kripto (LIVE) arasında tek tıkla anında geçiş yapar."""
    target_mode = None
    try:
        body = await request.json()
        target_mode = body.get("trading_mode")
    except Exception:
        pass

    if target_mode in ["LIVE", "PAPER"]:
        config.TRADING_MODE = target_mode
    else:
        config.TRADING_MODE = "LIVE" if config.TRADING_MODE == "PAPER" else "PAPER"

    try:
        update_env_file({"TRADING_MODE": config.TRADING_MODE})
    except Exception:
        pass

    return JSONResponse(content={"status": "SUCCESS", "trading_mode": config.TRADING_MODE})

@app.post("/api/exchange/select")
async def select_exchange(req: Dict[str, Any]):
    """Hızlıca canlı işlem borsasını (AUTO, BINANCE, MEXC, OKX) değiştirir ve kaydeder."""
    ex = str(req.get("exchange", "AUTO")).upper().strip()
    config.TRADING_EXCHANGE = ex
    update_env_file({"TRADING_EXCHANGE": ex})
    return JSONResponse(content={"status": "SUCCESS", "trading_exchange": config.TRADING_EXCHANGE})

@app.get("/api/wallet/deposit-addresses")
async def get_deposit_addresses():
    """Kullanıcının Binance resmi kripto yatırma adreslerini döndürür."""
    if not orchestrator.binance_executor.enabled:
        return JSONResponse(status_code=400, content={"status": "ERROR", "message": "Binance API anahtarları tanımlı değil."})
    addrs = orchestrator.binance_executor.get_deposit_addresses()
    return JSONResponse(content={"status": "SUCCESS", "addresses": addrs})

@app.get("/api/market/all-coins")
async def get_all_market_coins(
    exchange: Optional[str] = "BINANCE",
    search: Optional[str] = None, 
    sort_by: Optional[str] = "volume"
):
    """Belirtilen borsada (Binance, OKX, MEXC) listelenen tüm aktif USDT altcoinlerini canlı fiyat ve hacimle listeler."""
    tickers = orchestrator.crypto_feed.get_market_tickers(exchange or "BINANCE")
    if search:
        q = search.strip().upper()
        tickers = [t for t in tickers if q in t["symbol"] or q in t["asset"]]
    if sort_by == "gainers":
        tickers = sorted(tickers, key=lambda x: x["change_24h"], reverse=True)
    elif sort_by == "losers":
        tickers = sorted(tickers, key=lambda x: x["change_24h"])
    elif sort_by == "alphabetical":
        tickers = sorted(tickers, key=lambda x: x["symbol"])
    else:
        tickers = sorted(tickers, key=lambda x: x.get("volume_try", x.get("volume_usd", 0.0)), reverse=True)
    return JSONResponse(content={"status": "SUCCESS", "exchange": (exchange or "BINANCE").upper(), "total": len(tickers), "coins": tickers})

@app.post("/api/market/analyze-coin")
async def analyze_single_coin(req: SingleCoinAnalysisRequest):
    """Herhangi bir Binance / Binance TR altcoinini anlık olarak derinlemesine analiz eder."""
    sym = req.symbol.strip().upper()
    if sym.endswith("_TRY") or sym.endswith("TRY"):
        # TRY paritesini veya karşılık USDT sembolünü analiz et
        base = sym.replace("_TRY", "").replace("TRY", "")
        usdt_sym = f"{base}USDT"
        analysis = orchestrator.scan_asset(usdt_sym)
        if analysis.get("status") != "FAILED":
            analysis["display_symbol"] = sym
            return JSONResponse(content={"status": "SUCCESS", "analysis": analysis})
    elif not sym.endswith("USDT"):
        sym += "USDT"
    analysis = orchestrator.scan_asset(sym)
    return JSONResponse(content={"status": "SUCCESS", "analysis": analysis})

@app.get("/api/radar/breakouts")
async def get_radar_breakouts():
    """Binance, MEXC ve OKX borsalarını tarayarak günlük yükseliş fırsatlarını döner."""
    return JSONResponse(content=orchestrator.radar.get_summary())

@app.post("/api/radar/scan")
async def scan_radar():
    """Tüm borsaları (Binance, MEXC, OKX) anlık olarak canlı tarar."""
    res = orchestrator.radar.scan_all_exchanges()
    return JSONResponse(content=res)

@app.post("/api/radar/track")
async def toggle_radar_track(req: Dict[str, Any]):
    """Bir coini çoklu borsa takip listesine ekler veya çıkarır."""
    symbol = req.get("symbol", "")
    coin_data = req.get("coin_data")
    is_tracked = orchestrator.radar.toggle_track(symbol, coin_data)
    return JSONResponse(content={
        "status": "SUCCESS",
        "symbol": symbol.upper(),
        "is_tracked": is_tracked,
        "watchlist": list(orchestrator.radar.watchlist.values())
    })

@app.get("/api/exchanges/status")
async def get_exchanges_status():
    """Çoklu borsa (Binance, Bybit, OKX, Gate.io) durumunu döner."""
    from bot.trading.exchanges import MultiExchangeManager
    mgr = MultiExchangeManager()
    return JSONResponse(content={"status": "SUCCESS", "exchanges": mgr.get_exchanges_status()})

@app.get("/api/config")
def get_config():
    """Mevcut ayarları ve durumları frontend için döner."""
    masked_binance = f"{config.BINANCE_API_KEY[:8]}...{config.BINANCE_API_KEY[-8:]}" if config.BINANCE_API_KEY and len(config.BINANCE_API_KEY) > 16 else (config.BINANCE_API_KEY or "")
    masked_binance_tr = f"{getattr(config, 'BINANCE_TR_API_KEY', '')[:8]}...{getattr(config, 'BINANCE_TR_API_KEY', '')[-8:]}" if getattr(config, "BINANCE_TR_API_KEY", "") and len(config.BINANCE_TR_API_KEY) > 16 else (getattr(config, "BINANCE_TR_API_KEY", "") or "")
    masked_okx = f"{config.OKX_API_KEY[:8]}...{config.OKX_API_KEY[-8:]}" if config.OKX_API_KEY and len(config.OKX_API_KEY) > 16 else (config.OKX_API_KEY or "")
    masked_mexc = f"{config.MEXC_API_KEY[:6]}...{config.MEXC_API_KEY[-6:]}" if config.MEXC_API_KEY and len(config.MEXC_API_KEY) > 12 else (config.MEXC_API_KEY or "")
    masked_deepseek = f"{config.DEEPSEEK_API_KEY[:6]}...{config.DEEPSEEK_API_KEY[-6:]}" if config.DEEPSEEK_API_KEY and len(config.DEEPSEEK_API_KEY) > 12 else (config.DEEPSEEK_API_KEY or "")
    masked_groq = f"{config.GROQ_API_KEY[:6]}...{config.GROQ_API_KEY[-4:]}" if getattr(config, "GROQ_API_KEY", "") and len(config.GROQ_API_KEY) > 10 else (getattr(config, "GROQ_API_KEY", "") or "")
    masked_cg = f"{config.COINGECKO_API_KEY[:6]}...{config.COINGECKO_API_KEY[-4:]}" if getattr(config, "COINGECKO_API_KEY", "") and len(config.COINGECKO_API_KEY) > 10 else (getattr(config, "COINGECKO_API_KEY", "") or "")
    masked_fred = f"{config.FRED_API_KEY[:6]}...{config.FRED_API_KEY[-4:]}" if getattr(config, "FRED_API_KEY", "") and len(config.FRED_API_KEY) > 10 else (getattr(config, "FRED_API_KEY", "") or "")

    return JSONResponse(content={
        "status": "SUCCESS",
        "deepseek_api_key_set": bool(config.DEEPSEEK_API_KEY),
        "deepseek_masked_key": masked_deepseek,
        "deepseek_model": config.DEEPSEEK_MODEL,
        "trading_mode": config.TRADING_MODE,
        "trading_exchange": getattr(config, "TRADING_EXCHANGE", "AUTO"),
        "ai_risk_profile": getattr(config, "AI_RISK_PROFILE", "SMART_AGGRESSIVE"),
        "max_risk_per_trade_percent": getattr(config, "MAX_RISK_PER_TRADE_PERCENT", 20.0),
        "binance_configured": bool(config.BINANCE_API_KEY),
        "binance_masked_key": masked_binance,
        "binance_secret_set": bool(config.BINANCE_SECRET_KEY),
        "binance_tr_configured": bool(getattr(config, "BINANCE_TR_API_KEY", "")),
        "binance_tr_masked_key": masked_binance_tr,
        "binance_tr_secret_set": bool(getattr(config, "BINANCE_TR_SECRET_KEY", "")),
        "okx_configured": bool(config.OKX_API_KEY),
        "okx_masked_key": masked_okx,
        "okx_secret_set": bool(config.OKX_SECRET_KEY),
        "okx_has_passphrase": bool(config.OKX_PASSPHRASE),
        "mexc_configured": bool(config.MEXC_API_KEY),
        "mexc_masked_key": masked_mexc,
        "mexc_secret_set": bool(config.MEXC_SECRET_KEY),
        "groq_configured": bool(getattr(config, "GROQ_API_KEY", "")),
        "groq_masked_key": masked_groq,
        "coingecko_configured": bool(getattr(config, "COINGECKO_API_KEY", "")),
        "coingecko_masked_key": masked_cg,
        "fred_configured": bool(getattr(config, "FRED_API_KEY", "")),
        "fred_masked_key": masked_fred,
        "telegram_configured": bool(config.TELEGRAM_BOT_TOKEN),
        "telegram_token_set": bool(config.TELEGRAM_BOT_TOKEN),
        "telegram_chat_id_set": bool(config.TELEGRAM_CHAT_ID),
        "admin_pin_configured": bool(config.ADMIN_PIN),
        "admin_pin_masked": "●●●●" if config.ADMIN_PIN else "Tanımlı Değil"
    })

@app.post("/api/config/update")
async def update_settings(req: ConfigUpdateRequest):
    """API anahtarları ve ayarları canlı günceller ve .env dosyasına kalıcı yazar."""
    env_updates = {}

    if req.admin_pin is not None and req.admin_pin.strip():
        config.ADMIN_PIN = req.admin_pin.strip()
        env_updates["ADMIN_PIN"] = config.ADMIN_PIN

    if req.deepseek_api_key is not None and req.deepseek_api_key.strip():
        config.DEEPSEEK_API_KEY = req.deepseek_api_key.strip()
        orchestrator.agent.api_key = config.DEEPSEEK_API_KEY
        env_updates["DEEPSEEK_API_KEY"] = config.DEEPSEEK_API_KEY

    if req.deepseek_model is not None and req.deepseek_model.strip():
        config.DEEPSEEK_MODEL = req.deepseek_model.strip()
        orchestrator.agent.model = config.DEEPSEEK_MODEL
        env_updates["DEEPSEEK_MODEL"] = config.DEEPSEEK_MODEL

    if req.trading_mode is not None and req.trading_mode.strip():
        config.TRADING_MODE = req.trading_mode.strip().upper()
        env_updates["TRADING_MODE"] = config.TRADING_MODE

    if req.trading_exchange is not None and req.trading_exchange.strip():
        config.TRADING_EXCHANGE = req.trading_exchange.strip().upper()
        env_updates["TRADING_EXCHANGE"] = config.TRADING_EXCHANGE

    if req.ai_risk_profile is not None and req.ai_risk_profile.strip():
        config.AI_RISK_PROFILE = req.ai_risk_profile.strip().upper()
        from bot.trading.risk_guard import RiskGuard
        orchestrator.risk_guard = RiskGuard(max_risk_pct=getattr(config, "MAX_RISK_PER_TRADE_PERCENT", 20.0))
        env_updates["AI_RISK_PROFILE"] = config.AI_RISK_PROFILE

    if req.max_risk_per_trade_percent is not None and req.max_risk_per_trade_percent > 0:
        config.MAX_RISK_PER_TRADE_PERCENT = float(req.max_risk_per_trade_percent)
        orchestrator.risk_guard.max_risk_pct = config.MAX_RISK_PER_TRADE_PERCENT
        env_updates["MAX_RISK_PER_TRADE_PERCENT"] = str(config.MAX_RISK_PER_TRADE_PERCENT)

    if req.binance_api_key is not None and req.binance_api_key.strip():
        config.BINANCE_API_KEY = req.binance_api_key.strip()
        orchestrator.binance_executor.api_key = config.BINANCE_API_KEY
        env_updates["BINANCE_API_KEY"] = config.BINANCE_API_KEY

    if req.binance_secret_key is not None and req.binance_secret_key.strip():
        config.BINANCE_SECRET_KEY = req.binance_secret_key.strip()
        orchestrator.binance_executor.secret_key = config.BINANCE_SECRET_KEY
        env_updates["BINANCE_SECRET_KEY"] = config.BINANCE_SECRET_KEY

    if req.binance_api_key or req.binance_secret_key:
        orchestrator.binance_executor.enabled = bool(orchestrator.binance_executor.api_key and orchestrator.binance_executor.secret_key)
    
    # Binance TR API Anahtarları
    if req.binance_tr_api_key is not None and req.binance_tr_api_key.strip():
        config.BINANCE_TR_API_KEY = req.binance_tr_api_key.strip()
        orchestrator.binance_tr_executor.api_key = config.BINANCE_TR_API_KEY
        env_updates["BINANCE_TR_API_KEY"] = config.BINANCE_TR_API_KEY

    if req.binance_tr_secret_key is not None and req.binance_tr_secret_key.strip():
        config.BINANCE_TR_SECRET_KEY = req.binance_tr_secret_key.strip()
        orchestrator.binance_tr_executor.secret_key = config.BINANCE_TR_SECRET_KEY
        env_updates["BINANCE_TR_SECRET_KEY"] = config.BINANCE_TR_SECRET_KEY

    # OKX API Anahtarları ve Parola
    if req.okx_api_key is not None and req.okx_api_key.strip():
        config.OKX_API_KEY = req.okx_api_key.strip()
        orchestrator.okx_executor.api_key = config.OKX_API_KEY
        env_updates["OKX_API_KEY"] = config.OKX_API_KEY

    if req.okx_secret_key is not None and req.okx_secret_key.strip():
        config.OKX_SECRET_KEY = req.okx_secret_key.strip()
        orchestrator.okx_executor.secret_key = config.OKX_SECRET_KEY
        env_updates["OKX_SECRET_KEY"] = config.OKX_SECRET_KEY

    if req.okx_passphrase is not None and req.okx_passphrase.strip():
        config.OKX_PASSPHRASE = req.okx_passphrase.strip()
        orchestrator.okx_executor.passphrase = config.OKX_PASSPHRASE
        env_updates["OKX_PASSPHRASE"] = config.OKX_PASSPHRASE

    if req.okx_api_key or req.okx_secret_key or req.okx_passphrase:
        orchestrator.okx_executor._init_client()

    # MEXC API Anahtarları
    if req.mexc_api_key is not None and req.mexc_api_key.strip():
        config.MEXC_API_KEY = req.mexc_api_key.strip()
        orchestrator.mexc_executor.api_key = config.MEXC_API_KEY
        env_updates["MEXC_API_KEY"] = config.MEXC_API_KEY

    if req.mexc_secret_key is not None and req.mexc_secret_key.strip():
        config.MEXC_SECRET_KEY = req.mexc_secret_key.strip()
        orchestrator.mexc_executor.secret_key = config.MEXC_SECRET_KEY
        env_updates["MEXC_SECRET_KEY"] = config.MEXC_SECRET_KEY

    if req.mexc_api_key or req.mexc_secret_key:
        orchestrator.mexc_executor._init_client()

    if req.telegram_token is not None and req.telegram_token.strip():
        config.TELEGRAM_BOT_TOKEN = req.telegram_token.strip()
        orchestrator.notifier.token = config.TELEGRAM_BOT_TOKEN
        env_updates["TELEGRAM_BOT_TOKEN"] = config.TELEGRAM_BOT_TOKEN

    if req.telegram_chat_id is not None and req.telegram_chat_id.strip():
        config.TELEGRAM_CHAT_ID = req.telegram_chat_id.strip()
        orchestrator.notifier.chat_id = config.TELEGRAM_CHAT_ID
        env_updates["TELEGRAM_CHAT_ID"] = config.TELEGRAM_CHAT_ID

    # 4 Kritik İstihbarat & Alfa API Anahtarları
    if req.groq_api_key is not None and req.groq_api_key.strip():
        config.GROQ_API_KEY = req.groq_api_key.strip()
        orchestrator.agent.groq_api_key = config.GROQ_API_KEY
        env_updates["GROQ_API_KEY"] = config.GROQ_API_KEY

    if req.coingecko_api_key is not None and req.coingecko_api_key.strip():
        config.COINGECKO_API_KEY = req.coingecko_api_key.strip()
        orchestrator.coingecko_feed.api_key = config.COINGECKO_API_KEY
        env_updates["COINGECKO_API_KEY"] = config.COINGECKO_API_KEY

    if req.fred_api_key is not None and req.fred_api_key.strip():
        config.FRED_API_KEY = req.fred_api_key.strip()
        orchestrator.macro_feed.fred_api_key = config.FRED_API_KEY
        env_updates["FRED_API_KEY"] = config.FRED_API_KEY

    orchestrator.notifier.enabled = bool(orchestrator.notifier.token and orchestrator.notifier.chat_id)

    # .env dosyasına kalıcı olarak yaz
    if env_updates:
        update_env_file(env_updates)

    # Önbellekleri sıfırla
    orchestrator._exchange_cache_time = 0.0

    return JSONResponse(content={"status": "SUCCESS", "message": "Ayarlar başarıyla güncellendi ve kaydedildi."})

@app.post("/api/wallet/reset-paper")
async def reset_paper_wallet():
    """Sanal kasayı 10.000$ başlangıç bakiyesine sıfırlar ve pozisyonları temizler."""
    orchestrator.wallet.state["cash_balance"] = 10000.0
    orchestrator.wallet.state["initial_balance"] = 10000.0
    orchestrator.wallet.state["open_positions"] = []
    orchestrator.wallet.state["closed_trades"] = []
    orchestrator.wallet._save_state()
    return JSONResponse(content={"status": "SUCCESS", "message": "Sanal kasa $10.000 olarak sıfırlandı."})

@app.get("/api/wallet/binancetr-deposit-addresses")
async def get_binancetr_deposit_addresses():
    """Kullanıcının Binance TR resmi kripto yatırma adreslerini döndürür."""
    if not orchestrator.binance_tr_executor.enabled:
        return JSONResponse(status_code=400, content={"status": "ERROR", "message": "Binance TR API bağlantısı aktif değil veya anahtarlar tanımlanmadı."})
    addrs = orchestrator.binance_tr_executor.get_deposit_addresses()
    return JSONResponse(content={"status": "SUCCESS", "addresses": addrs})

@app.get("/api/wallet/okx-deposit-addresses")
async def get_okx_deposit_addresses():
    """Kullanıcının OKX resmi kripto yatırma adreslerini döndürür."""
    if not orchestrator.okx_executor.enabled:
        return JSONResponse(status_code=400, content={"status": "ERROR", "message": "OKX API bağlantısı aktif değil veya parola (passphrase) girilmedi."})
    addrs = orchestrator.okx_executor.get_deposit_addresses()
    return JSONResponse(content={"status": "SUCCESS", "addresses": addrs})

@app.get("/api/wallet/mexc-deposit-addresses")
async def get_mexc_deposit_addresses():
    """Kullanıcının MEXC resmi kripto yatırma adreslerini döndürür."""
    if not orchestrator.mexc_executor.enabled:
        return JSONResponse(status_code=400, content={"status": "ERROR", "message": "MEXC API bağlantısı aktif değil."})
    res = orchestrator.mexc_executor.get_deposit_addresses()
    return JSONResponse(content={"status": "SUCCESS" if res.get("success") else "INFO", **res})

@app.get("/api/macro/regime")
def get_macro_regime():
    """Anlık makro ekonomik göstergeleri ve piyasa rejimini döner."""
    return JSONResponse(content={"status": "SUCCESS", "macro": orchestrator.macro_feed.get_macro_regime()})

@app.get("/api/sectors/momentum")
def get_sectors_momentum():
    """CoinGecko dinamik sektör hacimleri ve trend altcoinleri döner."""
    return JSONResponse(content={"status": "SUCCESS", "momentum": orchestrator.coingecko_feed.get_sector_momentum_summary()})

@app.get("/api/market/funding/{symbol}")
def get_asset_funding(symbol: str):
    """Hyperliquid türev piyasası fonlama oranı ve OI durumunu döner."""
    return JSONResponse(content={"status": "SUCCESS", "perps": orchestrator.hyperliquid_feed.get_asset_perps_info(symbol)})
