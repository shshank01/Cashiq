from datetime import datetime, timezone
from typing import List, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, desc

from app.models.payable import Payable

class PayableService:
    @staticmethod
    async def get_all(db: AsyncSession, workspace_id: str) -> Dict[str, Any]:
        now = datetime.now(timezone.utc)
        res = await db.execute(
            select(Payable).where(Payable.workspace_id == workspace_id).order_by(Payable.due_date.asc())
        )
        payables = res.scalars().all()

        total_minor = 0
        upcoming_minor = 0
        overdue_minor = 0
        items = []

        for p in payables:
            remaining = p.amount_minor - p.amount_paid_minor
            p_due = p.due_date if p.due_date.tzinfo else p.due_date.replace(tzinfo=timezone.utc)
            
            # Determine dynamic status based on due date
            status = p.status
            if status != "paid":
                if p_due < now:
                    status = "overdue"
                else:
                    status = "pending"
                    
            if status != "paid":
                total_minor += remaining
                if status == "overdue":
                    overdue_minor += remaining
                else:
                    upcoming_minor += remaining

            items.append({
                "id": p.id,
                "vendor": p.vendor,
                "description": p.description,
                "amount_minor": p.amount_minor,
                "amount_paid_minor": p.amount_paid_minor,
                "currency": p.currency,
                "due_date": p.due_date.strftime("%Y-%m-%d"),
                "status": status,
                "created_at": p.created_at.isoformat()
            })

        return {
            "payables": items,
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

        payable = Payable(
            workspace_id=workspace_id,
            vendor=data["vendor"],
            description=data.get("description"),
            amount_minor=abs(int(data.get("amount_minor", 0))),
            currency=data.get("currency", "USD"),
            due_date=due_dt,
            status=data.get("status", "pending")
        )
        db.add(payable)
        await db.commit()
        await db.refresh(payable)
        return {
            "id": payable.id,
            "vendor": payable.vendor,
            "description": payable.description,
            "amount_minor": payable.amount_minor,
            "currency": payable.currency,
            "due_date": payable.due_date.strftime("%Y-%m-%d"),
            "status": payable.status
        }
