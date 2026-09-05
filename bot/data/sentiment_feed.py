import requests
from typing import Dict, Any

class SentimentFeed:
    """
    Piyasa genel duygu durumunu ve Fear & Greed (Korku & Açgözlülük)
    endeksini çeken servis.
    """
    FNG_URL = "https://api.alternative.me/fng/?limit=1"

    @classmethod
    def get_crypto_fear_and_greed(cls) -> Dict[str, Any]:
        """Kripto Korku ve Açgözlülük Endeksini çeker."""
        try:
            resp = requests.get(cls.FNG_URL, timeout=8)
            resp.raise_for_status()
            data = resp.json()
            item = data.get("data", [{}])[0]
            val = int(item.get("value", 50))
            classification = item.get("value_classification", "Neutral")
            
            # Türkçe karşılık
            tr_map = {
                "Extreme Fear": "Aşırı Korku (Alım Fırsatı Olabilir)",
                "Fear": "Korku",
                "Neutral": "Nötr",
                "Greed": "Açgözlülük",
                "Extreme Greed": "Aşırı Açgözlülük (Düzeltme Riski)"
            }
            
            return {
                "value": val,
                "classification": classification,
                "label_tr": tr_map.get(classification, classification),
                "timestamp": item.get("timestamp", "")
            }
        except Exception as e:
            return {
                "value": 50,
                "classification": "Neutral",
                "label_tr": "Nötr (Veri Alınamadı)",
                "error": str(e)
            }
