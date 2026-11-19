from fastapi import APIRouter, Depends
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.auth.dependencies import verify_workspace_access
from app.models.category import Category
from app.models.transaction import Transaction
from datetime import datetime, timedelta, timezone

router = APIRouter(prefix="/workspaces/{wid}/categories", tags=["categories"])


@router.get("")
async def list_categories(
    wid: str,
    ctx: dict = Depends(verify_workspace_access),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Category).where(Category.workspace_id == wid).order_by(Category.name)
    )
    categories = result.scalars().all()

    # Get spend totals for last 30 days
    thirty_days_ago = datetime.now(timezone.utc) - timedelta(days=30)
    spend_result = await db.execute(
        select(
            Transaction.category_name,
            func.sum(func.abs(Transaction.amount_minor)).label("total"),
        )
        .where(
            Transaction.workspace_id == wid,
            Transaction.transaction_type == "expense",
            Transaction.date >= thirty_days_ago,
        )
        .group_by(Transaction.category_name)
    )
    spend_map = {row.category_name: row.total for row in spend_result.all()}

    return [
        {
            "id": c.id,
            "name": c.name,
            "description": c.description,
            "spend_minor": spend_map.get(c.name, 0),
        }
        for c in categories
    ]
