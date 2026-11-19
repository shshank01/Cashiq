"""
CashIQ Business-Context Industry-to-Category Taxonomy & Expense Relevance Layer.

Provides:
1. A maintainable, data-driven mapping from industry / business type / operating model
   to expected, unusual, and unrelated expense categories.
2. Semantic domain classification to detect category-level operational mismatches
   without hardcoding individual merchants or one-off product examples.
3. Gradual personalization of a workspace's expense profile from verified transactions
   and confirmed user feedback.
4. Neutral ("unknown") handling when business context is missing — never treating
   missing profile data as evidence of suspicious activity.
"""

import re
from typing import Any, Dict, List, Optional, Set, Tuple


# Canonical expense categories recognized across CashIQ
ALL_EXPENSE_CATEGORIES: List[str] = [
    "Software & Cloud Services",
    "Payroll & Wages",
    "Rent & Facilities",
    "Marketing & Advertising",
    "Professional & Legal",
    "Meals & Entertainment",
    "Office Supplies & Equipment",
    "Travel & Transportation",
    "Utilities & Telecom",
    "Taxes & Compliance",
    "Insurance",
    "Banking & Fees",
    "Loans & Financing",
    "Equipment & Hardware",
    "Shipping & Logistics",
    "Inventory & Raw Materials",
    "Groceries & Ingredients",
    "Medical Supplies & Equipment",
    "Construction & Site Materials",
    "Agricultural Supplies",
    "Personal & Household",
    "Client Revenue",
    "Miscellaneous",
]

# Core overhead categories expected across almost all operating businesses
CORE_UNIVERSAL_EXPECTED: Set[str] = {
    "Payroll & Wages",
    "Rent & Facilities",
    "Professional & Legal",
    "Utilities & Telecom",
    "Taxes & Compliance",
    "Insurance",
    "Banking & Fees",
    "Loans & Financing",
    "Office Supplies & Equipment",
    "Client Revenue",
}

# Industry taxonomy definitions (canonical key -> aliases, expected, unusual, unrelated, typical_weekend_ops)
INDUSTRY_TAXONOMY: Dict[str, Dict[str, Any]] = {
    "saas_technology": {
        "label": "SaaS & Technology",
        "aliases": [
            "saas", "b2b saas", "b2c saas", "technology", "tech", "software",
            "cloud computing", "cloud", "it services", "ai", "developer tools",
            "fintech", "cybersecurity", "data analytics", "internet", "edtech",
        ],
        "expected": list(CORE_UNIVERSAL_EXPECTED | {
            "Software & Cloud Services",
            "Marketing & Advertising",
            "Meals & Entertainment",
            "Travel & Transportation",
            "Equipment & Hardware",
        }),
        "unusual": [
            "Shipping & Logistics",
            "Miscellaneous",
        ],
        "unrelated": [
            "Groceries & Ingredients",
            "Inventory & Raw Materials",
            "Medical Supplies & Equipment",
            "Construction & Site Materials",
            "Agricultural Supplies",
            "Personal & Household",
        ],
        "weekend_operations_expected": False,
    },
    "restaurant_food_beverage": {
        "label": "Restaurant, Food & Beverage",
        "aliases": [
            "restaurant", "food", "food & beverage", "f&b", "cafe", "bakery",
            "catering", "hospitality", "cloud kitchen", "qsr", "bar", "hotel",
            "food service", "dining", "grocery", "supermarket",
        ],
        "expected": list(CORE_UNIVERSAL_EXPECTED | {
            "Groceries & Ingredients",
            "Inventory & Raw Materials",
            "Equipment & Hardware",
            "Shipping & Logistics",
            "Marketing & Advertising",
            "Meals & Entertainment",
            "Software & Cloud Services",
        }),
        "unusual": [
            "Travel & Transportation",
            "Miscellaneous",
        ],
        "unrelated": [
            "Medical Supplies & Equipment",
            "Construction & Site Materials",
            "Personal & Household",
        ],
        "weekend_operations_expected": True,
    },
    "retail_ecommerce": {
        "label": "Retail & E-commerce",
        "aliases": [
            "retail", "e-commerce", "ecommerce", "d2c", "consumer goods",
            "apparel", "fashion", "wholesale", "trading", "store", "marketplace",
            "distribution",
        ],
        "expected": list(CORE_UNIVERSAL_EXPECTED | {
            "Inventory & Raw Materials",
            "Shipping & Logistics",
            "Marketing & Advertising",
            "Software & Cloud Services",
            "Travel & Transportation",
            "Meals & Entertainment",
            "Equipment & Hardware",
        }),
        "unusual": [
            "Groceries & Ingredients",
            "Miscellaneous",
        ],
        "unrelated": [
            "Medical Supplies & Equipment",
            "Construction & Site Materials",
            "Agricultural Supplies",
            "Personal & Household",
        ],
        "weekend_operations_expected": True,
    },
    "agency_consulting": {
        "label": "Agency, Consulting & Professional Services",
        "aliases": [
            "agency", "consulting", "professional services", "services",
            "design", "marketing agency", "legal", "accounting", "advisory",
            "freelance", "studio", "media", "staffing",
        ],
        "expected": list(CORE_UNIVERSAL_EXPECTED | {
            "Software & Cloud Services",
            "Marketing & Advertising",
            "Meals & Entertainment",
            "Travel & Transportation",
            "Equipment & Hardware",
        }),
        "unusual": [
            "Shipping & Logistics",
            "Miscellaneous",
        ],
        "unrelated": [
            "Groceries & Ingredients",
            "Inventory & Raw Materials",
            "Medical Supplies & Equipment",
            "Construction & Site Materials",
            "Agricultural Supplies",
            "Personal & Household",
        ],
        "weekend_operations_expected": False,
    },
    "healthcare_medical": {
        "label": "Healthcare & Medical",
        "aliases": [
            "healthcare", "medical", "clinic", "hospital", "pharmacy",
            "diagnostics", "dental", "biotech", "pharma", "wellness",
            "healthtech",
        ],
        "expected": list(CORE_UNIVERSAL_EXPECTED | {
            "Medical Supplies & Equipment",
            "Equipment & Hardware",
            "Software & Cloud Services",
            "Shipping & Logistics",
            "Marketing & Advertising",
            "Travel & Transportation",
        }),
        "unusual": [
            "Meals & Entertainment",
            "Inventory & Raw Materials",
            "Miscellaneous",
        ],
        "unrelated": [
            "Groceries & Ingredients",
            "Construction & Site Materials",
            "Agricultural Supplies",
            "Personal & Household",
        ],
        "weekend_operations_expected": True,
    },
    "manufacturing_logistics": {
        "label": "Manufacturing & Logistics",
        "aliases": [
            "manufacturing", "factory", "industrial", "logistics", "supply chain",
            "warehousing", "freight", "automotive", "electronics manufacturing",
            "textiles", "hardware",
        ],
        "expected": list(CORE_UNIVERSAL_EXPECTED | {
            "Inventory & Raw Materials",
            "Shipping & Logistics",
            "Equipment & Hardware",
            "Travel & Transportation",
            "Software & Cloud Services",
            "Marketing & Advertising",
        }),
        "unusual": [
            "Meals & Entertainment",
            "Construction & Site Materials",
            "Miscellaneous",
        ],
        "unrelated": [
            "Groceries & Ingredients",
            "Medical Supplies & Equipment",
            "Agricultural Supplies",
            "Personal & Household",
        ],
        "weekend_operations_expected": False,
    },
    "construction_realestate": {
        "label": "Construction & Real Estate",
        "aliases": [
            "construction", "real estate", "property", "architecture",
            "civil engineering", "contracting", "infrastructure", "interior design",
        ],
        "expected": list(CORE_UNIVERSAL_EXPECTED | {
            "Construction & Site Materials",
            "Equipment & Hardware",
            "Shipping & Logistics",
            "Travel & Transportation",
            "Inventory & Raw Materials",
            "Marketing & Advertising",
            "Software & Cloud Services",
        }),
        "unusual": [
            "Meals & Entertainment",
            "Miscellaneous",
        ],
        "unrelated": [
            "Groceries & Ingredients",
            "Medical Supplies & Equipment",
            "Agricultural Supplies",
            "Personal & Household",
        ],
        "weekend_operations_expected": False,
    },
    "agriculture_agritech": {
        "label": "Agriculture & Farming",
        "aliases": [
            "agriculture", "farming", "agritech", "agribusiness", "dairy",
            "horticulture", "food processing",
        ],
        "expected": list(CORE_UNIVERSAL_EXPECTED | {
            "Agricultural Supplies",
            "Inventory & Raw Materials",
            "Equipment & Hardware",
            "Shipping & Logistics",
            "Travel & Transportation",
            "Groceries & Ingredients",
        }),
        "unusual": [
            "Software & Cloud Services",
            "Marketing & Advertising",
            "Meals & Entertainment",
            "Miscellaneous",
        ],
        "unrelated": [
            "Medical Supplies & Equipment",
            "Personal & Household",
        ],
        "weekend_operations_expected": True,
    },
    "education_training": {
        "label": "Education & Training",
        "aliases": [
            "education", "school", "university", "coaching", "training",
            "academy", "learning", "tutoring",
        ],
        "expected": list(CORE_UNIVERSAL_EXPECTED | {
            "Software & Cloud Services",
            "Marketing & Advertising",
            "Equipment & Hardware",
            "Travel & Transportation",
            "Meals & Entertainment",
        }),
        "unusual": [
            "Shipping & Logistics",
            "Miscellaneous",
        ],
        "unrelated": [
            "Groceries & Ingredients",
            "Inventory & Raw Materials",
            "Medical Supplies & Equipment",
            "Construction & Site Materials",
            "Agricultural Supplies",
            "Personal & Household",
        ],
        "weekend_operations_expected": False,
    },
}

# Operating-model adjustments (adds expected or shifts categories naturally)
OPERATING_MODEL_ADJUSTMENTS: Dict[str, Dict[str, List[str]]] = {
    "remote": {
        "expected": ["Software & Cloud Services", "Equipment & Hardware"],
        "unusual": ["Rent & Facilities"],
    },
    "remote-first": {
        "expected": ["Software & Cloud Services", "Equipment & Hardware"],
        "unusual": ["Rent & Facilities"],
    },
    "d2c": {
        "expected": ["Shipping & Logistics", "Marketing & Advertising", "Inventory & Raw Materials"],
    },
    "marketplace": {
        "expected": ["Software & Cloud Services", "Marketing & Advertising", "Banking & Fees"],
    },
    "brick-and-mortar": {
        "expected": ["Rent & Facilities", "Utilities & Telecom", "Inventory & Raw Materials"],
    },
    "b2b": {
        "expected": ["Software & Cloud Services", "Travel & Transportation", "Professional & Legal"],
    },
    "b2c": {
        "expected": ["Marketing & Advertising", "Banking & Fees"],
    },
}

# General semantic domain indicators (category-level vocabulary, NOT merchant names or one-off hardcodes)
# Used to detect when a transaction's description clearly belongs to a distinct operational domain
# even if a user or upstream system placed it in a generic bucket like "Miscellaneous" or "Meals & Entertainment".
SEMANTIC_DOMAIN_PATTERNS: Dict[str, str] = {
    "Groceries & Ingredients": (
        r"\b(?:grocer(?:y|ies)|supermarket|kirana|provisions|vegetables?|fruits?|produce|"
        r"spices?|masala|condiments?|seasonings?|herbs?|flour|atta|rice|dal|lentils?|pulses?|"
        r"cooking\s*oil|ghee|dairy|milk|paneer|butcher|meat|poultry|seafood|ingredients?|"
        r"pantry\s*staples?|baking\s*supplies?|dry\s*fruits?|sugar|salt|turmeric|cumin|coriander|"
        r"cardamom|peppercorns?|chill?i\s*powder|fresh\s*mart)\b"
    ),
    "Medical Supplies & Equipment": (
        r"\b(?:pharmacy|medicines?|pharmaceuticals?|surgical|syringes?|bandages?|diagnostic|"
        r"lab\s*reagents?|medical\s*supplies?|clinical\s*equipment|stethoscope|pathology|"
        r"prescription\s*drugs?|dental\s*supplies?)\b"
    ),
    "Construction & Site Materials": (
        r"\b(?:cement|concrete|rebar|timber|lumber|bricks?|masonry|plumbing\s*pipes?|"
        r"scaffolding|gravel|sand\s*load|roofing\s*sheets?|drywall|construction\s*materials?|"
        r"site\s*excavation|structural\s*steel)\b"
    ),
    "Agricultural Supplies": (
        r"\b(?:fertilizer|pesticide|herbicide|crop\s*seeds?|tractor\s*parts?|irrigation\s*drip|"
        r"livestock\s*feed|fodder|agro\s*chemicals?|farm\s*inputs?|nursery\s*saplings?)\b"
    ),
    "Personal & Household": (
        r"\b(?:personal\s*care|salon|spa\s*treatment|cosmetics?|jewelry|jewellery|"
        r"home\s*appliances?|laundry\s*detergent|pet\s*food|veterinary|gym\s*membership|"
        r"cinema\s*tickets?|movie\s*tickets?|video\s*games?|gaming\s*console|liquor\s*store|"
        r"wine\s*shop|personal\s*shopping|clothing\s*boutique)\b"
    ),
    "Inventory & Raw Materials": (
        r"\b(?:raw\s*materials?|wholesale\s*stock|merchandise\s*inventory|packaging\s*boxes?|"
        r"bulk\s*stock|finished\s*goods|sku\s*replenishment|fabric\s*rolls?|component\s*parts?)\b"
    ),
    "Shipping & Logistics": (
        r"\b(?:freight|courier|shipping\s*charges?|logistics|customs\s*duty|air\s*cargo|"
        r"warehouse\s*handling|parcel\s*delivery|dispatch|consignment|docket)\b"
    ),
}

# Category aliases for normalizing free-form category names to canonical CashIQ categories
CATEGORY_ALIASES: Dict[str, str] = {
    "software": "Software & Cloud Services",
    "software & services": "Software & Cloud Services",
    "cloud": "Software & Cloud Services",
    "saas": "Software & Cloud Services",
    "subscriptions": "Software & Cloud Services",
    "payroll": "Payroll & Wages",
    "salaries": "Payroll & Wages",
    "wages": "Payroll & Wages",
    "rent": "Rent & Facilities",
    "facilities": "Rent & Facilities",
    "marketing": "Marketing & Advertising",
    "advertising": "Marketing & Advertising",
    "legal": "Professional & Legal",
    "professional services": "Professional & Legal",
    "meals": "Meals & Entertainment",
    "dining": "Meals & Entertainment",
    "food & dining": "Meals & Entertainment",
    "office supplies": "Office Supplies & Equipment",
    "travel": "Travel & Transportation",
    "transportation": "Travel & Transportation",
    "utilities": "Utilities & Telecom",
    "telecom": "Utilities & Telecom",
    "taxes": "Taxes & Compliance",
    "banking fees": "Banking & Fees",
    "bank fees": "Banking & Fees",
    "equipment": "Equipment & Hardware",
    "hardware": "Equipment & Hardware",
    "groceries": "Groceries & Ingredients",
    "food ingredients": "Groceries & Ingredients",
    "ingredients": "Groceries & Ingredients",
    "inventory": "Inventory & Raw Materials",
    "raw materials": "Inventory & Raw Materials",
    "cogs": "Inventory & Raw Materials",
    "shipping": "Shipping & Logistics",
    "logistics": "Shipping & Logistics",
    "medical": "Medical Supplies & Equipment",
    "medical supplies": "Medical Supplies & Equipment",
    "construction": "Construction & Site Materials",
    "agriculture": "Agricultural Supplies",
    "personal": "Personal & Household",
    "household": "Personal & Household",
    "revenue": "Client Revenue",
    "client payment": "Client Revenue",
    "consulting income": "Client Revenue",
    "income": "Client Revenue",
    "uncategorized": "Miscellaneous",
    "other expense": "Miscellaneous",
    "other": "Miscellaneous",
}


def canonicalize_category(category: Optional[str]) -> str:
    """Normalizes category strings to canonical CashIQ category names while preserving custom ones."""
    if not category or not str(category).strip():
        return "Miscellaneous"
    raw = str(category).strip()
    low = raw.lower()
    if low in CATEGORY_ALIASES:
        return CATEGORY_ALIASES[low]
    for canonical in ALL_EXPENSE_CATEGORIES:
        if canonical.lower() == low:
            return canonical
    return raw


def resolve_industry_key(
    industry: Optional[str] = None,
    business_type: Optional[str] = None
) -> Optional[str]:
    """
    Matches free-text industry and/or business_type to a canonical taxonomy key.
    Returns None if neither is provided or recognizable (so missing info stays neutral).
    """
    candidates = []
    if business_type and str(business_type).strip():
        candidates.append(str(business_type).strip().lower())
    if industry and str(industry).strip():
        candidates.append(str(industry).strip().lower())

    if not candidates:
        return None

    # Exact alias match first
    for cand in candidates:
        if cand in INDUSTRY_TAXONOMY:
            return cand
        for key, spec in INDUSTRY_TAXONOMY.items():
            if cand == spec["label"].lower() or cand in spec["aliases"]:
                return key

    # Substring / token match second
    combined = " ".join(candidates)
    best_key = None
    best_len = 0
    for key, spec in INDUSTRY_TAXONOMY.items():
        for alias in spec["aliases"]:
            if alias in combined and len(alias) > best_len:
                best_key = key
                best_len = len(alias)
    return best_key


def infer_semantic_domain(text: Optional[str]) -> Optional[str]:
    """
    Infers a specialized operational expense domain from transaction description/item text
    using general category-level vocabulary (never hardcoded merchant names).
    """
    if not text or not str(text).strip():
        return None
    low = str(text).lower()
    for domain_cat, pattern in SEMANTIC_DOMAIN_PATTERNS.items():
        if re.search(pattern, low, re.IGNORECASE):
            return domain_cat
    return None


def derive_initial_expense_profile(
    industry: Optional[str] = None,
    business_type: Optional[str] = None,
    operating_model: Optional[str] = None,
    custom_categories: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Derives an initial business expense profile from industry, business type, and operating model.
    Preserves any learned categories or explicit user overrides.
    """
    industry_key = resolve_industry_key(industry=industry, business_type=business_type)
    if not industry_key:
        profile = {
            "industry_key": None,
            "industry_label": industry or business_type or "Unspecified",
            "operating_model": operating_model or "Unspecified",
            "expected": sorted(list(CORE_UNIVERSAL_EXPECTED)),
            "unusual": [],
            "unrelated": [],
            "weekend_operations_expected": False,
            "learned_categories": {},
            "custom_overrides": {},
        }
    else:
        spec = INDUSTRY_TAXONOMY[industry_key]
        expected = set(spec["expected"])
        unusual = set(spec["unusual"])
        unrelated = set(spec["unrelated"])

        # Apply operating model refinements
        if operating_model and str(operating_model).strip():
            om_low = str(operating_model).strip().lower()
            for om_key, adj in OPERATING_MODEL_ADJUSTMENTS.items():
                if om_key in om_low:
                    for cat in adj.get("expected", []):
                        expected.add(cat)
                        unusual.discard(cat)
                        unrelated.discard(cat)
                    for cat in adj.get("unusual", []):
                        if cat not in adj.get("expected", []):
                            expected.discard(cat)
                            unusual.add(cat)

        profile = {
            "industry_key": industry_key,
            "industry_label": spec["label"],
            "operating_model": operating_model or "Standard",
            "expected": sorted(list(expected)),
            "unusual": sorted(list(unusual - expected)),
            "unrelated": sorted(list(unrelated - expected - unusual)),
            "weekend_operations_expected": bool(spec.get("weekend_operations_expected", False)),
            "learned_categories": {},
            "custom_overrides": {},
        }

    # Merge existing learned data or explicit user overrides if provided
    if isinstance(custom_categories, dict):
        if "learned_categories" in custom_categories and isinstance(custom_categories["learned_categories"], dict):
            profile["learned_categories"] = dict(custom_categories["learned_categories"])
        if "custom_overrides" in custom_categories and isinstance(custom_categories["custom_overrides"], dict):
            profile["custom_overrides"] = dict(custom_categories["custom_overrides"])
        for bucket in ("expected", "unusual", "unrelated"):
            if isinstance(custom_categories.get(f"custom_{bucket}"), list):
                profile[f"custom_{bucket}"] = custom_categories[f"custom_{bucket}"]
        # If user passed explicit expected/unusual/unrelated overrides directly
        if custom_categories.get("user_customized"):
            for bucket in ("expected", "unusual", "unrelated"):
                if isinstance(custom_categories.get(bucket), list):
                    profile[bucket] = sorted(list({canonicalize_category(c) for c in custom_categories[bucket]}))
            profile["user_customized"] = True

    return profile


def personalize_expense_profile(
    expense_profile: Dict[str, Any],
    verified_category_counts: Dict[str, int],
    promote_to_unusual_min: int = 1,
    promote_to_expected_min: int = 3,
) -> Dict[str, Any]:
    """
    Gradually personalizes a business's expense profile using verified/confirmed transactions.
    - 1–2 verified legitimate transactions in an 'unrelated' category -> demote risk to 'unusual'
    - >=3 verified legitimate transactions in an 'unusual' or 'unrelated' category -> promote to 'expected'
    Never overwrites explicit user custom_overrides.
    """
    updated = dict(expense_profile)
    learned = dict(updated.get("learned_categories") or {})
    expected = set(updated.get("expected") or [])
    unusual = set(updated.get("unusual") or [])
    unrelated = set(updated.get("unrelated") or [])
    overrides = dict(updated.get("custom_overrides") or {})

    for raw_cat, count in verified_category_counts.items():
        if count <= 0:
            continue
        cat = canonicalize_category(raw_cat)
        prev_cnt = int(learned.get(cat, {}).get("verified_count", 0)) if isinstance(learned.get(cat), dict) else int(learned.get(cat, 0))
        new_cnt = max(prev_cnt, int(count))

        if cat in overrides:
            learned[cat] = {"verified_count": new_cnt, "status": overrides[cat]}
            continue

        if new_cnt >= promote_to_expected_min:
            expected.add(cat)
            unusual.discard(cat)
            unrelated.discard(cat)
            status = "expected"
        elif new_cnt >= promote_to_unusual_min and cat in unrelated:
            unrelated.discard(cat)
            unusual.add(cat)
            status = "unusual"
        elif cat in expected:
            status = "expected"
        elif cat in unusual:
            status = "unusual"
        elif cat in unrelated:
            status = "unrelated"
        else:
            status = "expected" if new_cnt >= promote_to_expected_min else "unusual"
            if status == "expected":
                expected.add(cat)
            else:
                unusual.add(cat)

        learned[cat] = {"verified_count": new_cnt, "status": status}

    updated["expected"] = sorted(list(expected))
    updated["unusual"] = sorted(list(unusual - expected))
    updated["unrelated"] = sorted(list(unrelated - expected - unusual))
    updated["learned_categories"] = learned
    return updated


def extract_profile_dict(business_profile: Optional[Any]) -> Optional[Dict[str, Any]]:
    """Normalizes ORM BusinessProfile or plain dict into a unified dictionary."""
    if business_profile is None:
        return None
    if isinstance(business_profile, dict):
        if not any(business_profile.get(k) for k in ("industry", "business_type", "operating_model", "relevant_expense_categories")):
            return None
        return dict(business_profile)

    industry = getattr(business_profile, "industry", None)
    business_type = getattr(business_profile, "business_type", None)
    operating_model = getattr(business_profile, "operating_model", None)
    rel_cats = getattr(business_profile, "relevant_expense_categories", None)
    if not any([industry, business_type, operating_model, rel_cats]):
        return None
    return {
        "company_name": getattr(business_profile, "company_name", None),
        "industry": industry,
        "business_type": business_type,
        "operating_model": operating_model,
        "relevant_expense_categories": rel_cats,
        "employee_count": getattr(business_profile, "employee_count", None),
        "approx_monthly_expenses_minor": getattr(business_profile, "approx_monthly_expenses_minor", None),
    }


def evaluate_category_relevance(
    category: Optional[str],
    business_profile: Optional[Any] = None,
    description: Optional[str] = None,
    merchant: Optional[str] = None,
    verified_category_counts: Optional[Dict[str, int]] = None,
    transaction_type: str = "expense",
) -> Dict[str, Any]:
    """
    Evaluates whether a transaction's category (and semantic domain) is operationally relevant
    for the business profile.

    Returns one of four canonical statuses:
      - 'expected': normal operational expense for this business
      - 'unusual': uncommon for this industry, warrants mild attention
      - 'unrelated': operationally mismatched for this business profile (triggers relevance warning
                     even when transaction amount is small)
      - 'unknown': business profile missing or category not covered by taxonomy (neutral, 0.0 score)
    """
    # Income transactions are evaluated separately from expense operational relevance
    if str(transaction_type).lower() == "income":
        return {
            "status": "expected",
            "score": 0.0,
            "confidence": 0.85,
            "evaluated_category": canonicalize_category(category),
            "inferred_domain": None,
            "industry_key": None,
            "industry_label": None,
            "personalized": False,
            "reason": "Inflow transaction.",
        }

    prof_dict = extract_profile_dict(business_profile)
    canonical_cat = canonicalize_category(category)

    # Missing business profile -> neutral "unknown", NEVER treated as suspicious!
    if not prof_dict:
        return {
            "status": "unknown",
            "score": 0.0,
            "confidence": 0.25,
            "evaluated_category": canonical_cat,
            "inferred_domain": infer_semantic_domain(f"{merchant or ''} {description or ''}"),
            "industry_key": None,
            "industry_label": None,
            "personalized": False,
            "reason": "Business profile not configured; operational category relevance is unknown (no penalty applied).",
        }

    stored_rel = prof_dict.get("relevant_expense_categories")
    expense_profile = derive_initial_expense_profile(
        industry=prof_dict.get("industry"),
        business_type=prof_dict.get("business_type"),
        operating_model=prof_dict.get("operating_model"),
        custom_categories=stored_rel if isinstance(stored_rel, dict) else None,
    )

    if verified_category_counts:
        expense_profile = personalize_expense_profile(expense_profile, verified_category_counts)

    industry_key = expense_profile.get("industry_key")
    industry_label = expense_profile.get("industry_label") or prof_dict.get("business_type") or prof_dict.get("industry")

    # If industry couldn't be resolved and no custom categories were configured -> unknown (neutral)
    if not industry_key and not (isinstance(stored_rel, dict) and stored_rel.get("user_customized")):
        return {
            "status": "unknown",
            "score": 0.0,
            "confidence": 0.30,
            "evaluated_category": canonical_cat,
            "inferred_domain": None,
            "industry_key": None,
            "industry_label": industry_label,
            "personalized": False,
            "reason": f"Industry '{industry_label}' has no specific taxonomy mapping; relevance is unknown (no penalty applied).",
        }

    expected_set = set(expense_profile.get("expected", []))
    unusual_set = set(expense_profile.get("unusual", []))
    unrelated_set = set(expense_profile.get("unrelated", []))
    overrides = expense_profile.get("custom_overrides") or {}
    learned = expense_profile.get("learned_categories") or {}

    # Check if transaction text reveals a specialized operational domain that was placed in a broad category
    # (e.g., cooking ingredients placed in Miscellaneous or Meals & Entertainment)
    inferred_domain = infer_semantic_domain(f"{merchant or ''} {description or ''}")
    effective_cat = canonical_cat
    domain_override_used = False
    if inferred_domain and canonical_cat in {"Miscellaneous", "Meals & Entertainment", "Office Supplies & Equipment"}:
        if inferred_domain in unrelated_set or inferred_domain in unusual_set:
            effective_cat = inferred_domain
            domain_override_used = True

    personalized = effective_cat in learned or effective_cat in overrides

    # Determine status
    if effective_cat in overrides:
        status = overrides[effective_cat]
    elif effective_cat in expected_set:
        status = "expected"
    elif effective_cat in unrelated_set:
        status = "unrelated"
    elif effective_cat in unusual_set:
        status = "unusual"
    else:
        status = "unknown"

    # Compute calibrated relevance score and confidence
    # Note: 'unrelated' scores high enough to trigger an operational-relevance warning
    # independently of transaction amount (e.g., ₹100 groceries at a SaaS company).
    biz_desc = prof_dict.get("business_type") or industry_label or "this business"
    if status == "expected":
        score = 0.0
        confidence = 0.90 if not personalized else 0.95
        reason = f"'{effective_cat}' is an expected operational expense category for a {biz_desc} business."
    elif status == "unrelated":
        # Slightly tempered if inferred only from description rather than explicit category
        score = 0.78 if not domain_override_used else 0.72
        confidence = 0.88 if not domain_override_used else 0.80
        if domain_override_used:
            reason = (
                f"Expense appears operationally unrelated ({effective_cat}) for a {biz_desc} business "
                f"(industry: {industry_label}), even though recorded under '{canonical_cat}'."
            )
        else:
            reason = (
                f"'{effective_cat}' is operationally unrelated to a {biz_desc} business "
                f"(industry: {industry_label})."
            )
    elif status == "unusual":
        score = 0.35
        confidence = 0.70
        reason = (
            f"'{effective_cat}' is uncommon for a {biz_desc} business "
            f"(industry: {industry_label})."
        )
    else:
        score = 0.0
        confidence = 0.35
        reason = f"Category '{effective_cat}' is not mapped in the {industry_label} taxonomy (treated neutrally)."

    return {
        "status": status,
        "score": round(float(score), 3),
        "confidence": round(float(confidence), 3),
        "evaluated_category": effective_cat,
        "original_category": canonical_cat,
        "inferred_domain": inferred_domain,
        "domain_override_used": domain_override_used,
        "industry_key": industry_key,
        "industry_label": industry_label,
        "operating_model": expense_profile.get("operating_model"),
        "weekend_operations_expected": bool(expense_profile.get("weekend_operations_expected", False)),
        "personalized": personalized,
        "reason": reason,
    }


def list_supported_industries() -> List[Dict[str, Any]]:
    """Returns supported industries and their default category profiles for API/UI consumption."""
    return [
        {
            "key": key,
            "label": spec["label"],
            "aliases": spec["aliases"],
            "expected": sorted(spec["expected"]),
            "unusual": sorted(spec["unusual"]),
            "unrelated": sorted(spec["unrelated"]),
            "weekend_operations_expected": spec.get("weekend_operations_expected", False),
        }
        for key, spec in INDUSTRY_TAXONOMY.items()
    ]
