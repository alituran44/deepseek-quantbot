"""
DeepSeek Finansal Akıl Yürütme ve Karar İstemleri (Prompts)
"""

FINANCIAL_SYSTEM_PROMPT = """Sen Wall Street ve Kripto Kantitatif Koruma Fonlarında (Crypto Quant Hedge Fund) görev yapan Kıdemli Portföy Yöneticisi ve Baş Finans Uzmanısın.

Temel Yatırım Felsefen: "HESAPLANMIŞ VE ASİMETRİK RİSK ALMAK" (Calculated Asymmetric Risk-Taking).
Gerçek bir finans uzmanı fırsatlardan korkup kenarda beklemez; tam aksine, riskin matematiksel olarak sınırlandığı (sıkı stop-loss) ve getirinin katbekat yüksek olduğu (1:3 - 1:5 Risk/Ödül) fırsatları cesurca ve kararlılıkla değerlendirir.

Piyasa Değerlendirme İlkelerin:
1. ASİMETRİK GETİRİ ODAĞI: Küçük bir risk birimiyle (örn. %2-3 stop mesafesi), büyük bir trend dalgasını (%8-15+ kâr hedefi) yakalamayı hedeflersin.
2. MOMENTUM VE LİKİDİTE AVLAYICISI: Konsolidasyon kırılımları, Bollinger Bant sıkışmaları, hacim patlamaları (Volume Surges), EMA trend uyumları ve RSI toparlanmalarında piyasa lideri veya yükseliş potansiyeli yüksek altcoinlerde agresif alım fırsatlarını tespit edersin.
3. PROFESYONEL HEDGE-FUND DİLİ: Analiz tezin sıradan bir kullanıcı gibi değil; 'Order Flow (Emir Akışı)', 'Market Structure (Piyasa Yapısı)', 'Liquidity Sweep (Likidite Temizliği)' ve 'Momentum Reversal' gibi kurumsal finans terminolojisiyle gerekçelendirilmelidir.
4. ÇELİŞKİ YOKSA CESUR OL: Piyasa hafif pozitif bile olsa, net bir destek seviyesi varsa ve stop seviyesi tanımlanabiliyorsa gereksiz yere 'HOLD' deyip fırsatı kaçırma. Riski tanımla ve aksiyon al.
5. ÇIKTI FORMATI: Yanıtın SADECE ve KESİNLİKLE aşağıdaki geçerli JSON formatında olmalıdır:

JSON Şablonu:
{
  "action": "BUY" | "SELL" | "HOLD",
  "confidence": 0.88,
  "entry_price": 64200.0,
  "stop_loss": 62800.0,
  "take_profit": 68400.0,
  "risk_reward_ratio": "1:3.0",
  "timeframe": "1H / 4H Momentum Swing",
  "thesis_summary": "Kurumsal finans uzmanı perspektifiyle yazılmış 1-2 cümlelik vurucu Türkçe yatırım tezi.",
  "reasoning_points": [
    "Likidite ve Hacim Analizi: İşlem hacmi ve para akışı göstergeleri",
    "Trend & Fiyat Yapısı: EMA ve destek/direnç kırılım dinamikleri",
    "Asimetrik Risk Yönetimi: Stop-loss matematiksel gerekçesi ve getiri potansiyeli"
  ],
  "risk_warning": "Bu işlemde gözetilen temel makro veya volatilite riski nedir?"
}
"""

def build_market_analysis_prompt(
    symbol: str, 
    asset_type: str, 
    indicators: dict, 
    sentiment: dict,
    hyperliquid_info: dict = None,
    sector_info: dict = None,
    macro_info: dict = None
) -> str:
    """Teknik, türev (Hyperliquid), sektör (CoinGecko) ve makro (FRED) verilerini modelin okuyabileceği yapılandırılmış bir analize dönüştürür."""
    hl_str = ""
    if hyperliquid_info:
        hl_str = f"""
Türev & Tasfiye İstihbaratı (Hyperliquid):
- 8 Saatlik Fonlama Oranı: %{hyperliquid_info.get('funding_rate_8h_pct', 0.01)} (Yıllık: %{hyperliquid_info.get('funding_rate_annual_pct', 10.95)})
- Açık Pozisyon (Open Interest): ${hyperliquid_info.get('open_interest_usd', 0):,.0f}
- Squeeze Durumu: {hyperliquid_info.get('squeeze_tr', 'Dengeli')} ({hyperliquid_info.get('squeeze_status', 'BALANCED')})
"""

    sector_str = ""
    if sector_info:
        sector_str = f"""
Sektör Hacim & Ralli Analizi (CoinGecko):
- Lider Kazandıran Sektör: {sector_info.get('top_gainer_sector', 'Genel')} (%{sector_info.get('top_gainer_change', 0.0)})
- Trend Altcoinler: {', '.join(sector_info.get('trending_coins', [])[:4]) or 'Normal'}
"""

    macro_str = ""
    if macro_info:
        macro_str = f"""
Makro Risk Kalkanı & Fed Ortamı (FRED / EconPulse):
- DXY Dolar Endeksi: {macro_info.get('dxy_index', 99.0)}
- ABD 10 Yıllık Tahvil Faizi: %{macro_info.get('us_10y_yield', 4.25)} | Fed Politika Faizi: %{macro_info.get('fed_rate', 4.50)}
- Makro Rejim: {macro_info.get('regime_tr', 'Dengeli')} ({macro_info.get('regime', 'NEUTRAL')}) -> {macro_info.get('cash_recommendation', 'Standart Risk')}
"""

    return f"""Aşağıdaki piyasa verilerini analiz et ve katı finansal mantıkla karara var:

Varlık: {symbol} ({asset_type})
Anlık Fiyat: {indicators.get('current_price')}
Piyasa Duygu Durumu (Fear & Greed): {sentiment.get('value')}/100 - {sentiment.get('label_tr')}
{hl_str}{sector_str}{macro_str}
Teknik Göstergeler:
- RSI (14): {indicators.get('rsi')} ({indicators.get('rsi_status')})
- MACD: Değer: {indicators.get('macd', {}).get('macd')}, Sinyal: {indicators.get('macd', {}).get('signal')}, Hist: {indicators.get('macd', {}).get('histogram')} -> {indicators.get('macd', {}).get('cross')}
- Hareketli Ortalamalar:
  * EMA 20: {indicators.get('moving_averages', {}).get('ema_20')} (Fiyat: {indicators.get('moving_averages', {}).get('price_vs_ema20')})
  * EMA 50: {indicators.get('moving_averages', {}).get('ema_50')} (Fiyat: {indicators.get('moving_averages', {}).get('price_vs_ema50')})
  * EMA 200: {indicators.get('moving_averages', {}).get('ema_200')} (Fiyat: {indicators.get('moving_averages', {}).get('price_vs_ema200')})
- Bollinger Bantları: Üst: {indicators.get('bollinger_bands', {}).get('upper')}, Orta: {indicators.get('bollinger_bands', {}).get('middle')}, Alt: {indicators.get('bollinger_bands', {}).get('lower')} ({indicators.get('bollinger_bands', {}).get('position')})
- Volatilite & Risk: ATR: {indicators.get('volatility', {}).get('atr')} (%{indicators.get('volatility', {}).get('atr_percent')}), Hacim Patlaması: {indicators.get('volatility', {}).get('volume_surge')}
- Kritik Seviyeler: Destek: {indicators.get('key_levels', {}).get('support')}, Direnç: {indicators.get('key_levels', {}).get('resistance')}
- Algoritmik Trend Skoru: {indicators.get('summary')} (Bullish Skoru: {indicators.get('scores', {}).get('bullish_score')}, Bearish Skoru: {indicators.get('scores', {}).get('bearish_score')})

Lütfen bu verileri sentezle ve belirtilen katı JSON formatında analizi üret.
"""
