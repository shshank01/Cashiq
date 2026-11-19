from fastapi import APIRouter, Depends
from sqlalchemy import select, func, case, and_
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime, timedelta, timezone
from app.database import get_db
from app.auth.dependencies import verify_workspace_access
from app.models.transaction import Transaction
from app.models.account import Account
from app.models.payable import Payable
from app.models.receivable import Receivable
from app.models.insight import Insight
from app.models.recurring import RecurringRule

router = APIRouter(prefix="/workspaces/{wid}/dashboard", tags=["dashboard"])


@router.get("")
async def get_dashboard(
    wid: str,
    ctx: dict = Depends(verify_workspace_access),
    db: AsyncSession = Depends(get_db),
):
    now = datetime.now(timezone.utc)
    thirty_days_ago = now - timedelta(days=30)
    six_months_ago = now - timedelta(days=180)

    # === KPIs ===
    # Current cash = sum of all account balances
    acct_result = await db.execute(
        select(func.coalesce(func.sum(Account.balance_minor), 0))
        .where(Account.workspace_id == wid, Account.is_active == True)
    )
    current_cash = acct_result.scalar() or 0

    # Income this month
    income_result = await db.execute(
        select(func.coalesce(func.sum(Transaction.amount_minor), 0))
        .where(
            Transaction.workspace_id == wid,
            Transaction.transaction_type == "income",
            Transaction.date >= thirty_days_ago,
        )
    )
    income_minor = income_result.scalar() or 0

    # Expenses this month
    expense_result = await db.execute(
        select(func.coalesce(func.sum(Transaction.amount_minor), 0))
        .where(
            Transaction.workspace_id == wid,
            Transaction.transaction_type == "expense",
            Transaction.date >= thirty_days_ago,
        )
    )
    expenses_minor = abs(expense_result.scalar() or 0)

    net_cash_flow = income_minor - expenses_minor

    # Runway: if burning cash, months of runway; else null
    monthly_burn = expenses_minor - income_minor
    runway_months = None
    if monthly_burn > 0 and current_cash > 0:
        runway_months = round(current_cash / monthly_burn, 1)

    # Total payables pending
    payables_result = await db.execute(
        select(func.coalesce(func.sum(Payable.amount_minor - Payable.amount_paid_minor), 0))
        .where(Payable.workspace_id == wid, Payable.status != "paid")
    )
    total_payables = payables_result.scalar() or 0

    # Total receivables pending
    receivables_result = await db.execute(
        select(func.coalesce(func.sum(Receivable.amount_minor - Receivable.amount_received_minor), 0))
        .where(Receivable.workspace_id == wid, Receivable.status != "received")
    )
    total_receivables = receivables_result.scalar() or 0

    # === Cash flow history (last 6 months, monthly) ===
    cash_flow_history = []
    for i in range(6, 0, -1):
        month_start = now - timedelta(days=i * 30)
        month_end = now - timedelta(days=(i - 1) * 30)

        inc = await db.execute(
            select(func.coalesce(func.sum(Transaction.amount_minor), 0))
            .where(
                Transaction.workspace_id == wid,
                Transaction.transaction_type == "income",
                Transaction.date >= month_start,
                Transaction.date < month_end,
            )
        )
        exp = await db.execute(
            select(func.coalesce(func.sum(Transaction.amount_minor), 0))
            .where(
                Transaction.workspace_id == wid,
                Transaction.transaction_type == "expense",
                Transaction.date >= month_start,
                Transaction.date < month_end,
            )
        )
        inc_val = inc.scalar() or 0
        exp_val = abs(exp.scalar() or 0)
        cash_flow_history.append({
            "date": month_start.strftime("%Y-%m"),
            "income_minor": inc_val,
            "expenses_minor": exp_val,
            "net_minor": inc_val - exp_val,
        })

    # === Spending by category ===
    cat_result = await db.execute(
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
        .order_by(func.sum(func.abs(Transaction.amount_minor)).desc())
        .limit(10)
    )
    categories = cat_result.all()
    total_spend = sum(c.total for c in categories) if categories else 1
    spending_by_category = [
        {
            "category": c.category_name or "Uncategorized",
            "amount_minor": c.total,
            "percentage": round(c.total / total_spend * 100, 1) if total_spend > 0 else 0,
        }
        for c in categories
    ]

    # === Recent insights ===
    insight_result = await db.execute(
        select(Insight)
        .where(Insight.workspace_id == wid)
        .order_by(Insight.created_at.desc())
        .limit(5)
    )
    recent_insights = [
        {
            "id": i.id,
            "type": i.type,
            "title": i.title,
            "description": i.description,
            "severity": i.severity,
            "created_at": i.created_at.isoformat(),
        }
        for i in insight_result.scalars().all()
    ]

    # === Upcoming recurring ===
    recurring_result = await db.execute(
        select(RecurringRule)
        .where(RecurringRule.workspace_id == wid, RecurringRule.status == "active")
        .order_by(RecurringRule.next_date.asc())
        .limit(5)
    )
    upcoming_recurring = [
        {
            "id": r.id,
            "merchant": r.merchant,
            "description": r.description,
            "amount_minor": r.amount_minor,
            "frequency": r.frequency,
            "next_date": r.next_date.isoformat() if r.next_date else None,
        }
        for r in recurring_result.scalars().all()
    ]

    # === Anomalous transactions ===
    anomaly_result = await db.execute(
        select(Transaction)
        .where(Transaction.workspace_id == wid, Transaction.is_anomaly == True)
        .order_by(Transaction.date.desc())
        .limit(5)
    )
    anomalous_transactions = [
        {
            "id": t.id,
            "date": t.date.isoformat(),
            "description": t.description,
            "merchant": t.merchant,
            "amount_minor": t.amount_minor,
            "anomaly_reason": t.anomaly_reason,
        }
        for t in anomaly_result.scalars().all()
    ]

    # === Upcoming payables ===
    payable_result = await db.execute(
        select(Payable)
        .where(Payable.workspace_id == wid, Payable.status != "paid")
        .order_by(Payable.due_date.asc())
        .limit(5)
    )
    upcoming_payables = [
        {
            "id": p.id,
            "vendor": p.vendor,
            "description": p.description,
            "amount_minor": p.amount_minor,
            "due_date": p.due_date.isoformat(),
            "status": p.status,
        }
        for p in payable_result.scalars().all()
    ]

    # === Upcoming receivables ===
    recv_result = await db.execute(
        select(Receivable)
        .where(Receivable.workspace_id == wid, Receivable.status != "received")
        .order_by(Receivable.due_date.asc())
        .limit(5)
    )
    upcoming_receivables = [
        {
            "id": r.id,
            "client": r.client,
            "description": r.description,
            "amount_minor": r.amount_minor,
            "due_date": r.due_date.isoformat(),
            "status": r.status,
        }
        for r in recv_result.scalars().all()
    ]

    return {
        "kpis": {
            "current_cash_minor": current_cash,
            "income_minor": income_minor,
            "expenses_minor": expenses_minor,
            "net_cash_flow_minor": net_cash_flow,
            "runway_months": runway_months,
            "total_payables_minor": total_payables,
            "total_receivables_minor": total_receivables,
        },
        "cash_flow_history": cash_flow_history,
        "income_vs_expenses": cash_flow_history,  # same data, different chart
        "spending_by_category": spending_by_category,
        "forecast_preview": [],  # populated by forecast generation
        "recent_insights": recent_insights,
        "upcoming_recurring": upcoming_recurring,
        "anomalous_transactions": anomalous_transactions,
        "upcoming_payables": upcoming_payables,
        "upcoming_receivables": upcoming_receivables,
    }
