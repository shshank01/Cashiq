"""
Comprehensive Format-Aware Document Ingestion & OCR Accuracy Test Suite (v3.0.0).

Tests:
1. Clear US & Indian GST receipts (exact merchant, date, total, subtotal, CGST/SGST, GSTIN, currency, reconciliation).
2. Blurry, rotated (90°), and low-light receipt images (conditional preprocessing & orientation recovery).
3. Digital PDFs (bank statements with grid tables + single vendor invoice).
4. Scanned PDF (image-only PDF routed to OCR).
5. Mixed PDF (Page 1 digital bank statement + Page 2 scanned Indian GST invoice, preserving page numbers).
6. Indian bank statement CSV (zero OCR, preamble skip, DD/MM/YYYY, separate debit/credit, Indian commas,
   UPI/UTR extraction, running balance verification, footer exclusion).
7. Malformed CSV resilience (CP1252, semicolon delimiter, broken rows, missing dates flagged rather than invented).
8. Deterministic validation & reconciliation failure flagging `review_required=True`.
9. File-hash caching & repeated-parse speedup.
"""

import os
import sys
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.ml.document_parser import DocumentParser, document_parser_instance
from app.ml.financial_extractor import extract_financial_document
from tests.corpus_generator import (
    load_real_sample_documents,
    make_blurry_receipt_image,
    make_digital_indian_bank_pdf,
    make_indian_bank_csv,
    make_indian_gst_receipt_image,
    make_low_light_receipt,
    make_malformed_csv,
    make_mixed_pdf,
    make_rotated_photo_receipt,
    make_scanned_pdf,
)


@pytest.mark.asyncio
async def test_clear_indian_gst_receipt_extraction_and_reconciliation():
    img_bytes, gt = make_indian_gst_receipt_image()
    res = await document_parser_instance.parse_file_with_metadata(gt["name"], img_bytes, use_cache=False)
    assert res["count"] == 1
    d = res["drafts"][0]

    assert "techspark" in (d["merchant"] or "").lower()
    assert d["date"] and d["date"].startswith(gt["date"])
    assert d["amount_minor"] == gt["amount_minor"]  # ₹1,23,450.00 (NOT subtotal or previous balance!)
    assert d["subtotal_minor"] == gt["subtotal_minor"]
    assert d["tax_minor"] == gt["tax_minor"]
    assert d["discount_minor"] == gt["discount_minor"]
    assert d["currency"] == "INR"
    assert d["type"] == "expense"
    assert d["gstin"] == gt["gstin"]
    assert d["validation"]["is_valid"] is True
    assert d["validation"]["reconciliation_status"] in {"exact_match", "reconciled_within_rounding"}
    assert "field_metadata" in d and "amount_minor" in d["field_metadata"]
    assert d["raw_text"] and "GRAND TOTAL" in d["raw_text"]


@pytest.mark.asyncio
async def test_real_sample_documents_extraction():
    samples = load_real_sample_documents()
    assert len(samples) >= 3

    for fname, content, gt in samples:
        res = await document_parser_instance.parse_file_with_metadata(fname, content, use_cache=False)
        assert res["count"] >= 1, f"No drafts extracted for {fname}"

        if gt["kind"] == "image_clear_real":
            d = res["drafts"][0]
            assert "office depot" in (d["merchant"] or "").lower()
            assert d["date"] and d["date"].startswith(gt["date"])
            assert d["amount_minor"] == gt["amount_minor"]
            assert d["subtotal_minor"] == gt["subtotal_minor"]
            assert d["tax_minor"] == gt["tax_minor"]
            assert d["currency"] == "USD"
            assert d["validation"]["reconciliation_status"] in {"exact_match", "reconciled_within_rounding"}
            assert len(d["line_items"]) >= 3

        elif gt["kind"] == "pdf_digital_invoice_real":
            d = res["drafts"][0]
            assert "datadog" in (d["merchant"] or "").lower()
            assert d["date"] and d["date"].startswith(gt["date"])
            assert d["amount_minor"] == gt["amount_minor"]
            assert d["currency"] == "USD"
            assert res["metadata"]["pdf_kind"] == "digital"

        elif gt["kind"] == "pdf_digital_statement_real":
            assert res["count"] >= gt["min_expected_rows"]
            assert res["metadata"]["pdf_kind"] == "digital"


@pytest.mark.asyncio
async def test_blurry_rotated_and_low_light_receipts():
    # Blurry
    b_bytes, b_gt = make_blurry_receipt_image()
    b_res = await document_parser_instance.parse_file_with_metadata(b_gt["name"], b_bytes, use_cache=False)
    bd = b_res["drafts"][0]
    assert bd["amount_minor"] == b_gt["amount_minor"]
    assert bd["currency"] == "INR"
    assert bd["date"] and bd["date"].startswith(b_gt["date"])

    # Rotated 90 deg
    r_bytes, r_gt = make_rotated_photo_receipt()
    r_res = await document_parser_instance.parse_file_with_metadata(r_gt["name"], r_bytes, use_cache=False)
    rd = r_res["drafts"][0]
    assert rd["amount_minor"] == r_gt["amount_minor"]
    assert rd["currency"] == "INR"
    assert rd["date"] and rd["date"].startswith(r_gt["date"])

    # Low-light shadowed photo
    l_bytes, l_gt = make_low_light_receipt()
    l_res = await document_parser_instance.parse_file_with_metadata(l_gt["name"], l_bytes, use_cache=False)
    ld = l_res["drafts"][0]
    assert ld["amount_minor"] == l_gt["amount_minor"]
    assert ld["currency"] == "USD"
    assert ld["date"] and ld["date"].startswith(l_gt["date"])


@pytest.mark.asyncio
async def test_digital_scanned_and_mixed_pdfs():
    # Digital Indian Bank Statement PDF
    dig_bytes, dig_gt = make_digital_indian_bank_pdf()
    dig_res = await document_parser_instance.parse_file_with_metadata(dig_gt["name"], dig_bytes, use_cache=False)
    assert dig_res["metadata"]["pdf_kind"] == "digital"
    assert dig_res["metadata"]["scanned_pages"] == 0
    assert dig_res["count"] == len(dig_gt["expected_rows"])
    for got, exp in zip(dig_res["drafts"], dig_gt["expected_rows"]):
        assert got["amount_minor"] == exp["amount_minor"]
        assert got["type"] == exp["type"]
        assert got["currency"] == exp["currency"]
        assert got["date"].startswith(exp["date"])
        assert got["page_number"] == 1

    # Scanned PDF
    sc_bytes, sc_gt = make_scanned_pdf()
    sc_res = await document_parser_instance.parse_file_with_metadata(sc_gt["name"], sc_bytes, use_cache=False)
    assert sc_res["metadata"]["pdf_kind"] == "scanned"
    assert sc_res["metadata"]["scanned_pages"] == 1
    assert sc_res["count"] == 1
    assert sc_res["drafts"][0]["amount_minor"] == sc_gt["amount_minor"]
    assert sc_res["drafts"][0]["currency"] == "INR"

    # Mixed PDF (Page 1 digital table + Page 2 scanned Indian GST invoice)
    mx_bytes, mx_gt = make_mixed_pdf()
    mx_res = await document_parser_instance.parse_file_with_metadata(mx_gt["name"], mx_bytes, use_cache=False)
    assert mx_res["metadata"]["pdf_kind"] == "mixed"
    assert mx_res["metadata"]["digital_pages"] == 1
    assert mx_res["metadata"]["scanned_pages"] == 1
    assert mx_res["count"] == mx_gt["total_expected_transactions"]
    p1_drafts = [d for d in mx_res["drafts"] if d["page_number"] == 1]
    p2_drafts = [d for d in mx_res["drafts"] if d["page_number"] == 2]
    assert len(p1_drafts) == 4
    assert len(p2_drafts) == 1
    assert p2_drafts[0]["amount_minor"] == mx_gt["page2_invoice"]["amount_minor"]


@pytest.mark.asyncio
async def test_indian_bank_csv_and_malformed_csv():
    # Indian HDFC bank CSV (zero OCR, preamble skipped, running balance verified, footer excluded)
    csv_bytes, gt = make_indian_bank_csv()
    res = await document_parser_instance.parse_file_with_metadata(gt["name"], csv_bytes, use_cache=False)
    assert res["metadata"]["engine"] == "csv_native"
    assert res["metadata"]["available_ocr_engines"] is None  # Confirms OCR never ran on CSV
    assert res["count"] == len(gt["expected_rows"])
    assert res["metadata"]["running_balance_checks_passed"] >= 3
    assert res["metadata"]["running_balance_checks_failed"] == 0
    for got, exp in zip(res["drafts"], gt["expected_rows"]):
        assert got["amount_minor"] == exp["amount_minor"]
        assert got["type"] == exp["type"]
        assert got["currency"] == "INR"
        assert got["date"].startswith(exp["date"])

    # Malformed CP1252 semicolon CSV
    mal_bytes, mal_gt = make_malformed_csv()
    mal_res = await document_parser_instance.parse_file_with_metadata(mal_gt["name"], mal_bytes, use_cache=False)
    assert mal_res["metadata"]["delimiter"] == ";"
    assert mal_res["count"] == mal_gt["total_extracted_including_review"]
    # Invalid date row must NOT have a silently invented date and MUST require review
    bad_date_rows = [d for d in mal_res["drafts"] if d["date_missing"]]
    assert len(bad_date_rows) == 1
    assert bad_date_rows[0]["date"] is None
    assert bad_date_rows[0]["review_required"] is True
    assert bad_date_rows[0]["validation"]["is_valid"] is False


def test_deterministic_reconciliation_mismatch_requests_review():
    """If subtotal + tax != total, validator must flag mismatch and request human review."""
    text = (
        "ACME TECH SUPPLIES\n"
        "Invoice No: INV-99\n"
        "Date: 15/10/2026\n"
        "Subtotal: Rs. 1,000.00\n"
        "GST (18%): Rs. 180.00\n"
        "Grand Total: Rs. 1,500.00\n"  # Wrong! Should be 1,180.00
    )
    extracted = extract_financial_document(text=text, lines=text.splitlines(), filename="bad_math.png")
    assert extracted["validation"]["is_valid"] is False
    assert extracted["validation"]["reconciliation_status"] == "mismatch"
    assert extracted["review_required"] is True
    assert any("mismatch" in r.lower() for r in extracted["review_reasons"])


def test_missing_date_not_silently_invented():
    """Missing date must remain None with date_missing=True and review_required=True."""
    text = (
        "QUICK MART STORE\n"
        "Total Payable: Rs. 450.00\n"
    )
    extracted = extract_financial_document(text=text, lines=text.splitlines(), filename="no_date.png")
    assert extracted["date"] is None
    assert extracted["date_missing"] is True
    assert extracted["field_metadata"]["date"]["confidence"] == 0.0
    assert extracted["review_required"] is True


@pytest.mark.asyncio
async def test_file_hash_caching():
    parser = DocumentParser()
    csv_bytes, gt = make_indian_bank_csv()

    r1 = await parser.parse_file_with_metadata(gt["name"], csv_bytes, use_cache=True)
    r2 = await parser.parse_file_with_metadata(gt["name"], csv_bytes, use_cache=True)

    assert r1["cache_hit"] is False
    assert r2["cache_hit"] is True
    assert r1["file_hash"] == r2["file_hash"]
    assert r1["count"] == r2["count"]
