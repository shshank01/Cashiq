from datetime import datetime, timezone
from typing import Dict, Any, List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.account import Account
from app.models.transaction import Transaction
from app.models.payable import Payable
from app.models.receivable import Receivable
from app.models.business_profile import BusinessProfile
from app.models.forecast import Forecast
from app.ml.forecaster import forecaster_instance

class ForecastService:
    @staticmethod
    async def get_or_generate_forecast(db: AsyncSession, workspace_id: str, days: int = 30) -> Dict[str, Any]:
        # 1. Fetch current cash balance
        acct_res = await db.execute(
            select(Account).where(Account.workspace_id == workspace_id, Account.is_active == True)
        )
        accounts = acct_res.scalars().all()
        current_cash_minor = sum(a.balance_minor for a in accounts)

        # 2. Fetch history
        tx_res = await db.execute(
            select(Transaction).where(Transaction.workspace_id == workspace_id).order_by(Transaction.date.asc())
        )
        txs = tx_res.scalars().all()

        # 3. Fetch payables and receivables
        pay_res = await db.execute(
            select(Payable).where(Payable.workspace_id == workspace_id, Payable.status != "paid")
        )
        payables = pay_res.scalars().all()

        rec_res = await db.execute(
            select(Receivable).where(Receivable.workspace_id == workspace_id, Receivable.status != "received")
        )
        receivables = rec_res.scalars().all()

        # 4. Fetch business profile (cold start inputs)
        prof_res = await db.execute(
            select(BusinessProfile).where(BusinessProfile.workspace_id == workspace_id)
        )
        biz_profile = prof_res.scalar_one_or_none()

        # 5. Compute forecast via forecaster
        fc = forecaster_instance.forecast_cash_flow(
            current_cash_minor=current_cash_minor,
            transactions=txs,
            business_profile=biz_profile,
            known_payables=payables,
            known_receivables=receivables,
            forecast_days=days
        )

        end_30d = fc["summary"]["end_cash_position_minor"]
        low_30d = fc["summary"]["lowest_cash_position_minor"]

        # Compatibility fields for frontend
        fc["current_balance"] = current_cash_minor
        fc["projected_balance_30d"] = end_30d
        fc["lowest_balance_30d"] = low_30d
        fc["currency"] = "USD"

        # Persist forecast run
        db_fc = Forecast(
            workspace_id=workspace_id,
            forecast_type=fc["forecast_type"],
            current_balance_minor=current_cash_minor,
            projected_balance_30d_minor=end_30d,
            lowest_balance_30d_minor=low_30d,
            data=fc,
            metrics_mae=fc["metrics"]["mae"],
            metrics_rmse=fc["metrics"]["rmse"],
            method=fc["model_info"]["method"],
            data_points_used=fc["model_info"]["data_points_used"]
        )
        db.add(db_fc)
        await db.commit()

        return fc
