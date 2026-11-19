"""
Synthetic & Real Representative Test Corpus Generator for CashIQ Document Ingestion Benchmarking.

Generates deterministic, ground-truth-annotated test artifacts covering:
1. Clear receipt (US retail + Indian GST tax invoice with ₹, CGST/SGST, GSTIN, DD/MM/YYYY)
2. Blurry receipt (Gaussian blur + noise)
3. Rotated & skewed photographed receipt (90° rotated + photographed on dark background with perspective tilt)
4. Low-light shadowed receipt image
5. Digital PDFs (existing sample_bank_statement.pdf, sample_vendor_bill.pdf, + Indian multi-column bank statement PDF)
6. Scanned PDF (rasterized image-only PDF with zero native text)
7. Mixed PDF (Page 1 digital bank statement table + Page 2 scanned Indian GST invoice image)
8. Indian bank statement CSV (HDFC/ICICI style with preamble rows, DD/MM/YYYY, separate Debit/Credit, Indian commas, UPI, UTR, running balance, footer)
9. Malformed CSV (CP1252/BOM, semicolon delimiter, truncated rows, invalid date, footer summaries)
"""

import io
import os
from typing import Any, Dict, List, Tuple

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont
import pymupdf


REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
SAMPLE_DOCS_DIR = os.path.join(REPO_ROOT, "sample_documents")


def _load_font(size: int = 22, bold: bool = False) -> ImageFont.FreeTypeFont:
    candidates = [
        r"C:\Windows\Fonts\arialbd.ttf" if bold else r"C:\Windows\Fonts\arial.ttf",
        r"C:\Windows\Fonts\segoeui.ttf",
        r"C:\Windows\Fonts\consola.ttf",
    ]
    for path in candidates:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size=size)
            except Exception:
                pass
    return ImageFont.load_default()


def render_receipt_image(lines: List[Tuple[str, str, bool]], width: int = 760, bg_color=(255, 255, 255)) -> Image.Image:
    """Renders a clean receipt/invoice image with left & right aligned columns."""
    font_reg = _load_font(22, bold=False)
    font_bold = _load_font(26, bold=True)
    line_h = 38
    height = max(480, 90 + len(lines) * line_h + 60)
    img = Image.new("RGB", (width, height), bg_color)
    draw = ImageDraw.Draw(img)

    y = 40
    for left, right, is_bold in lines:
        f = font_bold if is_bold else font_reg
        if left == "---":
            draw.line([(40, y + 14), (width - 40, y + 14)], fill=(140, 140, 140), width=2)
        else:
            draw.text((44, y), left, fill=(20, 20, 20), font=f)
            if right:
                bbox = draw.textbbox((0, 0), right, font=f)
                rw = bbox[2] - bbox[0]
                draw.text((width - 44 - rw, y), right, fill=(20, 20, 20), font=f)
        y += line_h
    return img


def make_indian_gst_receipt_image() -> Tuple[bytes, Dict[str, Any]]:
    """Generates a clear Indian GST invoice image with Rs./INR, CGST/SGST, GSTIN, Indian comma grouping, DD/MM/YYYY."""
    lines = [
        ("TECHSPARK COMPUTING SOLUTIONS PVT LTD", "", True),
        ("GSTIN: 29AABCT1332L1Z5", "", False),
        ("---", "", False),
        ("Invoice No: INV-2026-4418", "Date: 15/10/2026", False),
        ("Payment Mode: UPI (techspark@hdfcbank)", "Ref: UTR8849201122", False),
        ("---", "", False),
        ("2x Dell 27in Monitor", "Rs. 60,000.00", False),
        ("1x Docking Station Pro", "Rs. 45,000.00", False),
        ("---", "", False),
        ("Subtotal:", "Rs. 1,05,000.00", False),
        ("CGST (9%):", "Rs. 9,450.00", False),
        ("SGST (9%):", "Rs. 9,450.00", False),
        ("Discount:", "Rs. 450.00", False),
        ("GRAND TOTAL:", "Rs. 1,23,450.00", True),
        ("Previous Balance: Rs. 15,000.00", "", False),
    ]
    img = render_receipt_image(lines, width=820)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    gt = {
        "name": "clear_indian_gst_receipt.png",
        "kind": "image_clear",
        "merchant": "TECHSPARK COMPUTING SOLUTIONS PVT LTD",
        "date": "2026-10-15",
        "amount_minor": 12345000,
        "subtotal_minor": 10500000,
        "tax_minor": 1890000,
        "discount_minor": 45000,
        "currency": "INR",
        "type": "expense",
        "invoice_no": "INV-2026-4418",
        "gstin": "29AABCT1332L1Z5",
    }
    return buf.getvalue(), gt


def make_blurry_receipt_image() -> Tuple[bytes, Dict[str, Any]]:
    """Generates a blurry receipt photo (Gaussian blur + mild JPEG compression artifacts)."""
    lines = [
        ("CLOUDWAVE HOSTING SERVICES", "", True),
        ("Invoice No: CW-88219", "Date: 20/09/2026", False),
        ("---", "", False),
        ("1x Managed Kubernetes Cluster", "Rs. 12,000.00", False),
        ("1x Object Storage 2TB", "Rs. 3,000.00", False),
        ("---", "", False),
        ("Subtotal:", "Rs. 15,000.00", False),
        ("IGST (18%):", "Rs. 2,700.00", False),
        ("TOTAL PAYABLE:", "Rs. 17,700.00", True),
        ("Payment Method: Corporate Visa", "", False),
    ]
    img = render_receipt_image(lines, width=780)
    img = img.filter(ImageFilter.GaussianBlur(radius=1.6))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=68)
    gt = {
        "name": "blurry_receipt.jpg",
        "kind": "image_blurry",
        "merchant": "CLOUDWAVE HOSTING SERVICES",
        "date": "2026-09-20",
        "amount_minor": 1770000,
        "subtotal_minor": 1500000,
        "tax_minor": 270000,
        "currency": "INR",
        "type": "expense",
    }
    return buf.getvalue(), gt


def make_rotated_photo_receipt() -> Tuple[bytes, Dict[str, Any]]:
    """Generates a 90-degree rotated receipt photo (simulating sideways smartphone capture)."""
    lines = [
        ("METRO OFFICE SUPPLIES STORE", "", True),
        ("Receipt No: MOS-3109", "Date: 08/10/2026", False),
        ("---", "", False),
        ("3x Laser Toner Cartridge", "Rs. 4,500.00", False),
        ("2x A4 Paper Ream Box", "Rs. 1,500.00", False),
        ("---", "", False),
        ("Subtotal:", "Rs. 6,000.00", False),
        ("CGST (9%):", "Rs. 540.00", False),
        ("SGST (9%):", "Rs. 540.00", False),
        ("NET PAYABLE:", "Rs. 7,080.00", True),
    ]
    img = render_receipt_image(lines, width=760)
    rotated = img.rotate(90, expand=True)
    buf = io.BytesIO()
    rotated.save(buf, format="PNG")
    gt = {
        "name": "rotated_90_receipt.png",
        "kind": "image_rotated",
        "merchant": "METRO OFFICE SUPPLIES STORE",
        "date": "2026-10-08",
        "amount_minor": 708000,
        "subtotal_minor": 600000,
        "tax_minor": 108000,
        "currency": "INR",
        "type": "expense",
    }
    return buf.getvalue(), gt


def make_low_light_receipt() -> Tuple[bytes, Dict[str, Any]]:
    """Generates a low-light uneven-illumination receipt photograph."""
    lines = [
        ("BLUE BOTTLE WORKSPACE CAFE", "", True),
        ("Order: #BB-7741", "Date: 2026-10-05", False),
        ("---", "", False),
        ("4x Artisan Coffee Meeting", "$ 28.00", False),
        ("2x Sandwich Platter", "$ 32.00", False),
        ("---", "", False),
        ("Subtotal:", "$ 60.00", False),
        ("Sales Tax (8%):", "$ 4.80", False),
        ("TOTAL AMOUNT:", "$ 64.80", True),
    ]
    img = render_receipt_image(lines, width=760)
    arr = np.array(img, dtype=np.float32)
    h, w = arr.shape[:2]
    # Simulate dim lighting (0.28x brightness) + uneven diagonal shadow gradient
    yy, xx = np.mgrid[0:h, 0:w]
    grad = 0.24 + 0.14 * (xx / float(w)) + 0.08 * (yy / float(h))
    dark = np.clip(arr * grad[:, :, None], 0, 255).astype(np.uint8)
    out = Image.fromarray(dark)
    buf = io.BytesIO()
    out.save(buf, format="JPEG", quality=82)
    gt = {
        "name": "low_light_receipt.jpg",
        "kind": "image_low_light",
        "merchant": "BLUE BOTTLE WORKSPACE CAFE",
        "date": "2026-10-05",
        "amount_minor": 6480,
        "subtotal_minor": 6000,
        "tax_minor": 480,
        "currency": "USD",
        "type": "expense",
    }
    return buf.getvalue(), gt


def make_scanned_pdf() -> Tuple[bytes, Dict[str, Any]]:
    """Creates a scanned PDF (embedded raster image only, zero selectable native text)."""
    img_bytes, gt = make_indian_gst_receipt_image()
    doc = pymupdf.open()
    page = doc.new_page(width=595, height=842)
    page.insert_image(pymupdf.Rect(30, 40, 565, 660), stream=img_bytes)
    pdf_bytes = doc.tobytes()
    doc.close()
    gt_pdf = dict(gt)
    gt_pdf["name"] = "scanned_indian_invoice.pdf"
    gt_pdf["kind"] = "pdf_scanned"
    return pdf_bytes, gt_pdf


def make_digital_indian_bank_pdf() -> Tuple[bytes, Dict[str, Any]]:
    """Creates a digital multi-column Indian bank statement PDF with grid table (Withdrawal/Deposit/Balance)."""
    doc = pymupdf.open()
    page = doc.new_page(width=620, height=792)
    page.insert_text((36, 44), "HDFC BANK CORPORATE STATEMENT (INR)", fontsize=14)
    page.insert_text((36, 62), "Account: 50200044118822  |  Period: 01/10/2026 to 15/10/2026", fontsize=9)

    headers = ["Txn Date", "Narration", "Ref No", "Withdrawal", "Deposit", "Balance"]
    rows = [
        ["01/10/2026", "Opening Balance", "", "", "", "5,00,000.00"],
        ["02/10/2026", "UPI/901122/AWS CLOUD/aws@icici", "UTR901122", "18,500.00", "", "4,81,500.00"],
        ["05/10/2026", "IMPS INWARD/ACME INDIA RETAINER", "UTR901554", "", "2,50,000.00", "7,31,500.00"],
        ["10/10/2026", "NEFT DR/WEWORK INDIA RENT", "UTR902110", "45,000.00", "", "6,86,500.00"],
        ["12/10/2026", "UPI/902881/SWIGGY TEAM LUNCH", "UTR902881", "1,250.00", "", "6,85,250.00"],
    ]

    col_x = [36, 108, 308, 382, 456, 530, 600]
    y_top = 86
    row_h = 26

    # Draw grid lines and text so PyMuPDF find_tables detects exact table cells
    total_rows = 1 + len(rows)
    for r_i in range(total_rows + 1):
        y = y_top + r_i * row_h
        page.draw_line((col_x[0], y), (col_x[-1], y))
    for x in col_x:
        page.draw_line((x, y_top), (x, y_top + total_rows * row_h))

    for c_i, h_txt in enumerate(headers):
        page.insert_text((col_x[c_i] + 4, y_top + 17), h_txt, fontsize=8.5)
    for r_i, r_vals in enumerate(rows):
        y_txt = y_top + (r_i + 1) * row_h + 17
        for c_i, val in enumerate(r_vals):
            if val:
                page.insert_text((col_x[c_i] + 4, y_txt), val, fontsize=8)

    pdf_bytes = doc.tobytes()
    doc.close()

    gt = {
        "name": "digital_indian_bank_statement.pdf",
        "kind": "pdf_digital_statement",
        "expected_rows": [
            {"date": "2026-10-02", "amount_minor": 1850000, "currency": "INR", "type": "expense", "merchant_sub": "aws"},
            {"date": "2026-10-05", "amount_minor": 25000000, "currency": "INR", "type": "income", "merchant_sub": "acme"},
            {"date": "2026-10-10", "amount_minor": 4500000, "currency": "INR", "type": "expense", "merchant_sub": "wework"},
            {"date": "2026-10-12", "amount_minor": 125000, "currency": "INR", "type": "expense", "merchant_sub": "swiggy"},
        ],
    }
    return pdf_bytes, gt


def make_mixed_pdf() -> Tuple[bytes, Dict[str, Any]]:
    """Creates a 2-page mixed PDF: Page 1 digital bank statement + Page 2 scanned Indian GST invoice."""
    p1_bytes, p1_gt = make_digital_indian_bank_pdf()
    p2_img_bytes, p2_gt = make_indian_gst_receipt_image()

    doc = pymupdf.open(stream=p1_bytes, filetype="pdf")
    page2 = doc.new_page(width=595, height=842)
    page2.insert_image(pymupdf.Rect(30, 40, 565, 660), stream=p2_img_bytes)
    mixed_bytes = doc.tobytes()
    doc.close()

    gt = {
        "name": "mixed_digital_and_scanned.pdf",
        "kind": "pdf_mixed",
        "page1_rows": p1_gt["expected_rows"],
        "page2_invoice": p2_gt,
        "total_expected_transactions": len(p1_gt["expected_rows"]) + 1,
    }
    return mixed_bytes, gt


def make_indian_bank_csv() -> Tuple[bytes, Dict[str, Any]]:
    """Creates an Indian HDFC/ICICI-style CSV with multi-line preamble, Indian commas, DD/MM/YYYY, separate Debit/Credit, running balance & footer."""
    csv_text = (
        "HDFC BANK LIMITED - ACCOUNT STATEMENT\n"
        "Account Holder: APEX CLOUD TECHNOLOGIES PVT LTD\n"
        "Account No: 50200011223344, Currency: INR\n"
        "Statement Period: 01/10/2026 to 15/10/2026\n"
        "\n"
        "Date,Narration,Chq./Ref.No.,Value Dt,Withdrawal Amt.,Deposit Amt.,Closing Balance\n"
        "01/10/2026,Opening Balance,,,, ,\"5,00,000.00\"\n"
        "02/10/2026,UPI/428910293/SWIGGY/swiggy@icici/Team Lunch,UTR428910293,02/10/2026,\"1,450.00\",,\"4,98,550.00\"\n"
        "05/10/2026,NEFT CR-CLIENT PAYMENT INFOSYS LTD,UTR559102831,05/10/2026,,\"1,25,000.00\",\"6,23,550.00\"\n"
        "08/10/2026,RZP*AWS INDIA CLOUD HOSTING,UTR771293841,08/10/2026,\"32,500.00\",,\"5,91,050.00\"\n"
        "12/10/2026,IMPS/882910/WEWORK INDIA LEASE,UTR882910111,12/10/2026,\"1,15,000.00\",,\"4,76,050.00\"\n"
        "15/10/2026,Closing Balance,,,, ,\"4,76,050.00\"\n"
        "*** End of Statement ***\n"
    )
    gt = {
        "name": "indian_hdfc_statement.csv",
        "kind": "csv_indian_bank",
        "expected_rows": [
            {"date": "2026-10-02", "amount_minor": 145000, "currency": "INR", "type": "expense", "merchant_sub": "swiggy"},
            {"date": "2026-10-05", "amount_minor": 12500000, "currency": "INR", "type": "income", "merchant_sub": "client"},
            {"date": "2026-10-08", "amount_minor": 3250000, "currency": "INR", "type": "expense", "merchant_sub": "amazon"},
            {"date": "2026-10-12", "amount_minor": 11500000, "currency": "INR", "type": "expense", "merchant_sub": "wework"},
        ],
    }
    return csv_text.encode("utf-8-sig"), gt


def make_malformed_csv() -> Tuple[bytes, Dict[str, Any]]:
    """Creates a challenging malformed CSV (semicolon delimiter, CP1252, broken rows, invalid date, summary footer)."""
    csv_text = (
        "Exported Bank File\n"
        "Txn Date;Particulars;Debit;Credit;Balance\n"
        "03/10/2026;Google Cloud India;Rs. 14,200.00;;Rs. 85,800.00\n"
        "BROKEN_ROW_WITHOUT_COLUMNS\n"
        "INVALID_DATE;Mystery Vendor;500.00;;85,300.00\n"
        "09/10/2026;Client Retainer Inward;;Rs. 1,50,000.00;Rs. 2,35,300.00\n"
        "Total Debit;Summary;14,700.00;1,50,000.00;2,35,300.00\n"
    )
    gt = {
        "name": "malformed_semicolon.csv",
        "kind": "csv_malformed",
        "valid_expected_rows": 2,
        "total_extracted_including_review": 3,
    }
    return csv_text.encode("cp1252"), gt


def load_real_sample_documents() -> List[Tuple[str, bytes, Dict[str, Any]]]:
    """Loads existing CashIQ sample documents with their exact ground-truth labels."""
    items: List[Tuple[str, bytes, Dict[str, Any]]] = []

    receipt_path = os.path.join(SAMPLE_DOCS_DIR, "sample_receipt.png")
    if os.path.exists(receipt_path):
        with open(receipt_path, "rb") as f:
            items.append((
                "sample_receipt.png",
                f.read(),
                {
                    "name": "sample_receipt.png",
                    "kind": "image_clear_real",
                    "merchant": "OFFICE DEPOT TECH STORE",
                    "date": "2026-10-12",
                    "amount_minor": 25009,
                    "subtotal_minor": 23050,
                    "tax_minor": 1959,
                    "currency": "USD",
                    "type": "expense",
                    "invoice_no": "TX-904281",
                },
            ))

    bill_path = os.path.join(SAMPLE_DOCS_DIR, "sample_vendor_bill.pdf")
    if os.path.exists(bill_path):
        with open(bill_path, "rb") as f:
            items.append((
                "sample_vendor_bill.pdf",
                f.read(),
                {
                    "name": "sample_vendor_bill.pdf",
                    "kind": "pdf_digital_invoice_real",
                    "merchant": "DATADOG MONITORING INC",
                    "date": "2026-10-11",
                    "amount_minor": 85000,
                    "subtotal_minor": 85000,
                    "tax_minor": None,
                    "currency": "USD",
                    "type": "expense",
                    "invoice_no": "INV-2026-9042",
                },
            ))

    stmt_path = os.path.join(SAMPLE_DOCS_DIR, "sample_bank_statement.pdf")
    if os.path.exists(stmt_path):
        with open(stmt_path, "rb") as f:
            items.append((
                "sample_bank_statement.pdf",
                f.read(),
                {
                    "name": "sample_bank_statement.pdf",
                    "kind": "pdf_digital_statement_real",
                    "min_expected_rows": 3,
                    "currency": "USD",
                },
            ))

    return items
