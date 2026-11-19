"""
Comprehensive Test Suite for CashIQ Business-Context-Aware Anomaly Detection (v3.0.0).

Covers:
1. Industry / category operational relevance (`expected`, `unusual`, `unrelated`, `unknown`).
2. Required scenario: ₹100 garam masala at a SaaS company (operational-relevance warning
   with amount NOT flagged as unusual) vs same ₹100 garam masala at a Restaurant (normal).
3. Missing business profile handled neutrally (`unknown`, score 0.0, never suspicious).
4. Gradual personalization of business expense profile from verified transactions.
5. Merchant normalization (case, punctuation, payment-gateway prefixes, UPI handles, aliases).
6. Merchant-category consistency checks (software vendor classified as groceries flagged)
   AND verified legitimate exceptions allowed.
7. Unfamiliar / new merchant NOT treated as suspicious solely on novelty.
8. Robust amount statistics (median, IQR, MAD) AND proof that raw unverified historical max
   does NOT suppress new anomalies.
9. Fixed contextual Isolation Forest (each historical tx uses its own baselines) + wired
   merchant-spike signal contributing to the final score.
10. Cold-start handling (including INR vs USD currency-aware scaling).
11. User feedback overrides (`legitimate`, `incorrect_category`, `genuine_anomaly`) adapting
    baselines without disabling future detection of genuinely new risk patterns.
"""

from datetime import datetime, timedelta, timezone
import os
import sys
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.ml.anomaly_detector import AnomalyDetector, anomaly_detector_instance
from app.ml.business_taxonomy import (
    derive_initial_expense_profile,
    evaluate_category_relevance,
    personalize_expense_profile,
)
from app.ml.categorizer import categorizer_instance
from app.ml.merchant_normalizer import (
    evaluate_merchant_category_consistency,
    normalize_merchant_name,
)


def _make_saas_profile():
    return {
        "company_name": "Apex SaaS Pvt Ltd",
        "industry": "Technology",
        "business_type": "B2B SaaS",
        "operating_model": "B2B",
        "relevant_expense_categories": derive_initial_expense_profile("Technology", "B2B SaaS", "B2B"),
    }


def _make_restaurant_profile():
    return {
        "company_name": "Spice Route Bistro",
        "industry": "Restaurant",
        "business_type": "Food & Beverage",
        "operating_model": "Brick-and-Mortar",
        "relevant_expense_categories": derive_initial_expense_profile("Restaurant", "Food & Beverage", "Brick-and-Mortar"),
    }


def test_saas_garam_masala_operational_relevance_vs_restaurant():
    """
    Core business-context test:
    - ₹100 (10000 paise) garam masala purchase by a SaaS company -> receives operational-relevance
      warning even though ₹100 is insignificant (amount_deviation NOT triggered!).
    - Same ₹100 garam masala purchase by a Restaurant -> completely normal (not flagged!).
    """
    saas_profile = _make_saas_profile()
    rest_profile = _make_restaurant_profile()

    # Auto-categorization of general spice/grocery purchase
    cat_pred = categorizer_instance.categorize("Local Kirana Store Garam masala spice pack")
    assert cat_pred["category"] == "Groceries & Ingredients"

    # Case A: SaaS company (explicit category)
    saas_res = anomaly_detector_instance.analyze_transaction(
        current_amount_minor=10000,  # ₹100.00
        category=cat_pred["category"],
        merchant="Fresh Kirana Store",
        description="Garam masala spice pack",
        currency="INR",
        transaction_type="expense",
        business_profile=saas_profile,
        historical_transactions=[],
    )
    assert saas_res["is_anomaly"] is True
    assert saas_res["alert_type"] == "operational_relevance"
    assert saas_res["explanation_details"]["business_context"]["category_relevance_status"] == "unrelated"
    assert saas_res["explanation_details"]["signals"]["amount_deviation"]["triggered"] is False
    assert saas_res["explanation_details"]["signals"]["category_relevance"]["triggered"] is True
    assert saas_res["confidence"] >= 0.75

    # Case B: SaaS company even if user placed it under "Miscellaneous" (semantic domain detection)
    saas_misc_res = anomaly_detector_instance.analyze_transaction(
        current_amount_minor=10000,
        category="Miscellaneous",
        merchant="Neighborhood Provisions",
        description="Garam masala and cooking spices",
        currency="INR",
        transaction_type="expense",
        business_profile=saas_profile,
        historical_transactions=[],
    )
    assert saas_misc_res["is_anomaly"] is True
    assert saas_misc_res["alert_type"] == "operational_relevance"
    assert saas_misc_res["explanation_details"]["signals"]["amount_deviation"]["triggered"] is False

    # Case C: Same ₹100 garam masala purchase at a Restaurant -> NORMAL!
    rest_res = anomaly_detector_instance.analyze_transaction(
        current_amount_minor=10000,
        category=cat_pred["category"],
        merchant="Fresh Kirana Store",
        description="Garam masala spice pack",
        currency="INR",
        transaction_type="expense",
        business_profile=rest_profile,
        historical_transactions=[],
    )
    assert rest_res["is_anomaly"] is False
    assert rest_res["explanation_details"]["business_context"]["category_relevance_status"] == "expected"


def test_missing_business_profile_is_neutral_not_suspicious():
    """Missing business profile must yield status='unknown' with 0.0 penalty and never trigger suspicion."""
    res = anomaly_detector_instance.analyze_transaction(
        current_amount_minor=10000,
        category="Groceries & Ingredients",
        merchant="Corner Mart",
        description="Kitchen supplies",
        currency="INR",
        business_profile=None,
        historical_transactions=[],
    )
    assert res["is_anomaly"] is False
    assert res["explanation_details"]["business_context"]["profile_configured"] is False
    assert res["explanation_details"]["business_context"]["category_relevance_status"] == "unknown"
    assert res["explanation_details"]["signals"]["category_relevance"]["score"] == 0.0


def test_gradual_business_profile_personalization():
    """Verified legitimate transactions gradually adapt an initially unrelated category to expected."""
    saas_profile = _make_saas_profile()
    base_rel = saas_profile["relevant_expense_categories"]
    assert "Groceries & Ingredients" in base_rel["unrelated"]

    # After 1 verified purchase -> shifts from unrelated to unusual
    step1 = personalize_expense_profile(base_rel, {"Groceries & Ingredients": 1})
    assert "Groceries & Ingredients" in step1["unusual"]

    # After 3 verified legitimate purchases -> promoted to expected!
    verified_hist = [
        {
            "amount_minor": 15000,
            "category_name": "Groceries & Ingredients",
            "merchant": "Pantry Mart",
            "type": "expense",
            "is_confirmed": True,
            "anomaly_feedback_status": "legitimate",
        }
        for _ in range(3)
    ]
    res = anomaly_detector_instance.analyze_transaction(
        current_amount_minor=16000,
        category="Groceries & Ingredients",
        merchant="Pantry Mart",
        description="Office pantry staples",
        currency="INR",
        business_profile=saas_profile,
        historical_transactions=verified_hist,
    )
    assert res["is_anomaly"] is False
    assert res["explanation_details"]["business_context"]["category_relevance_status"] == "expected"
    assert res["explanation_details"]["business_context"]["personalized"] is True


def test_merchant_normalization_gateways_upi_and_aliases():
    """Verifies normalization across case, punctuation, payment gateways, UPI handles, and aliases."""
    assert normalize_merchant_name("UPI/52910291/SWIGGY FOOD ORDER/BANGALORE")["canonical"] == "swiggy"
    assert normalize_merchant_name("swiggy.pay@icici")["canonical"] == "swiggy"
    assert normalize_merchant_name("RZP*AWS EMEA Cloud")["canonical"] == "amazon web services"
    assert normalize_merchant_name("Amazon Web Services Inc.")["canonical"] == "amazon web services"
    assert normalize_merchant_name("PAYTM*ZOMATO RESTAURANTS PVT LTD")["canonical"] == "zomato"
    assert normalize_merchant_name("STRIPE*FIGMA INC #9921")["canonical"] == "figma"
    assert normalize_merchant_name("merchant.store@okaxis")["upi_handle"] == "merchant.store@okaxis"


def test_merchant_category_mismatch_and_legitimate_exception():
    """
    - A software/cloud vendor (AWS) classified as Groceries -> flagged as merchant_category_mismatch.
    - A merchant historically in Software & Cloud Services classified under Travel -> flagged.
    - Once a verified exception exists for (merchant, category), mismatch alert is suppressed!
    """
    saas_profile = _make_saas_profile()
    history = [
        {"amount_minor": 90000, "category_name": "Software & Cloud Services", "merchant": "AWS EMEA", "type": "expense", "is_confirmed": True},
        {"amount_minor": 95000, "category_name": "Software & Cloud Services", "merchant": "Amazon Web Services", "type": "expense", "is_confirmed": True},
        {"amount_minor": 92000, "category_name": "Software & Cloud Services", "merchant": "RZP*AWS", "type": "expense", "is_confirmed": True},
    ]

    # Software vendor misclassified as Groceries & Ingredients
    mismatch_res = anomaly_detector_instance.analyze_transaction(
        current_amount_minor=91000,
        category="Groceries & Ingredients",
        merchant="AWS EMEA",
        description="Monthly compute invoice",
        currency="USD",
        business_profile=saas_profile,
        historical_transactions=history,
    )
    assert mismatch_res["is_anomaly"] is True
    assert mismatch_res["explanation_details"]["signals"]["merchant_category_consistency"]["triggered"] is True
    assert mismatch_res["alert_type"] in {"merchant_category_mismatch", "operational_relevance"}

    # Legitimate exception: e.g. Amazon / Flipkart or a verified vendor pair
    exc_history = [
        {"amount_minor": 50000, "category_name": "Office Supplies & Equipment", "merchant": "Global Mart", "type": "expense", "is_confirmed": True},
        {"amount_minor": 52000, "category_name": "Office Supplies & Equipment", "merchant": "Global Mart", "type": "expense", "is_confirmed": True},
        {"amount_minor": 51000, "category_name": "Office Supplies & Equipment", "merchant": "Global Mart", "type": "expense", "is_confirmed": True},
    ]
    # Without exception -> mismatch!
    m1 = evaluate_merchant_category_consistency("Global Mart", "Meals & Entertainment", historical_transactions=exc_history)
    assert m1["is_mismatch"] is True

    # Add a verified legitimate exception for (Global Mart, Meals & Entertainment)
    exc_history_with_override = exc_history + [
        {
            "amount_minor": 12000,
            "category_name": "Meals & Entertainment",
            "merchant": "Global Mart",
            "type": "expense",
            "is_confirmed": True,
            "anomaly_feedback_status": "legitimate",
        }
    ]
    m2 = evaluate_merchant_category_consistency("Global Mart", "Meals & Entertainment", historical_transactions=exc_history_with_override)
    assert m2["is_mismatch"] is False
    assert m2["exception_allowed"] is True


def test_unfamiliar_new_merchant_is_not_flagged_as_suspicious():
    """A brand new merchant in an expected category with a normal amount must NOT be flagged."""
    saas_profile = _make_saas_profile()
    history = [
        {"amount_minor": 50000, "category_name": "Software & Cloud Services", "merchant": "GitHub", "type": "expense"},
        {"amount_minor": 60000, "category_name": "Software & Cloud Services", "merchant": "Slack", "type": "expense"},
        {"amount_minor": 55000, "category_name": "Software & Cloud Services", "merchant": "Figma", "type": "expense"},
        {"amount_minor": 58000, "category_name": "Software & Cloud Services", "merchant": "Linear", "type": "expense"},
    ]
    res = anomaly_detector_instance.analyze_transaction(
        current_amount_minor=54000,
        category="Software & Cloud Services",
        merchant="Brand New DevTool Labs Inc",
        description="Annual API subscription",
        currency="USD",
        business_profile=saas_profile,
        historical_transactions=history,
    )
    assert res["is_anomaly"] is False
    assert res["explanation_details"]["signals"]["merchant_category_consistency"]["status"] == "unfamiliar_neutral"


def test_historical_max_does_not_suppress_new_anomaly():
    """
    Critical fix verification:
    An UNVERIFIED historical maximum in the ledger must NOT automatically suppress a new outlier!
    """
    now = datetime.now(timezone.utc)
    # 12 normal $100 software bills + 1 unverified $5,000 spike in history
    history = [
        {
            "amount_minor": 10000 + (i % 3) * 500,
            "category_name": "Software & Cloud Services",
            "merchant": "Slack",
            "type": "expense",
            "date": now - timedelta(days=30 + i * 5),
        }
        for i in range(12)
    ]
    # Unverified historical high amount (NOT marked legitimate!)
    history.append({
        "amount_minor": 500000,  # $5,000 unverified
        "category_name": "Software & Cloud Services",
        "merchant": "Unknown Vendor",
        "type": "expense",
        "date": now - timedelta(days=15),
    })

    # New $4,500 transaction (below raw historical max $5,000, but 43x median of $105!)
    res = anomaly_detector_instance.analyze_transaction(
        current_amount_minor=450000,
        category="Software & Cloud Services",
        merchant="Slack",
        currency="USD",
        historical_transactions=history,
        business_profile=_make_saas_profile(),
    )
    assert res["is_anomaly"] is True
    assert res["explanation_details"]["signals"]["amount_deviation"]["triggered"] is True
    assert res["explanation_details"]["signals"]["merchant_behavior"]["triggered"] is True
    assert res["explanation_details"]["is_within_confirmed_range"] is False


def test_merchant_spike_signal_contributes_to_final_score():
    """
    Audits that merchant-specific spend spike actually contributes to the final score
    even when category median is higher (e.g., category contains large AWS bills,
    while this specific merchant normally charges $50).
    """
    now = datetime.now(timezone.utc)
    history = [
        # Large AWS charges pull category median up to ~$2,000
        {"amount_minor": 200000, "category_name": "Software & Cloud Services", "merchant": "AWS", "type": "expense", "date": now - timedelta(days=90)},
        {"amount_minor": 210000, "category_name": "Software & Cloud Services", "merchant": "AWS", "type": "expense", "date": now - timedelta(days=60)},
        {"amount_minor": 220000, "category_name": "Software & Cloud Services", "merchant": "AWS", "type": "expense", "date": now - timedelta(days=30)},
        {"amount_minor": 195000, "category_name": "Software & Cloud Services", "merchant": "AWS", "type": "expense", "date": now - timedelta(days=15)},
        # Small Notion charges consistently ~$50
        {"amount_minor": 5000, "category_name": "Software & Cloud Services", "merchant": "Notion", "type": "expense", "date": now - timedelta(days=120)},
        {"amount_minor": 5200, "category_name": "Software & Cloud Services", "merchant": "Notion", "type": "expense", "date": now - timedelta(days=90)},
        {"amount_minor": 4900, "category_name": "Software & Cloud Services", "merchant": "Notion", "type": "expense", "date": now - timedelta(days=60)},
        {"amount_minor": 5100, "category_name": "Software & Cloud Services", "merchant": "Notion", "type": "expense", "date": now - timedelta(days=30)},
    ]

    # Sudden $400 charge from Notion (normal for category overall, but 8x spike for Notion!)
    res = anomaly_detector_instance.analyze_transaction(
        current_amount_minor=40000,
        category="Software & Cloud Services",
        merchant="Notion",
        currency="USD",
        historical_transactions=history,
        business_profile=_make_saas_profile(),
    )
    assert res["is_anomaly"] is True
    assert res["explanation_details"]["signals"]["merchant_behavior"]["triggered"] is True
    assert res["explanation_details"]["signals"]["merchant_behavior"]["score"] >= 0.60
    assert res["alert_type"] == "merchant_behavior"


def test_cold_start_currency_aware_inr_vs_usd():
    """INR cold-start benchmarks must scale appropriately (₹15,000 meal is normal SME catering, not $15,000!)."""
    # ₹2,500 (250,000 paise) in Meals & Entertainment for an INR workspace on cold start -> NORMAL!
    inr_res = anomaly_detector_instance.analyze_transaction(
        current_amount_minor=250000,
        category="Meals & Entertainment",
        merchant="Team Lunch Bistro",
        currency="INR",
        historical_transactions=[],
        business_profile=_make_saas_profile(),
    )
    assert inr_res["is_anomaly"] is False

    # ₹2,50,000 (25,000,000 paise) in Meals & Entertainment on cold start -> ANOMALY!
    inr_extreme = anomaly_detector_instance.analyze_transaction(
        current_amount_minor=25000000,
        category="Meals & Entertainment",
        merchant="Luxury Banquet",
        currency="INR",
        historical_transactions=[],
        business_profile=_make_saas_profile(),
    )
    assert inr_extreme["is_anomaly"] is True
    assert inr_extreme["alert_type"] == "amount_anomaly"


def test_contextual_isolation_forest_mixed_categories():
    """
    Verifies Isolation Forest uses each historical transaction's OWN contextual baseline
    (mixed Meals ~$20 and Payroll ~$12,000) so normal Payroll isn't mis-scored as an outlier.
    """
    now = datetime.now(timezone.utc)
    hist = []
    for i in range(8):
        hist.append({
            "amount_minor": 2000 + (i % 3) * 200,
            "category_name": "Meals & Entertainment",
            "merchant": "Cafe",
            "type": "expense",
            "date": now - timedelta(days=i * 7 + 1),
        })
        hist.append({
            "amount_minor": 1200000 + (i % 2) * 10000,
            "category_name": "Payroll & Wages",
            "merchant": "Gusto",
            "type": "expense",
            "date": now - timedelta(days=i * 14 + 2),
        })

    normal_payroll = anomaly_detector_instance.analyze_transaction(
        current_amount_minor=1205000,
        category="Payroll & Wages",
        merchant="Gusto",
        date=now,
        currency="USD",
        historical_transactions=hist,
        business_profile=_make_saas_profile(),
    )
    assert normal_payroll["is_anomaly"] is False
    assert normal_payroll["explanation_details"]["signals"]["multivariate_isolation"]["metrics"]["used"] is True
    assert normal_payroll["explanation_details"]["signals"]["multivariate_isolation"]["score"] < 0.50


def test_genuine_anomaly_feedback_excluded_from_baselines():
    """Confirmed genuine_anomaly transactions must NEVER inflate future normal baselines."""
    history = [
        {"amount_minor": 10000, "category_name": "Meals & Entertainment", "merchant": "Cafe", "type": "expense"},
        {"amount_minor": 11000, "category_name": "Meals & Entertainment", "merchant": "Cafe", "type": "expense"},
        {"amount_minor": 10500, "category_name": "Meals & Entertainment", "merchant": "Cafe", "type": "expense"},
        {"amount_minor": 12000, "category_name": "Meals & Entertainment", "merchant": "Cafe", "type": "expense"},
        # Confirmed genuine anomaly should be ignored when computing baselines
        {
            "amount_minor": 900000,
            "category_name": "Meals & Entertainment",
            "merchant": "Fraudulent Charge",
            "type": "expense",
            "is_anomaly": True,
            "anomaly_feedback_status": "genuine_anomaly",
        },
    ]
    res = anomaly_detector_instance.analyze_transaction(
        current_amount_minor=50000,  # $500 vs ~$108 median -> must STILL be flagged!
        category="Meals & Entertainment",
        merchant="Cafe",
        currency="USD",
        historical_transactions=history,
    )
    assert res["is_anomaly"] is True
    assert res["explanation_details"]["category_median_minor"] < 15000
