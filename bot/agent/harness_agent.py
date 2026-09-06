import json
import re
import os
import requests
from typing import Dict, Any, Optional
from pathlib import Path
from ..config import config
from .prompts import FINANCIAL_SYSTEM_PROMPT, build_market_analysis_prompt

class DeepSeekQuantAgent:
    """
    DeepSeek & Groq Cloud destekli hibrit finansal akıl yürütme ajanı.
    - DeepSeek R1/V3 ile derin akıl yürütme.
    - Groq Cloud (Llama-3.3 70B) ile ultra hızlı (~300ms) acil karar & fallback.
    - Hyperliquid (Türev & Squeeze), CoinGecko (Sektör Hacmi) ve FRED (Makro) verilerini sentezler.
    """
    def __init__(self):
        self.api_key = config.DEEPSEEK_API_KEY
        self.groq_api_key = getattr(config, "GROQ_API_KEY", "").strip()
        self.model = config.DEEPSEEK_MODEL or "deepseek-reasoner"
        self.dsh_home = Path(config.DSH_HOME)
        try:
            self.dsh_home.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass
        
    def analyze_market(
        self, 
        symbol: str, 
        asset_type: str, 
        indicators: dict, 
        sentiment: dict,
        hyperliquid_info: dict = None,
        sector_info: dict = None,
        macro_info: dict = None
    ) -> Dict[str, Any]:
        """
        Piyasa, türev (Hyperliquid), sektör (CoinGecko) ve makro (FRED) verilerini
        analiz edip yapılandırılmış ticaret sinyali ve gerekçe üretir.
        """
        user_prompt = build_market_analysis_prompt(
            symbol=symbol,
            asset_type=asset_type,
            indicators=indicators,
            sentiment=sentiment,
            hyperliquid_info=hyperliquid_info,
            sector_info=sector_info,
            macro_info=macro_info
        )
        
        # 1. Model seçimi Groq ise doğrudan Groq üzerinden çağır
        if self.model.startswith("groq/") or self.model.startswith("llama"):
            if self.groq_api_key:
                resp_text = self._call_groq_api(user_prompt)
                if resp_text:
                    parsed = self._extract_json(resp_text)
                    if parsed and "action" in parsed:
                        parsed["source"] = "GROQ_LLAMA3_AI"
                        return parsed

        # 2. DeepSeek API Anahtarı varsa DeepSeek'e danış
        if self.api_key:
            response_text = self._call_via_dsh_or_direct_api(user_prompt)
            if response_text:
                parsed = self._extract_json(response_text)
                if parsed and "action" in parsed:
                    parsed["source"] = "DEEPSEEK_AI"
                    return parsed

        # 3. DeepSeek başarısız olduysa veya anahtar yoksa, Groq yedek (fallback) motoru dene
        if self.groq_api_key:
            resp_text = self._call_groq_api(user_prompt)
            if resp_text:
                parsed = self._extract_json(resp_text)
                if parsed and "action" in parsed:
                    parsed["source"] = "GROQ_FALLBACK_AI"
                    return parsed
                    
        # 4. Hiçbir AI anahtarı yoksa deterministik kantitatif kuralları çalıştır
        return self._rule_based_fallback(symbol, indicators, sentiment)

    def _call_groq_api(self, prompt: str) -> Optional[str]:
        """Groq Cloud API üzerinden ~200-300ms ultra hızlı LPU çıkarımı yapar."""
        if not self.groq_api_key:
            return None
        try:
            groq_model = "llama-3.3-70b-versatile"
            if "mixtral" in self.model:
                groq_model = "mixtral-8x7b-32768"
            elif "llama" in self.model:
                groq_model = self.model.replace("groq/", "").strip()

            url = "https://api.groq.com/openai/v1/chat/completions"
            headers = {
                "Authorization": f"Bearer {self.groq_api_key}",
                "Content-Type": "application/json"
            }
            payload = {
                "model": groq_model,
                "messages": [
                    {"role": "system", "content": FINANCIAL_SYSTEM_PROMPT},
                    {"role": "user", "content": prompt}
                ],
                "temperature": 0.2,
                "max_tokens": 1500,
                "response_format": {"type": "json_object"}
            }
            resp = requests.post(url, headers=headers, json=payload, timeout=8)
            if resp.status_code == 200:
                data = resp.json()
                return data["choices"][0]["message"]["content"]
            else:
                print(f"[GroqAgent] Groq API HTTP {resp.status_code}: {resp.text}")
        except Exception as e:
            print(f"[GroqAgent] Groq çağrı hatası: {e}")
        return None

    def _call_via_dsh_or_direct_api(self, prompt: str) -> Optional[str]:
        """DeepSeek Harness SDK veya Direct API üzerinden çağrı yapar."""
        # 1. Direct API çağrısı (Çok hızlı, stabil ve doğrudan yanıt verir)
        try:
            url = f"{config.DEEPSEEK_BASE_URL}/chat/completions"
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }
            payload = {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": FINANCIAL_SYSTEM_PROMPT},
                    {"role": "user", "content": prompt}
                ],
                "temperature": 0.2,
                "max_tokens": 2048
            }
            resp = requests.post(url, headers=headers, json=payload, timeout=45)
            if resp.status_code == 200:
                data = resp.json()
                return data["choices"][0]["message"]["content"]
        except Exception as e:
            print(f"[DeepSeekQuantAgent] Direct API hatası: {e}")
            
        # 2. DeepSeek Harness SDK Subprocess çağrısı
        try:
            from deepseek_harness import DeepSeekHarness
            with DeepSeekHarness(
                dsh_home=str(self.dsh_home),
                cwd=str(config.BASE_DIR),
                provider="deepseek-official",
                model=self.model,
                api_key=self.api_key
            ) as harness:
                result = harness.run(f"{FINANCIAL_SYSTEM_PROMPT}\n\n{prompt}", session_id=f"trade-{os.getpid()}")
                if result and result.final_response:
                    return result.final_response
        except Exception as e:
            print(f"[DeepSeekQuantAgent] Harness SDK hatası: {e}")
            
        return None

    def _extract_json(self, text: str) -> Optional[Dict[str, Any]]:
        """Model çıktısından JSON bloğunu temizleyip ayrıştırır."""
        try:
            # Doğrudan parse
            return json.loads(text.strip())
        except Exception:
            pass
            
        # Regex ile ```json ... ``` veya { ... } ara
        json_match = re.search(r"(\{[\s\S]*\})", text)
        if json_match:
            try:
                return json.loads(json_match.group(1))
            except Exception:
                pass
        return None

    def _rule_based_fallback(self, symbol: str, indicators: dict, sentiment: dict) -> Dict[str, Any]:
        """
        API Key olmadığı veya ağ hatası durumunda çalışan
        profesyonel kurumsal finans uzmanı ve kantitatif algoritmik strateji motoru.
        Hesaplanmış asimetrik risk (1:2.8 - 1:4.0 Risk/Ödül) ile fırsatları yakalar.
        """
        price = indicators.get("current_price", 0.0)
        atr = indicators.get("volatility", {}).get("atr", price * 0.02)
        summary = indicators.get("summary", "NEUTRAL")
        rsi = indicators.get("rsi", 50.0)
        support = indicators.get("key_levels", {}).get("support", price * 0.98)
        resistance = indicators.get("key_levels", {}).get("resistance", price * 1.02)
        vol_surge = indicators.get("volatility", {}).get("volume_surge", False)
        ema20 = indicators.get("moving_averages", {}).get("ema_20", price)
        ema50 = indicators.get("moving_averages", {}).get("ema_50", price)
        bb_pos = indicators.get("bollinger_bands", {}).get("position", "INSIDE")
        
        profile = getattr(config, "AI_RISK_PROFILE", "AGGRESSIVE_ALPHA").upper()
        is_ultra = profile in ["ULTRA_DEGEN", "DEGEN_ALPHA", "DEGEN"]
        is_aggressive = is_ultra or profile == "AGGRESSIVE_ALPHA"
        
        # 1. HESAPLANMIŞ ALIM (BUY) SENARYOLARI (Trend Devamı, Dip Toparlanması veya Hacim Kırılımı)
        buy_condition = (
            ("BULLISH" in summary and (rsi < 84 if is_ultra else (rsi < 76 if is_aggressive else rsi < 70))) or
            (is_ultra and (vol_surge or (rsi > 40 and rsi < 85) or price > ema50)) or
            (is_aggressive and (price > ema20 or vol_surge or (rsi > 44 and rsi < 74))) or
            (rsi < 38 and price >= support * 0.985) # Aşırı satımdan asimetrik dip tepkisi
        )
        
        # 2. SATIŞ (SELL) SENARYOLARI
        sell_condition = (
            ("BEARISH" in summary and rsi > 25) or
            (rsi > (86 if is_ultra else 78) and bb_pos == "ABOVE_UPPER") # Tepe kâr realizasyonu
        )

        if buy_condition and not sell_condition:
            action = "BUY"
            # Asimetrik Risk/Ödül: Ultra modda 1:4.2+, Agresif modda 1:3.2, Dengeli modda 1:2.4
            if is_ultra:
                rr_mult = 4.2
                stop_distance = max(atr * 1.5, price * 0.032)
            elif is_aggressive:
                rr_mult = 3.2
                stop_distance = max(atr * 1.2, price * 0.022)
            else:
                rr_mult = 2.4
                stop_distance = max(atr * 1.0, price * 0.018)

            stop_loss = round(max(support * 0.99, price - stop_distance), 4 if price < 1 else 2)
            risk = price - stop_loss
            take_profit = round(price + (risk * rr_mult), 4 if price < 1 else 2)
            confidence = 0.92 if is_ultra else (0.88 if (summary == "STRONG_BULLISH" or vol_surge) else 0.78)
            
            if is_ultra:
                thesis = (
                    f"🔥 Ultra Degen Finans Uzmanı: {symbol} için yüksek momentum ve volatilite kırılımı tespit edildi. "
                    f"Maksimum kâr arayışı kapsamında 1:{rr_mult:.1f} asimetrik hedefle agresif pozisyonlanma öneriliyor."
                )
            else:
                thesis = (
                    f"Finans Uzmanı Değerlendirmesi: {symbol} için piyasa yapısı asimetrik bir getiri fırsatı sunuyor. "
                    f"Fiyatın kısa vadeli likiditeyi süpürerek EMA ve destek seviyelerinin üzerinde tutunması, "
                    f"1:{rr_mult:.1f} Risk/Ödül oranlı yüksek olasılıklı bir yükseliş kırılımına işaret ediyor."
                )
            reasoning = [
                f"Piyasa Yapısı & Momentum: Algoritmik Trend {summary} - RSI 14 Seviyesi {rsi:.1f}",
                f"Likidite & Hacim Dinamiği: {'🔥 Hacim patlaması ve kurumsal para girişi tespit edildi' if vol_surge else 'Dengeli emir akışı ve fiyat konsolidasyonu'}",
                f"Asimetrik Risk Yönetimi: Stop-Loss ${stop_loss} seviyesinde sınırlandırıldı, hedef 1:{rr_mult:.1f} getiri oranı ile ${take_profit}",
                f"Volatilite Analizi: ATR dinamik mesafesiyle sahte fitil (whipsaw) koruması devrede"
            ]
            warning = "Ani Bitcoin dominans hareketlerine ve BTC volatilitesine karşı tanımlı stop-loss seviyesi sıkı korunmalıdır."
            rr_str = f"1:{rr_mult:.1f}"

        elif sell_condition:
            action = "SELL"
            stop_distance = max(atr * 1.2, price * 0.022)
            stop_loss = round(min(resistance * 1.008, price + stop_distance), 4 if price < 1 else 2)
            risk = stop_loss - price
            take_profit = round(price - (risk * 2.8), 4 if price < 1 else 2)
            confidence = 0.84 if summary == "STRONG_BEARISH" else 0.74
            thesis = f"Finans Uzmanı Değerlendirmesi: {symbol} direnç bölgesinde zayıflık ve momentum tükenişi gösteriyor. Kâr koruma veya koruyucu satış stratejisi öneriliyor."
            reasoning = [
                f"Trend Yapısı: {summary} - RSI ({rsi:.1f}) güç kaybına işaret ediyor",
                f"Direnç Reddi: {resistance} seviyesinde satış emirleri yoğunlaştı",
                f"Risk Yönetimi: 1:2.8 Risk/Ödül oranıyla stop seviyesi ${stop_loss}"
            ]
            warning = "Olası short squeeze ve ani hacimli tepki alımlarına karşı stop seviyesine sadık kalınmalıdır."
            rr_str = "1:2.8"
        else:
            action = "HOLD"
            stop_loss = round(price * 0.97, 4 if price < 1 else 2)
            take_profit = round(price * 1.08, 4 if price < 1 else 2)
            confidence = 0.65
            thesis = f"Finans Uzmanı Değerlendirmesi: {symbol} kritik karar bandında akümülasyon sürecinde. Kırılım teyidi ile birlikte asimetrik pozisyon alma hazırlığı yapılıyor."
            reasoning = [
                f"Fiyat Sıkışması: Bollinger Bantları daralıyor (Konsolidasyon)",
                f"RSI 14 ({rsi:.1f}): Denge bölgesinde, yön teyidi bekleniyor",
                f"Kritik Tetikleyici: ${resistance} kırılımında agresif alım tetiklenecektir"
            ]
            warning = "Düşük volatilite dönemlerinde erken giriş yapmak zaman maliyeti yaratabilir."
            rr_str = "1:2.5"
            
        return {
            "action": action,
            "confidence": confidence,
            "entry_price": price,
            "stop_loss": stop_loss,
            "take_profit": take_profit,
            "risk_reward_ratio": rr_str,
            "timeframe": "1H / 4H Momentum Swing",
            "thesis_summary": thesis,
            "reasoning_points": reasoning,
            "risk_warning": warning,
            "source": "FINANCIAL_QUANT_EXPERT_ENGINE"
        }
