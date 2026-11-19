"""
Component 6: Model Builder
Manages separate models for transaction categorization, anomaly detection,
and cash-flow forecasting.
"""

import os
import joblib
import numpy as np
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional, Tuple
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import IsolationForest

from app.ml.architecture.feature_transformer import clean_text, feature_transformer


class CategorizerBuilder:
    def __init__(self):
        self.version = "v1.2.1-adaptive-logreg"

    def train_model(
        self,
        texts: List[str],
        labels: List[str],
        max_features: int = 15000
    ) -> Dict[str, Any]:
        """Trains TF-IDF + LogisticRegression model on text and category labels."""
        if len(texts) < 10 or len(set(labels)) < 2:
            raise ValueError("Insufficient training samples or classes to train categorizer.")

        cleaned_texts = [clean_text(t) for t in texts]

        vectorizer = TfidfVectorizer(
            ngram_range=(1, 2),
            sublinear_tf=True,
            min_df=1,
            max_features=max_features
        )
        X_vec = vectorizer.fit_transform(cleaned_texts)

        model = LogisticRegression(
            C=2.0,
            max_iter=1000,
            class_weight="balanced",
            random_state=42
        )
        model.fit(X_vec, labels)

        classes = list(model.classes_)
        return {
            "model": model,
            "vectorizer": vectorizer,
            "classes": classes,
            "model_version": self.version,
            "sample_count": len(texts),
            "classes_count": len(classes)
        }


class AnomalyDetectorBuilder:
    def __init__(self):
        self.version = "v2.0.0-multivariate-isoforest"

    def build_category_baselines(self, historical_transactions: List[Any]) -> Dict[str, Dict[str, Any]]:
        """
        Builds separate robust behavioural baselines for each category.
        Computes count, mean, std, median, q25, q75, iqr, and max_legitimate.
        """
        cat_amounts: Dict[str, List[int]] = {}
        for t in historical_transactions:
            c = getattr(t, 'category_name', None) or (t.get('category_name') if isinstance(t, dict) else None)
            if not c:
                c = "Miscellaneous"
            amt = abs(int(getattr(t, 'amount_minor', 0) if hasattr(t, 'amount_minor') else (t.get('amount_minor', 0) if isinstance(t, dict) else 0)))
            cat_amounts.setdefault(c, []).append(amt)

        baselines = {}
        for cat, amounts in cat_amounts.items():
            if not amounts:
                continue
            arr = np.array(amounts, dtype=np.float64)
            cnt = len(arr)
            mean_val = float(np.mean(arr))
            std_val = float(np.std(arr)) if cnt > 1 else max(100.0, mean_val * 0.2)
            med_val = float(np.median(arr))
            q25_val = float(np.percentile(arr, 25))
            q75_val = float(np.percentile(arr, 75))
            iqr_val = float(q75_val - q25_val)
            max_legit = float(np.max(arr))

            baselines[cat] = {
                "count": cnt,
                "mean": mean_val,
                "std": max(1.0, std_val),
                "median": med_val,
                "q25": q25_val,
                "q75": q75_val,
                "iqr": max(1.0, iqr_val),
                "max_legitimate": max_legit,
                "last_updated": datetime.now(timezone.utc).isoformat()
            }
        return baselines

    def build_merchant_baselines(self, historical_transactions: List[Any]) -> Dict[str, Dict[str, Any]]:
        """Builds behavioural baselines per merchant."""
        merch_amounts: Dict[str, List[int]] = {}
        for t in historical_transactions:
            m = getattr(t, 'merchant', None) or (t.get('merchant') if isinstance(t, dict) else None)
            if not m or not str(m).strip():
                continue
            amt = abs(int(getattr(t, 'amount_minor', 0) if hasattr(t, 'amount_minor') else (t.get('amount_minor', 0) if isinstance(t, dict) else 0)))
            merch_amounts.setdefault(str(m).strip(), []).append(amt)

        baselines = {}
        for merch, amounts in merch_amounts.items():
            arr = np.array(amounts, dtype=np.float64)
            cnt = len(arr)
            baselines[merch] = {
                "count": cnt,
                "mean": float(np.mean(arr)),
                "std": float(np.std(arr)) if cnt > 1 else float(np.mean(arr) * 0.2),
                "max": float(np.max(arr)),
                "last_updated": datetime.now(timezone.utc).isoformat()
            }
        return baselines

    def train_multivariate_forest(
        self,
        feature_matrix: np.ndarray,
        contamination: float = 0.05
    ) -> IsolationForest:
        """Trains a multivariate Isolation Forest on multi-dimensional feature vectors."""
        clf = IsolationForest(
            contamination=contamination,
            random_state=42,
            n_estimators=100,
            max_samples="auto"
        )
        clf.fit(feature_matrix)
        return clf


class ModelBuilder:
    def __init__(self):
        self.categorizer_builder = CategorizerBuilder()
        self.anomaly_detector_builder = AnomalyDetectorBuilder()

    def build_categorizer(self, texts: List[str], labels: List[str]) -> Dict[str, Any]:
        return self.categorizer_builder.train_model(texts, labels)

    def build_anomaly_baselines(self, historical_transactions: List[Any]) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        cat_base = self.anomaly_detector_builder.build_category_baselines(historical_transactions)
        merch_base = self.anomaly_detector_builder.build_merchant_baselines(historical_transactions)
        return cat_base, merch_base

    def train_isolation_forest(self, feature_matrix: np.ndarray, contamination: float = 0.05) -> IsolationForest:
        return self.anomaly_detector_builder.train_multivariate_forest(feature_matrix, contamination)


model_builder = ModelBuilder()
