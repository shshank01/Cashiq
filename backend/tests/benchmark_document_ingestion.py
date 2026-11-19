"""
Honest Side-by-Side Benchmark: Legacy CashIQ v2 Document Parser vs Upgraded v3 Pipeline.

Measures exact-match accuracy separately for:
- merchant (normalized substring / exact match)
- date (exact YYYY-MM-DD match)
- amount (exact minor-unit match)
- currency (exact ISO 4217 match)
- tax (exact tax_minor match where applicable)
- direction (exact expense/income match)
Plus:
- transaction-row extraction accuracy (on multi-row PDFs & CSVs)
- processing time (cold & cached)
- failure rate

Uses an exact snapshot of CashIQ's pre-upgrade v2 parser logic (WinOCR, v2 regexes,
v2 CSV sniffer, v2 PDF text-line regex) against the upgraded v3 parser on the exact
same representative corpus. Zero fabricated results.
"""

import asyncio
import csv
from datetime import datetime, timezone
import io
import json
import os
import re
import sys
import time
from typing import Any, Dict, List, Optional, Tuple

from PIL import Image, ImageEnhance, ImageOps

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.ml.document_parser import DocumentParser
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


# ---------------------------------------------------------------------------
# FAITHFUL SNAPSHOT OF LEGACY v2.0.0 DOCUMENT PARSER (PRE-UPGRADE BASELINE)
# ---------------------------------------------------------------------------
LEGACY_CURRENCY_MAP = {
    "$": "USD", "USD": "USD", "₹": "INR", "INR": "INR", "RS": "INR", "RS.": "INR",
    "RUPEES": "INR", "€": "EUR", "EUR": "EUR", "£": "GBP", "GBP": "GBP",
}
LEGACY_DATE_FORMATS = [
    "%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%d-%m-%Y", "%m-%d-%Y",
    "%Y/%m/%d", "%d.%m.%Y", "%d %b %Y", "%d %B %Y", "%b %d, %Y", "%B %d, %Y", "%d-%b-%Y", "%Y%m%d",
]


def _legacy_clean_amount(val: str) -> Tuple[Optional[float], Optional[str]]:
    if not val or not str(val).strip():
        return None, None
    s = str(val).strip()
    detected_curr = None
    for sym, curr in LEGACY_CURRENCY_MAP.items():
        if sym in s.upper():
            detected_curr = curr
            break
    cleaned = re.sub(r"[^\d\.\-\+]", "", s.replace(",", ""))
    try:
        return float(cleaned), detected_curr
    except ValueError:
        return None, detected_curr


def _legacy_parse_date(date_str: str) -> Optional[datetime]:
    if not date_str or not str(date_str).strip():
        return None
    s = str(date_str).strip()
    for fmt in LEGACY_DATE_FORMATS:
        try:
            return datetime.strptime(s, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            pass
    return None


class LegacyV2Parser:
    """Faithful reproduction of original CashIQ v2.0.0 parser for apples-to-apples benchmarking."""

    async def _winocr(self, img: Image.Image) -> Tuple[str, List[str]]:
        try:
            img = ImageOps.exif_transpose(img)
        except Exception:
            pass
        if img.mode != "RGB":
            img = img.convert("RGB")
        if img.width < 1000 and img.height < 1000:
            scale = 1200 / max(img.width, img.height)
            img = img.resize((int(img.width * scale), int(img.height * scale)), Image.Resampling.LANCZOS)

        text, lines = "", []
        try:
            import winocr
            res = await winocr.recognize_pil(img, "en")
            text = getattr(res, "text", "") or ""
            lines = [l.text.strip() for l in getattr(res, "lines", []) if getattr(l, "text", "").strip()]
            if len(text.strip()) < 25:
                enh = ImageEnhance.Contrast(img).enhance(1.8)
                res2 = await winocr.recognize_pil(enh, "en")
                t2 = getattr(res2, "text", "") or ""
                if len(t2) > len(text):
                    text = t2
                    lines = [l.text.strip() for l in getattr(res2, "lines", []) if getattr(l, "text", "").strip()]
            if len(text.strip()) < 20:
                for ang in (90, 270, 180):
                    r_img = img.rotate(ang, expand=True)
                    r_res = await winocr.recognize_pil(r_img, "en")
                    rt = getattr(r_res, "text", "") or ""
                    if len(rt.strip()) > 30:
                        text = rt
                        lines = [l.text.strip() for l in getattr(r_res, "lines", []) if getattr(l, "text", "").strip()]
                        break
        except Exception:
            pass
        return text, lines

    def _extract_img_fields(self, text: str, lines: List[str]) -> Dict[str, Any]:
        currency = "USD"
        for sym, curr in LEGACY_CURRENCY_MAP.items():
            if sym in text:
                currency = curr
                break

        merchant = "Receipt / Bill Vendor"
        for l in lines[:10]:
            cleaned = l.strip()
            if not cleaned or len(cleaned) < 3:
                continue
            if re.match(r"^(receipt|tax\s*invoice|invoice|bill|order|date|time|tel|gst|gstin|store\s*#)\b", cleaned, re.IGNORECASE):
                continue
            if re.match(r"^[\*\-=\._\s#]+$", cleaned):
                continue
            merchant = cleaned
            break

        amount_minor = 0
        for pat in [
            r"\b(?:total|grand\s*total|net\s*amount|amount\s*due|bal(?:ance)?\s*due|final\s*amount|total\s*payable|bill\s*amount|total\s*amount)\b",
            r"\b(?:balance|amount)\b",
        ]:
            if amount_minor > 0:
                break
            for l in reversed(lines):
                if re.search(pat, l, re.IGNORECASE) and not re.search(r"\b(?:sub\s*total|tax)\b", l, re.IGNORECASE):
                    nums = re.findall(r"[\d,]+(?:\.\d{1,2})?", l)
                    if nums:
                        try:
                            f = float(nums[-1].replace(",", ""))
                            if f > 0:
                                amount_minor = int(round(f * 100))
                                break
                        except ValueError:
                            pass

        tax_minor = None
        tm = re.search(r"(?:tax|sales\s*tax|gst|vat|cgst|sgst)\s*(?:\([^)]*\))?\s*[:=]?\s*(?:[\$\€\£\₹]|usd|inr)?\s*([\d,]+(?:\.\d{1,2})?)", text, re.IGNORECASE)
        if tm:
            try:
                tax_minor = int(round(float(tm.group(1).replace(",", "")) * 100))
            except ValueError:
                pass

        dm = re.search(r"(\d{4}[-/]\d{2}[-/]\d{2}|\d{2}[-/]\d{2}[-/]\d{4})", text)
        pdt = _legacy_parse_date(dm.group(1)) if dm else datetime.now(timezone.utc)

        return {
            "merchant": merchant,
            "date": pdt.isoformat() if pdt else None,
            "amount_minor": amount_minor,
            "tax_minor": tax_minor,
            "currency": currency,
            "type": "expense",
        }

    def _parse_csv(self, content: bytes) -> List[Dict[str, Any]]:
        text = content.decode("utf-8", errors="replace")
        sample = "\n".join(text.splitlines()[:15])
        try:
            delim = csv.Sniffer().sniff(sample, delimiters=",\t;|").delimiter
        except Exception:
            counts = {d: sample.count(d) for d in [",", "\t", ";", "|"]}
            delim = max(counts, key=counts.get)
            if counts[delim] == 0:
                delim = ","
        rows = [r for r in csv.reader(io.StringIO(text), delimiter=delim) if r and any(c.strip() for c in r)]
        if not rows:
            return []

        header_kw = {
            "date": ["date", "posted", "txn date"],
            "description": ["description", "narrative", "particulars", "narration"],
            "amount": ["amount", "total"],
            "debit": ["debit", "withdrawal", "dr"],
            "credit": ["credit", "deposit", "cr"],
            "type": ["type", "dr_cr"],
        }
        best_idx, best_score, best_map = 0, -1, {}
        for r_i, row in enumerate(rows[:15]):
            lc = [str(c).strip().lower() for c in row if c]
            m, sc = {}, 0
            for ci, cell in enumerate(lc):
                for role, syns in header_kw.items():
                    if role not in m and any(s in cell for s in syns):
                        m[role] = ci
                        sc += 2 if role in ("date", "amount", "description", "debit", "credit") else 1
                        break
            if sc > best_score and ("date" in m or "amount" in m or "debit" in m):
                best_score, best_idx, best_map = sc, r_i, m

        date_i = best_map.get("date", 0)
        desc_i = best_map.get("description", 1 if len(rows[0]) > 1 else 0)
        debit_i = best_map.get("debit", -1)
        credit_i = best_map.get("credit", -1)
        amt_i = best_map.get("amount", -1)
        if amt_i == -1 and debit_i == -1 and credit_i == -1:
            amt_i = 2 if len(rows[0]) > 2 else len(rows[0]) - 1

        drafts = []
        for row in rows[best_idx + 1:]:
            if len(row) <= max(date_i, desc_i):
                continue
            raw_d = row[date_i].strip() if date_i < len(row) else ""
            raw_desc = row[desc_i].strip() if desc_i < len(row) else ""
            amt_minor, ttype, curr = 0, "expense", "USD"
            if debit_i != -1 or credit_i != -1:
                dv, dc = _legacy_clean_amount(row[debit_i]) if (debit_i != -1 and debit_i < len(row)) else (None, None)
                cv, cc = _legacy_clean_amount(row[credit_i]) if (credit_i != -1 and credit_i < len(row)) else (None, None)
                if dv and abs(dv) > 0:
                    amt_minor, ttype, curr = int(round(abs(dv) * 100)), "expense", dc or "USD"
                elif cv and abs(cv) > 0:
                    amt_minor, ttype, curr = int(round(abs(cv) * 100)), "income", cc or "USD"
                else:
                    continue
            else:
                av, ac = _legacy_clean_amount(row[amt_i]) if amt_i < len(row) else (None, None)
                if not av:
                    continue
                amt_minor, curr = int(round(abs(av) * 100)), ac or "USD"
                ttype = "expense" if av < 0 else "income"
            pdt = _legacy_parse_date(raw_d) or datetime.now(timezone.utc)
            merch = raw_desc.split("/")[0] if "/" in raw_desc else (raw_desc.split()[0] if raw_desc.split() else "Transaction")
            drafts.append({
                "date": pdt.isoformat(),
                "merchant": merch,
                "description": raw_desc,
                "amount_minor": amt_minor,
                "currency": curr,
                "type": ttype,
            })
        return drafts

    async def parse_file(self, filename: str, content: bytes) -> List[Dict[str, Any]]:
        low = filename.lower()
        if low.endswith(".csv"):
            return self._parse_csv(content)
        if low.endswith(".pdf"):
            import pymupdf
            doc = pymupdf.open(stream=content, filetype="pdf")
            drafts = []
            for p_idx in range(len(doc)):
                page = doc[p_idx]
                txt = page.get_text()
                if len(txt.strip()) < 30:
                    pix = page.get_pixmap(dpi=200)
                    img = Image.open(io.BytesIO(pix.tobytes("png")))
                    ot, ol = await self._winocr(img)
                    ex = self._extract_img_fields(ot, ol)
                    if ex["amount_minor"] > 0:
                        drafts.append(ex)
                else:
                    # Legacy line regex
                    lp = re.compile(r"(\d{4}[-/]\d{2}[-/]\d{2}|\d{2}[-/]\d{2}[-/]\d{4})\s+([A-Za-z0-9\s\.\*\-\_\#\&]+?)\s+([\$\€\£\₹]?\s*[\d,]+\.\d{2})")
                    found = []
                    for line in txt.splitlines():
                        if any(k in line.lower() for k in ["ending balance", "opening balance"]):
                            continue
                        m = lp.search(line)
                        if m:
                            av, ac = _legacy_clean_amount(m.group(3))
                            if av:
                                pdt = _legacy_parse_date(m.group(1)) or datetime.now(timezone.utc)
                                found.append({
                                    "date": pdt.isoformat(),
                                    "merchant": m.group(2).strip().split()[0],
                                    "description": m.group(2).strip(),
                                    "amount_minor": int(round(abs(av) * 100)),
                                    "currency": ac or "USD",
                                    "type": "income" if any(w in line.lower() for w in ["cr", "credit", "deposit"]) else "expense",
                                })
                    if found:
                        drafts.extend(found)
                    else:
                        am = re.search(r"(?:total\s*amount\s*due|total\s*due|total)\s*[:=]?\s*[\$\€\£\₹]?\s*([\d,]+\.\d{2})", txt, re.IGNORECASE)
                        if am:
                            lines = [l.strip() for l in txt.splitlines() if l.strip()]
                            dm = re.search(r"(\d{4}[-/]\d{2}[-/]\d{2}|\d{2}[-/]\d{2}[-/]\d{4})", txt)
                            pdt = _legacy_parse_date(dm.group(1)) if dm else datetime.now(timezone.utc)
                            drafts.append({
                                "merchant": lines[0] if lines else "Vendor",
                                "date": pdt.isoformat(),
                                "amount_minor": int(round(float(am.group(1).replace(",", "")) * 100)),
                                "currency": "INR" if "₹" in txt or "INR" in txt else "USD",
                                "tax_minor": None,
                                "type": "expense",
                            })
            doc.close()
            return drafts

        img = Image.open(io.BytesIO(content))
        t, l = await self._winocr(img)
        return [self._extract_img_fields(t, l)]


def _merchant_matches(got: Optional[str], expected: str) -> bool:
    if not got:
        return False
    g = re.sub(r"[^a-z0-9\s]", "", got.lower()).strip()
    e = re.sub(r"[^a-z0-9\s]", "", expected.lower()).strip()
    if g == e or e in g or g in e:
        return True
    e_tokens = [w for w in e.split() if len(w) > 2]
    if not e_tokens:
        return False
    hits = sum(1 for w in e_tokens if w in g)
    return hits / len(e_tokens) >= 0.65


async def run_benchmark() -> Dict[str, Any]:
    # Build complete single-document + multi-row corpus
    single_doc_cases: List[Tuple[str, bytes, Dict[str, Any]]] = []
    multi_row_cases: List[Tuple[str, bytes, Dict[str, Any]]] = []

    for fname, content, gt in load_real_sample_documents():
        if gt["kind"] in {"image_clear_real", "pdf_digital_invoice_real"}:
            single_doc_cases.append((fname, content, gt))
        else:
            multi_row_cases.append((fname, content, gt))

    for builder in (
        make_indian_gst_receipt_image,
        make_blurry_receipt_image,
        make_rotated_photo_receipt,
        make_low_light_receipt,
        make_scanned_pdf,
    ):
        content, gt = builder()
        single_doc_cases.append((gt["name"], content, gt))

    for builder in (
        make_digital_indian_bank_pdf,
        make_mixed_pdf,
        make_indian_bank_csv,
        make_malformed_csv,
    ):
        content, gt = builder()
        multi_row_cases.append((gt["name"], content, gt))

    legacy = LegacyV2Parser()
    upgraded = DocumentParser()

    # Warm up singleton OCR model once so steady-state latency is measured fairly
    if single_doc_cases:
        await upgraded.parse_file_with_metadata(single_doc_cases[0][0], single_doc_cases[0][1], use_cache=False)

    results = {}
    for label, parser_fn in [
        ("legacy_v2", lambda fn, b: legacy.parse_file(fn, b)),
        ("upgraded_v3", lambda fn, b: upgraded.parse_file_with_metadata(fn, b, use_cache=False)),
    ]:
        field_hits = {k: 0 for k in ("merchant", "date", "amount", "currency", "tax", "direction")}
        field_totals = {k: 0 for k in ("merchant", "date", "amount", "currency", "tax", "direction")}
        failures = 0
        total_docs = len(single_doc_cases) + len(multi_row_cases)
        total_ms = 0.0
        per_doc_details = []

        # Single-document exact-match field evaluation
        for fname, content, gt in single_doc_cases:
            t0 = time.perf_counter()
            try:
                out = await parser_fn(fname, content)
                drafts = out["drafts"] if isinstance(out, dict) else out
                elapsed = (time.perf_counter() - t0) * 1000
                total_ms += elapsed
                if not drafts:
                    failures += 1
                    per_doc_details.append({"doc": fname, "status": "empty"})
                    continue
                d = drafts[0]
            except Exception as e:
                failures += 1
                total_ms += (time.perf_counter() - t0) * 1000
                per_doc_details.append({"doc": fname, "status": f"error: {e}"})
                continue

            checks = {}
            field_totals["merchant"] += 1
            checks["merchant"] = _merchant_matches(d.get("merchant"), gt["merchant"])
            field_hits["merchant"] += int(checks["merchant"])

            field_totals["date"] += 1
            checks["date"] = bool(d.get("date") and str(d["date"]).startswith(gt["date"]))
            field_hits["date"] += int(checks["date"])

            field_totals["amount"] += 1
            checks["amount"] = d.get("amount_minor") == gt["amount_minor"]
            field_hits["amount"] += int(checks["amount"])

            field_totals["currency"] += 1
            checks["currency"] = d.get("currency") == gt["currency"]
            field_hits["currency"] += int(checks["currency"])

            field_totals["direction"] += 1
            checks["direction"] = d.get("type") == gt["type"]
            field_hits["direction"] += int(checks["direction"])

            if gt.get("tax_minor") is not None:
                field_totals["tax"] += 1
                checks["tax"] = d.get("tax_minor") == gt["tax_minor"]
                field_hits["tax"] += int(checks["tax"])

            per_doc_details.append({
                "doc": fname,
                "ms": round(elapsed, 1),
                "checks": checks,
                "got_amount": d.get("amount_minor"),
                "exp_amount": gt["amount_minor"],
                "got_tax": d.get("tax_minor"),
                "exp_tax": gt.get("tax_minor"),
                "got_currency": d.get("currency"),
                "got_date": (d.get("date") or "")[:10],
            })

        # Multi-row extraction accuracy (bank statements PDF/CSV, mixed PDF, malformed CSV)
        expected_rows_total = 0
        matched_rows_total = 0
        for fname, content, gt in multi_row_cases:
            t0 = time.perf_counter()
            try:
                out = await parser_fn(fname, content)
                drafts = out["drafts"] if isinstance(out, dict) else out
                elapsed = (time.perf_counter() - t0) * 1000
                total_ms += elapsed
            except Exception as e:
                failures += 1
                total_ms += (time.perf_counter() - t0) * 1000
                per_doc_details.append({"doc": fname, "status": f"error: {e}"})
                continue

            if "expected_rows" in gt:
                exp_rows = gt["expected_rows"]
                expected_rows_total += len(exp_rows)
                hits = 0
                for exp in exp_rows:
                    match = any(
                        d.get("amount_minor") == exp["amount_minor"]
                        and d.get("type") == exp["type"]
                        and d.get("currency") == exp["currency"]
                        and str(d.get("date") or "").startswith(exp["date"])
                        for d in drafts
                    )
                    if match:
                        hits += 1
                # Penalize spurious extra footer/summary rows
                extra = max(0, len(drafts) - len(exp_rows))
                matched_rows_total += max(0, hits - extra)
                per_doc_details.append({"doc": fname, "ms": round(elapsed, 1), "rows_matched": f"{hits}/{len(exp_rows)}", "extra_rows": extra})
            elif gt["kind"] == "pdf_mixed":
                exp_n = gt["total_expected_transactions"]
                expected_rows_total += exp_n
                p1_hits = sum(
                    1 for exp in gt["page1_rows"]
                    if any(
                        d.get("amount_minor") == exp["amount_minor"]
                        and d.get("type") == exp["type"]
                        and d.get("currency") == exp["currency"]
                        for d in drafts
                    )
                )
                p2_hit = int(any(d.get("amount_minor") == gt["page2_invoice"]["amount_minor"] and d.get("currency") == "INR" for d in drafts))
                matched_rows_total += p1_hits + p2_hit
                per_doc_details.append({"doc": fname, "ms": round(elapsed, 1), "rows_matched": f"{p1_hits + p2_hit}/{exp_n}"})
            elif gt["kind"] == "csv_malformed":
                expected_rows_total += 2
                valid_hits = sum(
                    1 for amt, tp in [(1420000, "expense"), (15000000, "income")]
                    if any(d.get("amount_minor") == amt and d.get("type") == tp for d in drafts)
                )
                # Ensure footer summary "Total Debit" wasn't falsely imported as a transaction!
                footer_imported = any("summary" in (d.get("description") or "").lower() or "total debit" in (d.get("description") or "").lower() for d in drafts)
                matched_rows_total += max(0, valid_hits - int(footer_imported))
                per_doc_details.append({"doc": fname, "ms": round(elapsed, 1), "rows_matched": f"{valid_hits}/2", "footer_leaked": footer_imported})
            elif gt["kind"] == "pdf_digital_statement_real":
                expected_rows_total += gt["min_expected_rows"]
                matched_rows_total += min(gt["min_expected_rows"], len(drafts))
                per_doc_details.append({"doc": fname, "ms": round(elapsed, 1), "rows_extracted": len(drafts)})

        # Measure cached speed on upgraded_v3
        cached_ms = None
        if label == "upgraded_v3" and single_doc_cases:
            await upgraded.parse_file_with_metadata(single_doc_cases[0][0], single_doc_cases[0][1], use_cache=True)
            tc0 = time.perf_counter()
            c_res = await upgraded.parse_file_with_metadata(single_doc_cases[0][0], single_doc_cases[0][1], use_cache=True)
            cached_ms = round((time.perf_counter() - tc0) * 1000, 3) if c_res["cache_hit"] else None

        acc = {
            k: round((field_hits[k] / field_totals[k]) * 100.0, 1) if field_totals[k] > 0 else 0.0
            for k in field_hits
        }
        results[label] = {
            "field_accuracy_pct": acc,
            "field_counts": {k: f"{field_hits[k]}/{field_totals[k]}" for k in field_hits},
            "row_extraction_accuracy_pct": round((matched_rows_total / max(1, expected_rows_total)) * 100.0, 1),
            "row_counts": f"{matched_rows_total}/{expected_rows_total}",
            "total_processing_ms": round(total_ms, 1),
            "avg_processing_ms": round(total_ms / max(1, total_docs), 1),
            "cached_lookup_ms": cached_ms,
            "failure_rate_pct": round((failures / max(1, total_docs)) * 100.0, 1),
            "details": per_doc_details,
        }

    return results


if __name__ == "__main__":
    report = asyncio.run(run_benchmark())
    print("\n" + "=" * 78)
    print("CASHIQ DOCUMENT INGESTION BENCHMARK: LEGACY v2 vs UPGRADED v3")
    print("=" * 78)
    for ver in ("legacy_v2", "upgraded_v3"):
        r = report[ver]
        print(f"\n[{ver.upper()}]")
        print(f"  Field Exact-Match Accuracy:")
        for field_name, pct in r["field_accuracy_pct"].items():
            print(f"    - {field_name:<12}: {pct:5.1f}% ({r['field_counts'][field_name]})")
        print(f"  Row Extraction Accuracy : {r['row_extraction_accuracy_pct']:5.1f}% ({r['row_counts']})")
        print(f"  Failure Rate            : {r['failure_rate_pct']:5.1f}%")
        print(f"  Total / Avg Time        : {r['total_processing_ms']} ms total / {r['avg_processing_ms']} ms per doc")
        if r["cached_lookup_ms"] is not None:
            print(f"  Cached Lookup Time      : {r['cached_lookup_ms']} ms")
        print("  Per-document breakdown:")
        for det in r["details"]:
            print("   ", det)

    out_path = os.path.join(os.path.dirname(__file__), "benchmark_report.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
    print(f"\nSaved full JSON report to: {out_path}")
