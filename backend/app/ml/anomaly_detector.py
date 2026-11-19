"""
CashIQ Business-Context-Aware Adaptive Anomaly Detector (v3.0.0).

Key capabilities:
1. Business-context operational relevance: evaluates expenses against the workspace's
   business profile (industry, business type, operating model, learned categories)
   distinguishing expected, unusual, unrelated, and unknown expenses — keeping
   operational irrelevance explicitly separate from unusual spending amounts.
2. Merchant normalization & merchant-category consistency: normalizes gateway prefixes,
   UPI handles, punctuation, and aliases; learns merchant-category pairs per business;
   flags mismatches while honoring verified legitimate exceptions and treating unfamiliar
   merchants neutrally.
3. Robust amount anomaly detection: uses median, IQR, and MAD (Modified Z-Score) per
   (category, type) and merchant context with minimum sample requirements and
   currency-aware cold-start handling. Raw historical maximums never suppress anomalies.
4. Contextual Isolation Forest: each historical transaction is featurized using its OWN
   category, type, merchant, velocity, and relevance baselines (never the current
   transaction's baselines).
5. Calibrated multi-signal fusion: every calculated signal (amount deviation, category
   relevance, merchant-category mismatch, merchant behavior spike, frequency/timing,
   and multivariate isolation) contributes transparently to the final score and
   structured explanation.
6. Feedback integration: handles `legitimate`, `incorrect_category`, and
   `genuine_anomaly` (plus legacy `suspicious`), adapting baselines for verified
   patterns without permanently disabling detection of new risk patterns.
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
import math
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
from sklearn.ensemble import IsolationForest

from app.ml.architecture.feature_transformer import feature_transformer
from app.ml.business_taxonomy import (
    canonicalize_category,
    evaluate_category_relevance,
    extract_profile_dict,
)
from app.ml.merchant_normalizer import (
    evaluate_merchant_category_consistency,
    normalize_merchant_name,
)


# Currency approximate minor-unit scale relative to USD cents (used for cold-start benchmarks only)
CURRENCY_USD_SCALE: Dict[str, float] = {
    "USD": 1.0,
    "EUR": 0.92,
    "GBP": 0.79,
    "CAD": 1.36,
    "AUD": 1.52,
    "SGD": 1.34,
    "AED": 3.67,
    "INR": 83.5,
}

# Sensible SME Category Cold-Start Benchmarks (in USD cents / minor units; scaled per currency)
DEFAULT_CATEGORY_BENCHMARKS: Dict[str, Dict[str, float]] = {
    "Software & Cloud Services": {"median": 120000, "mad": 65000, "max_normal": 1000000},
    "Payroll & Wages": {"median": 1500000, "mad": 500000, "max_normal": 5000000},
    "Rent & Facilities": {"median": 450000, "mad": 120000, "max_normal": 1500000},
    "Marketing & Advertising": {"median": 250000, "mad": 130000, "max_normal": 2000000},
    "Professional & Legal": {"median": 350000, "mad": 200000, "max_normal": 2500000},
    "Meals & Entertainment": {"median": 6500, "mad": 3500, "max_normal": 50000},
    "Office Supplies & Equipment": {"median": 18000, "mad": 10000, "max_normal": 150000},
    "Travel & Transportation": {"median": 25000, "mad": 15000, "max_normal": 200000},
    "Utilities & Telecom": {"median": 20000, "mad": 10000, "max_normal": 120000},
    "Taxes & Compliance": {"median": 250000, "mad": 150000, "max_normal": 2000000},
    "Insurance": {"median": 80000, "mad": 40000, "max_normal": 600000},
    "Banking & Fees": {"median": 5000, "mad": 3000, "max_normal": 50000},
    "Equipment & Hardware": {"median": 150000, "mad": 100000, "max_normal": 1500000},
    "Shipping & Logistics": {"median": 30000, "mad": 20000, "max_normal": 300000},
    "Inventory & Raw Materials": {"median": 250000, "mad": 150000, "max_normal": 2500000},
    "Groceries & Ingredients": {"median": 20000, "mad": 12000, "max_normal": 200000},
    "Medical Supplies & Equipment": {"median": 100000, "mad": 60000, "max_normal": 1000000},
    "Construction & Site Materials": {"median": 300000, "mad": 180000, "max_normal": 3000000},
    "Agricultural Supplies": {"median": 120000, "mad": 70000, "max_normal": 1200000},
    "Personal & Household": {"median": 10000, "mad": 6000, "max_normal": 100000},
    "Client Revenue": {"median": 1200000, "mad": 600000, "max_normal": 10000000},
    "Loans & Financing": {"median": 500000, "mad": 180000, "max_normal": 3000000},
    "Miscellaneous": {"median": 10000, "mad": 8000, "max_normal": 100000},
}


@dataclass
class AnomalyConfig:
    """Configurable weights, minimum sample sizes, and thresholds for calibrated anomaly scoring."""
    # Minimum sample requirements before relying on empirical baselines
    min_category_samples: int = 3
    min_robust_iqr_samples: int = 4
    min_merchant_samples: int = 3
    min_isolation_forest_samples: int = 12

    # Calibrated channel weights (sum = 1.0 for blended multi-signal score)
    weights: Dict[str, float] = field(default_factory=lambda: {
        "amount_deviation": 0.30,
        "category_relevance": 0.24,
        "merchant_category_consistency": 0.18,
        "merchant_behavior": 0.12,
        "frequency_timing": 0.08,
        "multivariate_isolation": 0.08,
    })

    # Alert thresholds
    overall_alert_threshold: float = 0.50
    operational_relevance_threshold: float = 0.65
    merchant_mismatch_threshold: float = 0.60
    amount_channel_threshold: float = 0.55
    merchant_spike_threshold: float = 0.60
    frequency_timing_threshold: float = 0.65

    # Robust amount deviation parameters
    mad_mild_threshold: float = 3.5
    mad_extreme_threshold: float = 6.0
    median_multiple_alert: float = 2.2
    merchant_spike_multiple: float = 2.8
    cold_start_benchmark_multiple: float = 2.5

    # Severity cutoffs
    severity_critical: float = 0.80
    severity_high: float = 0.65
    severity_medium: float = 0.50


def _get_field(obj: Any, key: str, default: Any = None) -> Any:
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def _parse_dt(val: Any, fallback: datetime) -> datetime:
    if isinstance(val, datetime):
        return val if val.tzinfo else val.replace(tzinfo=timezone.utc)
    if isinstance(val, str) and val.strip():
        try:
            dt = datetime.fromisoformat(val.replace("Z", "+00:00"))
            return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
        except Exception:
            pass
    return fallback


def _currency_symbol(currency: str) -> str:
    c = (currency or "USD").upper()
    return {"USD": "$", "INR": "₹", "EUR": "€", "GBP": "£"}.get(c, f"{c} ")


def _compute_robust_stats(amounts: List[int]) -> Dict[str, Any]:
    """Computes robust location and scale statistics (median, IQR, MAD, plus mean/std)."""
    arr = np.array(amounts, dtype=np.float64)
    cnt = len(arr)
    med = float(np.median(arr))
    q25, q75 = np.percentile(arr, [25, 75])
    iqr = float(max(0.0, q75 - q25))
    abs_devs = np.abs(arr - med)
    raw_mad = float(np.median(abs_devs))
    # Fallback scale if all values are identical (MAD == 0)
    mean_val = float(np.mean(arr))
    std_val = float(np.std(arr)) if cnt > 1 else max(1.0, med * 0.20)
    scaled_mad = raw_mad if raw_mad > 0 else max(iqr / 1.349, std_val * 0.6745, med * 0.08, 100.0)
    effective_iqr = iqr if iqr > 0 else max(scaled_mad * 1.349, med * 0.25, 100.0)

    return {
        "count": cnt,
        "mean": mean_val,
        "std": max(1.0, std_val),
        "median": med,
        "mad": scaled_mad,
        "raw_mad": raw_mad,
        "q25": float(q25),
        "q75": float(q75),
        "iqr": effective_iqr,
        "p90": float(np.percentile(arr, 90)),
        "p95": float(np.percentile(arr, 95)),
        "min": float(np.min(arr)),
        "max": float(np.max(arr)),
        "is_cold_start": False,
    }


def _cold_start_category_stats(category: str, currency: str, observed_count: int = 0) -> Dict[str, Any]:
    scale = CURRENCY_USD_SCALE.get((currency or "USD").upper(), 1.0)
    bench = DEFAULT_CATEGORY_BENCHMARKS.get(category, DEFAULT_CATEGORY_BENCHMARKS["Miscellaneous"])
    med = float(bench["median"] * scale)
    mad = float(bench["mad"] * scale)
    max_norm = float(bench["max_normal"] * scale)
    return {
        "count": observed_count,
        "mean": med,
        "std": mad * 1.4826,
        "median": med,
        "mad": mad,
        "raw_mad": mad,
        "q25": med * 0.65,
        "q75": med * 1.35,
        "iqr": med * 0.70,
        "p90": med * 1.8,
        "p95": max_norm,
        "min": med * 0.1,
        "max": max_norm,
        "max_normal": max_norm,
        "is_cold_start": True,
    }


class AnomalyDetector:
    def __init__(self, config: Optional[AnomalyConfig] = None):
        self.config = config or AnomalyConfig()
        self.model_version = "v3.0.0-business-context-multivariate"
        self._fitted_forests: Dict[str, IsolationForest] = {}

    def _filter_clean_history(self, historical_transactions: List[Any]) -> Tuple[List[Any], List[Any], Dict[str, int]]:
        """
        Separates clean baseline transactions from confirmed genuine anomalies / unverified anomalies,
        and counts verified transactions per category for gradual business-profile personalization.
        """
        clean_txs: List[Any] = []
        confirmed_legit_txs: List[Any] = []
        verified_cat_counts: Dict[str, int] = {}

        for t in historical_transactions or []:
            fb = str(_get_field(t, "anomaly_feedback_status", "") or "").lower().strip()
            is_anom = bool(_get_field(t, "is_anomaly", False))
            is_conf = bool(_get_field(t, "is_confirmed", False)) or bool(_get_field(t, "verified_label", None))

            # Confirmed genuine anomalies / suspicious NEVER enter normal baselines
            if fb in {"suspicious", "genuine_anomaly", "genuine anomaly"}:
                continue

            # Unreviewed anomalies also do not pollute normal amount baselines
            if is_anom and fb != "legitimate":
                continue

            clean_txs.append(t)

            if fb == "legitimate":
                confirmed_legit_txs.append(t)

            # Count verified transactions for gradual expense-profile personalization
            t_cat = _get_field(t, "category_name")
            if t_cat and (fb == "legitimate" or is_conf):
                cc = canonicalize_category(t_cat)
                verified_cat_counts[cc] = verified_cat_counts.get(cc, 0) + 1

        return clean_txs, confirmed_legit_txs, verified_cat_counts

    def extract_stats_from_history(
        self,
        category: str,
        transaction_type: str,
        merchant: Optional[str],
        historical_transactions: List[Any],
        currency: str = "USD",
        learned_profiles: Optional[List[Dict[str, Any]]] = None,
    ) -> Tuple[Dict[str, Any], Dict[str, Any], Dict[str, Any], Dict[str, Any]]:
        """
        Calculates context-isolated robust baselines (median, IQR, MAD) for:
        1. (category, transaction_type) with fallback to category
        2. transaction_type
        3. canonical merchant (and merchant + category + type)
        4. explicitly confirmed legitimate scale bands (separate from raw historical max!)
        """
        clean_txs, confirmed_legit_txs, _ = self._filter_clean_history(historical_transactions)

        target_cat = canonicalize_category(category)
        target_type = str(transaction_type or "expense").lower().strip()
        target_norm_merch = normalize_merchant_name(merchant)["canonical"] if merchant else ""

        cat_type_amounts: List[int] = []
        cat_amounts: List[int] = []
        type_amounts: List[int] = []
        merch_amounts: List[int] = []
        ctx_amounts: List[int] = []  # (category, merchant, transaction_type)

        confirmed_cat_legit_amounts: List[int] = []
        confirmed_ctx_legit_amounts: List[int] = []

        for t in clean_txs:
            amt = abs(int(_get_field(t, "amount_minor", 0) or 0))
            if amt <= 0:
                continue
            t_cat = canonicalize_category(_get_field(t, "category_name"))
            t_type = str(_get_field(t, "type", _get_field(t, "transaction_type", "expense")) or "expense").lower().strip()
            t_merch = normalize_merchant_name(_get_field(t, "merchant"), _get_field(t, "description"))["canonical"]

            if t_type == target_type:
                type_amounts.append(amt)

            if t_cat == target_cat:
                cat_amounts.append(amt)
                if t_type == target_type:
                    cat_type_amounts.append(amt)

            if target_norm_merch and t_merch == target_norm_merch:
                merch_amounts.append(amt)
                if t_cat == target_cat and t_type == target_type:
                    ctx_amounts.append(amt)

        for t in confirmed_legit_txs:
            amt = abs(int(_get_field(t, "amount_minor", 0) or 0))
            if amt <= 0:
                continue
            t_cat = canonicalize_category(_get_field(t, "category_name"))
            t_type = str(_get_field(t, "type", _get_field(t, "transaction_type", "expense")) or "expense").lower().strip()
            t_merch = normalize_merchant_name(_get_field(t, "merchant"), _get_field(t, "description"))["canonical"]
            if t_cat == target_cat and t_type == target_type:
                confirmed_cat_legit_amounts.append(amt)
                if target_norm_merch and t_merch == target_norm_merch:
                    confirmed_ctx_legit_amounts.append(amt)

        # Also incorporate persisted confirmed legitimate bounds from BehavioralProfileModel
        for prof in learned_profiles or []:
            ptype = prof.get("profile_type")
            pkey = prof.get("profile_key", "")
            stats = prof.get("stats") or {}
            if ptype == "category" and canonicalize_category(pkey) == target_cat:
                ml = stats.get("max_verified_legitimate") or stats.get("max_legitimate")
                if ml and float(ml) > 0:
                    confirmed_cat_legit_amounts.append(int(float(ml)))
            elif ptype == "merchant" and target_norm_merch:
                if normalize_merchant_name(pkey)["canonical"] == target_norm_merch:
                    ml = stats.get("max_verified_legitimate") or stats.get("max")
                    if ml and float(ml) > 0 and canonicalize_category(stats.get("category", target_cat)) == target_cat:
                        confirmed_ctx_legit_amounts.append(int(float(ml)))

        # 1. Category baseline (prefer category + transaction_type when enough samples exist)
        chosen_cat_amounts = cat_type_amounts if len(cat_type_amounts) >= self.config.min_category_samples else cat_amounts
        if len(chosen_cat_amounts) >= self.config.min_category_samples:
            cat_stats = _compute_robust_stats(chosen_cat_amounts)
        else:
            cat_stats = _cold_start_category_stats(target_cat, currency, observed_count=len(chosen_cat_amounts))
            if chosen_cat_amounts:
                # Blend small empirical history smoothly with cold-start benchmark without collapsing scale
                emp_med = float(np.median(chosen_cat_amounts))
                cat_stats["observed_median"] = emp_med
                cat_stats["observed_amounts"] = chosen_cat_amounts

        # 2. Type baseline
        if len(type_amounts) >= 2:
            type_stats = _compute_robust_stats(type_amounts)
        else:
            scale = CURRENCY_USD_SCALE.get((currency or "USD").upper(), 1.0)
            type_stats = {
                "count": len(type_amounts),
                "mean": 100000.0 * scale,
                "std": 50000.0 * scale,
                "median": 100000.0 * scale,
                "mad": 35000.0 * scale,
            }

        # 3. Merchant baseline (prefer full (category, merchant, type) context if >= min_merchant_samples)
        chosen_merch = ctx_amounts if len(ctx_amounts) >= self.config.min_merchant_samples else merch_amounts
        if chosen_merch:
            merch_stats = _compute_robust_stats(chosen_merch)
            merch_stats["context_count"] = len(ctx_amounts)
        else:
            merch_stats = {
                "count": 0,
                "context_count": 0,
                "mean": 0.0,
                "std": 1.0,
                "median": 0.0,
                "mad": 1.0,
                "q25": 0.0,
                "q75": 0.0,
                "iqr": 1.0,
                "max": 0.0,
            }

        confirmed_bounds = {
            "category_confirmed_max": max(confirmed_cat_legit_amounts) if confirmed_cat_legit_amounts else None,
            "category_confirmed_count": len(confirmed_cat_legit_amounts),
            "context_confirmed_max": max(confirmed_ctx_legit_amounts) if confirmed_ctx_legit_amounts else None,
            "context_confirmed_count": len(confirmed_ctx_legit_amounts),
        }

        return cat_stats, type_stats, merch_stats, confirmed_bounds

    def _compute_frequency_timing_signal(
        self,
        target_amount: int,
        target_cat: str,
        target_type: str,
        canonical_merch: str,
        tx_date: datetime,
        clean_history: List[Any],
        weekend_ops_expected: bool,
    ) -> Dict[str, Any]:
        """
        Evaluates transaction frequency (7d velocity, 24h rapid bursts), business-specific
        timing patterns, and recurring-payment cadence alignment.
        """
        dt_utc = tx_date if tx_date.tzinfo else tx_date.replace(tzinfo=timezone.utc)
        seven_days_ago = dt_utc - timedelta(days=7)
        one_day_ago = dt_utc - timedelta(days=1)

        cat_dates: List[datetime] = []
        merch_dates: List[datetime] = []
        merch_amounts_by_date: List[Tuple[datetime, int]] = []
        all_dates: List[datetime] = []

        cat_vel_7d = 0
        merch_vel_7d = 0
        merch_vel_24h = 0

        for h in clean_history:
            h_dt = _parse_dt(_get_field(h, "date"), dt_utc - timedelta(days=30))
            h_cat = canonicalize_category(_get_field(h, "category_name"))
            h_type = str(_get_field(h, "type", _get_field(h, "transaction_type", "expense")) or "expense").lower()
            h_merch = normalize_merchant_name(_get_field(h, "merchant"), _get_field(h, "description"))["canonical"]
            h_amt = abs(int(_get_field(h, "amount_minor", 0) or 0))

            all_dates.append(h_dt)
            if h_cat == target_cat and h_type == target_type:
                cat_dates.append(h_dt)
                if seven_days_ago <= h_dt <= dt_utc:
                    cat_vel_7d += 1
            if canonical_merch and h_merch == canonical_merch:
                merch_dates.append(h_dt)
                merch_amounts_by_date.append((h_dt, h_amt))
                if seven_days_ago <= h_dt <= dt_utc:
                    merch_vel_7d += 1
                if one_day_ago <= h_dt <= dt_utc:
                    merch_vel_24h += 1

        # Detect whether this merchant has an established recurring pattern (e.g., ~monthly or ~bi-weekly)
        is_recurring_match = False
        recurring_cadence_days: Optional[float] = None
        if len(merch_dates) >= 3:
            sorted_md = sorted(merch_dates)
            gaps = [(sorted_md[i] - sorted_md[i - 1]).total_seconds() / 86400.0 for i in range(1, len(sorted_md))]
            positive_gaps = [g for g in gaps if g >= 3.0]
            if len(positive_gaps) >= 2:
                med_gap = float(np.median(positive_gaps))
                gap_std = float(np.std(positive_gaps))
                if med_gap >= 6.0 and gap_std <= max(4.0, med_gap * 0.25):
                    recurring_cadence_days = round(med_gap, 1)
                    # Check if current tx fits expected amount & cadence window
                    recent_amts = [a for _, a in merch_amounts_by_date if a > 0]
                    if recent_amts:
                        med_a = float(np.median(recent_amts))
                        days_since_last = abs((dt_utc - sorted_md[-1]).total_seconds() / 86400.0)
                        if abs(target_amount - med_a) <= max(med_a * 0.20, 500) and abs(days_since_last - med_gap) <= max(5.0, med_gap * 0.30):
                            is_recurring_match = True

        # Burst velocity anomaly: e.g. rapid duplicate/burst charges for a normally monthly merchant
        velocity_score = 0.0
        velocity_reasons: List[str] = []
        if recurring_cadence_days and recurring_cadence_days >= 20.0 and merch_vel_7d >= 2:
            velocity_score = max(velocity_score, 0.72)
            velocity_reasons.append(
                f"{merch_vel_7d + 1} charges from this merchant within 7 days despite an established ~{recurring_cadence_days:.0f}-day recurring cadence."
            )
        elif merch_vel_24h >= 3:
            velocity_score = max(velocity_score, 0.68)
            velocity_reasons.append(f"Rapid burst of {merch_vel_24h + 1} transactions with the same merchant within 24 hours.")
        elif len(cat_dates) >= 8:
            # Compare 7d category velocity to historical weekly average
            span_days = max(14.0, (max(cat_dates) - min(cat_dates)).total_seconds() / 86400.0)
            avg_weekly = (len(cat_dates) / span_days) * 7.0
            if avg_weekly > 0 and (cat_vel_7d + 1) >= max(5, avg_weekly * 3.5):
                velocity_score = max(velocity_score, min(0.75, 0.45 + 0.08 * ((cat_vel_7d + 1) / max(1.0, avg_weekly))))
                velocity_reasons.append(
                    f"Unusual transaction frequency: {cat_vel_7d + 1} {target_cat} transactions in 7 days vs typical {avg_weekly:.1f}/week."
                )

        # Business-specific timing check (weekend / late-night) — ONLY if history shows this business rarely transacts then
        timing_score = 0.0
        is_weekend = dt_utc.weekday() in (5, 6)
        if is_weekend and not weekend_ops_expected and len(all_dates) >= 15:
            hist_weekend_ratio = sum(1 for d in all_dates if d.weekday() in (5, 6)) / len(all_dates)
            # Only mild signal; never enough to alert alone without other factors
            if hist_weekend_ratio < 0.05:
                timing_score = 0.25

        score = min(1.0, max(velocity_score, timing_score))
        triggered = score >= self.config.frequency_timing_threshold
        detail = velocity_reasons[0] if velocity_reasons else (
            "Matches established recurring payment schedule." if is_recurring_match else "Transaction cadence and timing are consistent with business history."
        )

        return {
            "score": round(float(score), 3),
            "triggered": triggered,
            "confidence": round(0.80 if triggered else 0.65, 3),
            "velocity_7d_category": cat_vel_7d + 1,
            "velocity_7d_merchant": merch_vel_7d + 1,
            "velocity_24h_merchant": merch_vel_24h + 1,
            "is_recurring_match": is_recurring_match,
            "recurring_cadence_days": recurring_cadence_days,
            "is_weekend": is_weekend,
            "detail": detail,
        }

    def _compute_contextual_isolation_forest_score(
        self,
        current_vec: np.ndarray,
        clean_history: List[Any],
        tx_date: datetime,
        currency: str,
        business_profile: Optional[Any],
        verified_cat_counts: Dict[str, int],
    ) -> Tuple[float, Dict[str, Any]]:
        """
        Builds a properly contextualized historical feature matrix where EACH historical
        transaction h is represented using h's OWN category, type, merchant, velocity,
        and relevance baselines (fixing the leakage bug of applying the current transaction's
        stats to the entire historical dataset).
        """
        if len(clean_history) < self.config.min_isolation_forest_samples:
            return 0.0, {"used": False, "samples": len(clean_history)}

        recent_hist = clean_history[:100]

        # Precompute group amount lists across history so every historical row uses its OWN group's stats
        cat_groups: Dict[Tuple[str, str], List[int]] = {}
        type_groups: Dict[str, List[int]] = {}
        merch_groups: Dict[str, List[int]] = {}
        parsed_rows: List[Dict[str, Any]] = []

        for h in recent_hist:
            h_amt = abs(int(_get_field(h, "amount_minor", 0) or 0))
            if h_amt <= 0:
                continue
            h_cat = canonicalize_category(_get_field(h, "category_name"))
            h_type = str(_get_field(h, "type", _get_field(h, "transaction_type", "expense")) or "expense").lower()
            h_raw_m = _get_field(h, "merchant")
            h_desc = _get_field(h, "description")
            h_norm_m = normalize_merchant_name(h_raw_m, h_desc)["canonical"]
            h_dt = _parse_dt(_get_field(h, "date"), tx_date)

            cat_groups.setdefault((h_cat, h_type), []).append(h_amt)
            type_groups.setdefault(h_type, []).append(h_amt)
            if h_norm_m:
                merch_groups.setdefault(h_norm_m, []).append(h_amt)

            parsed_rows.append({
                "amount_minor": h_amt,
                "category": h_cat,
                "type": h_type,
                "merchant": h_raw_m,
                "norm_merchant": h_norm_m,
                "description": h_desc,
                "date": h_dt,
            })

        if len(parsed_rows) < self.config.min_isolation_forest_samples:
            return 0.0, {"used": False, "samples": len(parsed_rows)}

        # Precompute group robust stats once (O(N))
        cat_stats_map = {
            k: _compute_robust_stats(v) if len(v) >= self.config.min_category_samples else _cold_start_category_stats(k[0], currency, len(v))
            for k, v in cat_groups.items()
        }
        type_stats_map = {
            k: _compute_robust_stats(v) if len(v) >= 2 else {"count": len(v), "mean": float(np.mean(v)), "median": float(np.median(v)), "std": 1000.0, "mad": 500.0}
            for k, v in type_groups.items()
        }
        merch_stats_map = {
            k: _compute_robust_stats(v) for k, v in merch_groups.items()
        }

        # Cache category relevance per category so we don't recompute redundantly
        rel_score_cache: Dict[Tuple[str, str], float] = {}
        X_hist: List[np.ndarray] = []

        for idx, row in enumerate(parsed_rows):
            h_cat = row["category"]
            h_type = row["type"]
            h_dt = row["date"]
            h_norm_m = row["norm_merchant"]

            # Row's own 7-day category velocity
            vel_7d = sum(
                1 for other in parsed_rows
                if other["category"] == h_cat and other["type"] == h_type
                and timedelta(days=0) <= (h_dt - other["date"]) <= timedelta(days=7)
            )

            rel_key = (h_cat, h_type)
            if rel_key not in rel_score_cache:
                rel_eval = evaluate_category_relevance(
                    category=h_cat,
                    business_profile=business_profile,
                    verified_category_counts=verified_cat_counts,
                    transaction_type=h_type,
                )
                rel_score_cache[rel_key] = rel_eval["score"]

            h_cat_stats = cat_stats_map[(h_cat, h_type)]
            h_type_stats = type_stats_map[h_type]
            h_merch_stats = merch_stats_map.get(h_norm_m)

            vec, _ = feature_transformer.build_feature_vector(
                amount_minor=row["amount_minor"],
                category=h_cat,
                transaction_type=h_type,
                merchant=row["merchant"],
                dt=h_dt,
                category_stats=h_cat_stats,
                type_stats=h_type_stats,
                merchant_stats=h_merch_stats,
                recent_velocity_7d=max(1, vel_7d),
                currency_matches_workspace=True,
                category_relevance_score=rel_score_cache[rel_key],
                merchant_category_mismatch_score=0.0,
            )
            X_hist.append(vec)

        try:
            X_mat = np.array(X_hist, dtype=np.float32)
            clf = IsolationForest(
                contamination=0.05,
                n_estimators=100,
                random_state=42,
            )
            clf.fit(X_mat)
            hist_decisions = clf.decision_function(X_mat)
            curr_decision = float(clf.decision_function([current_vec])[0])

            # Calibrate relative to historical decision distribution (robust percentile/z calibration)
            med_dec = float(np.median(hist_decisions))
            iqr_dec = float(max(0.05, np.percentile(hist_decisions, 75) - np.percentile(hist_decisions, 25)))
            # Lower decision_function = more anomalous
            if curr_decision >= med_dec:
                iso_score = 0.0
            else:
                # Map negative deviation smoothly into [0, 1]
                norm_dev = (med_dec - curr_decision) / (iqr_dec * 2.5)
                raw_neg = max(0.0, -curr_decision) * 1.8
                iso_score = float(min(1.0, max(0.0, 0.5 * norm_dev + 0.5 * raw_neg)))

            return round(iso_score, 3), {
                "used": True,
                "samples": len(X_hist),
                "decision_value": round(curr_decision, 4),
                "historical_median_decision": round(med_dec, 4),
            }
        except Exception as e:
            return 0.0, {"used": False, "error": str(e)}

    def analyze_transaction(
        self,
        current_amount_minor: int,
        category: str,
        merchant: Optional[str] = None,
        historical_transactions: Optional[List[Any]] = None,
        date: Optional[datetime] = None,
        transaction_type: str = "expense",
        currency: str = "USD",
        feedback_status: Optional[str] = None,
        workspace_id: Optional[str] = None,
        business_profile: Optional[Any] = None,
        description: Optional[str] = None,
        learned_profiles: Optional[List[Dict[str, Any]]] = None,
        workspace_currency: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Business-context-aware multivariate anomaly detection.

        Evaluates 6 distinct, transparent signals:
          1. amount_deviation (robust median / IQR / MAD + cold-start)
          2. category_relevance (business profile industry taxonomy + learned categories)
          3. merchant_category_consistency (learned merchant-category pairs + domain priors)
          4. merchant_behavior (merchant-specific robust spend spike; never flags novelty alone)
          5. frequency_timing (velocity bursts, recurring cadence, business-specific timing)
          6. multivariate_isolation (contextual Isolation Forest)

        Keeps operational irrelevance cleanly separate from spending amount anomalies.
        """
        fb_norm = str(feedback_status or "").lower().strip()
        canonical_cat = canonicalize_category(category)
        norm_merch_info = normalize_merchant_name(merchant, description)
        canonical_merch = norm_merch_info["canonical"]
        target_amount = abs(int(current_amount_minor))
        tx_date = _parse_dt(date, datetime.now(timezone.utc))
        hist = historical_transactions or []
        curr_sym = _currency_symbol(currency)
        ws_curr = (workspace_currency or currency or "USD").upper()
        currency_matches = (currency or "USD").upper() == ws_curr

        # 0. Confirmed legitimate override on THIS specific transaction -> never re-alert
        if fb_norm == "legitimate":
            return {
                "is_anomaly": False,
                "anomaly_score": 0.0,
                "severity": None,
                "alert_type": "none",
                "confidence": 1.0,
                "reason": "Verified legitimate by user.",
                "explanation_details": {
                    "alert_type": "none",
                    "feedback_override": True,
                    "status": "resolved_legitimate",
                    "confidence": 1.0,
                    "category": canonical_cat,
                    "merchant": merchant,
                    "canonical_merchant": canonical_merch,
                    "contributing_factors": [],
                },
                "model_version": self.model_version,
            }

        # Filter clean baseline history & extract verified category counts for personalization
        clean_hist, confirmed_legit_txs, verified_cat_counts = self._filter_clean_history(hist)
        cat_stats, type_stats, merch_stats, confirmed_bounds = self.extract_stats_from_history(
            category=canonical_cat,
            transaction_type=transaction_type,
            merchant=merchant,
            historical_transactions=hist,
            currency=currency,
            learned_profiles=learned_profiles,
        )

        # ------------------------------------------------------------------
        # SIGNAL 1: Business-Context Category Relevance (Operational Fit)
        # ------------------------------------------------------------------
        relevance_res = evaluate_category_relevance(
            category=canonical_cat,
            business_profile=business_profile,
            description=description,
            merchant=merchant,
            verified_category_counts=verified_cat_counts,
            transaction_type=transaction_type,
        )
        rel_score = relevance_res["score"]
        rel_triggered = relevance_res["status"] == "unrelated" or rel_score >= self.config.operational_relevance_threshold

        # ------------------------------------------------------------------
        # SIGNAL 2: Merchant-Category Consistency
        # ------------------------------------------------------------------
        mc_res = evaluate_merchant_category_consistency(
            merchant=merchant,
            category=canonical_cat,
            description=description,
            historical_transactions=hist,
            learned_profiles=learned_profiles,
        )
        mc_score = mc_res["score"]
        mc_triggered = bool(mc_res["is_mismatch"]) and mc_score >= self.config.merchant_mismatch_threshold

        # ------------------------------------------------------------------
        # SIGNAL 3: Robust Amount Deviation (Median, IQR, MAD — No Raw-Max Suppression!)
        # ------------------------------------------------------------------
        is_cold_start = bool(cat_stats.get("is_cold_start", False))
        cat_count = int(cat_stats.get("count", 0))
        cat_median = float(cat_stats["median"])
        cat_mean = float(cat_stats["mean"])
        cat_std = float(cat_stats["std"])
        cat_mad = float(cat_stats["mad"])
        q75 = float(cat_stats["q75"])
        iqr = float(cat_stats["iqr"])

        median_multiple = target_amount / (cat_median + 1.0)
        mean_multiple = target_amount / (cat_mean + 1.0)
        effective_mad = max(cat_mad, cat_median * 0.08, 100.0)
        mad_z = 0.6745 * (target_amount - cat_median) / effective_mad
        cat_z = (target_amount - cat_mean) / (cat_std + 1.0)

        iqr_upper_mild = q75 + 1.5 * iqr
        iqr_upper_extreme = q75 + 3.0 * iqr
        is_mild_iqr = (target_amount > iqr_upper_mild) and (cat_count >= self.config.min_robust_iqr_samples)
        is_extreme_iqr = (target_amount > iqr_upper_extreme) and (cat_count >= self.config.min_robust_iqr_samples)

        # Check ONLY explicitly confirmed legitimate scale (NOT raw historical max!)
        # Allows verified expansion (e.g. $10k server confirmed legitimate -> $9.5k server is normal,
        # while $100k spike is still flagged, and an UNVERIFIED historical max never suppresses alerts).
        ctx_conf_max = confirmed_bounds.get("context_confirmed_max")
        cat_conf_max = confirmed_bounds.get("category_confirmed_max")
        within_explicitly_confirmed_scale = False
        if ctx_conf_max is not None and target_amount <= ctx_conf_max * 1.15:
            within_explicitly_confirmed_scale = True
        elif cat_conf_max is not None and confirmed_bounds.get("category_confirmed_count", 0) >= 2 and target_amount <= cat_conf_max * 1.10:
            within_explicitly_confirmed_scale = True

        amount_score = 0.0
        amount_detail = f"Amount of {curr_sym}{target_amount / 100:,.2f} is within normal range for {canonical_cat}."
        amount_confidence = 0.85 if not is_cold_start else 0.55

        if within_explicitly_confirmed_scale:
            amount_score = 0.0
            amount_detail = (
                f"Amount of {curr_sym}{target_amount / 100:,.2f} is within the business's confirmed "
                f"legitimate spending scale for {canonical_cat}."
            )
        elif not is_cold_start:
            # Combine robust MAD z-score, median multiple, and IQR fence
            sub_scores: List[float] = []
            if median_multiple >= self.config.median_multiple_alert:
                sub_scores.append(min(1.0, 0.48 + ((median_multiple - 1.5) / 5.5) * 0.52))
            if mad_z >= self.config.mad_mild_threshold:
                sub_scores.append(min(1.0, 0.45 + ((mad_z - self.config.mad_mild_threshold) / 8.0) * 0.55))
            if is_extreme_iqr:
                sub_scores.append(0.82)
            elif is_mild_iqr:
                sub_scores.append(0.56)

            if sub_scores:
                amount_score = max(sub_scores)
                if median_multiple >= self.config.median_multiple_alert:
                    amount_detail = (
                        f"{canonical_cat} expense of {curr_sym}{target_amount / 100:,.2f} is "
                        f"{median_multiple:.1f}× higher than the typical median of {curr_sym}{cat_median / 100:,.2f} "
                        f"(robust MAD Z-score: {mad_z:.1f})."
                    )
                elif is_extreme_iqr:
                    amount_detail = (
                        f"Amount of {curr_sym}{target_amount / 100:,.2f} is an extreme statistical outlier "
                        f"(above 3.0× IQR fence; MAD Z-score: {mad_z:.1f}) for {canonical_cat}."
                    )
                else:
                    amount_detail = (
                        f"Amount of {curr_sym}{target_amount / 100:,.2f} deviates significantly from "
                        f"typical {canonical_cat} spending (median {curr_sym}{cat_median / 100:,.2f}, MAD Z-score: {mad_z:.1f})."
                    )
                amount_confidence = min(0.96, 0.72 + 0.03 * min(cat_count, 8))
        else:
            # Cold-start: conservative comparison against currency-scaled category benchmark
            bench_max = float(cat_stats.get("max_normal", cat_median * 8.0))
            if target_amount > bench_max * self.config.cold_start_benchmark_multiple:
                over_ratio = target_amount / max(1.0, bench_max)
                amount_score = min(0.90, 0.65 + min(0.25, (over_ratio - 2.5) * 0.05))
                amount_confidence = 0.72
                amount_detail = (
                    f"Initial {canonical_cat} expense of {curr_sym}{target_amount / 100:,.2f} substantially "
                    f"exceeds cold-start industry benchmark ({curr_sym}{bench_max / 100:,.2f} upper bound)."
                )

        amount_triggered = amount_score >= self.config.amount_channel_threshold

        # ------------------------------------------------------------------
        # SIGNAL 4: Merchant Behavior (Robust Merchant-Specific Spike)
        # NOTE: Unfamiliar merchant alone NEVER triggers an anomaly!
        # ------------------------------------------------------------------
        m_count = int(merch_stats.get("count", 0))
        m_median = float(merch_stats.get("median", 0.0))
        m_mad = float(merch_stats.get("mad", 1.0))
        merch_novelty = 1.0 if m_count == 0 else round(1.0 / (1.0 + math.log1p(m_count)), 3)

        merch_behavior_score = 0.0
        merch_spike = False
        merch_multiple = 1.0
        merch_mad_z = 0.0
        merch_detail = (
            "New merchant with no prior spending baseline (treated neutrally)."
            if m_count == 0
            else f"Consistent with historical spending for {norm_merch_info['display'] or merchant}."
        )

        if m_count >= self.config.min_merchant_samples and m_median > 0 and not within_explicitly_confirmed_scale:
            merch_multiple = target_amount / (m_median + 1.0)
            eff_m_mad = max(m_mad, m_median * 0.08, 100.0)
            merch_mad_z = 0.6745 * (target_amount - m_median) / eff_m_mad
            m_iqr_upper = float(merch_stats.get("q75", m_median)) + 2.0 * float(merch_stats.get("iqr", m_median * 0.3))

            if merch_multiple >= self.config.merchant_spike_multiple or (merch_mad_z >= 4.5 and target_amount > m_iqr_upper):
                merch_spike = True
                merch_behavior_score = min(
                    1.0,
                    max(
                        0.55 + ((merch_multiple - 2.0) / 6.0) * 0.45 if merch_multiple >= 2.0 else 0.0,
                        0.52 + ((merch_mad_z - 3.5) / 8.0) * 0.48 if merch_mad_z >= 3.5 else 0.0,
                    ),
                )
                merch_detail = (
                    f"Merchant spend spike: {curr_sym}{target_amount / 100:,.2f} at "
                    f"'{norm_merch_info['display'] or merchant}' is {merch_multiple:.1f}× higher than "
                    f"the typical median of {curr_sym}{m_median / 100:,.2f} ({m_count} prior transactions)."
                )

        merch_triggered = merch_spike and merch_behavior_score >= self.config.merchant_spike_threshold

        # ------------------------------------------------------------------
        # SIGNAL 5: Frequency, Velocity & Timing (with Recurring Awareness)
        # ------------------------------------------------------------------
        freq_res = self._compute_frequency_timing_signal(
            target_amount=target_amount,
            target_cat=canonical_cat,
            target_type=transaction_type,
            canonical_merch=canonical_merch,
            tx_date=tx_date,
            clean_history=clean_hist,
            weekend_ops_expected=bool(relevance_res.get("weekend_operations_expected", False)),
        )
        freq_score = freq_res["score"]
        freq_triggered = freq_res["triggered"]

        # If this matches an established recurring payment schedule & amount, dampen mild statistical noise
        if freq_res["is_recurring_match"] and not rel_triggered and not mc_triggered:
            amount_score *= 0.25
            amount_triggered = False

        # ------------------------------------------------------------------
        # SIGNAL 6: Contextual Multivariate Isolation Forest
        # ------------------------------------------------------------------
        current_vec, factor_map = feature_transformer.build_feature_vector(
            amount_minor=target_amount,
            category=canonical_cat,
            transaction_type=transaction_type,
            merchant=merchant,
            dt=tx_date,
            category_stats=cat_stats,
            type_stats=type_stats,
            merchant_stats=merch_stats,
            recent_velocity_7d=freq_res["velocity_7d_category"],
            currency_matches_workspace=currency_matches,
            category_relevance_score=rel_score,
            merchant_category_mismatch_score=mc_score,
        )

        iso_score, iso_meta = self._compute_contextual_isolation_forest_score(
            current_vec=current_vec,
            clean_history=clean_hist,
            tx_date=tx_date,
            currency=currency,
            business_profile=business_profile,
            verified_cat_counts=verified_cat_counts,
        )
        # Do not let Isolation Forest override an explicitly confirmed legitimate scale or a normal recurring charge
        if within_explicitly_confirmed_scale or freq_res["is_recurring_match"]:
            iso_score = min(iso_score, 0.25)
        iso_triggered = iso_score >= 0.65 and (amount_score >= 0.30 or rel_score >= 0.30 or mc_score >= 0.30 or freq_score >= 0.30 or iso_score >= 0.78)

        # ------------------------------------------------------------------
        # CALIBRATED SCORE AGGREGATION & ALERT TYPE CLASSIFICATION
        # ------------------------------------------------------------------
        w = self.config.weights
        weighted_sum = (
            w["amount_deviation"] * amount_score
            + w["category_relevance"] * rel_score
            + w["merchant_category_consistency"] * mc_score
            + w["merchant_behavior"] * merch_behavior_score
            + w["frequency_timing"] * freq_score
            + w["multivariate_isolation"] * iso_score
        )

        # Calibrated channel-aware fusion:
        # A high-confidence single-channel signal (like unrelated operational expense, merchant-category
        # mismatch, or large amount spike) must not be diluted below threshold by zero scores on
        # orthogonal channels (e.g., ₹100 garam masala has amount_score=0 but rel_score=0.78).
        dominant_channel_score = max(
            amount_score if amount_triggered else 0.0,
            rel_score if rel_triggered else 0.0,
            mc_score if mc_triggered else 0.0,
            merch_behavior_score if merch_triggered else 0.0,
            freq_score if freq_triggered else 0.0,
            iso_score if iso_triggered else 0.0,
        )

        # Combine dominant signal with corroborating weighted evidence smoothly in [0, 1]
        if dominant_channel_score > 0:
            combined_score = min(1.0, max(dominant_channel_score, weighted_sum + 0.15 * dominant_channel_score))
            # Mild corroboration boost if multiple distinct channels agree
            triggered_count = sum(
                1 for flag in [amount_triggered, rel_triggered, mc_triggered, merch_triggered, freq_triggered, iso_triggered] if flag
            )
            if triggered_count >= 2:
                combined_score = min(1.0, combined_score + 0.08 * (triggered_count - 1))
        else:
            combined_score = min(0.49, weighted_sum)

        is_anomaly = (
            amount_triggered
            or rel_triggered
            or mc_triggered
            or merch_triggered
            or freq_triggered
            or iso_triggered
            or combined_score >= self.config.overall_alert_threshold
        )

        # Build structured factor list (sorted by impact descending)
        signals_dict = {
            "amount_deviation": {
                "score": round(float(amount_score), 3),
                "weight": w["amount_deviation"],
                "triggered": amount_triggered,
                "confidence": round(float(amount_confidence), 3),
                "label": "Amount Deviation",
                "detail": amount_detail,
                "metrics": {
                    "target_amount_minor": target_amount,
                    "category_median_minor": int(cat_median),
                    "category_mean_minor": int(cat_mean),
                    "category_mad_minor": int(cat_mad),
                    "category_iqr_minor": int(iqr),
                    "median_multiple": round(float(median_multiple), 2),
                    "mad_z_score": round(float(mad_z), 2),
                    "is_iqr_mild_outlier": is_mild_iqr,
                    "is_iqr_extreme_outlier": is_extreme_iqr,
                    "sample_count": cat_count,
                    "is_cold_start": is_cold_start,
                },
            },
            "category_relevance": {
                "score": round(float(rel_score), 3),
                "weight": w["category_relevance"],
                "triggered": rel_triggered,
                "confidence": relevance_res["confidence"],
                "label": "Business Operational Relevance",
                "status": relevance_res["status"],
                "detail": relevance_res["reason"],
                "metrics": {
                    "relevance_status": relevance_res["status"],
                    "evaluated_category": relevance_res["evaluated_category"],
                    "industry_label": relevance_res.get("industry_label"),
                    "operating_model": relevance_res.get("operating_model"),
                    "personalized": relevance_res.get("personalized", False),
                },
            },
            "merchant_category_consistency": {
                "score": round(float(mc_score), 3),
                "weight": w["merchant_category_consistency"],
                "triggered": mc_triggered,
                "confidence": mc_res["confidence"],
                "label": "Merchant-Category Consistency",
                "status": mc_res["status"],
                "detail": mc_res["reason"],
                "metrics": {
                    "canonical_merchant": canonical_merch,
                    "expected_categories": mc_res.get("expected_categories", []),
                    "historical_occurrences": mc_res.get("historical_occurrences", 0),
                    "exception_allowed": mc_res.get("exception_allowed", False),
                },
            },
            "merchant_behavior": {
                "score": round(float(merch_behavior_score), 3),
                "weight": w["merchant_behavior"],
                "triggered": merch_triggered,
                "confidence": round(0.84 if merch_triggered else 0.60, 3),
                "label": "Merchant Spend Behavior",
                "detail": merch_detail,
                "metrics": {
                    "merchant_sample_count": m_count,
                    "merchant_median_minor": int(m_median),
                    "merchant_multiple": round(float(merch_multiple), 2),
                    "merchant_mad_z": round(float(merch_mad_z), 2),
                    "merchant_novelty": merch_novelty,
                    "merchant_spike": merch_spike,
                },
            },
            "frequency_timing": {
                "score": round(float(freq_score), 3),
                "weight": w["frequency_timing"],
                "triggered": freq_triggered,
                "confidence": freq_res["confidence"],
                "label": "Frequency & Timing",
                "detail": freq_res["detail"],
                "metrics": {
                    "velocity_7d_category": freq_res["velocity_7d_category"],
                    "velocity_7d_merchant": freq_res["velocity_7d_merchant"],
                    "velocity_24h_merchant": freq_res["velocity_24h_merchant"],
                    "is_recurring_match": freq_res["is_recurring_match"],
                    "recurring_cadence_days": freq_res["recurring_cadence_days"],
                    "is_weekend": freq_res["is_weekend"],
                },
            },
            "multivariate_isolation": {
                "score": round(float(iso_score), 3),
                "weight": w["multivariate_isolation"],
                "triggered": iso_triggered,
                "confidence": round(0.75 if iso_meta.get("used") else 0.30, 3),
                "label": "Multivariate Pattern (Isolation Forest)",
                "detail": (
                    f"Contextual Isolation Forest deviation score: {iso_score:.2f} (trained on {iso_meta.get('samples', 0)} contextual records)."
                    if iso_meta.get("used")
                    else f"Insufficient history ({iso_meta.get('samples', 0)}/{self.config.min_isolation_forest_samples}) for multivariate Isolation Forest."
                ),
                "metrics": iso_meta,
            },
        }

        contributing_factors = [
            {
                "factor": key,
                "label": val["label"],
                "score": val["score"],
                "weight": val["weight"],
                "triggered": val["triggered"],
                "confidence": val["confidence"],
                "detail": val["detail"],
                "metrics": val["metrics"],
            }
            for key, val in sorted(signals_dict.items(), key=lambda kv: (kv[1]["triggered"], kv[1]["score"]), reverse=True)
            if val["triggered"] or val["score"] >= 0.25
        ]

        # Determine primary alert_type (keeping operational irrelevance separate from amount anomaly!)
        if not is_anomaly:
            alert_type = "none"
            severity = None
            reason = None
            overall_confidence = round(float(max(0.60, relevance_res["confidence"], amount_confidence)), 3)
        else:
            # Choose primary alert type based on highest triggered channel
            ranked_channels = [
                ("merchant_category_mismatch", mc_score if mc_triggered else 0.0, mc_res["reason"], mc_res["confidence"]),
                ("operational_relevance", rel_score if rel_triggered else 0.0, relevance_res["reason"], relevance_res["confidence"]),
                ("amount_anomaly", amount_score if amount_triggered else 0.0, amount_detail, amount_confidence),
                ("merchant_behavior", merch_behavior_score if merch_triggered else 0.0, merch_detail, 0.84),
                ("frequency_timing", freq_score if freq_triggered else 0.0, freq_res["detail"], freq_res["confidence"]),
                ("multivariate", iso_score if iso_triggered else 0.0, signals_dict["multivariate_isolation"]["detail"], 0.75),
            ]
            ranked_channels.sort(key=lambda x: x[1], reverse=True)
            alert_type, top_score, top_reason, top_conf = ranked_channels[0]

            # Build concise, accurate multi-factor reason
            secondary_reasons = [
                f["detail"] for f in contributing_factors
                if f["triggered"] and f["detail"] != top_reason
            ]
            if alert_type == "operational_relevance" and not amount_triggered:
                reason = f"Operational relevance warning: {top_reason} (Amount is not unusually large.)"
            elif secondary_reasons:
                reason = f"{top_reason} Additionally: {secondary_reasons[0]}"
            else:
                reason = top_reason

            # Calibrated severity
            if combined_score >= self.config.severity_critical or is_extreme_iqr:
                severity = "critical"
            elif combined_score >= self.config.severity_high:
                severity = "high"
            elif combined_score >= self.config.severity_medium:
                severity = "medium"
            else:
                severity = "low"

            # Operational relevance on an insignificant amount is medium/high warning, not critical fraud
            if alert_type == "operational_relevance" and not amount_triggered and not mc_triggered and severity == "critical":
                severity = "high"

            triggered_confs = [f["confidence"] for f in contributing_factors if f["triggered"]]
            overall_confidence = round(float(np.mean(triggered_confs)) if triggered_confs else float(top_conf), 3)

        prof_dict = extract_profile_dict(business_profile)
        business_context = {
            "profile_configured": prof_dict is not None,
            "industry": (prof_dict or {}).get("industry"),
            "business_type": (prof_dict or {}).get("business_type"),
            "operating_model": (prof_dict or {}).get("operating_model"),
            "category_relevance_status": relevance_res["status"],
            "evaluated_category": relevance_res["evaluated_category"],
            "personalized": relevance_res.get("personalized", False),
        }

        explanation_details = {
            "alert_type": alert_type,
            "primary_factor": contributing_factors[0]["factor"] if contributing_factors else "none",
            "confidence": overall_confidence,
            "business_context": business_context,
            "contributing_factors": contributing_factors,
            "signals": signals_dict,
            # Backward-compatible summary fields
            "category": canonical_cat,
            "target_amount_minor": target_amount,
            "category_mean_minor": int(cat_mean),
            "category_median_minor": int(cat_median),
            "category_mad_minor": int(cat_mad),
            "category_multiple": round(float(median_multiple), 2),
            "category_mean_multiple": round(float(mean_multiple), 2),
            "category_z_score": round(float(cat_z), 2),
            "category_mad_z_score": round(float(mad_z), 2),
            "merchant": merchant,
            "canonical_merchant": canonical_merch,
            "merchant_novelty_score": merch_novelty,
            "merchant_spike": merch_spike,
            "isolation_forest_score": round(float(iso_score), 3),
            "multivariate_isolation_score": round(float(iso_score), 3),
            "is_weekend": freq_res["is_weekend"],
            "category_sample_count": cat_count,
            "is_cold_start": is_cold_start,
            "is_within_confirmed_range": within_explicitly_confirmed_scale,
            "currency_matches_workspace": currency_matches,
        }

        return {
            "is_anomaly": bool(is_anomaly),
            "anomaly_score": round(float(combined_score), 3),
            "severity": severity,
            "alert_type": alert_type,
            "confidence": overall_confidence,
            "reason": reason,
            "contributing_factors": contributing_factors,
            "explanation_details": explanation_details,
            "model_version": self.model_version,
        }


anomaly_detector_instance = AnomalyDetector()
