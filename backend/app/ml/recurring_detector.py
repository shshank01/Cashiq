from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Any
import numpy as np

class RecurringTransactionDetector:
    """
    Statistical pattern-based recurring payment detector.
    Analyzes transaction intervals, merchant regularity, and amount variance.
    """

    def detect(self, transactions: List[Any]) -> List[Dict[str, Any]]:
        if not transactions or len(transactions) < 2:
            return []

        # Group transactions by normalized merchant or description
        groups = defaultdict(list)
        for t in transactions:
            key = (t.merchant if hasattr(t, 'merchant') and t.merchant else (t.description if hasattr(t, 'description') else t.get('description', ''))).strip().lower()
            if key:
                dt = t.date if hasattr(t, 'date') else datetime.fromisoformat(str(t['date']))
                if isinstance(dt, str):
                    try:
                        dt = datetime.fromisoformat(dt)
                    except Exception:
                        dt = datetime.now(timezone.utc)
                if hasattr(dt, 'tzinfo') and dt.tzinfo:
                    dt = dt.astimezone(timezone.utc)
                else:
                    dt = dt.replace(tzinfo=timezone.utc)

                amt = abs(t.amount_minor if hasattr(t, 'amount_minor') else t['amount_minor'])
                ttype = t.type if hasattr(t, 'type') else t.get('type', 'expense')
                cat = t.category_name if hasattr(t, 'category_name') else t.get('category_name', '')
                raw_m = (t.merchant if hasattr(t, 'merchant') and t.merchant else (t.get('merchant') if isinstance(t, dict) else None)) or (t.description if hasattr(t, 'description') else (t.get('description') if isinstance(t, dict) else ''))
                groups[key].append({
                    "raw_merchant": raw_m,
                    "date": dt,
                    "amount": amt,
                    "type": ttype,
                    "category": cat
                })

        recurring_rules = []
        now = datetime.now(timezone.utc)

        for key, txs in groups.items():
            if len(txs) < 2:
                continue

            # Sort chronologically
            txs.sort(key=lambda x: x["date"])
            
            # Check amounts consistency
            amounts = [x["amount"] for x in txs]
            mean_amt = np.mean(amounts)
            std_amt = np.std(amounts)
            cv_amt = std_amt / (mean_amt + 1e-6)

            # High variance in amount is likely not a fixed recurring rule unless it's a utility
            if cv_amt > 0.35 and len(txs) < 3:
                continue

            # Calculate intervals in days
            intervals = [(txs[i]["date"].date() - txs[i-1]["date"].date()).days for i in range(1, len(txs))]
            if not intervals:
                continue

            median_interval = np.median(intervals)
            frequency = None
            step_days = 30

            if 6 <= median_interval <= 8:
                frequency = "weekly"
                step_days = 7
            elif 13 <= median_interval <= 16:
                frequency = "bi-weekly"
                step_days = 14
            elif 25 <= median_interval <= 35:
                frequency = "monthly"
                step_days = 30
            elif 80 <= median_interval <= 100:
                frequency = "quarterly"
                step_days = 90
            elif 340 <= median_interval <= 380:
                frequency = "yearly"
                step_days = 365
            else:
                # If >= 2 events and interval standard deviation is small (< 4 days) and median_interval >= 5
                if len(intervals) >= 2 and np.std(intervals) < 4.0 and median_interval >= 5:
                    frequency = "monthly" if median_interval < 45 else "custom"
                    step_days = max(5, int(median_interval))

            if frequency and step_days > 0:
                last_tx_date = txs[-1]["date"]
                next_date = last_tx_date + timedelta(days=step_days)
                
                # If next_date is in the past, roll forward until future with safety cap
                max_iterations = 200
                while next_date < now and max_iterations > 0:
                    next_date += timedelta(days=step_days)
                    max_iterations -= 1

                # Confidence based on count and consistency
                consistency_score = max(0.5, 1.0 - cv_amt)
                count_score = min(1.0, len(txs) / 5.0)
                confidence = round(float(0.5 * consistency_score + 0.5 * count_score), 2)

                recurring_rules.append({
                    "merchant": txs[-1]["raw_merchant"] or key.title(),
                    "description": f"Recurring {frequency} {txs[-1]['category'] or 'payment'}",
                    "amount_minor": int(np.median(amounts)),
                    "currency": "USD",
                    "frequency": frequency,
                    "next_date": next_date.isoformat(),
                    "confidence": confidence,
                    "type": txs[-1]["type"],
                    "status": "active",
                    "category_name": txs[-1]["category"]
                })

        return recurring_rules

recurring_detector_instance = RecurringTransactionDetector()
