from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime, timedelta, timezone
from app.database import get_db
from app.auth.dependencies import verify_workspace_access
from app.models.transaction import Transaction

router = APIRouter(prefix="/workspaces/{wid}/reports", tags=["reports"])


@router.get("/income-expense")
async def income_expense_report(
    wid: str,
    months: int = Query(6, ge=1, le=24),
    ctx: dict = Depends(verify_workspace_access),
    db: AsyncSession = Depends(get_db),
):
    now = datetime.now(timezone.utc)
    data = []
    for i in range(months, 0, -1):
        month_start = now - timedelta(days=i * 30)
        month_end = now - timedelta(days=(i - 1) * 30)

        inc = await db.execute(
            select(func.coalesce(func.sum(Transaction.amount_minor), 0))
            .where(Transaction.workspace_id == wid, Transaction.transaction_type == "income",
                   Transaction.date >= month_start, Transaction.date < month_end)
        )
        exp = await db.execute(
            select(func.coalesce(func.sum(func.abs(Transaction.amount_minor)), 0))
            .where(Transaction.workspace_id == wid, Transaction.transaction_type == "expense",
                   Transaction.date >= month_start, Transaction.date < month_end)
        )
        data.append({
            "month": month_start.strftime("%Y-%m"),
            "income_minor": inc.scalar() or 0,
            "expenses_minor": exp.scalar() or 0,
        })

    return {"data": data}


@router.get("/category-spend")
async def category_spend_report(
    wid: str,
    months: int = Query(3, ge=1, le=12),
    ctx: dict = Depends(verify_workspace_access),
    db: AsyncSession = Depends(get_db),
):
    cutoff = datetime.now(timezone.utc) - timedelta(days=months * 30)
    result = await db.execute(
        select(
            Transaction.category_name,
            func.sum(func.abs(Transaction.amount_minor)).label("total"),
            func.count().label("count"),
        )
        .where(Transaction.workspace_id == wid, Transaction.transaction_type == "expense", Transaction.date >= cutoff)
        .group_by(Transaction.category_name)
        .order_by(func.sum(func.abs(Transaction.amount_minor)).desc())
    )
    rows = result.all()
    grand_total = sum(r.total for r in rows) if rows else 1

    return {
        "data": [
            {
                "category": r.category_name or "Uncategorized",
                "amount_minor": r.total,
                "transaction_count": r.count,
                "percentage": round(r.total / grand_total * 100, 1),
            }
            for r in rows
        ]
    }


@router.get("/cash-flow")
async def cash_flow_report(
    wid: str,
    months: int = Query(6, ge=1, le=24),
    ctx: dict = Depends(verify_workspace_access),
    db: AsyncSession = Depends(get_db),
):
    now = datetime.now(timezone.utc)
    data = []
    for i in range(months, 0, -1):
        month_start = now - timedelta(days=i * 30)
        month_end = now - timedelta(days=(i - 1) * 30)

        inc = await db.execute(
            select(func.coalesce(func.sum(Transaction.amount_minor), 0))
            .where(Transaction.workspace_id == wid, Transaction.transaction_type == "income",
                   Transaction.date >= month_start, Transaction.date < month_end)
        )
        exp = await db.execute(
            select(func.coalesce(func.sum(func.abs(Transaction.amount_minor)), 0))
            .where(Transaction.workspace_id == wid, Transaction.transaction_type == "expense",
                   Transaction.date >= month_start, Transaction.date < month_end)
        )
        inc_val = inc.scalar() or 0
        exp_val = exp.scalar() or 0
        data.append({
            "month": month_start.strftime("%Y-%m"),
            "income_minor": inc_val,
            "expenses_minor": exp_val,
            "net_minor": inc_val - exp_val,
        })

    return {"data": data}
