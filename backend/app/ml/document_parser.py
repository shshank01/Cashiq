import io
import re
import csv
from datetime import datetime, timezone
from typing import List, Dict, Any
from app.ml.categorizer import categorizer_instance

class DocumentParser:
    """
    Ingests CSV statements, PDF bank statements, and receipt images.
    Extracts draft transactions with confidence scores and automated ML categorization.
    """

    def parse_csv(self, file_content: bytes) -> List[Dict[str, Any]]:
        text = file_content.decode("utf-8", errors="replace")
        reader = csv.reader(io.StringIO(text))
        rows = list(reader)
        if not rows:
            return []

        header = [c.strip().lower() for c in rows[0]]
        
        # Identify columns
        date_idx = -1
        desc_idx = -1
        amount_idx = -1
        merchant_idx = -1
        type_idx = -1

        for i, col in enumerate(header):
            if any(k in col for k in ["date", "time", "posted"]):
                date_idx = i
            elif any(k in col for k in ["description", "narrative", "details", "memo", "text", "particulars"]):
                desc_idx = i
            elif any(k in col for k in ["amount", "total", "net", "debit", "credit"]):
                amount_idx = i
            elif any(k in col for k in ["merchant", "payee", "vendor", "beneficiary"]):
                merchant_idx = i
            elif any(k in col for k in ["type", "dr_cr", "cr/dr"]):
                type_idx = i

        if date_idx == -1: date_idx = 0
        if desc_idx == -1: desc_idx = 1 if len(header) > 1 else 0
        if amount_idx == -1: amount_idx = 2 if len(header) > 2 else len(header) - 1

        drafts = []
        for r in rows[1:]:
            if not r or len(r) <= max(date_idx, desc_idx, amount_idx):
                continue
            
            raw_date = r[date_idx].strip()
            raw_desc = r[desc_idx].strip()
            raw_amt = r[amount_idx].strip()
            raw_merch = r[merchant_idx].strip() if merchant_idx != -1 and merchant_idx < len(r) else None

            # Parse amount
            clean_amt = re.sub(r'[^\d\.\-]', '', raw_amt)
            try:
                amt_float = float(clean_amt)
            except ValueError:
                continue

            amount_minor = int(round(abs(amt_float) * 100))
            is_expense = amt_float < 0 or (type_idx != -1 and "debit" in r[type_idx].lower()) or "withdrawal" in raw_desc.lower()
            ttype = "expense" if is_expense else "income"

            # Parse date
            parsed_date = None
            for fmt in ["%Y-%m-%d", "%m/%d/%Y", "%d/%m/%Y", "%d-%m-%Y", "%Y/%m/%d", "%d %b %Y"]:
                try:
                    parsed_date = datetime.strptime(raw_date, fmt).replace(tzinfo=timezone.utc)
                    break
                except ValueError:
                    pass
            if not parsed_date:
                parsed_date = datetime.now(timezone.utc)

            # ML categorization
            cat_result = categorizer_instance.categorize(raw_desc)

            drafts.append({
                "date": parsed_date.isoformat(),
                "description": raw_desc or "Transaction Import",
                "merchant": raw_merch or (raw_desc.split(" - ")[0] if " - " in raw_desc else None),
                "amount_minor": amount_minor,
                "currency": "USD",
                "type": ttype,
                "category_name": cat_result["category"],
                "confidence": cat_result["confidence"],
                "model_version": cat_result["model_version"],
                "review_required": cat_result["review_required"] or cat_result["confidence"] < 0.75,
                "source": "csv_import"
            })

        return drafts

    def parse_pdf(self, file_content: bytes) -> List[Dict[str, Any]]:
        """Parses bank statement PDFs via pdfplumber."""
        drafts = []
        try:
            import pdfplumber
            with pdfplumber.open(io.BytesIO(file_content)) as pdf:
                full_text = "\n".join(page.extract_text() or "" for page in pdf.pages)
        except Exception:
            full_text = file_content.decode("utf-8", errors="ignore")

        # Standard banking line item regex: YYYY-MM-DD or DD/MM/YYYY followed by description and amount
        line_pattern = re.compile(
            r'(\d{4}[-/]\d{2}[-/]\d{2}|\d{2}[-/]\d{2}[-/]\d{4})\s+([A-Za-z0-9\s\.\*\-\_\#]+?)\s+([\$\€\£\₹]?\s*[\d,]+\.\d{2})'
        )

        for line in full_text.splitlines():
            match = line_pattern.search(line)
            if match:
                date_str, desc, amt_str = match.groups()
                clean_amt = re.sub(r'[^\d\.]', '', amt_str)
                try:
                    amt_float = float(clean_amt)
                except ValueError:
                    continue

                amount_minor = int(round(amt_float * 100))
                is_expense = "cr" not in line.lower() and "deposit" not in desc.lower()
                ttype = "expense" if is_expense else "income"

                parsed_date = None
                for fmt in ["%Y-%m-%d", "%m/%d/%Y", "%d/%m/%Y"]:
                    try:
                        parsed_date = datetime.strptime(date_str, fmt).replace(tzinfo=timezone.utc)
                        break
                    except ValueError:
                        pass
                if not parsed_date:
                    parsed_date = datetime.now(timezone.utc)

                cat_result = categorizer_instance.categorize(desc.strip())

                drafts.append({
                    "date": parsed_date.isoformat(),
                    "description": desc.strip(),
                    "merchant": desc.strip().split()[0] if desc.strip() else "Bank Item",
                    "amount_minor": amount_minor,
                    "currency": "USD",
                    "type": ttype,
                    "category_name": cat_result["category"],
                    "confidence": cat_result["confidence"],
                    "model_version": cat_result["model_version"],
                    "review_required": True, # PDF extractions require confirmation
                    "source": "pdf_statement"
                })

        if not drafts:
            # Single bill / invoice PDF fallback
            amount_match = re.search(r'(?:total|amount due|amount|balance|grand total)\s*[:]?\s*[\$\€\£\₹]?\s*([\d,]+\.\d{2})', full_text, re.IGNORECASE)
            if not amount_match:
                amount_match = re.search(r'(?:usd|inr|\$)\s*[:]?\s*([\d,]+\.\d{2})', full_text, re.IGNORECASE)
            if not amount_match:
                amount_match = re.search(r'[\$\€\£\₹]\s*([\d,]+\.\d{2})', full_text)

            amount_minor = 0
            if amount_match:
                try:
                    amount_minor = int(round(float(amount_match.group(1).replace(",", "")) * 100))
                except ValueError:
                    amount_minor = 0

            lines = [l.strip() for l in full_text.splitlines() if l.strip()]
            merchant = "Invoice Merchant"
            for l in lines:
                cleaned = l.strip()
                if cleaned and not re.match(r'^(receipt|tax invoice|invoice|bill|statement|date|order)\b', cleaned, re.IGNORECASE):
                    merchant = cleaned
                    break

            date_match = re.search(r'(\d{4}[-/]\d{2}[-/]\d{2}|\d{2}[-/]\d{2}[-/]\d{4})', full_text)
            parsed_date = datetime.now(timezone.utc)
            if date_match:
                for fmt in ["%Y-%m-%d", "%m/%d/%Y", "%d/%m/%Y"]:
                    try:
                        parsed_date = datetime.strptime(date_match.group(1), fmt).replace(tzinfo=timezone.utc)
                        break
                    except ValueError:
                        pass

            if amount_minor > 0:
                cat_result = categorizer_instance.categorize(merchant)
                drafts.append({
                    "date": parsed_date.isoformat(),
                    "description": f"Invoice from {merchant}",
                    "merchant": merchant[:50],
                    "amount_minor": amount_minor,
                    "currency": "USD",
                    "type": "expense",
                    "category_name": cat_result["category"],
                    "confidence": cat_result["confidence"],
                    "model_version": cat_result["model_version"],
                    "review_required": True,
                    "source": "pdf_statement"
                })

        return drafts

    async def parse_receipt(self, file_content: bytes) -> List[Dict[str, Any]]:
        """Parses receipt images using OCR / regex heuristics."""
        text = ""
        lines = []
        try:
            from PIL import Image, ImageOps, ImageEnhance
            img = Image.open(io.BytesIO(file_content))
            # Auto-rotate based on EXIF camera orientation
            try:
                img = ImageOps.exif_transpose(img)
            except Exception:
                pass

            # Handle alpha channel (transparent PNGs/TIFFs) so they don't turn into black backgrounds
            if img.mode in ("RGBA", "LA", "P"):
                bg = Image.new("RGB", img.size, (255, 255, 255))
                if img.mode == "P":
                    img = img.convert("RGBA")
                if "A" in img.mode:
                    bg.paste(img, mask=img.split()[-1])
                else:
                    bg.paste(img)
                img = bg
            elif img.mode != "RGB":
                img = img.convert("RGB")

            # Try native Windows OCR (winocr)
            try:
                import winocr
                ocr_res = await winocr.recognize_pil(img, 'en')
                if hasattr(ocr_res, 'text') and ocr_res.text:
                    text = ocr_res.text
                elif isinstance(ocr_res, dict):
                    text = ocr_res.get('text', '')

                if hasattr(ocr_res, 'lines') and ocr_res.lines:
                    lines = [l.text.strip() for l in ocr_res.lines if hasattr(l, 'text') and l.text.strip()]
                elif isinstance(ocr_res, dict):
                    lines = [l.get('text', '').strip() for l in ocr_res.get('lines', []) if l.get('text', '').strip()]

                # If text is too short or low-contrast, try enhancing contrast
                if len(text.strip()) < 15:
                    enhancer = ImageEnhance.Contrast(img)
                    enhanced_img = enhancer.enhance(1.8)
                    ocr_res2 = await winocr.recognize_pil(enhanced_img, 'en')
                    txt2 = getattr(ocr_res2, 'text', '') if not isinstance(ocr_res2, dict) else ocr_res2.get('text', '')
                    if len(txt2) > len(text):
                        text = txt2
                        if hasattr(ocr_res2, 'lines'):
                            lines = [l.text.strip() for l in ocr_res2.lines if hasattr(l, 'text') and l.text.strip()]
            except Exception:
                pass

            # Fallback to pytesseract if available and winocr had empty results
            if not text.strip():
                try:
                    import pytesseract
                    text = pytesseract.image_to_string(img)
                    lines = [l.strip() for l in text.splitlines() if l.strip()]
                except Exception:
                    pass
        except Exception:
            text = file_content.decode("utf-8", errors="ignore")
            lines = [l.strip() for l in text.splitlines() if l.strip()]

        if not lines and text:
            lines = [l.strip() for l in text.splitlines() if l.strip()]

        # 1. Currency Detection
        currency = "USD"
        if re.search(r'(?:₹|INR|Rs\.?|Rupees|rupee)', text, re.IGNORECASE):
            currency = "INR"
        elif re.search(r'(?:€|EUR|euro)', text, re.IGNORECASE):
            currency = "EUR"
        elif re.search(r'(?:£|GBP|pound)', text, re.IGNORECASE):
            currency = "GBP"

        # 2. Extract Total Amount
        amount_minor = 0

        # Primary pass: Look for lines with 'total' or 'balance due' or 'net amount'
        for l in lines:
            if re.search(r'\b(?:total|grand\s*total|net\s*amount|amount\s*due|bal(?:ance)?\s*due|final\s*amount|total\s*payable|bill\s*amount)\b', l, re.IGNORECASE) and not re.search(r'\b(?:sub\s*total)\b', l, re.IGNORECASE):
                nums = re.findall(r'[\d,]+(?:\.\d{1,2})?', l)
                if nums:
                    clean_num = nums[-1].replace(',', '')
                    try:
                        f = float(clean_num)
                        if f > 0:
                            amount_minor = int(round(f * 100))
                            break
                    except ValueError:
                        pass

        # Secondary pass: regex patterns across full text
        if amount_minor == 0:
            patterns = [
                r'(?:total|amount due|amount|balance|grand total|net amount|total payable)\s*[:=]?\s*(?:[\$\€\£\₹\¥]|usd|inr|eur|gbp|rs\.?)?\s*([\d,]+(?:\.\d{1,2})?)',
                r'(?:[\$\€\£\₹\¥]|rs\.?|inr|usd)\s*[:=]?\s*([\d,]+\.\d{2})',
                r'(?:[\$\€\£\₹\¥]|rs\.?|inr|usd)\s*[:=]?\s*([\d,]+)',
                r'\b([\d,]+\.\d{2})\b'
            ]
            for pat in patterns:
                m = re.search(pat, text, re.IGNORECASE)
                if m:
                    clean_num = m.group(1).replace(',', '')
                    try:
                        f = float(clean_num)
                        if f > 0:
                            amount_minor = int(round(f * 100))
                            break
                    except ValueError:
                        pass

        # 3. Extract Merchant
        merchant = "Receipt Merchant"
        for l in lines:
            cleaned = l.strip()
            if not cleaned or len(cleaned) < 3:
                continue
            # Filter generic title lines
            if re.match(r'^(receipt|tax\s*invoice|invoice|bill|order|cash\s*receipt|sales\s*receipt|duplicate|customer\s*copy|merchant\s*copy|date|time|tel|ph|phone|gst|gstin|cin|pan|tin|store\s*#|terminal)\b', cleaned, re.IGNORECASE):
                continue
            if re.match(r'^[\*\-=\._\s#]+$', cleaned):
                continue
            if re.match(r'^(street|suite|road|rd\.|st\.|blvd|avenue|ave|california|san\s*francisco|ca\b|ny\b|delhi|mumbai|bangalore)', cleaned, re.IGNORECASE):
                continue
            if re.search(r'\b\d{5}(?:-\d{4})?\b', cleaned):
                continue

            # Strip welcome / greeting prefix if present
            cleaned = re.sub(r'^(?:welcome\s+to\s+|thanks?\s+for\s+visiting\s+|thank\s+you\s+for\s+shopping\s+at\s+)', '', cleaned, flags=re.IGNORECASE).strip(' *-=_#')
            if cleaned:
                merchant = cleaned
                break

        # 4. Extract Date
        date_match = re.search(r'(\d{4}[-/]\d{2}[-/]\d{2}|\d{2}[-/]\d{2}[-/]\d{4}|\d{1,2}[-\s](?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*[-\s]\d{2,4})', text, re.IGNORECASE)
        parsed_date = datetime.now(timezone.utc)
        if date_match:
            raw_d = date_match.group(1)
            try:
                from dateutil import parser as dt_parser
                parsed_date = dt_parser.parse(raw_d, fuzzy=True).replace(tzinfo=timezone.utc)
            except Exception:
                for fmt in ["%Y-%m-%d", "%m/%d/%Y", "%d/%m/%Y", "%d-%m-%Y"]:
                    try:
                        parsed_date = datetime.strptime(raw_d, fmt).replace(tzinfo=timezone.utc)
                        break
                    except ValueError:
                        pass

        description = f"Receipt from {merchant}"
        cat_result = categorizer_instance.categorize(f"{merchant} {description}")

        return [{
            "date": parsed_date.isoformat(),
            "description": description,
            "merchant": merchant[:50],
            "amount_minor": amount_minor,
            "currency": currency,
            "type": "expense",
            "category_name": cat_result["category"],
            "confidence": cat_result["confidence"],
            "model_version": cat_result["model_version"],
            "review_required": True,
            "source": "receipt_ocr"
        }]

document_parser_instance = DocumentParser()

