"""
CashIQ Format-Aware Document & Image Ingestion Pipeline (v3.0.0).

Upgraded extraction architecture:
1. Images & Scanned Receipts:
   - Lazy singleton OCR manager supporting PaddleOCR (PP-OCR + selective PP-StructureV3),
     RapidOCR (PP-OCRv6 ONNX Runtime CPU), native Windows OCR, and Tesseract fallbacks.
   - Conditional preprocessing (EXIF, perspective correction, deskewing, resolution check,
     CLAHE contrast, adaptive threshold) compared against the original image.
   - Preserves bounding boxes and confidence scores for targeted low-confidence retries.
2. PDFs (Digital, Scanned, and Mixed):
   - PyMuPDF native text & table extraction for digital pages; OCR ONLY scanned/image pages.
   - Bounded parallelism across pages preserving page numbers, reading order, and table
     row/column relationships without merging unrelated columns.
3. CSV Files (Zero OCR):
   - Direct parsing with robust encoding, delimiter, preamble header, and footer detection.
   - Indian bank statement variations (HDFC/SBI/ICICI/Axis, separate debit/credit, UPI,
     UTR/ref, Indian comma grouping, running balance cross-validation) and malformed row resilience.
4. Financial-Field Extraction, Reconciliation & Caching:
   - Extracts merchant, date, total, subtotal, GST/CGST/SGST/IGST, discount, invoice #,
     payment method, transaction reference, debit/credit, currency, and line items.
   - Deterministic reconciliation (`subtotal + tax - discount == total`), field-level
     confidence & source provenance, full raw text retention, and SHA-256 result caching.
"""

import asyncio
from collections import OrderedDict
import copy
import csv
from datetime import datetime, timezone
import hashlib
import io
import os
import re
import time
from typing import Any, Dict, List, Optional, Tuple

from PIL import Image

from app.ml.categorizer import categorizer_instance
from app.ml.financial_extractor import (
    detect_currency_from_text,
    extract_financial_document,
    parse_amount_str,
    parse_date_robust,
    GSTIN_RE,
    UPI_ID_RE,
)
from app.ml.merchant_normalizer import normalize_merchant_name
from app.ml.ocr_engine import OCRResult, ocr_engine_manager

try:
    import pymupdf
except ImportError:
    try:
        import fitz as pymupdf
    except ImportError:
        pymupdf = None


# Backward-compatible helper aliases
def clean_amount_str(val: str) -> Tuple[Optional[float], Optional[str]]:
    return parse_amount_str(val)


# Summary / footer / non-transaction patterns to exclude from CSV & statement rows
SUMMARY_ROW_RE = re.compile(
    r"\b(?:opening\s*bal(?:ance)?|closing\s*bal(?:ance)?|ending\s*bal(?:ance)?|"
    r"brought\s*forward|carried\s*forward|balance\s*b/f|balance\s*c/f|"
    r"statement\s*(?:summary|period|total)|total\s*(?:debit|credit|withdrawal|deposit)|"
    r"end\s*of\s*statement|page\s*\d+\s*of\s*\d+)\b",
    re.IGNORECASE,
)


def _decode_csv_bytes(file_content: bytes) -> Tuple[str, str]:
    """Robustly decodes CSV bytes handling UTF-8-SIG, UTF-8, UTF-16, CP1252, Latin-1."""
    if not file_content:
        return "", "utf-8"

    # BOM checks first
    if file_content.startswith(b"\xef\xbb\xbf"):
        return file_content.decode("utf-8-sig", errors="replace"), "utf-8-sig"
    if file_content.startswith((b"\xff\xfe", b"\xfe\xff")):
        return file_content.decode("utf-16", errors="replace"), "utf-16"

    for enc in ("utf-8", "cp1252"):
        try:
            return file_content.decode(enc), enc
        except UnicodeDecodeError:
            pass

    try:
        from charset_normalizer import from_bytes
        best = from_bytes(file_content).best()
        if best is not None:
            return str(best), best.encoding or "detected"
    except Exception:
        pass

    return file_content.decode("latin-1", errors="replace"), "latin-1"


def _extract_merchant_from_narration(raw_desc: str, raw_merch: str = "") -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """
    Extracts clean merchant display name, UPI ID (if any), and UTR/reference (if any)
    from Indian & international bank narrations (UPI/NEFT/IMPS/RTGS/POS/card).
    """
    upi_m = UPI_ID_RE.search(raw_desc or "")
    upi_id = upi_m.group(1) if upi_m else None

    ref_no = None
    ref_m = re.search(
        r"(?:upi[/\-](\d{6,16})|utr[:\s\-/]*([a-z0-9]{8,22})|ref[:\s\-/]*([a-z0-9]{5,20})|imps[/\-](\d{6,16}))",
        raw_desc or "",
        re.IGNORECASE,
    )
    if ref_m:
        ref_no = next((g for g in ref_m.groups() if g), None)

    if raw_merch and raw_merch.strip():
        return raw_merch.strip()[:80], upi_id, ref_no

    if not raw_desc or not raw_desc.strip():
        return None, upi_id, ref_no

    norm = normalize_merchant_name(None, raw_desc)
    if norm["display"] and len(norm["display"]) >= 2:
        return norm["display"][:80], upi_id, ref_no

    if " - " in raw_desc:
        return raw_desc.split(" - ")[0].strip()[:80], upi_id, ref_no
    if "/" in raw_desc:
        parts = [p.strip() for p in raw_desc.split("/") if len(p.strip()) > 2 and not p.strip().isdigit()]
        if parts:
            return parts[0][:80], upi_id, ref_no
    return raw_desc.split()[0][:80], upi_id, ref_no


class CSVProcessor:
    """
    Zero-OCR hardened CSV ingestion:
    - Auto encoding & delimiter detection (skipping bank preambles)
    - Preamble header row & footer summary detection
    - Single amount or separate Debit/Credit columns (Indian & international banks)
    - Indian comma grouping, DD/MM/YYYY dates, UPI narrations, UTR/Ref extraction
    - Running balance cross-validation for debit/credit consistency
    - Graceful resilience to malformed rows
    """

    HEADER_KEYWORDS: Dict[str, List[str]] = {
        "date": ["txn date", "trans date", "transaction date", "posting date", "posted", "value date", "date", "dt"],
        "value_date": ["value date", "value dt"],
        "description": ["narration", "particulars", "description", "narrative", "details", "memo", "remarks", "transaction remarks", "text"],
        "merchant": ["merchant", "payee", "vendor", "beneficiary", "counterparty", "party"],
        "amount": ["transaction amount", "txn amount", "net amount", "amount", "total", "amt"],
        "debit": ["withdrawal amt", "withdrawal", "debit amt", "debit amount", "debit", "dr amt", "dr.", "paid out", "outflow"],
        "credit": ["deposit amt", "deposit", "credit amt", "credit amount", "credit", "cr amt", "cr.", "paid in", "inflow"],
        "type": ["dr/cr", "cr/dr", "dr_cr", "cr_dr", "transaction type", "txn type", "entry type", "type", "d/c"],
        "currency": ["currency", "curr", "ccy"],
        "category": ["category", "cat"],
        "balance": ["closing balance", "running balance", "available balance", "balance", "bal"],
        "ref": ["chq./ref.no", "chq/ref", "cheque", "chq", "utr", "ref no", "reference number", "reference", "txn id", "ref"],
    }

    @staticmethod
    def detect_delimiter(text: str) -> str:
        """Detects CSV delimiter across candidate table rows (avoiding single-column preamble lines)."""
        lines = [l for l in text.splitlines() if l.strip()]
        if not lines:
            return ","

        # Score delimiters by consistency across non-preamble rows
        candidates = [",", ";", "\t", "|"]
        best_delim = ","
        best_score = -1.0

        # Check lines that look like multi-column rows (top 35 lines)
        sample_lines = lines[:35]
        for d in candidates:
            counts = [l.count(d) for l in sample_lines if l.count(d) >= 2]
            if not counts:
                continue
            # Prefer delimiter appearing consistently across many rows with >=2 separators
            most_common_cnt = max(set(counts), key=counts.count)
            consistency = sum(1 for c in counts if abs(c - most_common_cnt) <= 1)
            score = consistency * 2.0 + min(10, most_common_cnt) * 0.5
            if score > best_score:
                best_score = score
                best_delim = d

        if best_score > 0:
            return best_delim

        try:
            dialect = csv.Sniffer().sniff("\n".join(sample_lines[:15]), delimiters=",\t;|")
            return dialect.delimiter
        except Exception:
            return ","

    @classmethod
    def locate_header_row(cls, rows: List[List[str]]) -> Tuple[int, Dict[str, int]]:
        """Scans top 30 rows to locate the true table header row, skipping bank preambles."""
        best_row_idx = 0
        best_score = -1
        best_mapping: Dict[str, int] = {}

        for r_idx, row in enumerate(rows[:30]):
            if len(row) < 2:
                continue
            lower_cells = [re.sub(r"\s+", " ", str(c).strip().lower()) for c in row]
            mapping: Dict[str, int] = {}
            score = 0

            for col_idx, cell in enumerate(lower_cells):
                if not cell or len(cell) > 45:
                    continue
                # Exact or strong synonym match
                matched_role = None
                for role in ("date", "debit", "credit", "balance", "ref", "description", "merchant", "type", "currency", "category", "amount"):
                    if role in mapping:
                        continue
                    syns = cls.HEADER_KEYWORDS[role]
                    for syn in syns:
                        # Avoid matching "value date" as primary date if "txn date" is present on same row
                        if role == "date" and syn == "value date" and any("txn date" in c or "trans date" in c or c == "date" for c in lower_cells):
                            continue
                        # Avoid matching "withdrawal amt" or "deposit amt" as generic "amount"
                        if role == "amount" and any(k in cell for k in ("debit", "credit", "withdrawal", "deposit", "balance")):
                            continue
                        if cell == syn or re.search(rf"(?:^|\W){re.escape(syn)}(?:$|\W)", cell):
                            matched_role = role
                            break
                    if matched_role:
                        break

                if matched_role:
                    mapping[matched_role] = col_idx
                    score += 3 if matched_role in ("date", "debit", "credit", "amount", "description") else 1

            has_money_col = any(k in mapping for k in ("amount", "debit", "credit"))
            if score > best_score and ("date" in mapping or has_money_col) and len(mapping) >= 2:
                best_score = score
                best_row_idx = r_idx
                best_mapping = mapping

        return best_row_idx, best_mapping

    def parse_with_metadata(self, file_content: bytes, filename: str = "statement.csv") -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        t0 = time.perf_counter()
        text, encoding = _decode_csv_bytes(file_content)
        if not text.strip():
            return [], {"encoding": encoding, "delimiter": ",", "malformed_rows": 0, "raw_text": ""}

        delimiter = self.detect_delimiter(text)
        # Detect document-wide currency hints (e.g. "Currency: INR" or "₹" in preamble)
        doc_currency, doc_curr_conf, doc_curr_method = detect_currency_from_text(text[:2500], default="USD")
        is_indian_csv = (doc_currency == "INR") or bool(
            re.search(r"\b(?:hdfc|icici|sbi|axis|kotak|upi|neft|imps|rtgs|ifsc|narration|withdrawal\s*amt|inr)\b", text[:3000], re.IGNORECASE)
        )
        if is_indian_csv and doc_currency == "USD":
            # Only switch default to INR if strong Indian banking headers exist AND no explicit USD/$
            if not re.search(r"(?:\$|\bUSD\b)", text[:3000]):
                doc_currency = "INR"
                doc_curr_conf = 0.85
                doc_curr_method = "indian_bank_statement_context"

        rows: List[List[str]] = []
        malformed_rows = 0
        try:
            reader = csv.reader(io.StringIO(text), delimiter=delimiter)
            for r in reader:
                if r and any(cell.strip() for cell in r):
                    rows.append(r)
        except csv.Error:
            # Resilient line-by-line fallback for malformed quotes/embedded newlines
            for line in text.splitlines():
                if not line.strip():
                    continue
                try:
                    parsed = next(csv.reader([line], delimiter=delimiter))
                    if any(c.strip() for c in parsed):
                        rows.append(parsed)
                except Exception:
                    malformed_rows += 1
                    parts = [p.strip().strip('"') for p in line.split(delimiter)]
                    if len(parts) >= 3:
                        rows.append(parts)

        if not rows:
            return [], {"encoding": encoding, "delimiter": delimiter, "malformed_rows": malformed_rows, "raw_text": text}

        header_idx, col_map = self.locate_header_row(rows)
        header_row = rows[header_idx]
        expected_cols = len(header_row)

        date_idx = col_map.get("date", 0)
        desc_idx = col_map.get("description", 1 if expected_cols > 1 else 0)
        merch_idx = col_map.get("merchant", -1)
        amt_idx = col_map.get("amount", -1)
        debit_idx = col_map.get("debit", -1)
        credit_idx = col_map.get("credit", -1)
        type_idx = col_map.get("type", -1)
        curr_idx = col_map.get("currency", -1)
        ref_idx = col_map.get("ref", -1)
        bal_idx = col_map.get("balance", -1)

        if amt_idx == -1 and debit_idx == -1 and credit_idx == -1:
            amt_idx = 2 if expected_cols > 2 else expected_cols - 1

        drafts: List[Dict[str, Any]] = []
        seen_keys = set()
        prev_balance_minor: Optional[int] = None
        balance_checks_passed = 0
        balance_checks_failed = 0
        skipped_summary_rows = 0

        for r_num, row in enumerate(rows[header_idx + 1:], start=header_idx + 2):
            joined = " ".join(c.strip() for c in row if c and c.strip())
            if not joined:
                continue

            # Skip summary/footer/opening/closing balance lines
            if SUMMARY_ROW_RE.search(joined):
                # Capture opening balance if present to seed running-balance validation
                if bal_idx != -1 and bal_idx < len(row):
                    ob_val, _ = parse_amount_str(row[bal_idx])
                    if ob_val is not None:
                        prev_balance_minor = int(round(ob_val * 100))
                skipped_summary_rows += 1
                continue

            # Guard against severely truncated/malformed rows
            min_required_idx = max(i for i in (date_idx, desc_idx) if i >= 0)
            if len(row) <= min_required_idx:
                malformed_rows += 1
                continue

            raw_date = row[date_idx].strip() if date_idx < len(row) else ""
            raw_desc = row[desc_idx].strip() if desc_idx < len(row) else ""
            raw_merch = row[merch_idx].strip() if (merch_idx != -1 and merch_idx < len(row)) else ""
            raw_ref = row[ref_idx].strip() if (ref_idx != -1 and ref_idx < len(row)) else None
            raw_curr = row[curr_idx].strip() if (curr_idx != -1 and curr_idx < len(row)) else ""
            raw_bal = row[bal_idx].strip() if (bal_idx != -1 and bal_idx < len(row)) else ""

            # Parse date (do NOT silently invent today's date for garbage rows!)
            parsed_date = parse_date_robust(raw_date, prefer_dayfirst=is_indian_csv)
            date_missing = parsed_date is None

            # Parse amount & determine debit/credit direction
            amount_minor = 0
            ttype = "expense"
            type_method = "default"
            detected_curr = raw_curr.upper() if len(raw_curr) == 3 else doc_currency
            row_issues: List[str] = []
            row_warnings: List[str] = []

            if debit_idx != -1 or credit_idx != -1:
                debit_val, d_curr = parse_amount_str(row[debit_idx]) if (debit_idx != -1 and debit_idx < len(row)) else (None, None)
                credit_val, c_curr = parse_amount_str(row[credit_idx]) if (credit_idx != -1 and credit_idx < len(row)) else (None, None)

                has_debit = debit_val is not None and abs(debit_val) > 0
                has_credit = credit_val is not None and abs(credit_val) > 0

                if has_debit and has_credit:
                    row_issues.append("Both debit and credit columns contain non-zero amounts.")
                    amount_minor = int(round(abs(debit_val) * 100))
                    ttype = "expense"
                    type_method = "dual_column_conflict"
                elif has_debit:
                    amount_minor = int(round(abs(debit_val) * 100))
                    ttype = "expense"
                    detected_curr = d_curr or detected_curr
                    type_method = "separate_debit_column"
                elif has_credit:
                    amount_minor = int(round(abs(credit_val) * 100))
                    ttype = "income"
                    detected_curr = c_curr or detected_curr
                    type_method = "separate_credit_column"
                else:
                    # Row has neither debit nor credit -> likely blank separator or malformed
                    if date_missing:
                        malformed_rows += 1
                    continue
            else:
                raw_amt = row[amt_idx].strip() if (amt_idx != -1 and amt_idx < len(row)) else ""
                # Handle trailing DR / CR suffix inside amount cell e.g. "1,250.00 DR"
                inline_dr = bool(re.search(r"\b(?:dr|debit)\b", raw_amt, re.IGNORECASE))
                inline_cr = bool(re.search(r"\b(?:cr|credit)\b", raw_amt, re.IGNORECASE))
                amt_val, a_curr = parse_amount_str(raw_amt)
                if amt_val is None or abs(amt_val) == 0:
                    malformed_rows += 1
                    continue
                amount_minor = int(round(abs(amt_val) * 100))
                detected_curr = a_curr or detected_curr

                is_negative = amt_val < 0
                if inline_dr:
                    ttype = "expense"
                    type_method = "inline_amount_dr"
                elif inline_cr:
                    ttype = "income"
                    type_method = "inline_amount_cr"
                elif type_idx != -1 and type_idx < len(row) and row[type_idx].strip():
                    type_str = row[type_idx].strip().lower()
                    if any(k == type_str or k in type_str for k in ["debit", "dr", "withdrawal", "payment", "out", "expense", "d"]):
                        ttype = "expense"
                        type_method = "type_column"
                    elif any(k == type_str or k in type_str for k in ["credit", "cr", "deposit", "inward", "receipt", "income", "c"]):
                        ttype = "income"
                        type_method = "type_column"
                    else:
                        ttype = "expense" if is_negative else "income"
                        type_method = "sign_fallback"
                else:
                    if is_negative:
                        ttype = "expense"
                        type_method = "negative_sign"
                    elif any(w in raw_desc.lower() for w in ["withdrawal", "debit", "fee", "pos", "upi/", "emi"]):
                        ttype = "expense"
                        type_method = "narration_debit_cue"
                    elif any(w in raw_desc.lower() for w in ["inward", "deposit", "payout", "credit", "refund", "client payment"]):
                        ttype = "income"
                        type_method = "narration_credit_cue"
                    else:
                        ttype = "income"
                        type_method = "positive_sign_default"

            # Running balance validation (if balance column present)
            curr_balance_minor: Optional[int] = None
            balance_status = "not_available"
            if raw_bal:
                b_val, _ = parse_amount_str(raw_bal)
                if b_val is not None:
                    curr_balance_minor = int(round(b_val * 100))
                    if prev_balance_minor is not None:
                        expected_if_exp = prev_balance_minor - amount_minor
                        expected_if_inc = prev_balance_minor + amount_minor
                        actual_expected = expected_if_exp if ttype == "expense" else expected_if_inc
                        if abs(curr_balance_minor - actual_expected) <= 5:
                            balance_status = "verified"
                            balance_checks_passed += 1
                        else:
                            # Check if running balance proves opposite direction (only override if type was ambiguous)
                            other_expected = expected_if_inc if ttype == "expense" else expected_if_exp
                            if abs(curr_balance_minor - other_expected) <= 5 and type_method in {"sign_fallback", "positive_sign_default", "narration_debit_cue"}:
                                ttype = "income" if ttype == "expense" else "expense"
                                type_method = "running_balance_corrected"
                                balance_status = "verified_corrected"
                                balance_checks_passed += 1
                            else:
                                balance_status = "mismatch"
                                balance_checks_failed += 1
                                row_warnings.append(
                                    f"Running balance {curr_balance_minor/100:.2f} does not reconcile with previous balance {prev_balance_minor/100:.2f}."
                                )
                    prev_balance_minor = curr_balance_minor

            if date_missing:
                row_issues.append(f"Invalid or missing date value '{raw_date}'.")

            if len(row) != expected_cols:
                row_warnings.append(f"Row has {len(row)} columns (expected {expected_cols}).")

            merchant, upi_id, extracted_ref = _extract_merchant_from_narration(raw_desc, raw_merch)
            final_ref = raw_ref or extracted_ref

            combined_text = f"{merchant or ''} {raw_desc}".strip()
            cat_res = categorizer_instance.categorize(combined_text, merchant=merchant)

            dedup_date_key = parsed_date.date().isoformat() if parsed_date else f"missing-{r_num}"
            dedup_key = (dedup_date_key, amount_minor, ttype, raw_desc.lower(), final_ref or "")
            is_dup = dedup_key in seen_keys
            seen_keys.add(dedup_key)

            date_conf = 0.98 if not date_missing else 0.0
            amt_conf = 0.99 if balance_status.startswith("verified") else (0.95 if not row_issues else 0.65)
            merch_conf = 0.92 if raw_merch else (0.84 if merchant else 0.30)
            type_conf = 0.98 if (type_method in {"separate_debit_column", "separate_credit_column", "type_column"} or balance_status.startswith("verified")) else 0.82

            review_reasons = list(row_issues)
            if is_dup:
                review_reasons.append("Potential duplicate row within file.")
            if cat_res["review_required"] or cat_res["confidence"] < 0.70:
                review_reasons.append(f"Low category confidence ({cat_res['confidence']:.0%}).")

            field_metadata = {
                "merchant": {"value": merchant, "confidence": merch_conf, "method": "csv_column" if raw_merch else "narration_parser", "source": {"line": r_num, "column": merch_idx if raw_merch else desc_idx}},
                "date": {"value": parsed_date.date().isoformat() if parsed_date else None, "confidence": date_conf, "method": "csv_date_column", "source": {"line": r_num, "column": date_idx}},
                "amount_minor": {"value": amount_minor, "confidence": amt_conf, "method": type_method, "source": {"line": r_num}},
                "currency": {"value": detected_curr, "confidence": doc_curr_conf if not raw_curr else 0.98, "method": "csv_currency_col" if raw_curr else doc_curr_method, "source": {"line": r_num}},
                "type": {"value": ttype, "confidence": type_conf, "method": type_method, "source": {"line": r_num}},
                "reference_no": {"value": final_ref, "confidence": 0.95 if raw_ref else (0.85 if final_ref else 0.0), "method": "csv_ref_col" if raw_ref else "narration_regex", "source": {"line": r_num}},
            }

            extraction_conf = round(0.40 * amt_conf + 0.25 * date_conf + 0.25 * merch_conf + 0.10 * type_conf, 3)

            drafts.append({
                "date": parsed_date.isoformat() if parsed_date else None,
                "date_missing": date_missing,
                "description": raw_desc or f"Imported transaction from {filename}",
                "merchant": merchant,
                "amount_minor": amount_minor,
                "currency": detected_curr if len(detected_curr) == 3 else "USD",
                "type": ttype,
                "category_name": cat_res["category"],
                "confidence": cat_res["confidence"],
                "model_version": cat_res["model_version"],
                "review_required": bool(review_reasons) or extraction_conf < 0.75,
                "review_reasons": review_reasons,
                "source": "csv_import",
                "source_file": filename,
                "line_number": r_num,
                "reference_no": final_ref,
                "upi_id": upi_id,
                "running_balance_minor": curr_balance_minor,
                "is_duplicate": is_dup,
                "extraction_confidence": extraction_conf,
                "field_metadata": field_metadata,
                "validation": {
                    "is_valid": len(row_issues) == 0,
                    "running_balance_status": balance_status,
                    "issues": row_issues,
                    "warnings": row_warnings,
                },
                "raw_text": joined,
                "raw_text_snippet": joined[:200],
            })

        meta = {
            "engine": "csv_native",
            "encoding": encoding,
            "delimiter": delimiter,
            "header_row_index": header_idx + 1,
            "column_mapping": col_map,
            "rows_extracted": len(drafts),
            "malformed_rows_skipped": malformed_rows,
            "summary_rows_skipped": skipped_summary_rows,
            "running_balance_checks_passed": balance_checks_passed,
            "running_balance_checks_failed": balance_checks_failed,
            "processing_ms": round((time.perf_counter() - t0) * 1000, 1),
            "raw_text": text,
        }
        return drafts, meta

    def parse(self, file_content: bytes, filename: str = "statement.csv") -> List[Dict[str, Any]]:
        drafts, _ = self.parse_with_metadata(file_content, filename=filename)
        return drafts


class ImageReceiptProcessor:
    """
    Format-aware OCR extraction for receipts, invoices, bills, and photographed documents.
    Uses lazy-loaded OCR engine manager (PaddleOCR / RapidOCR PP-OCR / WinOCR / Tesseract),
    conditional preprocessing compared against the original image, targeted retries on
    low-confidence financial regions, and deterministic financial-field reconciliation.
    """

    async def parse_pil_image(
        self,
        img: Image.Image,
        filename: str = "receipt.png",
        page_num: int = 1,
        source_type: str = "receipt_ocr",
        preferred_engine: Optional[str] = None,
        use_structure: bool = False,
    ) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        ocr_res: OCRResult = await ocr_engine_manager.recognize_image(
            img,
            preferred_engine=preferred_engine,
            use_structure=use_structure,
            enable_targeted_retries=True,
        )

        lines = [l.text for l in ocr_res.lines] if ocr_res.lines else [l.strip() for l in ocr_res.text.splitlines() if l.strip()]
        line_boxes = [
            {"text": l.text, "confidence": l.confidence, "bbox": l.bbox}
            for l in ocr_res.lines
        ]

        # Detect if a scanned image is actually a multi-row bank statement rather than a single receipt
        stmt_drafts = PDFProcessor.extract_statement_rows_from_lines(
            lines=lines,
            line_boxes=line_boxes,
            filename=filename,
            page_num=page_num,
            source_type=source_type,
            full_text=ocr_res.text,
        )
        if len(stmt_drafts) >= 2:
            for d in stmt_drafts:
                d["ocr_engine"] = ocr_res.engine
                d["ocr_mean_confidence"] = round(ocr_res.mean_confidence, 3)
            meta = {
                "engine": ocr_res.engine,
                "variant_used": ocr_res.variant_used,
                "rotation_applied": ocr_res.rotation_applied,
                "retries_performed": ocr_res.retries_performed,
                "mean_confidence": round(ocr_res.mean_confidence, 3),
                "boxes_detected": len(ocr_res.boxes),
                "quality_metrics": ocr_res.quality_metrics,
                "processing_ms": ocr_res.processing_ms,
                "document_kind": "scanned_statement",
                "raw_text": ocr_res.text,
            }
            return stmt_drafts, meta

        extracted = extract_financial_document(
            text=ocr_res.text,
            lines=lines,
            line_boxes=line_boxes,
            filename=filename,
            page_num=page_num,
            source_type=source_type,
            ocr_mean_confidence=ocr_res.mean_confidence,
        )
        extracted["ocr_engine"] = ocr_res.engine
        extracted["ocr_mean_confidence"] = round(ocr_res.mean_confidence, 3)
        extracted["ocr_variant_used"] = ocr_res.variant_used
        extracted["ocr_rotation_applied"] = ocr_res.rotation_applied
        extracted["ocr_retries_performed"] = ocr_res.retries_performed

        meta = {
            "engine": ocr_res.engine,
            "variant_used": ocr_res.variant_used,
            "rotation_applied": ocr_res.rotation_applied,
            "retries_performed": ocr_res.retries_performed,
            "mean_confidence": round(ocr_res.mean_confidence, 3),
            "boxes_detected": len(ocr_res.boxes),
            "quality_metrics": ocr_res.quality_metrics,
            "processing_ms": ocr_res.processing_ms,
            "document_kind": "receipt_or_invoice",
            "raw_text": ocr_res.text,
        }
        return [extracted], meta

    async def parse_with_metadata(
        self,
        file_content: bytes,
        filename: str = "receipt.png",
        preferred_engine: Optional[str] = None,
    ) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        try:
            img = Image.open(io.BytesIO(file_content))
            return await self.parse_pil_image(
                img,
                filename=filename,
                page_num=1,
                source_type="receipt_ocr",
                preferred_engine=preferred_engine,
            )
        except Exception as e:
            err_draft = {
                "date": None,
                "date_missing": True,
                "description": f"Failed image extraction from {filename}",
                "merchant": None,
                "amount_minor": 0,
                "currency": "USD",
                "type": "expense",
                "category_name": "Miscellaneous",
                "confidence": 0.0,
                "model_version": "v3.0.0-error",
                "review_required": True,
                "review_reasons": [f"Image open/parse failed: {e}"],
                "source": "receipt_ocr",
                "source_file": filename,
                "extraction_confidence": 0.0,
                "validation": {"is_valid": False, "issues": [str(e)], "warnings": []},
                "error": str(e),
                "raw_text": "",
                "raw_text_snippet": "",
            }
            return [err_draft], {"engine": "error", "error": str(e), "raw_text": ""}

    async def parse(self, file_content: bytes, filename: str = "receipt.png") -> List[Dict[str, Any]]:
        drafts, _ = await self.parse_with_metadata(file_content, filename=filename)
        return drafts


class PDFProcessor:
    """
    Format-aware multi-page PDF processor:
    - Uses PyMuPDF native text & table extraction (`find_tables()` + reading-order word
      coordinates) for digital pages.
    - Detects scanned/image-based pages independently and runs OCR ONLY on scanned pages
      (supporting mixed PDFs containing both digital and scanned pages).
    - Processes scanned pages with bounded parallelism preserving exact page order.
    - Preserves page numbers, reading order, and table row/column relationships.
    """

    DATE_ROW_START_RE = re.compile(
        r"^\s*(\d{4}[-/\.]\d{2}[-/\.]\d{2}|\d{1,2}[-/\.]\d{1,2}[-/\.]\d{2,4}|\d{1,2}[-\s]+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*[-\s,]+\d{2,4})\b",
        re.IGNORECASE,
    )

    def __init__(self, image_processor: ImageReceiptProcessor, max_parallel_pages: int = 3):
        self.image_processor = image_processor
        self.max_parallel_pages = max(1, min(max_parallel_pages, os.cpu_count() or 2))

    @staticmethod
    def _extract_ordered_lines_from_digital_page(page: Any) -> Tuple[List[str], List[Dict[str, Any]], str]:
        """
        Extracts words from a digital PyMuPDF page and groups them into visual rows
        preserving left-to-right column separation and reading order.
        """
        words = page.get_text("words") or []
        if not words:
            raw = page.get_text("text") or ""
            lines = [l.strip() for l in raw.splitlines() if l.strip()]
            return lines, [], raw

        # Each word tuple: (x0, y0, x1, y1, word, block_no, line_no, word_no)
        words.sort(key=lambda w: (round(w[1] / 3.0) * 3.0, w[0]))
        rows: List[List[Tuple]] = []
        for w in words:
            y_mid = (w[1] + w[3]) * 0.5
            h = max(4.0, w[3] - w[1])
            placed = False
            for r in reversed(rows[-5:]):
                ry = sum((item[1] + item[3]) * 0.5 for item in r) / len(r)
                if abs(y_mid - ry) <= max(4.5, h * 0.55):
                    r.append(w)
                    placed = True
                    break
            if not placed:
                rows.append([w])

        rows.sort(key=lambda r: sum((item[1] + item[3]) * 0.5 for item in r) / len(r))
        lines: List[str] = []
        line_boxes: List[Dict[str, Any]] = []

        for r in rows:
            r.sort(key=lambda item: item[0])
            parts: List[str] = []
            for idx, w in enumerate(r):
                if idx > 0:
                    gap = w[0] - r[idx - 1][2]
                    parts.append("   " if gap > 14.0 else " ")
                parts.append(str(w[4]))
            text_line = "".join(parts).strip()
            if not text_line:
                continue
            bbox = [
                min(w[0] for w in r),
                min(w[1] for w in r),
                max(w[2] for w in r),
                max(w[3] for w in r),
            ]
            lines.append(text_line)
            line_boxes.append({"text": text_line, "confidence": 0.99, "bbox": bbox})

        return lines, line_boxes, "\n".join(lines)

    @staticmethod
    def _extract_tables_from_digital_page(
        page: Any,
        page_text: str,
        filename: str,
        page_num: int,
    ) -> List[Dict[str, Any]]:
        """
        Extracts multi-row bank statement tables using PyMuPDF `find_tables()`
        preserving strict row/column separation (e.g. Date | Narration | Ref | Debit | Credit | Balance).
        """
        if not hasattr(page, "find_tables"):
            return []
        try:
            finder = page.find_tables()
            tables = getattr(finder, "tables", None) or []
        except Exception:
            return []

        if not tables:
            return []

        doc_curr, doc_curr_conf, _ = detect_currency_from_text(page_text, default="USD")
        is_indian = (doc_curr == "INR") or bool(re.search(r"\b(?:inr|gstin|upi|neft|imps|hdfc|icici|sbi|axis|withdrawal|narration)\b", page_text, re.IGNORECASE))

        drafts: List[Dict[str, Any]] = []
        for tbl in tables:
            raw_rows = tbl.extract() or []
            clean_rows = [
                [str(c or "").replace("\n", " ").strip() for c in r]
                for r in raw_rows
                if r and any(c and str(c).strip() for c in r)
            ]
            if len(clean_rows) < 2:
                continue

            header_idx, col_map = CSVProcessor.locate_header_row(clean_rows)
            # Only treat as a bank statement table if it has a date column AND an amount/debit/credit column
            if "date" not in col_map or not any(k in col_map for k in ("amount", "debit", "credit")):
                continue

            date_i = col_map["date"]
            desc_i = col_map.get("description", -1)
            debit_i = col_map.get("debit", -1)
            credit_i = col_map.get("credit", -1)
            amt_i = col_map.get("amount", -1)
            type_i = col_map.get("type", -1)
            ref_i = col_map.get("ref", -1)
            bal_i = col_map.get("balance", -1)

            for r_offset, row in enumerate(clean_rows[header_idx + 1:], start=1):
                joined = " ".join(c for c in row if c)
                if SUMMARY_ROW_RE.search(joined):
                    continue
                if date_i >= len(row):
                    continue
                parsed_dt = parse_date_robust(row[date_i], prefer_dayfirst=is_indian)
                if not parsed_dt:
                    continue

                desc = row[desc_i].strip() if (desc_i != -1 and desc_i < len(row)) else ""
                if not desc:
                    # Pick longest non-date/non-numeric cell as description
                    non_meta = [
                        row[i] for i in range(len(row))
                        if i not in {date_i, debit_i, credit_i, amt_i, bal_i, ref_i, type_i} and row[i]
                    ]
                    desc = " ".join(non_meta).strip()

                raw_ref = row[ref_i].strip() if (ref_i != -1 and ref_i < len(row) and row[ref_i].strip()) else None
                bal_val, _ = parse_amount_str(row[bal_i]) if (bal_i != -1 and bal_i < len(row)) else (None, None)

                amount_minor = 0
                ttype = "expense"
                curr = doc_curr
                method = "pdf_table_column"

                if debit_i != -1 or credit_i != -1:
                    d_val, d_c = parse_amount_str(row[debit_i]) if (debit_i != -1 and debit_i < len(row)) else (None, None)
                    c_val, c_c = parse_amount_str(row[credit_i]) if (credit_i != -1 and credit_i < len(row)) else (None, None)
                    if d_val is not None and abs(d_val) > 0:
                        amount_minor = int(round(abs(d_val) * 100))
                        ttype = "expense"
                        curr = d_c or curr
                        method = "pdf_table_debit_col"
                    elif c_val is not None and abs(c_val) > 0:
                        amount_minor = int(round(abs(c_val) * 100))
                        ttype = "income"
                        curr = c_c or curr
                        method = "pdf_table_credit_col"
                    else:
                        continue
                elif amt_i != -1 and amt_i < len(row):
                    a_val, a_c = parse_amount_str(row[amt_i])
                    if a_val is None or abs(a_val) == 0:
                        continue
                    amount_minor = int(round(abs(a_val) * 100))
                    curr = a_c or curr
                    if type_i != -1 and type_i < len(row):
                        t_s = row[type_i].lower()
                        ttype = "income" if any(k in t_s for k in ("cr", "credit", "deposit", "inward")) else "expense"
                    else:
                        is_cr = (a_val > 0 and any(k in joined.lower() for k in ("cr", "credit", "deposit", "inward", "payout", "refund")))
                        ttype = "income" if is_cr else "expense"

                merchant, upi_id, ext_ref = _extract_merchant_from_narration(desc)
                final_ref = raw_ref or ext_ref
                cat_res = categorizer_instance.categorize(f"{merchant or ''} {desc}", merchant=merchant)

                drafts.append({
                    "date": parsed_dt.isoformat(),
                    "date_missing": False,
                    "description": desc or f"Statement row from {filename}",
                    "merchant": merchant,
                    "amount_minor": amount_minor,
                    "currency": curr,
                    "type": ttype,
                    "category_name": cat_res["category"],
                    "confidence": cat_res["confidence"],
                    "model_version": cat_res["model_version"],
                    "review_required": cat_res["review_required"] or cat_res["confidence"] < 0.75,
                    "review_reasons": [] if cat_res["confidence"] >= 0.75 else ["Verify ML category."],
                    "source": "pdf_statement_table",
                    "source_file": filename,
                    "page_number": page_num,
                    "line_number": r_offset,
                    "reference_no": final_ref,
                    "upi_id": upi_id,
                    "running_balance_minor": int(round(bal_val * 100)) if bal_val is not None else None,
                    "extraction_confidence": 0.96,
                    "field_metadata": {
                        "merchant": {"value": merchant, "confidence": 0.90, "method": "pdf_table_narration", "source": {"page": page_num, "line": r_offset}},
                        "date": {"value": parsed_dt.date().isoformat(), "confidence": 0.98, "method": "pdf_table_date_col", "source": {"page": page_num, "line": r_offset}},
                        "amount_minor": {"value": amount_minor, "confidence": 0.98, "method": method, "source": {"page": page_num, "line": r_offset}},
                        "currency": {"value": curr, "confidence": doc_curr_conf, "method": "pdf_doc_currency", "source": {"page": page_num}},
                        "type": {"value": ttype, "confidence": 0.95, "method": method, "source": {"page": page_num}},
                    },
                    "validation": {"is_valid": True, "reconciliation_status": "table_structured", "issues": [], "warnings": []},
                    "raw_text": joined,
                    "raw_text_snippet": joined[:200],
                })

        return drafts

    @classmethod
    def extract_statement_rows_from_lines(
        cls,
        lines: List[str],
        line_boxes: Optional[List[Dict[str, Any]]],
        filename: str,
        page_num: int,
        source_type: str = "pdf_statement",
        full_text: str = "",
    ) -> List[Dict[str, Any]]:
        """
        Extracts multi-row bank statement transactions from visual reading-order lines
        (works on both digital PDFs without gridlines and scanned bank statements).
        Handles dual debit/credit columns, trailing running balances, and Indian formats.
        """
        doc_text = full_text or "\n".join(lines)
        doc_curr, doc_curr_conf, _ = detect_currency_from_text(doc_text, default="USD")
        is_indian = (doc_curr == "INR") or bool(re.search(r"\b(?:inr|upi|neft|imps|rtgs|hdfc|icici|sbi|axis|withdrawal|narration)\b", doc_text, re.IGNORECASE))

        # Detect whether header indicates dual columns (Debit/Credit) + Balance column
        has_balance_col = False
        has_dual_dc = False
        header_line_idx = -1
        for idx, l in enumerate(lines[:12]):
            low = l.lower()
            if "date" in low and any(k in low for k in ("amount", "debit", "credit", "withdrawal", "deposit", "description", "narration", "particulars")):
                header_line_idx = idx
                has_balance_col = "balance" in low or "bal" in low
                has_dual_dc = any(k in low for k in ("withdrawal", "debit")) and any(k in low for k in ("deposit", "credit"))
                break

        table_drafts: List[Dict[str, Any]] = []
        prev_balance_minor: Optional[int] = None

        for idx, line in enumerate(lines):
            if idx <= header_line_idx:
                continue
            if SUMMARY_ROW_RE.search(line):
                # Capture opening balance if present
                bal_nums = re.findall(r"(?:₹|Rs\.?|INR|\$|€|£)?\s*([\d,]+\.\d{2})", line)
                if bal_nums:
                    bv, _ = parse_amount_str(bal_nums[-1])
                    if bv is not None:
                        prev_balance_minor = int(round(bv * 100))
                continue

            m_date = cls.DATE_ROW_START_RE.match(line)
            if not m_date:
                continue

            date_str = m_date.group(1)
            parsed_dt = parse_date_robust(date_str, prefer_dayfirst=is_indian)
            if not parsed_dt:
                continue

            rest = line[m_date.end():].strip()
            # Find all monetary amounts (with 2 decimal places) in remainder of row
            amt_matches = list(re.finditer(r"((?:₹|Rs\.?|INR|\$|USD|€|£)?\s*[+\-]?(?:\d{1,3}(?:,\d{2,3})+|\d+)\.\d{2})\s*(CR|DR)?", rest, re.IGNORECASE))
            if not amt_matches:
                continue

            # If a trailing balance column exists and >=2 amounts appear, last number is running balance!
            running_bal_minor: Optional[int] = None
            txn_match = amt_matches[-1]
            if has_balance_col and len(amt_matches) >= 2:
                bal_val, _ = parse_amount_str(amt_matches[-1].group(1))
                if bal_val is not None:
                    running_bal_minor = int(round(bal_val * 100))
                txn_match = amt_matches[-2]

            amt_val, row_curr = parse_amount_str(txn_match.group(1))
            if amt_val is None or abs(amt_val) == 0:
                continue

            amount_minor = int(round(abs(amt_val) * 100))
            curr = row_curr or doc_curr
            cr_dr_flag = (txn_match.group(2) or "").upper()

            # Description is text before the first amount token
            desc = rest[:amt_matches[0].start()].strip(" |-:")
            # Remove secondary value date if present right after txn date
            desc = re.sub(r"^\d{1,2}[-/\.]\d{1,2}[-/\.]\d{2,4}\s+", "", desc).strip()
            if not desc:
                desc = f"Statement transaction ({date_str})"

            # Determine debit / credit direction accurately
            type_method = "statement_line_rule"
            if cr_dr_flag == "CR":
                ttype = "income"
                type_method = "explicit_cr_tag"
            elif cr_dr_flag == "DR":
                ttype = "expense"
                type_method = "explicit_dr_tag"
            elif running_bal_minor is not None and prev_balance_minor is not None:
                if abs((prev_balance_minor + amount_minor) - running_bal_minor) <= 5:
                    ttype = "income"
                    type_method = "running_balance_verified"
                elif abs((prev_balance_minor - amount_minor) - running_bal_minor) <= 5:
                    ttype = "expense"
                    type_method = "running_balance_verified"
                else:
                    is_cr = any(w in line.lower() for w in [" cr", "credit", "deposit", "payout", "refund", "inward"])
                    ttype = "income" if is_cr else "expense"
            else:
                is_cr = (amt_val > 0 and any(w in line.lower() for w in [" cr", "credit", "deposit", "payout", "refund", "inward"]))
                ttype = "income" if is_cr else "expense"

            if running_bal_minor is not None:
                prev_balance_minor = running_bal_minor

            merchant, upi_id, ref_no = _extract_merchant_from_narration(desc)
            cat_res = categorizer_instance.categorize(f"{merchant or ''} {desc}", merchant=merchant)

            lb_conf = line_boxes[idx]["confidence"] if (line_boxes and idx < len(line_boxes)) else 0.92
            lb_bbox = line_boxes[idx]["bbox"] if (line_boxes and idx < len(line_boxes)) else None

            table_drafts.append({
                "date": parsed_dt.isoformat(),
                "date_missing": False,
                "description": desc,
                "merchant": merchant,
                "amount_minor": amount_minor,
                "currency": curr,
                "type": ttype,
                "category_name": cat_res["category"],
                "confidence": cat_res["confidence"],
                "model_version": cat_res["model_version"],
                "review_required": lb_conf < 0.85 or cat_res["review_required"],
                "review_reasons": [] if (lb_conf >= 0.85 and not cat_res["review_required"]) else ["Verify extracted statement row."],
                "source": source_type,
                "source_file": filename,
                "page_number": page_num,
                "line_number": idx + 1,
                "reference_no": ref_no,
                "upi_id": upi_id,
                "running_balance_minor": running_bal_minor,
                "extraction_confidence": round(min(0.96, lb_conf * 0.96), 3),
                "field_metadata": {
                    "merchant": {"value": merchant, "confidence": round(lb_conf * 0.90, 3), "method": "statement_narration", "source": {"page": page_num, "line": idx + 1, "bbox": lb_bbox}},
                    "date": {"value": parsed_dt.date().isoformat(), "confidence": round(lb_conf * 0.97, 3), "method": "statement_date_prefix", "source": {"page": page_num, "line": idx + 1, "bbox": lb_bbox}},
                    "amount_minor": {"value": amount_minor, "confidence": round(lb_conf * 0.96, 3), "method": "statement_amount_column", "source": {"page": page_num, "line": idx + 1, "bbox": lb_bbox}},
                    "currency": {"value": curr, "confidence": doc_curr_conf, "method": "document_currency", "source": {"page": page_num}},
                    "type": {"value": ttype, "confidence": 0.96 if type_method in {"explicit_cr_tag", "explicit_dr_tag", "running_balance_verified"} else 0.82, "method": type_method, "source": {"page": page_num}},
                },
                "validation": {"is_valid": True, "reconciliation_status": type_method, "issues": [], "warnings": []},
                "raw_text": line,
                "raw_text_snippet": line[:200],
            })

        return table_drafts

    @staticmethod
    def _is_scanned_page(page: Any, native_text: str) -> bool:
        """Determines if a PDF page is image/scan-based rather than native digital text."""
        stripped = (native_text or "").strip()
        alnum_chars = sum(1 for c in stripped if c.isalnum())
        if alnum_chars >= 40:
            return False
        images = page.get_images(full=False) if hasattr(page, "get_images") else []
        if images and alnum_chars < 40:
            return True
        return alnum_chars < 25

    async def parse_with_metadata(
        self,
        file_content: bytes,
        filename: str = "document.pdf",
        preferred_engine: Optional[str] = None,
    ) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        t0 = time.perf_counter()
        if pymupdf is None:
            return [], {"engine": "pymupdf_missing", "error": "PyMuPDF is not installed", "raw_text": ""}

        try:
            doc = pymupdf.open(stream=file_content, filetype="pdf")
            total_pages = len(doc)
        except Exception as e:
            return [], {"engine": "pdf_open_error", "error": str(e), "raw_text": ""}

        # Step 1: Classify every page synchronously using PyMuPDF (fast, thread-safe before parallel OCR)
        digital_pages: List[Tuple[int, List[str], List[Dict[str, Any]], str, List[Dict[str, Any]]]] = []
        scanned_renders: List[Tuple[int, Image.Image, bool]] = []
        page_modes: Dict[int, str] = {}

        for page_idx in range(total_pages):
            page = doc[page_idx]
            page_num = page_idx + 1
            raw_native = page.get_text("text") or ""

            if self._is_scanned_page(page, raw_native):
                page_modes[page_num] = "scanned_ocr"
                pix = page.get_pixmap(dpi=220)
                img = Image.open(io.BytesIO(pix.tobytes("png")))
                # Use heavier structure pipeline only on wide/landscape or multi-column statement aspect
                use_struct = img.width > img.height * 1.05
                scanned_renders.append((page_num, img, use_struct))
            else:
                page_modes[page_num] = "digital_native"
                ordered_lines, line_boxes, ordered_text = self._extract_ordered_lines_from_digital_page(page)
                table_drafts = self._extract_tables_from_digital_page(page, ordered_text, filename, page_num)
                digital_pages.append((page_num, ordered_lines, line_boxes, ordered_text, table_drafts))

        doc.close()

        # Step 2: Process digital pages immediately (preserving page numbers)
        page_results: Dict[int, Tuple[List[Dict[str, Any]], str, Dict[str, Any]]] = {}
        for page_num, ordered_lines, line_boxes, ordered_text, table_drafts in digital_pages:
            if table_drafts:
                page_results[page_num] = (table_drafts, ordered_text, {"mode": "digital_table", "engine": "pymupdf_table"})
            else:
                line_stmt = self.extract_statement_rows_from_lines(
                    lines=ordered_lines,
                    line_boxes=line_boxes,
                    filename=filename,
                    page_num=page_num,
                    source_type="pdf_statement",
                    full_text=ordered_text,
                )
                if len(line_stmt) >= 2:
                    page_results[page_num] = (line_stmt, ordered_text, {"mode": "digital_statement", "engine": "pymupdf_native"})
                else:
                    inv = extract_financial_document(
                        text=ordered_text,
                        lines=ordered_lines,
                        line_boxes=line_boxes,
                        filename=filename,
                        page_num=page_num,
                        source_type="pdf_invoice",
                        ocr_mean_confidence=0.99,
                    )
                    drafts_p = [inv] if inv["amount_minor"] > 0 or not inv["date_missing"] else []
                    page_results[page_num] = (drafts_p, ordered_text, {"mode": "digital_invoice", "engine": "pymupdf_native"})

        # Step 3: Process ONLY scanned pages with bounded parallelism preserving exact page order
        if scanned_renders:
            sem = asyncio.Semaphore(self.max_parallel_pages)

            async def _ocr_scanned_page(p_num: int, p_img: Image.Image, p_struct: bool):
                async with sem:
                    drafts_p, p_meta = await self.image_processor.parse_pil_image(
                        p_img,
                        filename=filename,
                        page_num=p_num,
                        source_type="scanned_pdf_ocr",
                        preferred_engine=preferred_engine,
                        use_structure=p_struct,
                    )
                    return p_num, drafts_p, p_meta.get("raw_text", ""), p_meta

            ocr_tasks = [_ocr_scanned_page(pn, pim, ps) for pn, pim, ps in scanned_renders]
            ocr_outputs = await asyncio.gather(*ocr_tasks)
            for p_num, drafts_p, p_text, p_meta in ocr_outputs:
                page_results[p_num] = (drafts_p, p_text, {"mode": "scanned_ocr", **p_meta})

        # Step 4: Reassemble in strict ascending page order
        all_drafts: List[Dict[str, Any]] = []
        raw_pages_text: List[str] = []
        page_summaries: List[Dict[str, Any]] = []

        for p_num in range(1, total_pages + 1):
            p_drafts, p_text, p_meta = page_results.get(p_num, ([], "", {"mode": "empty"}))
            all_drafts.extend(p_drafts)
            raw_pages_text.append(f"--- Page {p_num} ({page_modes.get(p_num, 'unknown')}) ---\n{p_text}")
            page_summaries.append({
                "page": p_num,
                "mode": page_modes.get(p_num, "unknown"),
                "engine": p_meta.get("engine", "pymupdf_native"),
                "transactions_extracted": len(p_drafts),
            })

        digital_count = sum(1 for m in page_modes.values() if m == "digital_native")
        scanned_count = sum(1 for m in page_modes.values() if m == "scanned_ocr")
        pdf_kind = "mixed" if (digital_count > 0 and scanned_count > 0) else ("scanned" if scanned_count > 0 else "digital")

        meta = {
            "engine": "pymupdf+ocr" if scanned_count > 0 else "pymupdf_native",
            "pdf_kind": pdf_kind,
            "page_count": total_pages,
            "digital_pages": digital_count,
            "scanned_pages": scanned_count,
            "pages": page_summaries,
            "processing_ms": round((time.perf_counter() - t0) * 1000, 1),
            "raw_text": "\n\n".join(raw_pages_text),
        }
        return all_drafts, meta

    async def parse(self, file_content: bytes, filename: str = "document.pdf") -> List[Dict[str, Any]]:
        drafts, _ = await self.parse_with_metadata(file_content, filename=filename)
        return drafts


class DocumentParser:
    """
    Main format-aware entry point for CashIQ document & image ingestion.
    Features SHA-256 content-hash caching, bounded multi-page parallelism,
    lazy singleton OCR model reuse, and full audit metadata retention.
    """

    PARSER_VERSION = "v3.0.0"

    def __init__(self, cache_max_size: int = 256):
        self.csv_processor = CSVProcessor()
        self.image_processor = ImageReceiptProcessor()
        self.pdf_processor = PDFProcessor(self.image_processor)
        self._cache_max_size = cache_max_size
        self._result_cache: "OrderedDict[str, Dict[str, Any]]" = OrderedDict()

    @staticmethod
    def compute_file_hash(content: bytes) -> str:
        return hashlib.sha256(content).hexdigest()

    def clear_cache(self) -> None:
        self._result_cache.clear()

    def _cache_get(self, key: str) -> Optional[Dict[str, Any]]:
        if key in self._result_cache:
            self._result_cache.move_to_end(key)
            return copy.deepcopy(self._result_cache[key])
        return None

    def _cache_put(self, key: str, value: Dict[str, Any]) -> None:
        self._result_cache[key] = copy.deepcopy(value)
        self._result_cache.move_to_end(key)
        while len(self._result_cache) > self._cache_max_size:
            self._result_cache.popitem(last=False)

    def parse_csv(self, file_content: bytes, filename: str = "statement.csv") -> List[Dict[str, Any]]:
        return self.csv_processor.parse(file_content, filename=filename)

    async def parse_receipt(self, file_content: bytes, filename: str = "receipt.png") -> List[Dict[str, Any]]:
        return await self.image_processor.parse(file_content, filename=filename)

    async def parse_pdf(self, file_content: bytes, filename: str = "document.pdf") -> List[Dict[str, Any]]:
        return await self.pdf_processor.parse(file_content, filename=filename)

    async def parse_file_with_metadata(
        self,
        filename: str,
        content: bytes,
        use_cache: bool = True,
        preferred_engine: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Format-aware parser with SHA-256 caching and complete extraction & validation metadata."""
        t0 = time.perf_counter()
        low = (filename or "").lower().strip()
        file_hash = self.compute_file_hash(content)

        if low.endswith(".csv") or low.endswith(".tsv"):
            file_type = "csv"
        elif low.endswith(".pdf"):
            file_type = "pdf"
        else:
            file_type = "receipt"

        cache_key = f"{self.PARSER_VERSION}:{file_type}:{preferred_engine or 'auto'}:{file_hash}"
        if use_cache:
            cached = self._cache_get(cache_key)
            if cached is not None:
                cached["cache_hit"] = True
                cached["processing_ms"] = round((time.perf_counter() - t0) * 1000, 2)
                return cached

        if file_type == "csv":
            drafts, meta = self.csv_processor.parse_with_metadata(content, filename=filename)
        elif file_type == "pdf":
            drafts, meta = await self.pdf_processor.parse_with_metadata(
                content, filename=filename, preferred_engine=preferred_engine
            )
        else:
            drafts, meta = await self.image_processor.parse_with_metadata(
                content, filename=filename, preferred_engine=preferred_engine
            )

        raw_text = meta.pop("raw_text", "")
        review_needed_count = sum(1 for d in drafts if d.get("review_required"))
        invalid_count = sum(1 for d in drafts if not (d.get("validation") or {}).get("is_valid", True))

        payload = {
            "file_hash": file_hash,
            "file_type": file_type,
            "filename": filename,
            "drafts": drafts,
            "count": len(drafts),
            "review_required_count": review_needed_count,
            "validation_failed_count": invalid_count,
            "raw_text": raw_text,
            "cache_hit": False,
            "processing_ms": round((time.perf_counter() - t0) * 1000, 1),
            "metadata": {
                **meta,
                "parser_version": self.PARSER_VERSION,
                "available_ocr_engines": ocr_engine_manager.get_available_engines() if file_type != "csv" else None,
            },
        }

        if use_cache:
            self._cache_put(cache_key, payload)

        return payload

    async def parse_file(self, filename: str, content: bytes) -> List[Dict[str, Any]]:
        """Backward-compatible polymorphic parser returning extracted draft transactions."""
        res = await self.parse_file_with_metadata(filename, content)
        return res["drafts"]


document_parser_instance = DocumentParser()
