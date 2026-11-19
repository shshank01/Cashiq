import json
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_, func, desc, asc

from app.models.transaction import Transaction
from app.models.account import Account
from app.models.workspace import Workspace
from app.ml.categorizer import categorizer_instance
from app.ml.anomaly_detector import anomaly_detector_instance
from app.ml.architecture.data_collector import data_collector
from app.ml.architecture.ground_truth import ground_truth_collector
from app.ml.architecture.orchestrator import ml_orchestrator


def _serialize_transaction(t: Transaction) -> Dict[str, Any]:
    parsed_expl: Optional[Dict[str, Any]] = None
    if t.anomaly_explanation:
        try:
            parsed_expl = json.loads(t.anomaly_explanation)
        except Exception:
            parsed_expl = None

    return {
        "id": t.id,
        "date": t.date.isoformat(),
        "amount_minor": t.amount_minor,
        "currency": t.currency,
        "description": t.description,
        "merchant": t.merchant,
        "category_name": t.category_name or "Miscellaneous",
        "type": t.type,
        "account_id": t.account_id,
        "notes": t.notes,
        "source": t.source,
        "confidence": t.confidence,
        "model_version": t.model_version,
        "review_required": t.review_required,
        "is_anomaly": t.is_anomaly,
        "anomaly_score": t.anomaly_score,
        "anomaly_severity": t.anomaly_severity,
        "anomaly_reason": t.anomaly_reason,
        "anomaly_explanation": t.anomaly_explanation,
        "anomaly_explanation_details": parsed_expl,
        "anomaly_alert_type": (parsed_expl or {}).get("alert_type"),
        "anomaly_confidence": (parsed_expl or {}).get("confidence"),
        "anomaly_feedback_status": t.anomaly_feedback_status,
        "created_at": t.created_at.isoformat()
    }


class TransactionService:
    @staticmethod
    async def get_transactions(
        db: AsyncSession,
        workspace_id: str,
        page: int = 1,
        per_page: int = 15,
        search: Optional[str] = None,
        category: Optional[str] = None,
        type_: Optional[str] = None,
        account_id: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        sort_by: str = "date",
        sort_order: str = "desc"
    ) -> Dict[str, Any]:
        query = select(Transaction).where(Transaction.workspace_id == workspace_id)

        if search and search.strip():
            term = f"%{search.strip()}%"
            query = query.where(
                or_(
                    Transaction.description.ilike(term),
                    Transaction.merchant.ilike(term),
                    Transaction.category_name.ilike(term),
                    Transaction.notes.ilike(term)
                )
            )

        if category and category.strip():
            query = query.where(Transaction.category_name == category.strip())

        if type_ and type_.strip():
            query = query.where(Transaction.type == type_.strip().lower())

        if account_id and account_id.strip():
            query = query.where(Transaction.account_id == account_id.strip())

        if start_date:
            try:
                s_dt = datetime.fromisoformat(start_date)
                query = query.where(Transaction.date >= s_dt)
            except Exception:
                pass

        if end_date:
            try:
                e_dt = datetime.fromisoformat(end_date)
                query = query.where(Transaction.date <= e_dt)
            except Exception:
                pass

        count_query = select(func.count()).select_from(query.subquery())
        total_count = (await db.execute(count_query)).scalar_one()

        sort_column = getattr(Transaction, sort_by, Transaction.date)
        if sort_order.lower() == "asc":
            query = query.order_by(asc(sort_column))
        else:
            query = query.order_by(desc(sort_column))

        offset = (page - 1) * per_page
        query = query.offset(offset).limit(per_page)

        result = await db.execute(query)
        items = result.scalars().all()

        total_pages = max(1, (total_count + per_page - 1) // per_page)
        serialized = [_serialize_transaction(t) for t in items]

        return {
            "transactions": serialized,
            "data": serialized,  # for frontend compatibility
            "total": total_count,
            "page": page,
            "per_page": per_page,
            "total_pages": total_pages
        }

    @staticmethod
    async def create_transaction(db: AsyncSession, workspace_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
        ws_res = await db.execute(select(Workspace).where(Workspace.id == workspace_id))
        ws = ws_res.scalar_one_or_none()
        default_currency = ws.currency if ws else "USD"

        normalized = data_collector.normalize_transaction_record(data, workspace_id, default_currency=default_currency)
        desc = normalized["description"]
        merchant = normalized["merchant"]
        amount_minor = normalized["amount_minor"]
        ttype = normalized["type"]
        currency = normalized["currency"]
        notes = normalized["notes"]
        account_id = normalized["account_id"]
        source = normalized["source"]
        tx_date = normalized["date"]

        # Load workspace business profile & learned behavioral profiles
        ctx = await ml_orchestrator.load_workspace_context(db, workspace_id)

        # Automatic ML Categorization if category is not explicitly provided
        category_name = normalized["category_name"]
        if not category_name or category_name == "Miscellaneous":
            classification = categorizer_instance.categorize(
                f"{merchant or ''} {desc}",
                workspace_id=workspace_id,
                merchant=merchant,
                workspace_merchant_map=ctx["workspace_merchant_map"],
            )
            category_name = classification["category"]
            confidence = classification["confidence"]
            model_ver = classification["model_version"]
            review_required = classification["review_required"]
            is_confirmed = False
        else:
            confidence = 1.0
            model_ver = "user_selected"
            review_required = False
            is_confirmed = True

        # Business-context-aware Anomaly Detection against workspace historical transactions
        hist_res = await db.execute(
            select(Transaction)
            .where(Transaction.workspace_id == workspace_id)
            .order_by(Transaction.date.desc())
            .limit(120)
        )
        history = hist_res.scalars().all()

        anomaly_analysis = anomaly_detector_instance.analyze_transaction(
            current_amount_minor=amount_minor,
            category=category_name,
            merchant=merchant,
            historical_transactions=history,
            date=tx_date,
            transaction_type=ttype,
            currency=currency,
            workspace_id=workspace_id,
            business_profile=ctx["business_profile"],
            description=desc,
            learned_profiles=ctx["learned_profiles"],
            workspace_currency=default_currency,
        )

        explanation_json = json.dumps(anomaly_analysis.get("explanation_details", {}))

        tx = Transaction(
            workspace_id=workspace_id,
            account_id=account_id,
            date=tx_date,
            amount_minor=amount_minor,
            currency=currency,
            description=desc,
            merchant=merchant,
            category_name=category_name,
            type=ttype,
            notes=notes,
            source=source,
            confidence=confidence,
            model_version=model_ver,
            review_required=review_required,
            is_confirmed=is_confirmed,
            is_anomaly=anomaly_analysis["is_anomaly"],
            anomaly_score=anomaly_analysis["anomaly_score"],
            anomaly_severity=anomaly_analysis["severity"],
            anomaly_reason=anomaly_analysis["reason"],
            anomaly_explanation=explanation_json,
            anomaly_feedback_status=None
        )
        db.add(tx)

        if account_id:
            acct_res = await db.execute(select(Account).where(Account.id == account_id, Account.workspace_id == workspace_id))
            acct = acct_res.scalar_one_or_none()
            if acct:
                if ttype == "income":
                    acct.balance_minor += amount_minor
                else:
                    acct.balance_minor -= amount_minor

        await db.commit()
        await db.refresh(tx)
        return _serialize_transaction(tx)

    @staticmethod
    async def update_transaction(db: AsyncSession, workspace_id: str, transaction_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
        res = await db.execute(
            select(Transaction).where(Transaction.id == transaction_id, Transaction.workspace_id == workspace_id)
        )
        tx = res.scalar_one_or_none()
        if not tx:
            raise Exception("Transaction not found")

        needs_recheck = False
        if "description" in data and data["description"] != tx.description:
            tx.description = data["description"]
            needs_recheck = True
        if "merchant" in data and data["merchant"] != tx.merchant:
            tx.merchant = data["merchant"]
            needs_recheck = True
        if "amount_minor" in data and abs(int(data["amount_minor"])) != tx.amount_minor:
            tx.amount_minor = abs(int(data["amount_minor"]))
            needs_recheck = True
        if "type" in data and data["type"].lower() != tx.type:
            tx.type = data["type"].lower()
            needs_recheck = True
        if "notes" in data:
            tx.notes = data["notes"]
        if "date" in data:
            try:
                tx.date = datetime.fromisoformat(data["date"])
                needs_recheck = True
            except Exception:
                pass

        if "category_name" in data and data["category_name"] != tx.category_name:
            tx.category_name = data["category_name"]
            tx.verified_label = data["category_name"]
            tx.verified_at = datetime.now(timezone.utc)
            tx.is_confirmed = True
            tx.review_required = False
            needs_recheck = True

        if needs_recheck and tx.anomaly_feedback_status != "legitimate":
            ctx = await ml_orchestrator.load_workspace_context(db, workspace_id)
            hist_res = await db.execute(
                select(Transaction)
                .where(Transaction.workspace_id == workspace_id, Transaction.id != tx.id)
                .order_by(Transaction.date.desc())
                .limit(120)
            )
            history = hist_res.scalars().all()
            anomaly_analysis = anomaly_detector_instance.analyze_transaction(
                current_amount_minor=tx.amount_minor,
                category=tx.category_name or "Miscellaneous",
                merchant=tx.merchant,
                historical_transactions=history,
                date=tx.date,
                transaction_type=tx.type,
                currency=tx.currency,
                feedback_status=tx.anomaly_feedback_status,
                workspace_id=workspace_id,
                business_profile=ctx["business_profile"],
                description=tx.description,
                learned_profiles=ctx["learned_profiles"],
            )
            tx.is_anomaly = anomaly_analysis["is_anomaly"]
            tx.anomaly_score = anomaly_analysis["anomaly_score"]
            tx.anomaly_severity = anomaly_analysis["severity"]
            tx.anomaly_reason = anomaly_analysis["reason"]
            tx.anomaly_explanation = json.dumps(anomaly_analysis.get("explanation_details", {}))

        await db.commit()
        await db.refresh(tx)
        return _serialize_transaction(tx)

    @staticmethod
    async def confirm_category(db: AsyncSession, workspace_id: str, transaction_id: str, confirmed_category: Optional[str] = None) -> Dict[str, Any]:
        """User confirms or overrides an ML suggested category. Stores verified label and adapts profiles."""
        res = await db.execute(
            select(Transaction).where(Transaction.id == transaction_id, Transaction.workspace_id == workspace_id)
        )
        tx = res.scalar_one_or_none()
        if not tx:
            raise Exception("Transaction not found")

        final_cat = confirmed_category or tx.category_name
        if confirmed_category:
            tx.category_name = confirmed_category
            tx.verified_label = confirmed_category
        else:
            tx.verified_label = tx.category_name

        await ground_truth_collector.record_category_confirmation(
            db=db,
            workspace_id=workspace_id,
            transaction_id=transaction_id,
            verified_category=final_cat
        )

        if tx.merchant and final_cat:
            categorizer_instance.register_merchant_override(workspace_id, tx.merchant, final_cat)

        return {
            "id": tx.id,
            "category_name": tx.category_name,
            "verified_label": tx.verified_label,
            "review_required": False
        }

    @staticmethod
    async def submit_anomaly_feedback(
        db: AsyncSession,
        workspace_id: str,
        transaction_id: str,
        feedback: str,
        notes: Optional[str] = None,
        confirmed_category: Optional[str] = None,
        user_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Submits user verification feedback on a detected anomaly
        ('legitimate', 'incorrect_category', 'genuine_anomaly', or legacy 'suspicious').
        Updates ground truth, adapts workspace behavioral baselines, and re-evaluates if needed.
        """
        return await ml_orchestrator.handle_anomaly_feedback(
            db=db,
            workspace_id=workspace_id,
            transaction_id=transaction_id,
            feedback=feedback,
            notes=notes,
            confirmed_category=confirmed_category,
            user_id=user_id
        )

    @staticmethod
    async def delete_transaction(db: AsyncSession, workspace_id: str, transaction_id: str) -> None:
        res = await db.execute(
            select(Transaction).where(Transaction.id == transaction_id, Transaction.workspace_id == workspace_id)
        )
        tx = res.scalar_one_or_none()
        if tx:
            await db.delete(tx)
            await db.commit()
