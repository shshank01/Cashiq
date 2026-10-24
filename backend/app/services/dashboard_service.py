from datetime import datetime, timedelta, timezone
from typing import Dict, Any, List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func

from app.models.account import Account
from app.models.transaction import Transaction
from app.models.payable import Payable
from app.models.receivable import Receivable
from app.models.recurring import RecurringRule
from app.models.business_profile import BusinessProfile
from app.services.insight_service import InsightService
from app.ml.forecaster import forecaster_instance

class DashboardService:
    @staticmethod
    async def get_dashboard_data(db: AsyncSession, workspace_id: str) -> Dict[str, Any]:
        now = datetime.now(timezone.utc)
        thirty_days_ago = now - timedelta(days=30)
        ninety_days_ago = now - timedelta(days=90)

        # 1. Accounts & Total Cash
        acct_res = await db.execute(
            select(Account).where(Account.workspace_id == workspace_id, Account.is_active == True)
        )
        accounts = acct_res.scalars().all()
        current_cash_minor = sum(a.balance_minor for a in accounts)

        # 2. Last 30-day transactions
        tx_30_res = await db.execute(
            select(Transaction).where(
                Transaction.workspace_id == workspace_id,
                Transaction.date >= thirty_days_ago
            )
        )
        txs_30 = tx_30_res.scalars().all()

        income_30_minor = sum(abs(t.amount_minor) for t in txs_30 if t.type == "income")
        expenses_30_minor = sum(abs(t.amount_minor) for t in txs_30 if t.type == "expense")
        net_cash_flow_minor = income_30_minor - expenses_30_minor

        # 3. Payables & Receivables KPIs
        pay_res = await db.execute(
            select(Payable).where(Payable.workspace_id == workspace_id, Payable.status != "paid")
        )
        active_payables = pay_res.scalars().all()
        total_payables_minor = sum(p.amount_minor - p.amount_paid_minor for p in active_payables)

        rec_res = await db.execute(
            select(Receivable).where(Receivable.workspace_id == workspace_id, Receivable.status != "received")
        )
        active_receivables = rec_res.scalars().all()
        total_receivables_minor = sum(r.amount_minor - r.amount_received_minor for r in active_receivables)

        # 4. Runway calculation
        # If burning cash (net < 0): Runway = Cash / Monthly Net Burn
        runway_months = None
        if net_cash_flow_minor < 0:
            burn = abs(net_cash_flow_minor)
            if burn > 0 and current_cash_minor > 0:
                runway_months = round(current_cash_minor / burn, 1)
        # If profitable / cash flow positive, runway is None (prompt: "If the business is not burning cash, do not show an artificial finite runway.")

        # 5. Cash-Flow History (daily for last 30 days)
        daily_map = {}
        for d in range(30):
            day_dt = (thirty_days_ago + timedelta(days=d)).date()
            daily_map[day_dt] = {"income": 0, "expenses": 0}

        for t in txs_30:
            t_dt = (t.date if t.date.tzinfo else t.date.replace(tzinfo=timezone.utc)).date()
            if t_dt in daily_map:
                if t.type == "income":
                    daily_map[t_dt]["income"] += abs(t.amount_minor)
                else:
                    daily_map[t_dt]["expenses"] += abs(t.amount_minor)

        cash_flow_history = []
        for day_dt in sorted(daily_map.keys()):
            inc = daily_map[day_dt]["income"]
            exp = daily_map[day_dt]["expenses"]
            cash_flow_history.append({
                "date": day_dt.strftime("%b %d"),
                "income_minor": inc,
                "expenses_minor": exp,
                "net_minor": inc - exp
            })

        # 6. Income vs Expenses History (last 6 months by month)
        all_tx_res = await db.execute(
            select(Transaction).where(
                Transaction.workspace_id == workspace_id,
                Transaction.date >= now - timedelta(days=180)
            )
        )
        all_txs = all_tx_res.scalars().all()

        month_map = {}
        for i in range(5, -1, -1):
            m_dt = now - timedelta(days=i*30)
            m_key = m_dt.strftime("%b %Y")
            month_map[m_key] = {"income": 0, "expenses": 0}

        for t in all_txs:
            t_dt = t.date if t.date.tzinfo else t.date.replace(tzinfo=timezone.utc)
            m_key = t_dt.strftime("%b %Y")
            if m_key in month_map:
                if t.type == "income":
                    month_map[m_key]["income"] += abs(t.amount_minor)
                else:
                    month_map[m_key]["expenses"] += abs(t.amount_minor)

        income_vs_expenses = [
            {
                "month": k,
                "income_minor": v["income"],
                "expenses_minor": v["expenses"]
            }
            for k, v in month_map.items()
        ]

        # 7. Spending by Category (last 30 days)
        cat_map = {}
        for t in txs_30:
            if t.type == "expense":
                cat = t.category_name or "Miscellaneous"
                cat_map[cat] = cat_map.get(cat, 0) + abs(t.amount_minor)

        tot_cat_exp = sum(cat_map.values()) or 1
        spending_by_category = [
            {
                "category": cat,
                "amount_minor": amt,
                "percentage": round((amt / tot_cat_exp) * 100, 1)
            }
            for cat, amt in sorted(cat_map.items(), key=lambda x: x[1], reverse=True)[:8]
        ]

        # 8. Forecast Preview (next 14 days)
        prof_res = await db.execute(select(BusinessProfile).where(BusinessProfile.workspace_id == workspace_id))
        biz_prof = prof_res.scalar_one_or_none()

        fc_result = forecaster_instance.forecast_cash_flow(
            current_cash_minor=current_cash_minor,
            transactions=all_txs,
            business_profile=biz_prof,
            known_payables=active_payables,
            known_receivables=active_receivables,
            forecast_days=14
        )
        forecast_preview = [
            {
                "date": f["date"],
                "predicted_minor": f["cash_position_minor"],
                "lower_minor": f["lower_minor"],
                "upper_minor": f["upper_minor"]
            }
            for f in fc_result["daily_forecast"]
        ]

        # 9. Important Insights
        insights = await InsightService.generate_insights(db, workspace_id)

        # 10. Upcoming Recurring Payments
        rec_res = await db.execute(
            select(RecurringRule).where(
                RecurringRule.workspace_id == workspace_id,
                RecurringRule.status == "active"
            ).order_by(RecurringRule.next_date.asc()).limit(5)
        )
        upcoming_recs = [
            {
                "id": r.id,
                "merchant": r.merchant,
                "description": r.description or r.merchant,
                "amount_minor": r.amount_minor,
                "frequency": r.frequency,
                "next_date": r.next_date.strftime("%Y-%m-%d") if hasattr(r.next_date, "strftime") else (str(r.next_date).split("T")[0].split(" ")[0] if r.next_date else "")
            }
            for r in rec_res.scalars().all()
        ]

        # 11. Unusual Transactions (Anomalies)
        anom_res = await db.execute(
            select(Transaction).where(
                Transaction.workspace_id == workspace_id,
                Transaction.is_anomaly == True
            ).order_by(Transaction.date.desc()).limit(5)
        )
        anomalies = [
            {
                "id": a.id,
                "date": a.date.strftime("%Y-%m-%d"),
                "description": a.description,
                "merchant": a.merchant,
                "amount_minor": a.amount_minor,
                "anomaly_score": a.anomaly_score,
                "anomaly_severity": a.anomaly_severity,
                "anomaly_reason": a.anomaly_reason
            }
            for a in anom_res.scalars().all()
        ]

        # 12. Upcoming Payables & Receivables
        upcoming_payables = [
            {
                "id": p.id,
                "vendor": p.vendor,
                "amount_minor": p.amount_minor - p.amount_paid_minor,
                "due_date": p.due_date.strftime("%Y-%m-%d")
            }
            for p in sorted(active_payables, key=lambda x: x.due_date)[:5]
        ]

        upcoming_receivables = [
            {
                "id": r.id,
                "client": r.client,
                "amount_minor": r.amount_minor - r.amount_received_minor,
                "due_date": r.due_date.strftime("%Y-%m-%d")
            }
            for r in sorted(active_receivables, key=lambda x: x.due_date)[:5]
        ]

        return {
            "kpis": {
                "current_cash_minor": current_cash_minor,
                "total_income_minor": income_30_minor,
                "income_minor": income_30_minor,
                "total_expenses_minor": expenses_30_minor,
                "expenses_minor": expenses_30_minor,
                "net_cash_flow_minor": net_cash_flow_minor,
                "runway_months": runway_months,
                "total_payables_minor": total_payables_minor,
                "total_receivables_minor": total_receivables_minor
            },
            "cash_flow_history": cash_flow_history,
            "income_vs_expenses": income_vs_expenses,
            "income_expense_history": income_vs_expenses, # compatibility
            "spending_by_category": spending_by_category,
            "forecast_preview": forecast_preview,
            "recent_insights": insights[:5],
            "upcoming_recurring": upcoming_recs,
            "anomalous_transactions": anomalies,
            "upcoming_payables": upcoming_payables,
            "upcoming_receivables": upcoming_receivables
        }
