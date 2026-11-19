"""
Component 4: Data Preprocessor & Feature Transformer
Cleans, normalizes, and transforms transaction text and numerical attributes into
contextual multivariate feature vectors for anomaly detection, categorization, and forecasting.
"""

import re
import math
import numpy as np
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional, Tuple


def clean_text(text: str) -> str:
    """Cleans and standardizes raw transaction descriptions for NLP models."""
    if not isinstance(text, str):
        return ""
    text = text.lower()
    text = re.sub(r'ref:[a-f0-9]+', 'ref_id', text)
    text = re.sub(r'inr\s*[\d\.,]+', 'inr_amount', text)
    text = re.sub(r'usd\s*[\d\.,]+', 'usd_amount', text)
    text = re.sub(r'[\d]{4,}', 'num_token', text)
    text = re.sub(r'[^\w\s]', ' ', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text


class FeatureTransformer:
    def __init__(self):
        self.version = "v3.0.0-context-multivariate"

    def clean_text(self, text: str) -> str:
        return clean_text(text)

    def extract_temporal_features(self, dt: datetime) -> Dict[str, float]:
        """Extracts cyclical hour, day-of-week, and calendar context."""
        hour = dt.hour if hasattr(dt, 'hour') else 12
        dow = dt.weekday() if hasattr(dt, 'weekday') else 2
        dom = dt.day if hasattr(dt, 'day') else 15

        sin_hour = math.sin(2 * math.pi * hour / 24.0)
        cos_hour = math.cos(2 * math.pi * hour / 24.0)
        sin_dow = math.sin(2 * math.pi * dow / 7.0)
        cos_dow = math.cos(2 * math.pi * dow / 7.0)

        is_weekend = 1.0 if dow in (5, 6) else 0.0
        is_month_end = 1.0 if (dom >= 27 or dom <= 3) else 0.0

        return {
            "hour": float(hour),
            "sin_hour": sin_hour,
            "cos_hour": cos_hour,
            "dow": float(dow),
            "sin_dow": sin_dow,
            "cos_dow": cos_dow,
            "is_weekend": is_weekend,
            "is_month_end": is_month_end,
        }

    def compute_category_relative_features(
        self,
        amount_minor: int,
        category: str,
        category_stats: Optional[Dict[str, Any]] = None
    ) -> Dict[str, float]:
        """
        Computes robust amount features relative to the specific category's historical baseline
        using median, IQR, and MAD (Median Absolute Deviation) rather than raw mean/std alone.
        """
        amt = float(abs(amount_minor))
        log_amt = math.log1p(amt)

        if not category_stats or category_stats.get("count", 0) < 2:
            return {
                "log_amount": log_amt,
                "cat_ratio": 1.0,
                "cat_median_ratio": 1.0,
                "cat_z_score": 0.0,
                "cat_mad_z": 0.0,
                "is_cat_iqr_outlier": 0.0,
                "cat_mean": amt,
                "cat_std": 0.0,
                "cat_median": amt,
                "cat_mad": 0.0,
            }

        cat_mean = float(category_stats.get("mean", amt))
        cat_std = float(category_stats.get("std", 1.0))
        cat_median = float(category_stats.get("median", cat_mean))
        cat_mad = float(category_stats.get("mad", max(1.0, cat_std * 0.6745)))
        q75 = float(category_stats.get("q75", cat_median))
        iqr = float(category_stats.get("iqr", max(1.0, cat_median * 0.4)))

        cat_ratio = amt / (cat_mean + 1.0)
        cat_median_ratio = amt / (cat_median + 1.0)
        cat_z_score = (amt - cat_mean) / (cat_std + 1.0)
        # Robust Modified Z-Score (Iglewicz & Hoaglin): 0.6745 * (x - median) / MAD
        effective_mad = max(cat_mad, cat_median * 0.08, 100.0)
        cat_mad_z = 0.6745 * (amt - cat_median) / effective_mad
        is_iqr_outlier = 1.0 if amt > (q75 + 1.5 * iqr) else 0.0

        return {
            "log_amount": log_amt,
            "cat_ratio": cat_ratio,
            "cat_median_ratio": cat_median_ratio,
            "cat_z_score": cat_z_score,
            "cat_mad_z": cat_mad_z,
            "is_cat_iqr_outlier": is_iqr_outlier,
            "cat_mean": cat_mean,
            "cat_std": cat_std,
            "cat_median": cat_median,
            "cat_mad": cat_mad,
        }

    def compute_merchant_features(
        self,
        amount_minor: int,
        merchant: Optional[str],
        merchant_stats: Optional[Dict[str, Any]] = None
    ) -> Dict[str, float]:
        """Computes merchant familiarity and robust spend deviation."""
        amt = float(abs(amount_minor))
        if not merchant or not str(merchant).strip() or not merchant_stats or merchant_stats.get("count", 0) == 0:
            return {
                "merchant_novelty": 1.0,
                "merchant_count": 0.0,
                "merchant_z_score": 0.0,
                "merchant_mad_z": 0.0,
                "merchant_ratio": 1.0,
                "merchant_median_ratio": 1.0,
            }

        m_count = float(merchant_stats.get("count", 0))
        m_mean = float(merchant_stats.get("mean", amt))
        m_std = float(merchant_stats.get("std", 1.0))
        m_median = float(merchant_stats.get("median", m_mean))
        m_mad = float(merchant_stats.get("mad", max(1.0, m_std * 0.6745)))

        novelty = 1.0 / (1.0 + math.log1p(m_count))
        m_ratio = amt / (m_mean + 1.0)
        m_median_ratio = amt / (m_median + 1.0)
        m_z = (amt - m_mean) / (m_std + 1.0) if m_count >= 2 else 0.0
        effective_mad = max(m_mad, m_median * 0.08, 100.0)
        m_mad_z = (0.6745 * (amt - m_median) / effective_mad) if m_count >= 2 else 0.0

        return {
            "merchant_novelty": novelty,
            "merchant_count": m_count,
            "merchant_z_score": m_z,
            "merchant_mad_z": m_mad_z,
            "merchant_ratio": m_ratio,
            "merchant_median_ratio": m_median_ratio,
        }

    def build_feature_vector(
        self,
        amount_minor: int,
        category: str,
        transaction_type: str,
        merchant: Optional[str],
        dt: datetime,
        category_stats: Optional[Dict[str, Any]] = None,
        type_stats: Optional[Dict[str, Any]] = None,
        merchant_stats: Optional[Dict[str, Any]] = None,
        recent_velocity_7d: int = 1,
        currency_matches_workspace: bool = True,
        category_relevance_score: float = 0.0,
        merchant_category_mismatch_score: float = 0.0,
    ) -> Tuple[np.ndarray, Dict[str, Any]]:
        """
        Builds a 12-dimensional contextual numerical feature vector for multivariate Isolation Forest
        along with a structured factor map for explainable reporting.

        Indices:
        [0]  log_amount
        [1]  cat_median_ratio (robust amount / category median)
        [2]  cat_mad_z (robust modified Z-score vs category median/MAD)
        [3]  type_ratio (amount / type median)
        [4]  merchant_novelty (1.0 if new -> 0 if frequent)
        [5]  merchant_median_ratio
        [6]  log1p(velocity_7d)
        [7]  sin_dow
        [8]  cos_dow
        [9]  is_weekend
        [10] category_relevance_score (0..1)
        [11] merchant_category_mismatch_score (0..1)
        """
        temp = self.extract_temporal_features(dt)
        cat_feat = self.compute_category_relative_features(amount_minor, category, category_stats)
        merch_feat = self.compute_merchant_features(amount_minor, merchant, merchant_stats)

        amt = float(abs(amount_minor))
        type_ref = float(type_stats.get("median", type_stats.get("mean", amt))) if type_stats else amt
        type_ratio = amt / (type_ref + 1.0)

        feature_vec = np.array([
            cat_feat["log_amount"],
            min(50.0, cat_feat["cat_median_ratio"]),
            max(-5.0, min(25.0, cat_feat["cat_mad_z"])),
            min(50.0, type_ratio),
            merch_feat["merchant_novelty"],
            min(50.0, merch_feat["merchant_median_ratio"]),
            math.log1p(max(0, recent_velocity_7d)),
            temp["sin_dow"],
            temp["cos_dow"],
            temp["is_weekend"],
            float(max(0.0, min(1.0, category_relevance_score))),
            float(max(0.0, min(1.0, merchant_category_mismatch_score))),
        ], dtype=np.float32)

        factor_map = {
            "amount_minor": amount_minor,
            "category": category,
            "transaction_type": transaction_type,
            "merchant": merchant,
            "temporal": temp,
            "category_relative": cat_feat,
            "merchant_relative": merch_feat,
            "type_ratio": type_ratio,
            "velocity_7d": recent_velocity_7d,
            "currency_matches": currency_matches_workspace,
            "category_relevance_score": category_relevance_score,
            "merchant_category_mismatch_score": merchant_category_mismatch_score,
        }

        return feature_vec, factor_map


feature_transformer = FeatureTransformer()
