import numpy as np
from typing import List, Dict, Any, Optional
from sklearn.ensemble import IsolationForest

class AnomalyDetector:
    def __init__(self):
        self.model_version = "v1.1.0-iqr-zscore-isoforest"

    def analyze_transaction(
        self,
        current_amount_minor: int,
        category: str,
        merchant: Optional[str],
        historical_transactions: List[Any]
    ) -> Dict[str, Any]:
        """
        Analyzes a single transaction against historical business behavior using
        IQR, Z-score, category spend multiples, and Isolation Forest.
        """
        if not historical_transactions or len(historical_transactions) < 5:
            return {
                "is_anomaly": False,
                "anomaly_score": 0.0,
                "severity": None,
                "reason": None,
                "model_version": self.model_version
            }

        # Extract historical amounts (positive absolute values in minor units)
        all_amounts = [abs(t.amount_minor if hasattr(t, 'amount_minor') else t['amount_minor']) for t in historical_transactions]
        cat_amounts = [
            abs(t.amount_minor if hasattr(t, 'amount_minor') else t['amount_minor'])
            for t in historical_transactions
            if (t.category_name if hasattr(t, 'category_name') else t.get('category_name')) == category
        ]
        
        target_amount = abs(current_amount_minor)
        
        # 1. Category-specific multiplier check
        cat_reason = None
        cat_score = 0.0
        if len(cat_amounts) >= 3:
            cat_mean = np.mean(cat_amounts)
            if cat_mean > 0:
                multiple = target_amount / cat_mean
                if multiple >= 2.0:
                    cat_score = min(1.0, 0.4 + (multiple / 6.0) * 0.6)
                    cat_reason = f"{category} expense is {multiple:.1f}× higher than the business's normal average of ${cat_mean/100:,.2f} for this category."

        # 2. Z-score calculation
        mean_all = np.mean(all_amounts)
        std_all = np.std(all_amounts)
        z_score = (target_amount - mean_all) / (std_all + 1e-6)
        
        # 3. IQR calculation
        q25, q75 = np.percentile(all_amounts, [25, 75])
        iqr = q75 - q25
        iqr_upper_mild = q75 + 1.5 * iqr
        iqr_upper_extreme = q75 + 3.0 * iqr
        
        iqr_flag = target_amount > iqr_upper_mild
        extreme_iqr_flag = target_amount > iqr_upper_extreme

        # 4. Isolation Forest
        iso_score = 0.0
        try:
            if len(all_amounts) >= 15:
                X = np.array(all_amounts).reshape(-1, 1)
                clf = IsolationForest(contamination=0.05, random_state=42)
                clf.fit(X)
                # decision_function: lower means more abnormal
                df_val = clf.decision_function([[target_amount]])[0]
                iso_score = max(0.0, min(1.0, 0.5 - df_val))
        except Exception:
            iso_score = 0.0

        # Combine scores
        combined_score = max(
            cat_score,
            min(1.0, max(0.0, z_score / 4.0)),
            0.75 if extreme_iqr_flag else (0.55 if iqr_flag else 0.0),
            iso_score
        )

        is_anomaly = combined_score >= 0.50 or cat_score >= 0.50

        if not is_anomaly:
            return {
                "is_anomaly": False,
                "anomaly_score": round(float(combined_score), 3),
                "severity": None,
                "reason": None,
                "model_version": self.model_version
            }

        # Determine severity and reason
        if combined_score >= 0.80 or (cat_score >= 0.80):
            severity = "critical"
        elif combined_score >= 0.65:
            severity = "high"
        elif combined_score >= 0.50:
            severity = "medium"
        else:
            severity = "low"

        reason = cat_reason
        if not reason:
            if z_score >= 2.5:
                reason = f"Transaction amount of ${target_amount/100:,.2f} is significantly unusual (Z-score: {z_score:.1f}) compared to historical spending average."
            elif extreme_iqr_flag:
                reason = f"Transaction amount of ${target_amount/100:,.2f} is an extreme statistical outlier (3.0× IQR above Q3 threshold)."
            elif iqr_flag:
                reason = f"Transaction amount of ${target_amount/100:,.2f} is higher than the typical spending range (1.5× IQR above Q3)."
            else:
                reason = f"Multivariate Isolation Forest flagged unusual expenditure pattern for merchant {merchant or 'vendor'}."

        return {
            "is_anomaly": True,
            "anomaly_score": round(float(combined_score), 3),
            "severity": severity,
            "reason": reason,
            "model_version": self.model_version
        }

anomaly_detector_instance = AnomalyDetector()
