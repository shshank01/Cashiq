from fastapi import APIRouter, Depends
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime, timedelta, timezone
from app.database import get_db
from app.auth.dependencies import verify_workspace_access
from app.models.insight import Insight
from app.models.transaction import Transaction
from app.models.payable import Payable
from app.models.receivable import Receivable
from app.models.recurring import RecurringRule
from app.models.account import Account
import uuid

router = APIRouter(prefix="/workspaces/{wid}/insights", tags=["insights"])


@router.get("")
async def list_insights(
    wid: str,
    ctx: dict = Depends(verify_workspace_access),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Insight)
        .where(Insight.workspace_id == wid)
        .order_by(Insight.created_at.desc())
        .limit(20)
    )
    insights = result.scalars().all()
    return {
        "insights": [
            {
                "id": i.id,
                "type": i.type,
                "title": i.title,
                "description": i.description,
                "severity": i.severity,
                "is_read": i.is_read,
                "created_at": i.created_at.isoformat(),
            }
            for i in insights
        ]
    }


@router.post("/generate")
async def generate_insights(
    wid: str,
    ctx: dict = Depends(verify_workspace_access),
    db: AsyncSession = Depends(get_db),
):
    now = datetime.now(timezone.utc)
    thirty_days_ago = now - timedelta(days=30)
    sixty_days_ago = now - timedelta(days=60)
    generated = []

    # Delete old insights before generating new ones
    old = await db.execute(select(Insight).where(Insight.workspace_id == wid))
    for insight in old.scalars().all():
        await db.delete(insight)

    # 1. Compare this month vs last month expenses
    this_month_exp = await db.execute(
        select(func.coalesce(func.sum(func.abs(Transaction.amount_minor)), 0))
        .where(Transaction.workspace_id == wid, Transaction.transaction_type == "expense", Transaction.date >= thirty_days_ago)
    )
    last_month_exp = await db.execute(
        select(func.coalesce(func.sum(func.abs(Transaction.amount_minor)), 0))
        .where(Transaction.workspace_id == wid, Transaction.transaction_type == "expense",
               Transaction.date >= sixty_days_ago, Transaction.date < thirty_days_ago)
    )
    this_exp = this_month_exp.scalar() or 0
    last_exp = last_month_exp.scalar() or 0

    if last_exp > 0:
        change_pct = round((this_exp - last_exp) / last_exp * 100, 1)
        if abs(change_pct) >= 5:
            direction = "increased" if change_pct > 0 else "decreased"
            severity = "warning" if change_pct > 15 else "info"
            ins = Insight(
                id=str(uuid.uuid4()), workspace_id=wid,
                type="expense_change",
                title=f"Expenses {direction} {abs(change_pct)}%",
                description=f"Your expenses {direction} by {abs(change_pct)}% compared with the previous month.",
                severity=severity,
            )
            db.add(ins)
            generated.append(ins)

    # 2. Largest expense category
    cat_result = await db.execute(
        select(Transaction.category_name, func.sum(func.abs(Transaction.amount_minor)).label("total"))
        .where(Transaction.workspace_id == wid, Transaction.transaction_type == "expense", Transaction.date >= thirty_days_ago)
        .group_by(Transaction.category_name)
        .order_by(func.sum(func.abs(Transaction.amount_minor)).desc())
        .limit(1)
    )
    top_cat = cat_result.first()
    if top_cat and top_cat.category_name:
        ins = Insight(
            id=str(uuid.uuid4()), workspace_id=wid,
            type="largest_category",
            title=f"{top_cat.category_name} is your largest expense",
            description=f"{top_cat.category_name} is your largest expense category this month.",
            severity="info",
        )
        db.add(ins)
        generated.append(ins)

    # 3. Upcoming recurring payments
    upcoming = await db.execute(
        select(func.count()).select_from(RecurringRule)
        .where(RecurringRule.workspace_id == wid, RecurringRule.status == "active",
               RecurringRule.next_date <= now + timedelta(days=7))
    )
    upcoming_count = upcoming.scalar() or 0
    if upcoming_count > 0:
        ins = Insight(
            id=str(uuid.uuid4()), workspace_id=wid,
            type="recurring_alert",
            title=f"{upcoming_count} recurring payment{'s' if upcoming_count > 1 else ''} due this week",
            description=f"You have {upcoming_count} recurring payment{'s' if upcoming_count > 1 else ''} due in the next 7 days.",
            severity="info",
        )
        db.add(ins)
        generated.append(ins)

    # 4. Overdue payables
    overdue_pay = await db.execute(
        select(func.count()).select_from(Payable)
        .where(Payable.workspace_id == wid, Payable.status != "paid", Payable.due_date < now)
    )
    overdue_count = overdue_pay.scalar() or 0
    if overdue_count > 0:
        ins = Insight(
            id=str(uuid.uuid4()), workspace_id=wid,
            type="overdue_payables",
            title=f"{overdue_count} overdue payable{'s' if overdue_count > 1 else ''}",
            description=f"You have {overdue_count} overdue payment{'s' if overdue_count > 1 else ''} that need attention.",
            severity="warning",
        )
        db.add(ins)
        generated.append(ins)

    # 5. Cash flow direction
    this_month_inc = await db.execute(
        select(func.coalesce(func.sum(Transaction.amount_minor), 0))
        .where(Transaction.workspace_id == wid, Transaction.transaction_type == "income", Transaction.date >= thirty_days_ago)
    )
    this_inc = this_month_inc.scalar() or 0
    if this_exp > this_inc and this_exp > 0:
        ins = Insight(
            id=str(uuid.uuid4()), workspace_id=wid,
            type="negative_cash_flow",
            title="Cash outflow exceeds inflow",
            description="Your expenses exceeded income this month. Review your spending.",
            severity="warning",
        )
        db.add(ins)
        generated.append(ins)

    # 6. Runway warning
    acct_result = await db.execute(
        select(func.coalesce(func.sum(Account.balance_minor), 0))
        .where(Account.workspace_id == wid, Account.is_active == True)
    )
    cash = acct_result.scalar() or 0
    monthly_burn = this_exp - this_inc
    if monthly_burn > 0 and cash > 0:
        runway = round(cash / monthly_burn, 1)
        if runway < 6:
            ins = Insight(
                id=str(uuid.uuid4()), workspace_id=wid,
                type="runway_warning",
                title=f"Runway is approximately {runway} months",
                description=f"At current burn rate, you have approximately {runway} months of runway remaining.",
                severity="critical" if runway < 3 else "warning",
            )
            db.add(ins)
            generated.append(ins)

    await db.commit()

    return {
        "insights": [
            {
                "id": i.id,
                "type": i.type,
                "title": i.title,
                "description": i.description,
                "severity": i.severity,
                "created_at": i.created_at.isoformat(),
            }
            for i in generated
        ],
        "count": len(generated),
    }
