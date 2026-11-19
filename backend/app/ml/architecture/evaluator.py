"""
Component 7: Evaluator
Evaluates models using suitable quantitative metrics:
- Categorization: Precision, Recall, F1-Score, Accuracy, Confusion Matrix
- Anomaly Detection: Anomaly flag rate, Score Distribution, False-Positive Rate from Feedback
- Cash Flow Forecasting: MAE, RMSE, MAPE
"""

import numpy as np
from typing import Dict, Any, List, Optional
from sklearn.metrics import accuracy_score, precision_recall_fscore_support, classification_report, confusion_matrix


class MLEvaluator:
    def evaluate_categorizer(
        self,
        y_true: List[str],
        y_pred: List[str],
        classes: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """Calculates accuracy, precision, recall, and F1 metrics for categorization."""
        if not y_true or not y_pred or len(y_true) != len(y_pred):
            return {"error": "Invalid ground truth or predictions"}

        acc = float(accuracy_score(y_true, y_pred))
        p_wt, r_wt, f1_wt, _ = precision_recall_fscore_support(y_true, y_pred, average="weighted", zero_division=0)
        p_mac, r_mac, f1_mac, _ = precision_recall_fscore_support(y_true, y_pred, average="macro", zero_division=0)

        report = classification_report(y_true, y_pred, output_dict=True, zero_division=0)

        unique_labels = sorted(list(set(y_true) | set(y_pred)))
        cm = confusion_matrix(y_true, y_pred, labels=unique_labels).tolist()

        return {
            "sample_count": len(y_true),
            "accuracy": round(acc, 4),
            "weighted_precision": round(float(p_wt), 4),
            "weighted_recall": round(float(r_wt), 4),
            "weighted_f1": round(float(f1_wt), 4),
            "macro_f1": round(float(f1_mac), 4),
            "per_class": report,
            "confusion_matrix": cm,
            "classes": unique_labels
        }

    def evaluate_anomaly_detector(
        self,
        anomaly_scores: List[float],
        is_anomaly_flags: List[bool],
        ground_truth_feedbacks: Optional[List[Dict[str, Any]]] = None
    ) -> Dict[str, Any]:
        """
        Evaluates anomaly detector behavior:
        - contamination rate (% flagged)
        - average score for normal vs flagged
        - false positive rate against confirmed user feedback
        """
        n = len(anomaly_scores)
        if n == 0:
            return {"sample_count": 0, "flagged_count": 0}

        flagged_count = sum(1 for f in is_anomaly_flags if f)
        contamination_rate = flagged_count / n

        scores_arr = np.array(anomaly_scores)
        avg_score = float(np.mean(scores_arr))
        p90_score = float(np.percentile(scores_arr, 90))

        # Check user ground truth feedback if available
        fp_rate = 0.0
        feedback_count = 0
        if ground_truth_feedbacks:
            feedback_count = len(ground_truth_feedbacks)
            legit_count = sum(1 for fb in ground_truth_feedbacks if fb.get("feedback_type") == "legitimate")
            fp_rate = (legit_count / feedback_count) if feedback_count > 0 else 0.0

        return {
            "sample_count": n,
            "flagged_count": flagged_count,
            "contamination_rate": round(contamination_rate, 4),
            "mean_anomaly_score": round(avg_score, 4),
            "p90_anomaly_score": round(p90_score, 4),
            "feedback_verified_count": feedback_count,
            "false_positive_rate": round(fp_rate, 4)
        }

    def evaluate_forecaster(
        self,
        actual_series: List[float],
        predicted_series: List[float]
    ) -> Dict[str, Any]:
        """Calculates MAE, RMSE, and MAPE for cash-flow predictions."""
        if not actual_series or not predicted_series or len(actual_series) != len(predicted_series):
            return {"mae": None, "rmse": None, "mape": None}

        actual = np.array(actual_series, dtype=np.float64)
        pred = np.array(predicted_series, dtype=np.float64)

        errors = actual - pred
        mae = float(np.mean(np.abs(errors)))
        rmse = float(np.sqrt(np.mean(errors ** 2)))

        # Non-zero MAPE
        non_zeros = actual != 0
        if np.any(non_zeros):
            mape = float(np.mean(np.abs(errors[non_zeros] / actual[non_zeros]))) * 100.0
        else:
            mape = 0.0

        return {
            "mae": round(mae, 2),
            "rmse": round(rmse, 2),
            "mape_percent": round(mape, 2),
            "data_points": len(actual)
        }


evaluator = MLEvaluator()
