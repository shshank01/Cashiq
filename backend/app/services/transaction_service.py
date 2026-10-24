import uuid
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_, func, desc, asc

from app.models.transaction import Transaction
from app.models.account import Account
from app.models.category import Category
from app.ml.categorizer import categorizer_instance
from app.ml.anomaly_detector import anomaly_detector_instance

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

        # Total count
        count_query = select(func.count()).select_from(query.subquery())
        total_count = (await db.execute(count_query)).scalar_one()

        # Sorting
        sort_column = getattr(Transaction, sort_by, Transaction.date)
        if sort_order.lower() == "asc":
            query = query.order_by(asc(sort_column))
        else:
            query = query.order_by(desc(sort_column))

        # Pagination
        offset = (page - 1) * per_page
        query = query.offset(offset).limit(per_page)

        result = await db.execute(query)
        items = result.scalars().all()

        total_pages = max(1, (total_count + per_page - 1) // per_page)

        serialized = [
            {
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
                "created_at": t.created_at.isoformat()
            }
            for t in items
        ]

        return {
            "transactions": serialized,
            "data": serialized, # for frontend compatibility
            "total": total_count,
            "page": page,
            "per_page": per_page,
            "total_pages": total_pages
        }

    @staticmethod
    async def create_transaction(db: AsyncSession, workspace_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
        # Parse fields
        desc = (data.get("description") or "Manual Transaction").strip()
        raw_m = data.get("merchant")
        merchant = raw_m.strip() if isinstance(raw_m, str) and raw_m.strip() else None
        amount_minor = abs(int(data.get("amount_minor", 0)))
        ttype = data.get("type", "expense").lower()
        currency = data.get("currency", "USD")
        notes = data.get("notes")
        account_id = data.get("account_id")
        source = data.get("source", "manual")
        
        date_str = data.get("date")
        if date_str:
            try:
                tx_date = datetime.fromisoformat(date_str)
            except Exception:
                tx_date = datetime.now(timezone.utc)
        else:
            tx_date = datetime.now(timezone.utc)

        # Automatic ML Categorization if category is not explicitly verified
        category_name = data.get("category_name")
        if not category_name or category_name == "Miscellaneous":
            classification = categorizer_instance.categorize(f"{merchant or ''} {desc}")
            category_name = classification["category"]
            confidence = classification["confidence"]
            model_ver = classification["model_version"]
            review_required = classification["review_required"]
        else:
            confidence = 1.0
            model_ver = "user_selected"
            review_required = False

        # Anomaly Detection against workspace historical transactions
        hist_res = await db.execute(
            select(Transaction).where(Transaction.workspace_id == workspace_id).order_by(Transaction.date.desc()).limit(100)
        )
        history = hist_res.scalars().all()
        
        anomaly_analysis = anomaly_detector_instance.analyze_transaction(
            current_amount_minor=amount_minor,
            category=category_name,
            merchant=merchant,
            historical_transactions=history
        )

        # Create record
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
            is_anomaly=anomaly_analysis["is_anomaly"],
            anomaly_score=anomaly_analysis["anomaly_score"],
            anomaly_severity=anomaly_analysis["severity"],
            anomaly_reason=anomaly_analysis["reason"]
        )
        db.add(tx)

        # Update account balance if account is attached
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

        return {
            "id": tx.id,
            "date": tx.date.isoformat(),
            "amount_minor": tx.amount_minor,
            "currency": tx.currency,
            "description": tx.description,
            "merchant": tx.merchant,
            "category_name": tx.category_name,
            "type": tx.type,
            "account_id": tx.account_id,
            "notes": tx.notes,
            "source": tx.source,
            "confidence": tx.confidence,
            "model_version": tx.model_version,
            "review_required": tx.review_required,
            "is_anomaly": tx.is_anomaly,
            "anomaly_score": tx.anomaly_score,
            "anomaly_severity": tx.anomaly_severity,
            "anomaly_reason": tx.anomaly_reason,
            "created_at": tx.created_at.isoformat()
        }

    @staticmethod
    async def update_transaction(db: AsyncSession, workspace_id: str, transaction_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
        res = await db.execute(
            select(Transaction).where(Transaction.id == transaction_id, Transaction.workspace_id == workspace_id)
        )
        tx = res.scalar_one_or_none()
        if not tx:
            raise Exception("Transaction not found")

        if "description" in data: tx.description = data["description"]
        if "merchant" in data: tx.merchant = data["merchant"]
        if "amount_minor" in data: tx.amount_minor = abs(int(data["amount_minor"]))
        if "type" in data: tx.type = data["type"].lower()
        if "notes" in data: tx.notes = data["notes"]
        if "date" in data:
            try:
                tx.date = datetime.fromisoformat(data["date"])
            except Exception:
                pass
        
        # Category correction handling
        if "category_name" in data and data["category_name"] != tx.category_name:
            tx.category_name = data["category_name"]
            tx.verified_label = data["category_name"]
            tx.verified_at = datetime.now(timezone.utc)
            tx.review_required = False

        await db.commit()
        await db.refresh(tx)
        return {
            "id": tx.id,
            "date": tx.date.isoformat(),
            "amount_minor": tx.amount_minor,
            "currency": tx.currency,
            "description": tx.description,
            "merchant": tx.merchant,
            "category_name": tx.category_name,
            "type": tx.type,
            "account_id": tx.account_id,
            "notes": tx.notes,
            "source": tx.source,
            "confidence": tx.confidence,
            "model_version": tx.model_version,
            "review_required": tx.review_required,
            "is_anomaly": tx.is_anomaly,
            "created_at": tx.created_at.isoformat()
        }

    @staticmethod
    async def confirm_category(db: AsyncSession, workspace_id: str, transaction_id: str, confirmed_category: Optional[str] = None) -> Dict[str, Any]:
        """User confirms or overrides an ML suggested category. Stores verified label."""
        res = await db.execute(
            select(Transaction).where(Transaction.id == transaction_id, Transaction.workspace_id == workspace_id)
        )
        tx = res.scalar_one_or_none()
        if not tx:
            raise Exception("Transaction not found")

        if confirmed_category:
            tx.category_name = confirmed_category
            tx.verified_label = confirmed_category
        else:
            tx.verified_label = tx.category_name

        tx.verified_at = datetime.now(timezone.utc)
        tx.review_required = False
        tx.confidence = 1.0

        await db.commit()
        await db.refresh(tx)
        return {
            "id": tx.id,
            "category_name": tx.category_name,
            "verified_label": tx.verified_label,
            "review_required": False
        }

    @staticmethod
    async def delete_transaction(db: AsyncSession, workspace_id: str, transaction_id: str) -> None:
        res = await db.execute(
            select(Transaction).where(Transaction.id == transaction_id, Transaction.workspace_id == workspace_id)
        )
        tx = res.scalar_one_or_none()
        if tx:
            await db.delete(tx)
            await db.commit()
