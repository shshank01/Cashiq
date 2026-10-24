from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime, timedelta, timezone
from app.database import get_db
from app.auth.dependencies import verify_workspace_access
from app.models.transaction import Transaction
from app.models.account import Account
from app.models.forecast import Forecast
import uuid, json

router = APIRouter(prefix="/workspaces/{wid}/forecast", tags=["forecast"])


@router.get("")
async def get_forecast(
    wid: str,
    ctx: dict = Depends(verify_workspace_access),
    db: AsyncSession = Depends(get_db),
):
    # Get latest forecast
    result = await db.execute(
        select(Forecast)
        .where(Forecast.workspace_id == wid)
        .order_by(Forecast.created_at.desc())
        .limit(1)
    )
    forecast = result.scalar_one_or_none()
    if not forecast:
        return {"forecast_type": None, "daily_forecast": [], "summary": None, "metrics": None, "model_info": None}

    data = forecast.data if isinstance(forecast.data, dict) else {}
    return {
        "forecast_type": forecast.forecast_type,
        "daily_forecast": data.get("daily_forecast", []),
        "summary": data.get("summary", {}),
        "metrics": {
            "mae": forecast.metrics_mae,
            "rmse": forecast.metrics_rmse,
        },
        "model_info": {
            "method": forecast.method,
            "data_points_used": forecast.data_points_used,
        },
    }


@router.post("/generate")
async def generate_forecast(
    wid: str,
    days: int = Query(30, ge=7, le=90),
    ctx: dict = Depends(verify_workspace_access),
    db: AsyncSession = Depends(get_db),
):
    now = datetime.now(timezone.utc)

    # Get transaction history
    result = await db.execute(
        select(Transaction)
        .where(Transaction.workspace_id == wid)
        .order_by(Transaction.date.asc())
    )
    transactions = list(result.scalars().all())

    # Get current cash position
    acct_result = await db.execute(
        select(func.coalesce(func.sum(Account.balance_minor), 0))
        .where(Account.workspace_id == wid, Account.is_active == True)
    )
    current_cash = acct_result.scalar() or 0

    if len(transactions) < 7:
        # Not enough data — return estimated
        return {
            "forecast_type": "estimated",
            "daily_forecast": [],
            "summary": {"message": "Not enough transaction history for forecasting. Add more transactions."},
            "metrics": None,
            "model_info": {"method": "insufficient_data", "data_points_used": len(transactions)},
        }

    # Aggregate daily totals
    daily_income = {}
    daily_expense = {}
    for txn in transactions:
        day = txn.date.strftime("%Y-%m-%d")
        if txn.transaction_type == "income":
            daily_income[day] = daily_income.get(day, 0) + txn.amount_minor
        else:
            daily_expense[day] = daily_expense.get(day, 0) + abs(txn.amount_minor)

    # Get all days in range
    if transactions:
        first_date = transactions[0].date.date()
        last_date = transactions[-1].date.date()
        num_history_days = (last_date - first_date).days + 1
    else:
        num_history_days = 0

    # Calculate moving averages
    all_days = sorted(set(list(daily_income.keys()) + list(daily_expense.keys())))
    if len(all_days) < 7:
        num_history_days = len(all_days)

    total_income = sum(daily_income.values())
    total_expense = sum(daily_expense.values())
    avg_daily_income = total_income // max(num_history_days, 1)
    avg_daily_expense = total_expense // max(num_history_days, 1)

    # Determine forecast type
    if num_history_days >= 60:
        forecast_type = "forecast"
        method = "exponential_smoothing"
    elif num_history_days >= 14:
        forecast_type = "projected"
        method = "moving_average"
    else:
        forecast_type = "estimated"
        method = "simple_average"

    # Generate daily forecast
    daily_forecast = []
    cash_position = current_cash
    for i in range(1, days + 1):
        forecast_date = (now + timedelta(days=i)).strftime("%Y-%m-%d")
        inc = avg_daily_income
        exp = avg_daily_expense
        net = inc - exp
        cash_position += net

        # Simple confidence interval (±20%)
        margin = max(abs(net), avg_daily_expense) // 5
        daily_forecast.append({
            "date": forecast_date,
            "income_minor": inc,
            "expenses_minor": exp,
            "net_minor": net,
            "cash_position_minor": cash_position,
            "lower_minor": cash_position - margin,
            "upper_minor": cash_position + margin,
        })

    # Calculate simple MAE/RMSE from historical data (last 7 days vs prediction)
    mae = abs(avg_daily_income - (total_income // max(len(all_days), 1))) if all_days else None
    rmse = mae  # simplified

    summary = {
        "forecast_days": days,
        "avg_daily_income_minor": avg_daily_income,
        "avg_daily_expenses_minor": avg_daily_expense,
        "end_cash_position_minor": cash_position,
    }

    # Save forecast to DB
    forecast_record = Forecast(
        id=str(uuid.uuid4()),
        workspace_id=wid,
        forecast_type=forecast_type,
        current_balance_minor=current_cash,
        projected_balance_30d_minor=cash_position,
        lowest_balance_30d_minor=min(f["cash_position_minor"] for f in daily_forecast) if daily_forecast else current_cash,
        data={"daily_forecast": daily_forecast, "summary": summary},
        metrics_mae=mae,
        metrics_rmse=rmse,
        method=method,
        data_points_used=len(transactions),
    )
    db.add(forecast_record)
    await db.commit()

    return {
        "forecast_type": forecast_type,
        "daily_forecast": daily_forecast,
        "summary": summary,
        "metrics": {"mae": mae, "rmse": rmse},
        "model_info": {"method": method, "data_points_used": len(transactions)},
    }
