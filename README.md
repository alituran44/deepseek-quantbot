# DeepSeek-QuantBot: Otonom Yapay Zeka Kripto Sepet (Crypto Basket) Sistemi

**DeepSeek Harness (`deepseek-harness-sdk`)** mimarisi üzerine inşa edilmiş, **saf kripto varlıklar (Bitcoin, Ethereum ve Altcoinler)** için çalışan kurumsal seviyede bir yapay zeka kripto sepet yöneticisi, sanal öğrenme motoru ve canlı Binance al-sat botudur.

---

## 🌟 Temel Özellikler

1. **4 Tematik Sektörlü Kripto Sepet Mimarisi:**
   - **Çekirdek Varlıklar (Core - %35 Hedef):** `BTCUSDT`, `ETHUSDT` (Düşük volatilite ve portföy çapası)
   - **Katman-1 Blokzincirleri (L1 - %25 Hedef):** `SOL`, `SUI`, `BNB`, `AVAX`, `ADA`
   - **Yapay Zeka & DePIN (AI - %25 Hedef):** `TAO`, `NEAR`, `FET`, `RENDER`
   - **DeFi & Momentum (%15 Hedef):** `UNI`, `LINK`, `ENA`, `ARB`, `DOGE`
2. **Kantitatif İndikatör Motoru:**
   - RSI (14), MACD (12, 26, 9), EMA (20, 50, 200), Bollinger Bantları (20, 2), ATR (14), Destek & Direnç Pivotları ve Hacim Anomalisi tespiti.
3. **DeepSeek Akıl Yürütme Ajanı (AI Reasoning):**
   - DeepSeek-R1 (`deepseek-reasoner`) veya DeepSeek-V3 (`deepseek-chat`) modelleri üzerinden kripto piyasa tezi, gerekçeli analiz ve al/sat/bekle kararları.
4. **Çift Modlu Çalışma Altyapısı:**
   - **🧪 Sanal Kasa & Öğrenme Modu (Paper):** 10.000$ sanal kasa ile gerçek Binance piyasa verileri üzerinde sıfır riskli strateji testi.
   - **⚡ Canlı Binance Kripto Modu (Live):** Tek tıkla gerçek Binance Spot cüzdanına bağlanarak canlı OCO (Stop-Loss + Take-Profit) emirleri iletimi.
5. **Obsidian-Dark Web Kontrol Paneli:**
   - Çok renkli sepet dağılım çubuğu, sektör dengesi, tek tıkla mod değiştirici ve canlı PnL takibi (`http://127.0.0.1:8080`).

---

## 🚀 Hızlı Başlangıç

### 1. Botu Başlatma
```powershell
.\.venv\Scripts\python.exe run.py --port 8080
```
Tarayıcınızdan panele erişin:
👉 **[http://127.0.0.1:8080](http://127.0.0.1:8080)**

---

## 📁 Proje Dizin Yapısı

```text
BitCoin Ve Kripto/
├── bot/
│   ├── config.py              # Kripto sepet ağırlıkları ve ayarlar
│   ├── orchestrator.py        # Kripto veri ve yapay zeka orkestratörü
│   ├── agent/                 # DeepSeek akıl yürütme motoru
│   ├── data/
│   │   ├── crypto_feed.py     # Binance Public REST API (Kripto mum/fiyat)
│   │   └── sentiment_feed.py  # Fear & Greed kripto duygu analizi
│   ├── indicators/            # Saf matematiksel teknik analiz indikatörleri
│   ├── trading/
│   │   ├── basket_manager.py  # 4 sektörlü sepet dengeleme motoru
│   │   ├── risk_guard.py      # Sermaye koruma ve bütçe tavanı filtresi
│   │   ├── paper_wallet.py    # 10.000$ sanal kasa simülatörü
│   │   └── binance_live.py    # Binance canlı REST API & OCO emir motoru
│   └── notifications/         # Telegram anlık sinyal bildirimi
├── web/                       # FastAPI web dashboard ve Obsidian Dark UI
└── tests/                     # Kripto ve sepet birim testleri
```
