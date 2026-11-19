"""
CashIQ Financial-Field Extraction & Deterministic Validation Engine.

Accurately extracts structured financial fields from OCR lines/boxes or native PDF text:
- Merchant / payee
- Transaction date (Indian DD/MM/YYYY, DD-MMM-YYYY, ISO, US formats with Indian disambiguation)
- Final payable total (strictly separated from subtotals, taxes, discounts, previous/closing balances,
  amounts paid/tendered, and individual line items)
- Subtotal / taxable value
- Taxes: GST, CGST, SGST, IGST, UTGST, VAT, Sales Tax (with granular breakdown)
- Discount & round-off
- Invoice / bill / order number
- Payment method, UPI ID, transaction reference (UTR / Auth / Ref), GSTIN
- Debit/Credit direction (`expense` / `income`)
- Currency (₹, Rs., INR, $, USD, €, EUR, £, GBP, etc., with Indian tax/UPI inference)
- Line items (`description`, `quantity`, `unit_price_minor`, `amount_minor`)

Performs deterministic validation:
- Reconciles `subtotal + tax - discount + round_off == total` within defined tolerance
- Reconciles line items sum against subtotal/total when present
- Checks date validity (never silently fabricates missing dates without flagging!)
- Checks amount validity & debit/credit direction consistency
- Attaches field-level confidence, extraction method, and source location (page/line/bbox)
- Requests human review (`review_required=True` + explicit `review_reasons`) whenever a
  critical field has low confidence or fails validation.
"""

from datetime import datetime, timezone
import re
from typing import Any, Dict, List, Optional, Tuple

from app.ml.categorizer import categorizer_instance


# Currency symbol & token detection (ordered longest/most specific first)
CURRENCY_PATTERNS: List[Tuple[str, str]] = [
    (r"₹", "INR"),
    (r"\bINR\b", "INR"),
    (r"\bRs\.?\s*(?=\d)", "INR"),
    (r"\bRupees\b", "INR"),
    (r"\bUSD\b", "USD"),
    (r"\$", "USD"),
    (r"\bEUR\b", "EUR"),
    (r"€", "EUR"),
    (r"\bGBP\b", "GBP"),
    (r"£", "GBP"),
    (r"\bCAD\b", "CAD"),
    (r"\bAUD\b", "AUD"),
    (r"\bSGD\b", "SGD"),
    (r"\bAED\b", "AED"),
]

# Indian 15-character GSTIN pattern (2-digit state + 10-char PAN + 1 entity + Z + 1 checksum)
GSTIN_RE = re.compile(r"\b(\d{2}[A-Z]{5}\d{4}[A-Z][A-Z\d]Z[A-Z\d])\b")
UPI_ID_RE = re.compile(r"\b([a-zA-Z0-9][a-zA-Z0-9._\-]{1,40}@[a-zA-Z][a-zA-Z0-9]{1,20})\b")

# Number token supporting BOTH Indian grouping (1,23,456.78) and International grouping (123,456.78)
# Also supports optional negative sign or accounting parentheses (1,234.56)
AMOUNT_TOKEN_RE = re.compile(
    r"(?:(?:₹|Rs\.?|INR|\$|USD|€|EUR|£|GBP)\s*)?"
    r"(\(?[+\-]?(?:\d{1,3}(?:,\d{2,3})+|\d+)(?:\.\d{1,2})?\)?)"
)

# Strict exclusion patterns for lines that must NEVER be mistaken for final payable total
EXCLUDED_TOTAL_LINE_RE = re.compile(
    r"\b(?:sub\s*[-]?\s*total|taxable\s*(?:value|amount|amt)|assessable\s*value|"
    r"cgst|sgst|igst|utgst|gst\s*@|sales\s*tax|vat\s*@|cess|"
    r"discount|savings|round\s*off|rounding|"
    r"previous\s*bal(?:ance)?|opening\s*bal(?:ance)?|closing\s*bal(?:ance)?|"
    r"bal(?:ance)?\s*(?:b/f|c/f|brought|carried)|"
    r"amount\s*paid|cash\s*tendered|tendered|change\s*due|paid\s*amount|"
    r"qty|quantity|rate|unit\s*price|mrp|hsn|sac|gstin|pan|cin|phone|tel|mobile|pin\s*code)\b",
    re.IGNORECASE,
)

# Prioritized final payable total label tiers (tier 1 = highest specificity)
TOTAL_LABEL_TIERS: List[Tuple[int, str, float]] = [
    (
        1,
        r"\b(?:grand\s*total|net\s*payable|total\s*payable|amount\s*payable|total\s*amount\s*due|"
        r"invoice\s*total|final\s*amount|final\s*total|bill\s*total|total\s*bill|total\s*invoice\s*value|"
        r"net\s*amount\s*payable|net\s*invoice\s*amount)\b",
        0.96,
    ),
    (
        2,
        r"\b(?:total\s*amount|amount\s*due|balance\s*due|total\s*due|bill\s*amount|net\s*amount|payable\s*amount)\b",
        0.92,
    ),
    (
        3,
        r"(?:^|\s)(?:total)(?:\s*\([A-Z₹$]{1,4}\))?\s*[:=\-₹$]",
        0.86,
    ),
    (
        4,
        r"^\s*total\s+[\d₹\$Rs]",
        0.82,
    ),
]

SUBTOTAL_LABEL_RE = re.compile(
    r"\b(?:sub\s*[-]?\s*total|taxable\s*(?:value|amount|amt|total)|assessable\s*value|net\s*before\s*tax|gross\s*amount)\b",
    re.IGNORECASE,
)

DISCOUNT_LABEL_RE = re.compile(
    r"\b(?:discount|less\s*discount|promo\s*discount|coupon|rebate|trade\s*discount)\b",
    re.IGNORECASE,
)

ROUNDOFF_LABEL_RE = re.compile(
    r"\b(?:round\s*[-]?\s*off|rounding(?:\s*adj(?:ustment)?)?)\b",
    re.IGNORECASE,
)

# Line item regex: optional qty + description + amount at right end
LINE_ITEM_RE = re.compile(
    r"^\s*(?:(\d+)\s*[xX\*]\s+)?([A-Za-z][A-Za-z0-9\s\-\(\)/&,\.]{2,65}?)\s+(?:(\d+)\s+)?(?:₹|Rs\.?|INR|\$|€|£)?\s*([\d,]+(?:\.\d{2}))\s*$"
)


def parse_amount_str(raw: str) -> Tuple[Optional[float], Optional[str]]:
    """
    Parses Indian (1,23,456.78) or international (123,456.78) currency amount strings,
    including accounting parentheses `(450.00)` -> `-450.00`.
    """
    if not raw or not str(raw).strip():
        return None, None
    s = str(raw).strip()

    detected_curr = None
    for pat, curr in CURRENCY_PATTERNS:
        if re.search(pat, s, re.IGNORECASE):
            detected_curr = curr
            break

    is_paren_neg = s.startswith("(") and s.endswith(")")
    cleaned = s.replace(",", "").replace(" ", "")
    # Remove currency markers
    cleaned = re.sub(r"(?:₹|Rs\.?|INR|\$|USD|€|EUR|£|GBP|CAD|AUD|SGD|AED)", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"[^\d.\-+]", "", cleaned)
    if not cleaned or cleaned in {".", "-", "+", "-.", "+."}:
        return None, detected_curr
    # Guard against multiple decimal points (e.g. IP address or date 12.10.2026)
    if cleaned.count(".") > 1:
        return None, detected_curr
    try:
        val = float(cleaned)
        if is_paren_neg and val > 0:
            val = -val
        return val, detected_curr
    except ValueError:
        return None, detected_curr


def detect_currency_from_text(text: str, default: str = "USD") -> Tuple[str, float, str]:
    """Detects document currency with confidence and extraction method."""
    if not text:
        return default, 0.30, "default_fallback"

    for pat, curr in CURRENCY_PATTERNS:
        if re.search(pat, text, re.IGNORECASE if len(pat) > 2 else 0):
            return curr, 0.96, "explicit_symbol_or_code"

    # Indian tax / banking indicators strongly imply INR even if ₹ symbol was dropped by OCR
    if re.search(r"\b(?:gstin|cgst|sgst|igst|utgst|upi|neft|imps|rtgs|ifsc|hsn|sac|paise|lakhs?)\b", text, re.IGNORECASE):
        return "INR", 0.90, "indian_tax_or_rail_context"

    return default, 0.40, "default_fallback"


def parse_date_robust(date_str: str, prefer_dayfirst: bool = True) -> Optional[datetime]:
    """
    Parses transaction dates across Indian (DD/MM/YYYY, DD-MMM-YYYY), ISO (YYYY-MM-DD),
    and US formats with explicit Indian day-first disambiguation and calendar plausibility checks.
    """
    if not date_str or not str(date_str).strip():
        return None
    s = str(date_str).strip()
    s = re.sub(r"\s+", " ", s)
    # Strip ordinal suffixes like 12th Oct 2026
    s = re.sub(r"\b(\d{1,2})(?:st|nd|rd|th)\b", r"\1", s, flags=re.IGNORECASE)

    iso_formats = ["%Y-%m-%d", "%Y/%m/%d", "%Y.%m.%d", "%Y%m%d"]
    dayfirst_formats = [
        "%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y",
        "%d/%m/%y", "%d-%m-%y", "%d.%m.%y",
        "%d %b %Y", "%d %B %Y", "%d-%b-%Y", "%d-%B-%Y",
        "%d-%b-%y", "%d %b %y", "%d/%b/%Y", "%d %b, %Y", "%d %B, %Y",
    ]
    monthfirst_formats = [
        "%m/%d/%Y", "%m-%d-%Y", "%m/%d/%y", "%m-%d-%y",
        "%b %d, %Y", "%B %d, %Y", "%b %d %Y", "%B %d %Y",
    ]

    ordered_formats = iso_formats + (dayfirst_formats + monthfirst_formats if prefer_dayfirst else monthfirst_formats + dayfirst_formats)

    for fmt in ordered_formats:
        try:
            dt = datetime.strptime(s, fmt)
            if 1995 <= dt.year <= 2035:
                return dt.replace(tzinfo=timezone.utc)
        except ValueError:
            pass

    try:
        from dateutil import parser as dt_parser
        parsed = dt_parser.parse(s, dayfirst=prefer_dayfirst, fuzzy=True)
        if 1995 <= parsed.year <= 2035:
            return parsed.replace(tzinfo=timezone.utc)
    except Exception:
        pass

    return None


def _extract_amounts_on_line(line: str) -> List[Tuple[float, str]]:
    """Extracts plausible monetary numbers from a single line, ignoring years/dates/percentages."""
    # Remove date tokens and percentage tokens like (18%) or 8.5% or GSTINs before finding money amounts
    cleaned = re.sub(r"\b\d{4}[-/\.]\d{2}[-/\.]\d{2}\b", " ", line)
    cleaned = re.sub(r"\b\d{1,2}[-/\.]\d{1,2}[-/\.]\d{2,4}\b", " ", cleaned)
    cleaned = re.sub(r"\b\d{1,2}:\d{2}(?::\d{2})?\s*(?:am|pm)?\b", " ", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\b\d+(?:\.\d+)?\s*%", " ", cleaned)
    cleaned = GSTIN_RE.sub(" ", cleaned)
    # Remove phone / ref / invoice IDs with >= 8 contiguous digits without decimals
    cleaned = re.sub(r"\b\d{8,}\b", " ", cleaned)
    # Remove explicit order/invoice/store numbers like #TX-904281 or #4028
    cleaned = re.sub(r"#\s*[A-Za-z0-9\-]+", " ", cleaned)

    results: List[Tuple[float, str]] = []
    for m in AMOUNT_TOKEN_RE.finditer(cleaned):
        raw_tok = m.group(1)
        # Skip plain 4-digit years (1990..2035) if no decimal and no currency symbol right before
        full_match = m.group(0)
        has_curr = bool(re.search(r"(?:₹|Rs\.?|INR|\$|USD|€|EUR|£|GBP)", full_match, re.IGNORECASE))
        val, _ = parse_amount_str(raw_tok)
        if val is None:
            continue
        if not has_curr and "." not in raw_tok and "," not in raw_tok and 1990 <= abs(val) <= 2035:
            continue
        results.append((val, raw_tok))
    return results


def _make_field_meta(
    value: Any,
    confidence: float,
    method: str,
    page: int = 1,
    line_idx: Optional[int] = None,
    bbox: Optional[List[float]] = None,
) -> Dict[str, Any]:
    return {
        "value": value,
        "confidence": round(max(0.0, min(1.0, float(confidence))), 3),
        "method": method,
        "source": {
            "page": page,
            "line": (line_idx + 1) if line_idx is not None else None,
            "bbox": [round(float(v), 1) for v in bbox] if bbox else None,
        },
    }


def extract_financial_document(
    text: str,
    lines: List[str],
    line_boxes: Optional[List[Dict[str, Any]]] = None,
    filename: str = "document.png",
    page_num: int = 1,
    source_type: str = "receipt_ocr",
    ocr_mean_confidence: Optional[float] = None,
) -> Dict[str, Any]:
    """
    Extracts full structured transaction fields, line items, GST breakdown, field-level
    confidence/provenance, and deterministic reconciliation validation from a receipt or invoice.
    """
    clean_lines = [l.strip() for l in (lines or text.splitlines()) if l and l.strip()]
    full_text = text or "\n".join(clean_lines)

    # Helper to look up line confidence & bbox from OCR line_boxes
    def _line_info(idx: Optional[int]) -> Tuple[float, Optional[List[float]]]:
        if idx is None or not line_boxes or idx >= len(line_boxes):
            base_c = ocr_mean_confidence if ocr_mean_confidence is not None else 0.92
            return float(base_c), None
        lb = line_boxes[idx]
        return float(lb.get("confidence", 0.90)), lb.get("bbox")

    # 1. Currency detection
    currency, curr_conf, curr_method = detect_currency_from_text(full_text, default="USD")
    is_indian_context = (currency == "INR") or bool(
        re.search(r"\b(?:gstin|cgst|sgst|igst|upi|india|bengaluru|bangalore|mumbai|delhi|chennai|hyderabad|pune|kolkata)\b", full_text, re.IGNORECASE)
    )

    # 2. Extract GSTIN & UPI ID
    gstin_match = GSTIN_RE.search(full_text)
    gstin = gstin_match.group(1) if gstin_match else None
    upi_match = UPI_ID_RE.search(full_text)
    upi_id = upi_match.group(1) if upi_match else None

    # 3. Extract Merchant / Payee (prefer top non-boilerplate lines with clean text)
    merchant: Optional[str] = None
    merchant_line_idx: Optional[int] = None
    merchant_method = "not_found"
    merchant_conf = 0.0

    boilerplate_re = re.compile(
        r"^(?:tax\s*invoice|retail\s*invoice|cash\s*memo|invoice|receipt|bill|bill\s*of\s*supply|"
        r"order|cash\s*receipt|sales\s*receipt|duplicate|original\s*for\s*recipient|customer\s*copy|"
        r"merchant\s*copy|date|time|tel|ph|phone|mobile|email|www\.|http|gst|gstin|cin|pan|tin|"
        r"store\s*#|terminal|billed\s*to|bill\s*to|ship\s*to|sold\s*by|invoice\s*no|inv\s*no|"
        r"table\s*no|cashier|page\s*\d)\b",
        re.IGNORECASE,
    )
    address_re = re.compile(
        r"^(?:street|suite|road|rd\.|st\.|blvd|avenue|ave|floor|plot\s*no|sector|phase|block|"
        r"san\s*francisco|california|new\s*york|delhi|new\s*delhi|mumbai|bangalore|bengaluru|"
        r"hyderabad|chennai|pune|kolkata|karnataka|maharashtra|tamil\s*nadu)\b",
        re.IGNORECASE,
    )

    # Check explicit "Sold By:" / "Vendor:" / "Merchant:" / "Payee:" label first
    for idx, l in enumerate(clean_lines[:15]):
        m_lbl = re.match(r"^(?:sold\s*by|vendor|merchant|payee|from|supplier|biller)\s*[:\-]\s*(.+)$", l, re.IGNORECASE)
        if m_lbl:
            cand = m_lbl.group(1).strip(" *=-_#:")
            if len(cand) >= 3:
                merchant = cand
                merchant_line_idx = idx
                merchant_method = "labeled_merchant"
                line_c, _ = _line_info(idx)
                merchant_conf = min(0.98, line_c * 0.98)
                break

    if not merchant:
        for idx, l in enumerate(clean_lines[:10]):
            cleaned = l.strip()
            if len(cleaned) < 3:
                continue
            if boilerplate_re.match(cleaned):
                continue
            if re.match(r"^[\*\-=\._\s#\|/\\:]+$", cleaned):
                continue
            if address_re.match(cleaned):
                continue
            if re.search(r"\b\d{5,6}(?:-\d{4})?\b", cleaned) and not re.search(r"\b(?:pvt|ltd|inc|llc|store|mart|cafe|tech|corp)\b", cleaned, re.IGNORECASE):
                continue
            if re.match(r"^\d+[\d\s/\-\.:,]+$", cleaned):
                continue
            cleaned = re.sub(
                r"^(?:welcome\s+to\s+|thanks?\s+for\s+visiting\s+|thank\s+you\s+for\s+shopping\s+at\s+)",
                "",
                cleaned,
                flags=re.IGNORECASE,
            ).strip(" *-=_#")
            # Strip trailing metadata separated by wide gap or pipe
            cleaned = re.split(r"\s{3,}|\|", cleaned)[0].strip()
            if len(cleaned) >= 3:
                merchant = cleaned
                merchant_line_idx = idx
                merchant_method = "header_top_line"
                line_c, _ = _line_info(idx)
                merchant_conf = min(0.95, line_c * 0.94)
                break

    # 4. Extract Invoice / Order / Bill Number & Transaction Reference (UTR / Auth)
    invoice_no: Optional[str] = None
    invoice_line_idx: Optional[int] = None
    inv_patterns = [
        r"(?:invoice\s*(?:no|number|#)|inv\s*(?:no|#)|bill\s*(?:no|#)|receipt\s*(?:no|#)|order\s*(?:no|id|#))\s*[:#\-]?\s*([A-Za-z0-9][A-Za-z0-9\-_/]{2,26})",
        r"\b(?:invoice|order)\s*[:#]\s*#?\s*([A-Za-z0-9][A-Za-z0-9\-_/]{2,26})",
    ]
    for idx, l in enumerate(clean_lines):
        for pat in inv_patterns:
            m = re.search(pat, l, re.IGNORECASE)
            if m:
                cand = m.group(1).strip(" .,:;")
                if cand.lower() not in {"date", "no", "number", "amount", "total", "copy"} and re.search(r"\d", cand):
                    invoice_no = cand
                    invoice_line_idx = idx
                    break
        if invoice_no:
            break

    reference_no: Optional[str] = None
    ref_line_idx: Optional[int] = None
    ref_patterns = [
        r"\b(?:utr|upi\s*ref(?:erence)?|txn\s*(?:id|ref|no)|transaction\s*(?:id|ref)|rrn|auth\s*code|approval\s*code|ref(?:erence)?\s*(?:no|id|#))\s*[:#\-]?\s*([A-Za-z0-9\-_]{4,30})",
    ]
    for idx, l in enumerate(clean_lines):
        for pat in ref_patterns:
            m = re.search(pat, l, re.IGNORECASE)
            if m:
                reference_no = m.group(1).strip(" .,:;")
                ref_line_idx = idx
                break
        if reference_no:
            break

    # 5. Extract Transaction Date (labeled first, then unlabeled; NEVER silently invent without flagging!)
    parsed_date: Optional[datetime] = None
    date_line_idx: Optional[int] = None
    date_method = "missing"
    date_conf = 0.0

    date_token_re = (
        r"(\d{4}[-/\.]\d{1,2}[-/\.]\d{1,2}|"
        r"\d{1,2}[-/\.]\d{1,2}[-/\.]\d{2,4}|"
        r"\d{1,2}[-\s]+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*[-\s,]+\d{2,4}|"
        r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{1,2},?\s+\d{4})"
    )

    # Pass A: explicitly labeled invoice/bill/txn date (skip "Due Date" in pass A)
    for idx, l in enumerate(clean_lines):
        if re.search(r"\bdue\s*date\b", l, re.IGNORECASE) and not re.search(r"\b(?:invoice|bill|txn|order|receipt)\s*date\b", l, re.IGNORECASE):
            continue
        m_lbl = re.search(r"(?:invoice\s*date|bill\s*date|txn\s*date|transaction\s*date|order\s*date|date)\s*[:=\-]?\s*" + date_token_re, l, re.IGNORECASE)
        if m_lbl:
            dt = parse_date_robust(m_lbl.group(1), prefer_dayfirst=is_indian_context)
            if dt:
                parsed_date = dt
                date_line_idx = idx
                date_method = "labeled_date"
                line_c, _ = _line_info(idx)
                date_conf = min(0.98, line_c * 0.98)
                break

    # Pass B: unlabeled date token on any line (excluding due date line if possible)
    if not parsed_date:
        for idx, l in enumerate(clean_lines):
            if re.search(r"\bdue\s*date\b", l, re.IGNORECASE):
                continue
            m = re.search(date_token_re, l, re.IGNORECASE)
            if m:
                dt = parse_date_robust(m.group(1), prefer_dayfirst=is_indian_context)
                if dt:
                    parsed_date = dt
                    date_line_idx = idx
                    date_method = "unlabeled_date_regex"
                    line_c, _ = _line_info(idx)
                    date_conf = min(0.90, line_c * 0.90)
                    break

    date_missing = parsed_date is None

    # 6. Extract Subtotal, Taxes (CGST/SGST/IGST/GST/Sales Tax/VAT), Discount, Round-off
    subtotal_minor: Optional[int] = None
    subtotal_line_idx: Optional[int] = None
    subtotal_conf = 0.0

    discount_minor: Optional[int] = None
    discount_line_idx: Optional[int] = None

    round_off_minor: int = 0

    tax_breakdown: Dict[str, int] = {}
    tax_line_indices: List[int] = []

    for idx, l in enumerate(clean_lines):
        amts = _extract_amounts_on_line(l)
        if not amts:
            continue

        # Subtotal / Taxable Value
        if subtotal_minor is None and SUBTOTAL_LABEL_RE.search(l):
            val = abs(amts[-1][0])
            if val > 0:
                subtotal_minor = int(round(val * 100))
                subtotal_line_idx = idx
                line_c, _ = _line_info(idx)
                subtotal_conf = min(0.96, line_c * 0.96)
                continue

        # Discount
        if discount_minor is None and DISCOUNT_LABEL_RE.search(l):
            val = abs(amts[-1][0])
            if val > 0:
                discount_minor = int(round(val * 100))
                discount_line_idx = idx
                continue

        # Round off (can be positive or negative, typically small < 1.00)
        if ROUNDOFF_LABEL_RE.search(l):
            val = amts[-1][0]
            if abs(val) <= 5.0:
                round_off_minor = int(round(val * 100))
                continue

        # Granular Taxes: CGST, SGST, IGST, UTGST, CESS, GST, Sales Tax, VAT
        low_l = l.lower()
        for tax_key, tax_re in [
            ("cgst_minor", r"\bcgst\b"),
            ("sgst_minor", r"\bsgst\b"),
            ("igst_minor", r"\bigst\b"),
            ("utgst_minor", r"\butgst\b"),
            ("cess_minor", r"\bcess\b"),
            ("sales_tax_minor", r"\bsales\s*tax\b"),
            ("vat_minor", r"\bvat\b"),
            ("gst_minor", r"\b(?:total\s*)?gst\b"),
            ("tax_generic_minor", r"\b(?:service\s*tax|total\s*tax|tax)\b"),
        ]:
            if re.search(tax_re, low_l) and not re.search(r"\b(?:gstin|tax\s*invoice|taxable|before\s*tax|after\s*tax)\b", low_l):
                val = abs(amts[-1][0])
                if val > 0:
                    minor_v = int(round(val * 100))
                    # Avoid capturing rate (e.g. "CGST 9%" already stripped, but guard against double-counting same line)
                    if tax_key not in tax_breakdown:
                        tax_breakdown[tax_key] = minor_v
                        tax_line_indices.append(idx)
                    break

    # Compute total tax without double-counting (if CGST+SGST exist alongside total GST, prefer CGST+SGST)
    split_gst = (
        tax_breakdown.get("cgst_minor", 0)
        + tax_breakdown.get("sgst_minor", 0)
        + tax_breakdown.get("igst_minor", 0)
        + tax_breakdown.get("utgst_minor", 0)
        + tax_breakdown.get("cess_minor", 0)
    )
    tax_minor: Optional[int] = None
    if split_gst > 0:
        tax_minor = split_gst
    elif "gst_minor" in tax_breakdown:
        tax_minor = tax_breakdown["gst_minor"]
    elif "sales_tax_minor" in tax_breakdown:
        tax_minor = tax_breakdown["sales_tax_minor"]
    elif "vat_minor" in tax_breakdown:
        tax_minor = tax_breakdown["vat_minor"]
    elif "tax_generic_minor" in tax_breakdown:
        tax_minor = tax_breakdown["tax_generic_minor"]

    # 7. Extract Line Items (never mistaking a line item for final total!)
    line_items: List[Dict[str, Any]] = []
    # Find index where totals section begins
    totals_start_idx = len(clean_lines)
    for idx, l in enumerate(clean_lines):
        if SUBTOTAL_LABEL_RE.search(l) or any(re.search(pat, l, re.IGNORECASE) for _, pat, _ in TOTAL_LABEL_TIERS[:3]):
            totals_start_idx = min(totals_start_idx, idx)

    for idx, l in enumerate(clean_lines[:totals_start_idx]):
        if idx == merchant_line_idx or idx == date_line_idx:
            continue
        if EXCLUDED_TOTAL_LINE_RE.search(l) or boilerplate_re.match(l):
            continue
        m_item = LINE_ITEM_RE.match(l)
        if m_item:
            qty_str = m_item.group(1) or m_item.group(3)
            item_desc = m_item.group(2).strip(" -|:")
            amt_val, _ = parse_amount_str(m_item.group(4))
            if amt_val and amt_val > 0 and len(item_desc) >= 3:
                qty = int(qty_str) if qty_str and qty_str.isdigit() else 1
                item_amt_minor = int(round(amt_val * 100))
                line_items.append({
                    "description": item_desc,
                    "quantity": qty,
                    "unit_price_minor": int(round(item_amt_minor / max(1, qty))),
                    "amount_minor": item_amt_minor,
                    "line": idx + 1,
                })

    # 8. Extract Final Payable Total (strictly distinguished from subtotal, tax, balance, paid, line items!)
    amount_minor: int = 0
    total_line_idx: Optional[int] = None
    total_method = "not_found"
    total_conf = 0.0

    # Collect candidates across tiers scanning bottom-to-top (totals live near the bottom)
    total_candidates: List[Tuple[int, int, int, float, str]] = []  # (tier, -line_idx, amount_minor, conf, method)
    for tier, pat, base_conf in TOTAL_LABEL_TIERS:
        for idx in range(len(clean_lines) - 1, -1, -1):
            l = clean_lines[idx]
            if EXCLUDED_TOTAL_LINE_RE.search(l):
                continue
            if re.search(pat, l, re.IGNORECASE):
                amts = _extract_amounts_on_line(l)
                # Handle wrapped label where amount sits on the very next line
                if not amts and idx + 1 < len(clean_lines) and not EXCLUDED_TOTAL_LINE_RE.search(clean_lines[idx + 1]):
                    amts = _extract_amounts_on_line(clean_lines[idx + 1])
                if amts:
                    val = abs(amts[-1][0])
                    if val > 0:
                        minor_v = int(round(val * 100))
                        line_c, _ = _line_info(idx)
                        total_candidates.append((tier, -idx, minor_v, min(0.99, base_conf * line_c), f"labeled_total_tier{tier}"))

    if total_candidates:
        # Prefer best tier; if subtotal+tax exists, prefer candidate that reconciles cleanly!
        expected_reconciled: Optional[int] = None
        if subtotal_minor is not None:
            expected_reconciled = subtotal_minor + (tax_minor or 0) - (discount_minor or 0) + round_off_minor

        def _cand_rank(c: Tuple[int, int, int, float, str]) -> Tuple[int, int, int]:
            tier, neg_idx, val_m, _, _ = c
            reconciles = 0 if (expected_reconciled is not None and abs(val_m - expected_reconciled) <= 100) else 1
            return (reconciles, tier, neg_idx)

        total_candidates.sort(key=_cand_rank)
        _, neg_idx, amount_minor, total_conf, total_method = total_candidates[0]
        total_line_idx = -neg_idx

    # Fallback ONLY if no explicit total line matched: derive from subtotal + tax (never pick an arbitrary line item!)
    if amount_minor == 0 and subtotal_minor is not None and subtotal_minor > 0:
        amount_minor = subtotal_minor + (tax_minor or 0) - (discount_minor or 0) + round_off_minor
        total_line_idx = subtotal_line_idx
        total_method = "derived_from_subtotal_and_tax"
        total_conf = max(0.65, subtotal_conf * 0.85)
    elif amount_minor == 0:
        # Last-resort scan for currency-prefixed total in bottom 40% of document (excluding line-item block)
        start_scan = max(0, int(len(clean_lines) * 0.6))
        for idx in range(len(clean_lines) - 1, start_scan - 1, -1):
            l = clean_lines[idx]
            if EXCLUDED_TOTAL_LINE_RE.search(l):
                continue
            if re.search(r"(?:₹|Rs\.?|INR|\$|€|£)", l, re.IGNORECASE):
                amts = _extract_amounts_on_line(l)
                if amts:
                    val = abs(amts[-1][0])
                    if val > 0:
                        amount_minor = int(round(val * 100))
                        total_line_idx = idx
                        total_method = "bottom_currency_fallback"
                        total_conf = 0.58  # Low confidence -> triggers user review!
                        break

    # 9. Extract Payment Method
    payment_method: Optional[str] = None
    pm_line_idx: Optional[int] = None
    pm_patterns = [
        (r"\b(?:payment\s*method|paid\s*(?:by|via)|mode\s*of\s*payment|payment\s*mode)\s*[:\-]\s*([^\n\|]{2,45})", 1),
        (r"\b(upi|neft|imps|rtgs|visa|mastercard|rupay|amex|credit\s*card|debit\s*card|net\s*banking|cash|cheque)\b", 1),
    ]
    for idx, l in enumerate(clean_lines):
        for pat, grp in pm_patterns:
            m = re.search(pat, l, re.IGNORECASE)
            if m:
                payment_method = m.group(grp).strip(" .,:;")[:45]
                pm_line_idx = idx
                break
        if payment_method:
            break
    if not payment_method and upi_id:
        payment_method = f"UPI ({upi_id})"

    # 10. Determine Debit / Credit Direction
    tx_type = "expense"
    type_method = "receipt_invoice_default"
    type_conf = 0.90
    if re.search(r"\b(?:credit\s*note|refund\s*receipt|payout\s*statement|payment\s*received|inward\s*remittance)\b", full_text, re.IGNORECASE):
        tx_type = "income"
        type_method = "credit_keyword_match"
        type_conf = 0.88

    # 11. Deterministic Validation & Reconciliation
    validation_issues: List[str] = []
    validation_warnings: List[str] = []
    reconciliation_status = "not_applicable"
    reconciliation_diff_minor: Optional[int] = None

    if amount_minor <= 0:
        validation_issues.append("Critical field 'amount_minor' could not be extracted or is zero.")

    if date_missing:
        validation_issues.append("Critical field 'date' could not be found in document; not invented.")

    if not merchant:
        validation_issues.append("Critical field 'merchant' could not be reliably identified.")

    # Subtotal + Tax - Discount + RoundOff == Total check (tolerance ±100 minor units / 1.00 currency unit)
    if subtotal_minor is not None and amount_minor > 0:
        computed_total = subtotal_minor + (tax_minor or 0) - (discount_minor or 0) + round_off_minor
        reconciliation_diff_minor = amount_minor - computed_total
        if abs(reconciliation_diff_minor) <= 2:
            reconciliation_status = "exact_match"
            total_conf = min(0.99, total_conf + 0.04)
        elif abs(reconciliation_diff_minor) <= 100:
            reconciliation_status = "reconciled_within_rounding"
            total_conf = min(0.97, total_conf + 0.02)
        else:
            reconciliation_status = "mismatch"
            validation_issues.append(
                f"Arithmetic mismatch: subtotal ({subtotal_minor/100:.2f}) + tax ({(tax_minor or 0)/100:.2f})"
                f" - discount ({(discount_minor or 0)/100:.2f}) = {computed_total/100:.2f}, "
                f"but extracted total is {amount_minor/100:.2f}."
            )
            total_conf = min(total_conf, 0.62)

    # Line items sum reconciliation
    if line_items:
        items_sum = sum(i["amount_minor"] for i in line_items)
        ref_target = subtotal_minor if subtotal_minor is not None else amount_minor
        if ref_target > 0:
            if abs(items_sum - ref_target) > max(100, int(ref_target * 0.02)):
                validation_warnings.append(
                    f"Line items sum ({items_sum/100:.2f}) differs from {'subtotal' if subtotal_minor else 'total'} ({ref_target/100:.2f})."
                )

    # Split GST consistency check
    if "cgst_minor" in tax_breakdown and "sgst_minor" in tax_breakdown:
        if abs(tax_breakdown["cgst_minor"] - tax_breakdown["sgst_minor"]) > 5:
            validation_warnings.append("CGST and SGST values are unequal; please verify tax split.")

    is_valid = len(validation_issues) == 0

    # 12. Field-level provenance & confidence metadata
    _, merch_bbox = _line_info(merchant_line_idx)
    _, date_bbox = _line_info(date_line_idx)
    _, total_bbox = _line_info(total_line_idx)
    _, sub_bbox = _line_info(subtotal_line_idx)
    _, inv_bbox = _line_info(invoice_line_idx)
    _, ref_bbox = _line_info(ref_line_idx)
    _, pm_bbox = _line_info(pm_line_idx)
    first_tax_idx = tax_line_indices[0] if tax_line_indices else None
    tax_line_c, tax_bbox = _line_info(first_tax_idx)

    field_metadata = {
        "merchant": _make_field_meta(merchant, merchant_conf, merchant_method, page_num, merchant_line_idx, merch_bbox),
        "date": _make_field_meta(
            parsed_date.date().isoformat() if parsed_date else None,
            date_conf,
            date_method,
            page_num,
            date_line_idx,
            date_bbox,
        ),
        "amount_minor": _make_field_meta(amount_minor if amount_minor > 0 else None, total_conf, total_method, page_num, total_line_idx, total_bbox),
        "currency": _make_field_meta(currency, curr_conf, curr_method, page_num, None, None),
        "type": _make_field_meta(tx_type, type_conf, type_method, page_num, None, None),
        "subtotal_minor": _make_field_meta(subtotal_minor, subtotal_conf if subtotal_minor is not None else 0.0, "labeled_subtotal" if subtotal_minor is not None else "not_present", page_num, subtotal_line_idx, sub_bbox),
        "tax_minor": _make_field_meta(tax_minor, min(0.96, tax_line_c) if tax_minor is not None else 0.0, "labeled_tax" if tax_minor is not None else "not_present", page_num, first_tax_idx, tax_bbox),
        "discount_minor": _make_field_meta(discount_minor, 0.90 if discount_minor is not None else 0.0, "labeled_discount" if discount_minor is not None else "not_present", page_num, discount_line_idx, None),
        "invoice_no": _make_field_meta(invoice_no, 0.92 if invoice_no else 0.0, "regex_labeled_invoice" if invoice_no else "not_present", page_num, invoice_line_idx, inv_bbox),
        "reference_no": _make_field_meta(reference_no, 0.90 if reference_no else 0.0, "regex_labeled_ref" if reference_no else "not_present", page_num, ref_line_idx, ref_bbox),
        "payment_method": _make_field_meta(payment_method, 0.88 if payment_method else 0.0, "payment_pattern" if payment_method else "not_present", page_num, pm_line_idx, pm_bbox),
        "gstin": _make_field_meta(gstin, 0.96 if gstin else 0.0, "gstin_regex" if gstin else "not_present", page_num, None, None),
    }

    # 13. Determine review_required & explicit review_reasons
    review_reasons: List[str] = list(validation_issues)
    critical_fields = ["merchant", "date", "amount_minor", "type"]
    for cf in critical_fields:
        fc = field_metadata[cf]["confidence"]
        if fc < 0.75:
            msg = f"Low confidence on '{cf}' ({fc:.0%})."
            if msg not in review_reasons:
                review_reasons.append(msg)

    # 14. Feed merchant + description + line-item context into CashIQ's categorizer
    display_merchant = merchant or "Unknown Merchant"
    desc = f"Invoice {invoice_no} from {display_merchant}" if invoice_no else f"Receipt from {display_merchant}"
    line_item_text = " ".join(i["description"] for i in line_items[:6])
    categorizer_input = f"{merchant or ''} {desc} {line_item_text}".strip()
    cat_res = categorizer_instance.categorize(categorizer_input, merchant=merchant)

    if cat_res.get("review_required") or cat_res.get("confidence", 0.0) < 0.70:
        review_reasons.append(f"Category '{cat_res['category']}' has moderate confidence ({cat_res['confidence']:.0%}).")

    review_required = bool(review_reasons) or (source_type in {"receipt_ocr", "scanned_pdf_ocr"} and total_conf < 0.90)

    overall_extraction_conf = round(
        float(
            0.40 * field_metadata["amount_minor"]["confidence"]
            + 0.25 * field_metadata["date"]["confidence"]
            + 0.25 * field_metadata["merchant"]["confidence"]
            + 0.10 * field_metadata["currency"]["confidence"]
        ),
        3,
    )

    return {
        "date": parsed_date.isoformat() if parsed_date else None,
        "date_missing": date_missing,
        "description": desc,
        "merchant": merchant[:80] if merchant else None,
        "amount_minor": amount_minor,
        "currency": currency,
        "type": tx_type,
        "category_name": cat_res["category"],
        "confidence": cat_res["confidence"],
        "model_version": cat_res["model_version"],
        "review_required": review_required,
        "review_reasons": review_reasons,
        "source": source_type,
        "source_file": filename,
        "page_number": page_num,
        "invoice_no": invoice_no,
        "reference_no": reference_no,
        "gstin": gstin,
        "upi_id": upi_id,
        "subtotal_minor": subtotal_minor,
        "tax_minor": tax_minor,
        "tax_breakdown": tax_breakdown,
        "discount_minor": discount_minor,
        "round_off_minor": round_off_minor if round_off_minor != 0 else None,
        "payment_method": payment_method,
        "line_items": line_items,
        "extraction_confidence": overall_extraction_conf,
        "field_metadata": field_metadata,
        "validation": {
            "is_valid": is_valid,
            "reconciliation_status": reconciliation_status,
            "reconciliation_diff_minor": reconciliation_diff_minor,
            "issues": validation_issues,
            "warnings": validation_warnings,
        },
        "raw_text": full_text,
        "raw_text_snippet": full_text[:250],
    }
