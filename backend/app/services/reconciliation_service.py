import csv
import io
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple
from dateutil import parser as date_parser
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, desc

from app.models.account import Account
from app.models.transaction import Transaction
from app.models.reconciliation import ReconciliationSession, ReconciliationItem
from app.services.audit_service import AuditService

def normalize_text(text: str) -> str:
    if not text:
        return ""
    cleaned = re.sub(r"[^a-zA-Z0-9\s]", " ", text.lower())
    return " ".join(cleaned.split())

def string_similarity(a: str, b: str) -> float:
    wa = set(normalize_text(a).split())
    wb = set(normalize_text(b).split())
    if not wa or not wb:
        return 0.0
    intersection = wa.intersection(wb)
    union = wa.union(wb)
    return len(intersection) / len(union)

def parse_amount_to_minor(val: Any) -> Optional[int]:
    if val is None or str(val).strip() == "":
        return None
    s = str(val).strip()
    is_negative = False
    if s.startswith("(") and s.endswith(")"):
        is_negative = True
        s = s[1:-1].strip()
    s = re.sub(r"[^0-9.\-+]", "", s)
    if not s or s in {"-", "+"}:
        return None
    try:
        f = float(s)
        if is_negative and f > 0:
            f = -f
        return int(round(f * 100))
    except ValueError:
        return None

def parse_date_safe(val: Any) -> Optional[datetime]:
    if not val or not str(val).strip():
        return None
    s = str(val).strip()
    try:
        dt = date_parser.parse(s, dayfirst=True)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        try:
            dt = date_parser.parse(s, dayfirst=False)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except Exception:
            return None


class ReconciliationService:
    """
    Automated Bank Statement Reconciliation Engine.
    Matches uploaded bank statement lines against internal ledger transactions,
    detects discrepancies (date/amount), duplicates, and unmatched records.
    """

    @staticmethod
    def parse_csv_statement(file_content: str) -> List[Dict[str, Any]]:
        rows = []
        reader = csv.reader(io.StringIO(file_content))
        header = None

        for row in reader:
            if not row or all(c.strip() == "" for c in row):
                continue
            if header is None:
                header = [c.strip().lower() for c in row]
                continue

            row_dict = {}
            for i, col in enumerate(row):
                if i < len(header):
                    row_dict[header[i]] = col.strip()
            rows.append(row_dict)

        if not header:
            return []

        # Detect columns
        date_col = next((c for c in header if any(k in c for k in ["date", "txn", "posting", "value"])), None)
        desc_col = next((c for c in header if any(k in c for k in ["desc", "narration", "particular", "memo", "detail", "payee"])), None)
        amt_col = next((c for c in header if any(k in c for k in ["amount", "txn amt", "net"])), None)
        debit_col = next((c for c in header if any(k in c for k in ["debit", "withdrawal", "dr"])), None)
        credit_col = next((c for c in header if any(k in c for k in ["credit", "deposit", "cr"])), None)
        ref_col = next((c for c in header if any(k in c for k in ["ref", "cheque", "utr", "chq", "reference"])), None)

        parsed_items = []
        for r in rows:
            dt = parse_date_safe(r.get(date_col, "")) if date_col else None
            if not dt:
                continue

            desc = r.get(desc_col, "") if desc_col else "Bank Statement Item"
            ref = r.get(ref_col, None) if ref_col else None

            amt_minor = None
            if debit_col and credit_col:
                d_minor = parse_amount_to_minor(r.get(debit_col))
                c_minor = parse_amount_to_minor(r.get(credit_col))
                if d_minor and d_minor > 0:
                    amt_minor = -abs(d_minor)
                elif c_minor and c_minor > 0:
                    amt_minor = abs(c_minor)
            elif amt_col:
                amt_minor = parse_amount_to_minor(r.get(amt_col))

            if amt_minor is None:
                continue

            parsed_items.append({
                "date": dt,
                "description": desc,
                "amount_minor": amt_minor,
                "reference": ref,
            })

        return parsed_items

    @staticmethod
    async def process_reconciliation(
        db: AsyncSession,
        workspace_id: str,
        filename: str,
        file_content: str,
        account_id: Optional[str] = None,
        user_id: Optional[str] = None
    ) -> Dict[str, Any]:
        statement_rows = ReconciliationService.parse_csv_statement(file_content)
        if not statement_rows:
            raise ValueError("No valid bank statement transactions found in CSV. Please verify column headers.")

        # Find min and max dates
        dates = [r["date"] for r in statement_rows]
        min_date = min(dates) - timedelta(days=10)
        max_date = max(dates) + timedelta(days=10)

        # Fetch ledger transactions in window
        q = select(Transaction).where(
            Transaction.workspace_id == workspace_id,
            Transaction.date >= min_date,
            Transaction.date <= max_date
        )
        if account_id:
            q = q.where(Transaction.account_id == account_id)

        tx_res = await db.execute(q)
        ledger_txs = tx_res.scalars().all()

        # Build ledger lookup
        unmatched_ledger = {t.id: t for t in ledger_txs}
        used_ledger_ids = set()

        reconciliation_items = []
        exact_matches = 0
        probable_matches = 0
        difference_matches = 0
        duplicate_matches = 0

        # Match bank statement rows against ledger
        for bank_item in statement_rows:
            b_date = bank_item["date"]
            b_amt = bank_item["amount_minor"]  # negative for expense, positive for income
            b_desc = bank_item["description"]
            b_ref = bank_item["reference"]

            # Expected ledger type and amount
            expected_type = "expense" if b_amt < 0 else "income"
            expected_amount = abs(b_amt)

            best_match: Optional[Transaction] = None
            best_type = "unmatched_bank"
            best_score = 0.0
            discrepancy = None

            candidates = []
            for t_id, tx in unmatched_ledger.items():
                if tx.type != expected_type:
                    continue

                t_date = tx.date if tx.date.tzinfo else tx.date.replace(tzinfo=timezone.utc)
                date_diff_days = abs((t_date.date() - b_date.date()).days)
                amt_diff_minor = abs(tx.amount_minor - expected_amount)
                text_sim = string_similarity(b_desc, (tx.description or "") + " " + (tx.merchant or ""))

                candidates.append((tx, date_diff_days, amt_diff_minor, text_sim))

            # 1. Exact Match: same amount, date within 1 day, high similarity
            exact_cand = [
                c for c in candidates if c[2] == 0 and c[1] <= 1
            ]
            if exact_cand:
                # Pick highest text sim
                exact_cand.sort(key=lambda x: (x[3], -x[1]), reverse=True)
                match_tx, d_days, a_diff, sim = exact_cand[0]
                if match_tx.id in used_ledger_ids:
                    best_match = match_tx
                    best_type = "duplicate"
                    duplicate_matches += 1
                    discrepancy = {"reason": "Duplicate bank entry matching already reconciled transaction."}
                else:
                    best_match = match_tx
                    best_type = "exact"
                    exact_matches += 1
                    used_ledger_ids.add(match_tx.id)
            else:
                # 2. Probable Match: same amount, date within 3 days
                prob_cand = [c for c in candidates if c[2] == 0 and c[1] <= 3 and c[0].id not in used_ledger_ids]
                if prob_cand:
                    prob_cand.sort(key=lambda x: (x[3], -x[1]), reverse=True)
                    match_tx, d_days, a_diff, sim = prob_cand[0]
                    best_match = match_tx
                    best_type = "probable"
                    probable_matches += 1
                    used_ledger_ids.add(match_tx.id)
                    discrepancy = {"date_diff_days": d_days, "reason": f"Date shifted by {d_days} day(s)."}
                else:
                    # 3. Discrepancy Match: date within 2 days and amount difference < 5% or fee < $10/₹500
                    diff_cand = [
                        c for c in candidates
                        if c[1] <= 2 and c[2] <= max(1000, int(round(expected_amount * 0.05))) and c[0].id not in used_ledger_ids
                    ]
                    if diff_cand:
                        diff_cand.sort(key=lambda x: (x[3], -x[2]), reverse=True)
                        match_tx, d_days, a_diff, sim = diff_cand[0]
                        best_match = match_tx
                        best_type = "difference"
                        difference_matches += 1
                        used_ledger_ids.add(match_tx.id)
                        discrepancy = {
                            "date_diff_days": d_days,
                            "amount_diff_minor": a_diff,
                            "reason": f"Amount difference of ${(a_diff/100):,.2f} and date shifted by {d_days} day(s).",
                        }

            reconciliation_items.append({
                "statement_date": b_date,
                "statement_description": b_desc,
                "statement_amount_minor": b_amt,
                "statement_reference": b_ref,
                "transaction_id": best_match.id if best_match else None,
                "match_type": best_type,
                "status": "approved" if best_type == "exact" else "pending",
                "discrepancy_details": discrepancy,
            })

        # Remove used ledger entries from unmatched_ledger
        remaining_unmatched_ledger = [
            tx for tx_id, tx in unmatched_ledger.items() if tx_id not in used_ledger_ids
        ]

        total_rows = len(statement_rows)
        matched_total = exact_matches + probable_matches
        unmatched_bank_count = sum(1 for item in reconciliation_items if item["match_type"] == "unmatched_bank")
        match_rate = round((matched_total / total_rows) * 100.0, 1) if total_rows > 0 else 0.0

        # Save session to DB
        session = ReconciliationSession(
            workspace_id=workspace_id,
            account_id=account_id,
            filename=filename,
            total_statement_rows=total_rows,
            matched_count=matched_total,
            unmatched_bank_count=unmatched_bank_count,
            unmatched_ledger_count=len(remaining_unmatched_ledger),
            status="completed" if unmatched_bank_count == 0 and len(remaining_unmatched_ledger) == 0 else "in_review",
            summary={
                "exact_matches": exact_matches,
                "probable_matches": probable_matches,
                "difference_matches": difference_matches,
                "duplicate_matches": duplicate_matches,
                "match_rate_pct": match_rate,
            }
        )
        db.add(session)
        await db.flush()

        # Add items
        for it in reconciliation_items:
            db_item = ReconciliationItem(
                session_id=session.id,
                statement_date=it["statement_date"],
                statement_description=it["statement_description"],
                statement_amount_minor=it["statement_amount_minor"],
                statement_reference=it["statement_reference"],
                transaction_id=it["transaction_id"],
                match_type=it["match_type"],
                status=it["status"],
                discrepancy_details=it["discrepancy_details"],
            )
            db.add(db_item)

        await db.commit()
        await db.refresh(session)

        await AuditService.log_event(
            db,
            workspace_id=workspace_id,
            user_id=user_id,
            action="bank_statement_reconciliation",
            resource_type="reconciliation_session",
            resource_id=session.id,
            details={
                "filename": filename,
                "total_rows": total_rows,
                "match_rate_pct": match_rate,
                "matched_count": matched_total
            }
        )

        return {
            "session_id": session.id,
            "filename": filename,
            "total_statement_rows": total_rows,
            "matched_count": matched_total,
            "exact_matches": exact_matches,
            "probable_matches": probable_matches,
            "difference_matches": difference_matches,
            "duplicate_matches": duplicate_matches,
            "unmatched_bank_count": unmatched_bank_count,
            "unmatched_ledger_count": len(remaining_unmatched_ledger),
            "match_rate_pct": match_rate,
            "status": session.status,
            "items_preview": [
                {
                    "date": it["statement_date"].strftime("%Y-%m-%d"),
                    "description": it["statement_description"],
                    "amount_minor": it["statement_amount_minor"],
                    "match_type": it["match_type"],
                    "status": it["status"],
                    "discrepancy": it["discrepancy_details"],
                }
                for it in reconciliation_items[:20]
            ],
            "unmatched_ledger_preview": [
                {
                    "id": t.id,
                    "date": t.date.strftime("%Y-%m-%d"),
                    "description": t.description or t.merchant,
                    "amount_minor": t.amount_minor,
                    "type": t.type,
                }
                for t in remaining_unmatched_ledger[:10]
            ]
        }

    @staticmethod
    async def get_session(db: AsyncSession, workspace_id: str, session_id: str) -> Optional[Dict[str, Any]]:
        s_res = await db.execute(
            select(ReconciliationSession).where(
                ReconciliationSession.id == session_id,
                ReconciliationSession.workspace_id == workspace_id
            )
        )
        session = s_res.scalar_one_or_none()
        if not session:
            return None

        items_res = await db.execute(
            select(ReconciliationItem).where(ReconciliationItem.session_id == session.id).order_by(ReconciliationItem.statement_date.asc())
        )
        items = items_res.scalars().all()

        return {
            "id": session.id,
            "workspace_id": session.workspace_id,
            "filename": session.filename,
            "total_statement_rows": session.total_statement_rows,
            "matched_count": session.matched_count,
            "unmatched_bank_count": session.unmatched_bank_count,
            "unmatched_ledger_count": session.unmatched_ledger_count,
            "status": session.status,
            "summary": session.summary,
            "created_at": session.created_at.isoformat(),
            "items": [
                {
                    "id": it.id,
                    "date": it.statement_date.strftime("%Y-%m-%d"),
                    "description": it.statement_description,
                    "amount_minor": it.statement_amount_minor,
                    "reference": it.statement_reference,
                    "transaction_id": it.transaction_id,
                    "match_type": it.match_type,
                    "status": it.status,
                    "discrepancy_details": it.discrepancy_details,
                }
                for it in items
            ]
        }

    @staticmethod
    async def list_sessions(db: AsyncSession, workspace_id: str) -> List[Dict[str, Any]]:
        result = await db.execute(
            select(ReconciliationSession)
            .where(ReconciliationSession.workspace_id == workspace_id)
            .order_by(desc(ReconciliationSession.created_at))
        )
        sessions = result.scalars().all()
        return [
            {
                "id": s.id,
                "filename": s.filename,
                "total_statement_rows": s.total_statement_rows,
                "matched_count": s.matched_count,
                "unmatched_bank_count": s.unmatched_bank_count,
                "unmatched_ledger_count": s.unmatched_ledger_count,
                "status": s.status,
                "summary": s.summary,
                "created_at": s.created_at.isoformat(),
            }
            for s in sessions
        ]

    @staticmethod
    async def approve_match(db: AsyncSession, workspace_id: str, session_id: str, item_id: str) -> bool:
        res = await db.execute(
            select(ReconciliationItem)
            .join(ReconciliationSession)
            .where(
                ReconciliationItem.id == item_id,
                ReconciliationItem.session_id == session_id,
                ReconciliationSession.workspace_id == workspace_id
            )
        )
        item = res.scalar_one_or_none()
        if not item:
            return False

        item.status = "approved"
        await db.commit()
        return True

    @staticmethod
    async def import_unmatched_to_ledger(
        db: AsyncSession,
        workspace_id: str,
        session_id: str,
        item_ids: List[str],
        user_id: Optional[str] = None
    ) -> int:
        res = await db.execute(
            select(ReconciliationItem)
            .join(ReconciliationSession)
            .where(
                ReconciliationItem.session_id == session_id,
                ReconciliationSession.workspace_id == workspace_id,
                ReconciliationItem.id.in_(item_ids),
                ReconciliationItem.match_type == "unmatched_bank"
            )
        )
        items = res.scalars().all()
        imported_count = 0

        for it in items:
            tx_type = "expense" if it.statement_amount_minor < 0 else "income"
            amt_minor = abs(it.statement_amount_minor)

            new_tx = Transaction(
                workspace_id=workspace_id,
                amount_minor=amt_minor,
                currency="USD",
                type=tx_type,
                date=it.statement_date,
                description=it.statement_description,
                merchant=it.statement_description.split("-")[0].strip()[:100],
                source="bank_statement_reconciliation",
                category_name="Miscellaneous" if tx_type == "expense" else "Client Revenue",
                review_required=False,
                is_confirmed=True,
            )
            db.add(new_tx)
            await db.flush()

            it.transaction_id = new_tx.id
            it.match_type = "exact"
            it.status = "approved"
            imported_count += 1

        # Update session counts
        s_res = await db.execute(select(ReconciliationSession).where(ReconciliationSession.id == session_id))
        sess = s_res.scalar_one_or_none()
        if sess:
            sess.matched_count += imported_count
            sess.unmatched_bank_count = max(0, sess.unmatched_bank_count - imported_count)
            if sess.unmatched_bank_count == 0:
                sess.status = "reconciled"

        await db.commit()

        await AuditService.log_event(
            db,
            workspace_id=workspace_id,
            user_id=user_id,
            action="reconciliation_imported_unmatched",
            resource_type="reconciliation_session",
            resource_id=session_id,
            details={"imported_transactions_count": imported_count}
        )

        return imported_count
