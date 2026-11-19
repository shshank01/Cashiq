"""
Component 1: Data Collector
Collects and standardizes transactions from manual entry, CSV, PDF, OCR,
and bank sync ingestion sources into unified ML transaction records.
"""

from datetime import datetime, timezone
from typing import List, Dict, Any, Optional
import re


class DataCollector:
    def __init__(self):
        self.supported_sources = {
            "manual", "csv", "csv_import", "pdf", "pdf_statement",
            "pdf_statement_table", "pdf_invoice", "scanned_pdf_ocr",
            "receipt", "receipt_ocr", "bank_sync", "api",
        }

    def normalize_transaction_record(
        self,
        raw_data: Dict[str, Any],
        workspace_id: str,
        default_currency: str = "USD"
    ) -> Dict[str, Any]:
        """
        Validates, cleans, and standardizes a single transaction record from any ingestion source.
        """
        desc = (raw_data.get("description") or "Transaction").strip()
        raw_merchant = raw_data.get("merchant")
        merchant = raw_merchant.strip() if isinstance(raw_merchant, str) and raw_merchant.strip() else None

        # Amount normalization in minor units (integer cents/paise)
        raw_amt = raw_data.get("amount_minor", raw_data.get("amount", 0))
        try:
            amount_minor = abs(int(float(raw_amt)))
        except (ValueError, TypeError):
            amount_minor = 0

        # Transaction type: income vs expense
        ttype = str(raw_data.get("type", raw_data.get("transaction_type", "expense"))).lower().strip()
        if ttype not in {"income", "expense"}:
            ttype = "expense"

        # Currency
        currency = str(raw_data.get("currency", default_currency)).upper().strip()
        if len(currency) != 3:
            currency = default_currency

        # Source
        source = str(raw_data.get("source", "manual")).lower().strip()
        if source not in self.supported_sources:
            source = "manual"

        # Date normalization
        raw_date = raw_data.get("date")
        if isinstance(raw_date, datetime):
            tx_date = raw_date if raw_date.tzinfo else raw_date.replace(tzinfo=timezone.utc)
        elif isinstance(raw_date, str) and raw_date.strip():
            try:
                tx_date = datetime.fromisoformat(raw_date.replace("Z", "+00:00"))
            except Exception:
                try:
                    tx_date = datetime.strptime(raw_date.strip(), "%Y-%m-%d")
                    tx_date = tx_date.replace(tzinfo=timezone.utc)
                except Exception:
                    tx_date = datetime.now(timezone.utc)
        else:
            tx_date = datetime.now(timezone.utc)

        category_name = raw_data.get("category_name")
        if category_name and isinstance(category_name, str):
            category_name = category_name.strip()
        else:
            category_name = None

        return {
            "workspace_id": workspace_id,
            "description": desc,
            "merchant": merchant,
            "amount_minor": amount_minor,
            "currency": currency,
            "type": ttype,
            "date": tx_date,
            "source": source,
            "category_name": category_name,
            "account_id": raw_data.get("account_id"),
            "notes": raw_data.get("notes"),
            "is_anomaly": bool(raw_data.get("is_anomaly", False)),
            "anomaly_score": raw_data.get("anomaly_score"),
            "anomaly_reason": raw_data.get("anomaly_reason"),
        }

    def batch_collect(
        self,
        raw_records: List[Dict[str, Any]],
        workspace_id: str,
        default_currency: str = "USD"
    ) -> List[Dict[str, Any]]:
        """Collects and normalizes a batch of transactions for a specific workspace."""
        collected = []
        for rec in raw_records:
            try:
                norm = self.normalize_transaction_record(rec, workspace_id, default_currency)
                collected.append(norm)
            except Exception as e:
                print(f"[DataCollector] Skipped malformed record: {e}")
        return collected


data_collector = DataCollector()
