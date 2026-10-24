from typing import Dict, Any
from datetime import datetime, timezone

# Standard reference market rate (1 USD = 83.50 INR)
DEFAULT_USD_TO_INR = 83.50

class FxService:
    @staticmethod
    def get_rates() -> Dict[str, Any]:
        return {
            "base": "USD",
            "rates": {
                "USD": 1.0,
                "INR": DEFAULT_USD_TO_INR,
            },
            "usd_to_inr": DEFAULT_USD_TO_INR,
            "inr_to_usd": round(1.0 / DEFAULT_USD_TO_INR, 6),
            "last_updated": datetime.now(timezone.utc).isoformat()
        }

    @staticmethod
    def convert(amount: float, from_curr: str, to_curr: str, custom_rate: float = None) -> Dict[str, Any]:
        from_c = (from_curr or "USD").upper()
        to_c = (to_curr or "INR").upper()
        
        rate = custom_rate if (custom_rate is not None and custom_rate > 0) else DEFAULT_USD_TO_INR

        if from_c == to_c:
            converted = amount
            effective_rate = 1.0
        elif from_c == "USD" and to_c == "INR":
            effective_rate = rate
            converted = amount * effective_rate
        elif from_c == "INR" and to_c == "USD":
            effective_rate = 1.0 / rate
            converted = amount * effective_rate
        else:
            effective_rate = 1.0
            converted = amount

        return {
            "amount": round(amount, 2),
            "from_currency": from_c,
            "to_currency": to_c,
            "rate": round(effective_rate, 6),
            "usd_to_inr_rate": rate,
            "converted_amount": round(converted, 2),
            "converted_amount_minor": int(round(converted * 100)),
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
