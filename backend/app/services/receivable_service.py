from datetime import datetime, timezone
from typing import List, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, desc

from app.models.receivable import Receivable

class ReceivableService:
    @staticmethod
    async def get_all(db: AsyncSession, workspace_id: str) -> Dict[str, Any]:
        now = datetime.now(timezone.utc)
        res = await db.execute(
            select(Receivable).where(Receivable.workspace_id == workspace_id).order_by(Receivable.due_date.asc())
        )
        receivables = res.scalars().all()

        total_minor = 0
        upcoming_minor = 0
        overdue_minor = 0
        items = []

        for r in receivables:
            remaining = r.amount_minor - r.amount_received_minor
            r_due = r.due_date if r.due_date.tzinfo else r.due_date.replace(tzinfo=timezone.utc)

            status = r.status
            if status != "received":
                if r_due < now:
                    status = "overdue"
                else:
                    status = "pending"

            if status != "received":
                total_minor += remaining
                if status == "overdue":
                    overdue_minor += remaining
                else:
                    upcoming_minor += remaining

            items.append({
                "id": r.id,
                "client": r.client,
                "description": r.description,
                "amount_minor": r.amount_minor,
                "amount_received_minor": r.amount_received_minor,
                "currency": r.currency,
                "due_date": r.due_date.strftime("%Y-%m-%d"),
                "status": status,
                "created_at": r.created_at.isoformat()
            })

        return {
            "receivables": items,
            "summary": {
                "total_minor": total_minor,
                "upcoming_minor": upcoming_minor,
                "overdue_minor": overdue_minor,
                "count": len(items)
            }
        }

    @staticmethod
    async def create(db: AsyncSession, workspace_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
        due_str = data.get("due_date")
        if due_str:
            try:
                due_dt = datetime.fromisoformat(due_str)
            except Exception:
                due_dt = datetime.now(timezone.utc)
        else:
            due_dt = datetime.now(timezone.utc)

        receivable = Receivable(
            workspace_id=workspace_id,
            client=data["client"],
            description=data.get("description"),
            amount_minor=abs(int(data.get("amount_minor", 0))),
            currency=data.get("currency", "USD"),
            due_date=due_dt,
            status=data.get("status", "pending")
        )
        db.add(receivable)
        await db.commit()
        await db.refresh(receivable)
        return {
            "id": receivable.id,
            "client": receivable.client,
            "description": receivable.description,
            "amount_minor": receivable.amount_minor,
            "currency": receivable.currency,
            "due_date": receivable.due_date.strftime("%Y-%m-%d"),
            "status": receivable.status
        }
