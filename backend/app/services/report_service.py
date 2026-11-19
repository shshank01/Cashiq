from datetime import datetime, timedelta, timezone
from typing import Dict, Any, List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.transaction import Transaction
from app.models.account import Account

class ReportService:
    @staticmethod
    async def get_income_expense_report(
        db: AsyncSession,
        workspace_id: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None
    ) -> Dict[str, Any]:
        now = datetime.now(timezone.utc)
        s_dt = datetime.fromisoformat(start_date) if start_date else (now - timedelta(days=90))
        e_dt = datetime.fromisoformat(end_date) if end_date else now

        tx_res = await db.execute(
            select(Transaction).where(
                Transaction.workspace_id == workspace_id,
                Transaction.date >= s_dt,
                Transaction.date <= e_dt
            )
        )
        txs = tx_res.scalars().all()

        revenue_by_cat = {}
        expense_by_cat = {}

        for t in txs:
            amt = abs(t.amount_minor)
            cat = t.category_name or "Miscellaneous"
            if t.type == "income":
                revenue_by_cat[cat] = revenue_by_cat.get(cat, 0) + amt
            else:
                expense_by_cat[cat] = expense_by_cat.get(cat, 0) + amt

        total_income = sum(revenue_by_cat.values())
        total_expenses = sum(expense_by_cat.values())
        net_income = total_income - total_expenses
        margin_pct = round((net_income / total_income * 100.0), 1) if total_income > 0 else 0.0

        return {
            "period": {
                "start_date": s_dt.strftime("%Y-%m-%d"),
                "end_date": e_dt.strftime("%Y-%m-%d")
            },
            "total_income_minor": total_income,
            "total_expenses_minor": total_expenses,
            "net_income_minor": net_income,
            "net_profit_margin_pct": margin_pct,
            "revenue_breakdown": [
                {"category": k, "amount_minor": v, "percentage": round((v / total_income) * 100, 1) if total_income > 0 else 0}
                for k, v in sorted(revenue_by_cat.items(), key=lambda x: x[1], reverse=True)
            ],
            "expense_breakdown": [
                {"category": k, "amount_minor": v, "percentage": round((v / total_expenses) * 100, 1) if total_expenses > 0 else 0}
                for k, v in sorted(expense_by_cat.items(), key=lambda x: x[1], reverse=True)
            ]
        }

    @staticmethod
    async def get_category_spend_report(
        db: AsyncSession,
        workspace_id: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None
    ) -> Dict[str, Any]:
        now = datetime.now(timezone.utc)
        s_dt = datetime.fromisoformat(start_date) if start_date else (now - timedelta(days=90))
        e_dt = datetime.fromisoformat(end_date) if end_date else now

        tx_res = await db.execute(
            select(Transaction).where(
                Transaction.workspace_id == workspace_id,
                Transaction.type == "expense",
                Transaction.date >= s_dt,
                Transaction.date <= e_dt
            )
        )
        txs = tx_res.scalars().all()

        cats = {}
        for t in txs:
            cat = t.category_name or "Miscellaneous"
            if cat not in cats:
                cats[cat] = {"amount_minor": 0, "count": 0}
            cats[cat]["amount_minor"] += abs(t.amount_minor)
            cats[cat]["count"] += 1

        total_exp = sum(c["amount_minor"] for c in cats.values()) or 1

        items = [
            {
                "category": k,
                "amount_minor": v["amount_minor"],
                "transaction_count": v["count"],
                "percentage": round((v["amount_minor"] / total_exp) * 100, 1)
            }
            for k, v in sorted(cats.items(), key=lambda x: x[1]["amount_minor"], reverse=True)
        ]

        return {
            "total_spend_minor": total_exp,
            "categories": items
        }

    @staticmethod
    async def get_cash_flow_statement(
        db: AsyncSession,
        workspace_id: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None
    ) -> Dict[str, Any]:
        now = datetime.now(timezone.utc)
        s_dt = datetime.fromisoformat(start_date) if start_date else (now - timedelta(days=90))
        e_dt = datetime.fromisoformat(end_date) if end_date else now

        # Get accounts
        acct_res = await db.execute(
            select(Account).where(Account.workspace_id == workspace_id, Account.is_active == True)
        )
        accounts = acct_res.scalars().all()
        ending_cash = sum(a.balance_minor for a in accounts)

        tx_res = await db.execute(
            select(Transaction).where(
                Transaction.workspace_id == workspace_id,
                Transaction.date >= s_dt,
                Transaction.date <= e_dt
            ).order_by(Transaction.date.asc())
        )
        txs = tx_res.scalars().all()

        operating_inflows = 0
        operating_outflows = 0
        investing_financing_flow = 0

        for t in txs:
            amt = abs(t.amount_minor)
            cat = (t.category_name or "").lower()
            if "investment" in cat or "loan" in cat or "financing" in cat or "equity" in cat:
                if t.type == "income":
                    investing_financing_flow += amt
                else:
                    investing_financing_flow -= amt
            else:
                if t.type == "income":
                    operating_inflows += amt
                else:
                    operating_outflows += amt

        net_operating_flow = operating_inflows - operating_outflows
        net_cash_change = net_operating_flow + investing_financing_flow
        beginning_cash = ending_cash - net_cash_change

        return {
            "period": {
                "start_date": s_dt.strftime("%Y-%m-%d"),
                "end_date": e_dt.strftime("%Y-%m-%d")
            },
            "beginning_cash_minor": beginning_cash,
            "operating_cash_inflows_minor": operating_inflows,
            "operating_cash_outflows_minor": operating_outflows,
            "net_operating_cash_flow_minor": net_operating_flow,
            "investing_financing_cash_flow_minor": investing_financing_flow,
            "net_change_in_cash_minor": net_cash_change,
            "ending_cash_minor": ending_cash
        }
