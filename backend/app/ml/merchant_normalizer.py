"""
CashIQ Merchant Name Normalization & Merchant-Category Consistency Engine.

Handles:
1. Merchant normalization across case, punctuation, payment-gateway prefixes
   (UPI, IMPS, NEFT, RTGS, POS, Razorpay, Paytm, Stripe, Square, PayPal, etc.),
   UPI handles (@okaxis, @icici, @hdfcbank, @ybl, @paytm, etc.), trailing reference
   codes, legal suffixes, and maintainable canonical aliases.
2. Per-business merchant-category pair learning from historical verified transactions.
3. Domain-level vendor-category consistency checks (e.g. flagging a cloud/software
   vendor classified under Groceries) while allowing verified legitimate exceptions.
4. Neutral handling of unfamiliar merchants (novelty alone never flags an anomaly).
"""

import re
from collections import Counter
from typing import Any, Dict, List, Optional, Set, Tuple

from app.ml.business_taxonomy import canonicalize_category


# Payment rail / gateway prefixes to strip before comparing merchant names
GATEWAY_PREFIX_PATTERNS = [
    r"^(?:upi|imps|neft|rtgs|nach|ecs|ach|pos|ecom|atm)\s*[/\-:\*]\s*",
    r"^(?:upi\s+(?:dr|cr|in|out|txn|pay))\s*[/\-:\*\s]+",
    r"^(?:paytm|rzp|razorpay|stripe|sq|square|paypal|billdesk|ccavenue|cashfree|instamojo|phonepe|gpay|bhim|bharatpe|google|amzn\s*mktp|amazon\s*pay|payu)\s*[\*\-/:]\s*",
    r"^(?:pos\s+purchase\s+(?:at\s+)?|card\s+purchase\s+(?:at\s+)?|debit\s+card\s+)",
    r"^(?:neft\s+(?:cr|dr)|imps\s+(?:inward|outward|cr|dr)|rtgs\s+(?:cr|dr))\s*[\-/:]\s*",
]

# Known UPI PSP handles (after '@')
UPI_HANDLE_RE = re.compile(
    r"\b([a-z0-9][a-z0-9._\-]{1,40})@([a-z0-9]{2,20})\b", re.IGNORECASE
)

# Trailing corporate / legal suffixes to strip for canonical comparison
LEGAL_SUFFIX_RE = re.compile(
    r"\b(?:pvt\.?\s*ltd\.?|private\s+limited|limited|ltd\.?|inc\.?|incorporated|"
    r"llc|l\.l\.c\.?|llp|corp\.?|corporation|co\.?|technologies|technology|tech|"
    r"solutions|services|systems|enterprises?|india|emea|usa|global|online|pay|payments?)\b",
    re.IGNORECASE,
)

# Maintainable alias map (normalized stem -> canonical merchant key)
MERCHANT_ALIASES: Dict[str, str] = {
    "aws": "amazon web services",
    "aws cloud": "amazon web services",
    "amazon web": "amazon web services",
    "amazon web services": "amazon web services",
    "gcp": "google cloud",
    "google cloud platform": "google cloud",
    "google cloud": "google cloud",
    "gsuite": "google workspace",
    "google workspace": "google workspace",
    "msft": "microsoft",
    "microsoft azure": "microsoft azure",
    "azure": "microsoft azure",
    "openai": "openai",
    "anthropic": "anthropic",
    "github": "github",
    "gitlab": "gitlab",
    "slack": "slack",
    "atlassian": "atlassian",
    "jira": "atlassian",
    "figma": "figma",
    "notion": "notion",
    "datadog": "datadog",
    "vercel": "vercel",
    "mongodb": "mongodb",
    "zoom": "zoom",
    "zoom video communications": "zoom",
    "stripe": "stripe",
    "gusto": "gusto",
    "rippling": "rippling",
    "deel": "deel",
    "adp": "adp",
    "wework": "wework",
    "swiggy": "swiggy",
    "bundl": "swiggy",
    "zomato": "zomato",
    "uber": "uber",
    "ola": "ola",
    "starbucks": "starbucks",
    "tata starbucks": "starbucks",
    "doordash": "doordash",
    "staples": "staples",
    "office depot": "office depot",
    "deloitte": "deloitte",
    "google ads": "google ads",
    "meta ads": "meta ads",
    "facebook ads": "meta ads",
    "linkedin ads": "linkedin ads",
    "mailchimp": "mailchimp",
    "canva": "canva",
    "hdfc": "hdfc bank",
    "hdfc bank": "hdfc bank",
    "icici": "icici bank",
    "icici bank": "icici bank",
    "sbi": "state bank of india",
    "airtel": "airtel",
    "jio": "jio",
    "reliance jio": "jio",
    "bluedart": "blue dart",
    "blue dart": "blue dart",
    "delhivery": "delhivery",
    "fedex": "fedex",
    "dhl": "dhl",
    "bigbasket": "bigbasket",
    "blinkit": "blinkit",
    "zepto": "zepto",
    "instamart": "swiggy instamart",
    "dmart": "dmart",
}

# General vendor-domain patterns (used ONLY as a secondary domain-level check
# when a merchant's canonical name clearly identifies a specialized sector,
# e.g., a software/cloud vendor classified as Groceries & Ingredients).
VENDOR_DOMAIN_PRIORS: List[Tuple[str, Set[str], str]] = [
    (
        r"\b(?:amazon web services|google cloud|microsoft azure|github|gitlab|slack|figma|"
        r"notion|atlassian|datadog|vercel|openai|anthropic|mongodb|snowflake|cloudflare|"
        r"digitalocean|heroku|netlify|twilio|sendgrid|hubspot|salesforce|zoho|freshworks|"
        r"razorpay|stripe)\b",
        {"Software & Cloud Services", "Marketing & Advertising", "Banking & Fees", "Client Revenue"},
        "software/cloud platform vendor",
    ),
    (
        r"\b(?:gusto|rippling|deel|adp|paychex|keka|greythr|razorpayx payroll)\b",
        {"Payroll & Wages", "Software & Cloud Services", "Professional & Legal"},
        "payroll provider",
    ),
    (
        r"\b(?:google ads|meta ads|linkedin ads|mailchimp|semrush|ahrefs)\b",
        {"Marketing & Advertising", "Software & Cloud Services"},
        "advertising/marketing platform",
    ),
    (
        r"\b(?:deloitte|pwc|ey|kpmg|ernst|wilson sonsini|cooley|latham)\b",
        {"Professional & Legal", "Taxes & Compliance"},
        "legal/audit/advisory firm",
    ),
    (
        r"\b(?:delta air|united airlines|indigo|air india|vistara|emirates|lufthansa|makemytrip|uber|lyft|ola)\b",
        {"Travel & Transportation", "Shipping & Logistics"},
        "travel/transport provider",
    ),
    (
        r"\b(?:blue dart|delhivery|fedex|dhl|ups|dtdc|shiprocket|bluedart)\b",
        {"Shipping & Logistics", "Office Supplies & Equipment"},
        "logistics/courier provider",
    ),
]


def _extract_upi_merchant(raw: str) -> Tuple[Optional[str], Optional[str]]:
    """Extracts merchant stem and UPI handle from UPI strings or VPA handles."""
    m = UPI_HANDLE_RE.search(raw)
    if m:
        stem = m.group(1)
        handle = f"{m.group(1)}@{m.group(2)}".lower()
        cleaned_stem = re.sub(r"[._\-]+", " ", stem).strip()
        # Strip numeric suffixes from UPI stems like swiggy1234 -> swiggy
        cleaned_stem = re.sub(r"\d{3,}$", "", cleaned_stem).strip()
        return (cleaned_stem if len(cleaned_stem) >= 2 else None), handle
    return None, None


def normalize_merchant_name(
    raw_merchant: Optional[str],
    description: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Normalizes a merchant name for reliable behavioral comparison across transactions.
    Strips gateway prefixes, UPI handles, reference numbers, punctuation, and legal suffixes,
    and resolves known aliases.
    """
    source_text = (raw_merchant or "").strip()
    if not source_text and description:
        source_text = str(description).strip()

    if not source_text:
        return {
            "raw": raw_merchant,
            "canonical": "",
            "display": "",
            "gateway_prefix": None,
            "upi_handle": None,
            "alias_matched": False,
        }

    working = source_text
    gateway_prefix = None
    upi_handle = None

    # 1. Extract UPI handle if present
    upi_stem, found_handle = _extract_upi_merchant(working)
    if found_handle:
        upi_handle = found_handle
        # If the raw input is primarily a UPI ID or UPI slash narration, prefer the meaningful segment
        if "/" in working:
            parts = [p.strip() for p in working.split("/") if p.strip()]
            # Drop rail token (UPI/IMPS/NEFT) and pure numeric ref tokens and VPA if better name exists
            candidates = [
                p for p in parts
                if not re.match(r"^(?:upi|imps|neft|rtgs|dr|cr|in|out|pay)$", p, re.IGNORECASE)
                and not re.match(r"^\d{4,}$", p)
                and "@" not in p
                and not re.match(r"^[a-z]{4}0[a-z0-9]{6}$", p, re.IGNORECASE)  # IFSC
            ]
            if candidates:
                working = candidates[0]
            elif upi_stem:
                working = upi_stem
        elif upi_stem:
            working = upi_stem

    # 2. Handle structured slash-delimited bank narrations (e.g. UPI/52910291/SWIGGY FOOD ORDER/BANGALORE)
    if "/" in working and not upi_handle:
        parts = [p.strip() for p in working.split("/") if p.strip()]
        if parts and re.match(r"^(?:upi|imps|neft|rtgs|pos|ecom|ach|ecs|nach)$", parts[0], re.IGNORECASE):
            gateway_prefix = parts[0].upper()
            candidates = [
                p for p in parts[1:]
                if not re.match(r"^\d{4,}$", p)
                and not re.match(r"^[a-z]{4}0[a-z0-9]{6}$", p, re.IGNORECASE)
                and not re.match(r"^(?:dr|cr|in|out|txn|pay)$", p, re.IGNORECASE)
            ]
            if candidates:
                working = candidates[0]

    # 3. Strip payment gateway prefixes repeatedly
    for _ in range(2):
        matched = False
        for pat in GATEWAY_PREFIX_PATTERNS:
            m = re.match(pat, working, re.IGNORECASE)
            if m:
                if not gateway_prefix:
                    gateway_prefix = m.group(0).strip(" */-:")
                working = working[m.end():].strip()
                matched = True
        if not matched:
            break

    # 4. Strip leading numeric reference tokens (e.g. "582910-SWIGGY-BANGALORE")
    working = re.sub(r"^\d{4,}[\s\-_/]+", "", working).strip()
    # Strip trailing store/branch numbers and long reference codes
    working = re.sub(r"\s*#\s*\d+.*$", "", working).strip()
    working = re.sub(r"\b(?:ref|txn|utr|id|inv|order)[:\s#\-]*[a-z0-9]{4,}\b", "", working, flags=re.IGNORECASE).strip()
    working = re.sub(r"\b\d{5,}\b", "", working).strip()

    # 5. Lowercase and clean punctuation
    clean = working.lower()
    clean = re.sub(r"[^a-z0-9&\s]", " ", clean)
    clean = re.sub(r"\s+", " ", clean).strip()

    # 6. Check alias before stripping legal suffixes (preserves "amazon web services")
    alias_matched = False
    if clean in MERCHANT_ALIASES:
        canonical = MERCHANT_ALIASES[clean]
        alias_matched = True
    else:
        # Strip legal/region suffixes
        stripped = LEGAL_SUFFIX_RE.sub(" ", clean)
        stripped = re.sub(r"\s+", " ", stripped).strip()
        # Keep original cleaned form if stripping erased everything
        stem = stripped if len(stripped) >= 2 else clean

        if stem in MERCHANT_ALIASES:
            canonical = MERCHANT_ALIASES[stem]
            alias_matched = True
        else:
            # Check prefix alias match on multi-word merchant names (e.g. "swiggy food order" -> "swiggy")
            tokens = stem.split()
            canonical = stem
            for n in (3, 2, 1):
                if len(tokens) >= n:
                    prefix = " ".join(tokens[:n])
                    if prefix in MERCHANT_ALIASES:
                        canonical = MERCHANT_ALIASES[prefix]
                        alias_matched = True
                        break

    display = " ".join(w.capitalize() for w in canonical.split()) if canonical else (raw_merchant or "")
    return {
        "raw": raw_merchant,
        "canonical": canonical,
        "display": display,
        "gateway_prefix": gateway_prefix,
        "upi_handle": upi_handle,
        "alias_matched": alias_matched,
    }


def _extract_tx_field(tx: Any, field: str, default: Any = None) -> Any:
    if isinstance(tx, dict):
        return tx.get(field, default)
    return getattr(tx, field, default)


def build_merchant_category_map(
    historical_transactions: List[Any],
    learned_profiles: Optional[List[Dict[str, Any]]] = None,
) -> Tuple[Dict[str, Counter], Set[Tuple[str, str]]]:
    """
    Learns per-business merchant -> category frequency distributions and verified
    (merchant, category) legitimate exceptions from historical transactions and
    persisted behavioral profiles.
    Excludes confirmed genuine anomalies / suspicious transactions from normal mappings.
    """
    pair_counts: Dict[str, Counter] = {}
    verified_exceptions: Set[Tuple[str, str]] = set()

    for tx in historical_transactions or []:
        fb = str(_extract_tx_field(tx, "anomaly_feedback_status", "") or "").lower().strip()
        if fb in {"suspicious", "genuine_anomaly", "genuine anomaly"}:
            continue

        raw_m = _extract_tx_field(tx, "merchant")
        raw_d = _extract_tx_field(tx, "description")
        raw_c = _extract_tx_field(tx, "category_name")
        if not raw_m or not raw_c:
            continue

        norm = normalize_merchant_name(raw_m, raw_d)["canonical"]
        if not norm:
            continue

        cat = canonicalize_category(raw_c)
        is_confirmed = bool(_extract_tx_field(tx, "is_confirmed", False)) or bool(_extract_tx_field(tx, "verified_label", None))
        # Give slightly higher weight to verified/legitimate transactions
        weight = 2 if (fb == "legitimate" or is_confirmed) else 1

        # Don't let unreviewed anomalous transactions distort normal merchant-category mapping
        is_anom = bool(_extract_tx_field(tx, "is_anomaly", False))
        if is_anom and fb != "legitimate":
            continue

        pair_counts.setdefault(norm, Counter())[cat] += weight
        if fb == "legitimate" or is_confirmed:
            verified_exceptions.add((norm, cat))

    # Merge persisted BehavioralProfileModel entries if supplied
    for prof in learned_profiles or []:
        ptype = prof.get("profile_type")
        pkey = prof.get("profile_key", "")
        stats = prof.get("stats") or {}
        if ptype == "merchant" and pkey:
            norm = normalize_merchant_name(pkey)["canonical"] or pkey.lower().strip()
            cat_hist = stats.get("categories") or {}
            if isinstance(cat_hist, dict):
                for c, cnt in cat_hist.items():
                    cc = canonicalize_category(c)
                    pair_counts.setdefault(norm, Counter())[cc] += int(cnt)
            elif stats.get("category"):
                cc = canonicalize_category(stats["category"])
                pair_counts.setdefault(norm, Counter())[cc] += max(1, int(stats.get("count", 1)))
            for exc_cat in stats.get("verified_categories", []) or []:
                verified_exceptions.add((norm, canonicalize_category(exc_cat)))
        elif ptype == "merchant_category_exception" and pkey:
            norm_m = stats.get("canonical_merchant") or normalize_merchant_name(pkey.split("::")[0])["canonical"]
            exc_c = canonicalize_category(stats.get("category") or (pkey.split("::")[1] if "::" in pkey else ""))
            if norm_m and exc_c:
                verified_exceptions.add((norm_m, exc_c))
                pair_counts.setdefault(norm_m, Counter())[exc_c] += 2

    return pair_counts, verified_exceptions


def evaluate_merchant_category_consistency(
    merchant: Optional[str],
    category: Optional[str],
    description: Optional[str] = None,
    historical_transactions: Optional[List[Any]] = None,
    learned_profiles: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """
    Evaluates whether the (merchant, category) pair is consistent with:
    1. The business's own learned merchant-category history.
    2. General vendor-domain priors (catching obvious misclassifications such as
       a cloud software vendor classified as Groceries).
    3. Verified legitimate exceptions (which suppress false mismatch alerts).

    Unfamiliar merchants with no conflicting domain prior are treated neutrally (score 0.0).
    """
    norm_info = normalize_merchant_name(merchant, description)
    canonical_m = norm_info["canonical"]
    canonical_cat = canonicalize_category(category)

    if not canonical_m:
        return {
            "status": "unknown",
            "is_mismatch": False,
            "score": 0.0,
            "confidence": 0.25,
            "canonical_merchant": "",
            "expected_categories": [],
            "historical_occurrences": 0,
            "exception_allowed": False,
            "reason": "No merchant identifier available for consistency check.",
        }

    pair_counts, verified_exceptions = build_merchant_category_map(
        historical_transactions or [],
        learned_profiles=learned_profiles,
    )

    # Check if this exact (merchant, category) pair has been verified as a legitimate exception
    if (canonical_m, canonical_cat) in verified_exceptions:
        return {
            "status": "verified_exception",
            "is_mismatch": False,
            "score": 0.0,
            "confidence": 0.95,
            "canonical_merchant": canonical_m,
            "expected_categories": [c for c, _ in pair_counts.get(canonical_m, Counter()).most_common(3)],
            "historical_occurrences": sum(pair_counts.get(canonical_m, Counter()).values()),
            "exception_allowed": True,
            "reason": f"'{norm_info['display']}' under '{canonical_cat}' is a verified legitimate combination for this business.",
        }

    # 1. Check business-specific historical merchant-category consistency
    m_counts = pair_counts.get(canonical_m)
    if m_counts:
        total_obs = sum(m_counts.values())
        cat_obs = m_counts.get(canonical_cat, 0)
        dominant_cat, dominant_cnt = m_counts.most_common(1)[0]
        dominant_share = dominant_cnt / max(1, total_obs)
        expected_cats = [c for c, _ in m_counts.most_common(3)]

        # Consistent if we've seen this pair before with meaningful frequency
        if cat_obs > 0:
            share = cat_obs / max(1, total_obs)
            if share >= 0.20 or cat_obs >= 2:
                return {
                    "status": "consistent",
                    "is_mismatch": False,
                    "score": 0.0,
                    "confidence": min(0.95, 0.65 + 0.05 * total_obs),
                    "canonical_merchant": canonical_m,
                    "expected_categories": expected_cats,
                    "historical_occurrences": total_obs,
                    "exception_allowed": False,
                    "reason": f"'{norm_info['display']}' is historically consistent with '{canonical_cat}'.",
                }

        # Flag mismatch when history strongly associates merchant with a different category
        if total_obs >= 2 and cat_obs == 0 and dominant_share >= 0.75:
            # Scale score & confidence by historical support
            support_factor = min(1.0, total_obs / 5.0)
            score = round(0.62 + 0.24 * support_factor, 3)
            confidence = round(0.74 + 0.20 * support_factor, 3)
            return {
                "status": "mismatch",
                "is_mismatch": True,
                "score": score,
                "confidence": confidence,
                "canonical_merchant": canonical_m,
                "expected_categories": expected_cats,
                "dominant_category": dominant_cat,
                "dominant_share": round(dominant_share, 3),
                "historical_occurrences": total_obs,
                "exception_allowed": False,
                "reason": (
                    f"Merchant '{norm_info['display']}' is typically classified under '{dominant_cat}' "
                    f"({dominant_share:.0%} of prior occurrences) rather than '{canonical_cat}'."
                ),
            }

    # 2. Secondary check: general vendor-domain prior (catches obvious misclassifications
    # even on first occurrence, e.g., a cloud vendor categorized as Groceries & Ingredients)
    check_text = f"{canonical_m} {(merchant or '').lower()}"
    for pat, allowed_cats, vendor_desc in VENDOR_DOMAIN_PRIORS:
        if re.search(pat, check_text, re.IGNORECASE):
            if canonical_cat not in allowed_cats and canonical_cat != "Miscellaneous":
                expected_list = sorted(list(allowed_cats))
                return {
                    "status": "domain_mismatch",
                    "is_mismatch": True,
                    "score": 0.72,
                    "confidence": 0.85,
                    "canonical_merchant": canonical_m,
                    "expected_categories": expected_list,
                    "dominant_category": expected_list[0],
                    "historical_occurrences": sum(m_counts.values()) if m_counts else 0,
                    "exception_allowed": False,
                    "reason": (
                        f"'{norm_info['display']}' is a known {vendor_desc}, which conflicts with "
                        f"the assigned category '{canonical_cat}'."
                    ),
                }
            else:
                return {
                    "status": "consistent",
                    "is_mismatch": False,
                    "score": 0.0,
                    "confidence": 0.80,
                    "canonical_merchant": canonical_m,
                    "expected_categories": sorted(list(allowed_cats)),
                    "historical_occurrences": sum(m_counts.values()) if m_counts else 0,
                    "exception_allowed": False,
                    "reason": f"'{norm_info['display']}' aligns with category '{canonical_cat}'.",
                }

    # 3. Unfamiliar merchant with no contradiction -> neutral (DO NOT treat unfamiliar merchant as suspicious!)
    return {
        "status": "unfamiliar_neutral",
        "is_mismatch": False,
        "score": 0.0,
        "confidence": 0.40,
        "canonical_merchant": canonical_m,
        "expected_categories": [],
        "historical_occurrences": 0,
        "exception_allowed": False,
        "reason": f"'{norm_info['display']}' is a new merchant for this business; no category contradiction detected.",
    }
