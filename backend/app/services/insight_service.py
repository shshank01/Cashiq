import uuid
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from app.models.transaction import Transaction
from app.models.account import Account
from app.models.recurring import RecurringRule
from app.models.payable import Payable
from app.models.receivable import Receivable
from app.models.insight import Insight

class InsightService:
    @staticmethod
    async def generate_insights(db: AsyncSession, workspace_id: str) -> List[Dict[str, Any]]:
        """
        Generates deterministic, verified financial insights based on actual database numbers.
        Never fabricates numbers.
        """
        now = datetime.now(timezone.utc)
        thirty_days_ago = now - timedelta(days=30)
        sixty_days_ago = now - timedelta(days=60)
        seven_days_ahead = now + timedelta(days=7)

        # 1. Fetch current cash balance
        acct_res = await db.execute(select(Account).where(Account.workspace_id == workspace_id, Account.is_active == True))
        accounts = acct_res.scalars().all()
        current_cash_minor = sum(a.balance_minor for a in accounts)

        # 2. Fetch last 60 days transactions
        tx_res = await db.execute(
            select(Transaction)
            .where(
                Transaction.workspace_id == workspace_id,
                Transaction.date >= sixty_days_ago
            )
        )
        txs = tx_res.scalars().all()

        current_month_exp = 0
        current_month_inc = 0
        prev_month_exp = 0
        prev_month_inc = 0
        category_spend = {}

        for t in txs:
            amt = abs(t.amount_minor)
            t_date = t.date if t.date.tzinfo else t.date.replace(tzinfo=timezone.utc)
            if t_date >= thirty_days_ago:
                if t.type == "expense":
                    current_month_exp += amt
                    cat = t.category_name or "Miscellaneous"
                    category_spend[cat] = category_spend.get(cat, 0) + amt
                else:
                    current_month_inc += amt
            else:
                if t.type == "expense":
                    prev_month_exp += amt
                else:
                    prev_month_inc += amt

        insights = []

        # Insight A: Month-over-Month Expense Change
        if prev_month_exp > 0:
            diff = current_month_exp - prev_month_exp
            pct = (diff / prev_month_exp) * 100.0
            if abs(pct) >= 5.0:
                direction = "increased" if pct > 0 else "decreased"
                severity = "warning" if pct > 20.0 else ("info" if pct <= 0 else "info")
                insights.append({
                    "id": f"insight-mom-exp-{now.strftime('%Y%m%d')}",
                    "type": "spending_surge",
                    "title": f"Expenses {direction.capitalize()} {abs(pct):.1f}% Compared with Last Month",
                    "description": f"Operating expenses reached ${current_month_exp/100:,.2f} over the last 30 days, compared to ${prev_month_exp/100:,.2f} in the preceding 30-day period (net change: {'+' if diff > 0 else '-'}${abs(diff)/100:,.2f}).",
                    "severity": severity,
                    "created_at": now.isoformat()
                })

        # Insight B: Largest Expense Category
        if category_spend and current_month_exp > 0:
            sorted_cats = sorted(category_spend.items(), key=lambda x: x[1], reverse=True)
            top_cat, top_amt = sorted_cats[0]
            top_pct = (top_amt / current_month_exp) * 100.0
            if top_pct >= 20.0:
                insights.append({
                    "id": f"insight-largest-cat-{now.strftime('%Y%m%d')}",
                    "type": "largest_category",
                    "title": f"{top_cat} is Your Largest Expense Category",
                    "description": f"{top_cat} accounts for {top_pct:.1f}% of all outflows over the past month (${top_amt/100:,.2f} of ${current_month_exp/100:,.2f} total).",
                    "severity": "info",
                    "created_at": now.isoformat()
                })

        # Insight C: Runway & Burn Rate
        # Calculate monthly burn
        net_flow_30d = current_month_inc - current_month_exp
        if net_flow_30d < 0:
            monthly_burn_minor = abs(net_flow_30d)
            if monthly_burn_minor > 0 and current_cash_minor > 0:
                runway_months = round((current_cash_minor / monthly_burn_minor), 1)
                severity = "critical" if runway_months < 3.0 else ("warning" if runway_months < 6.0 else "info")
                insights.append({
                    "id": f"insight-runway-{now.strftime('%Y%m%d')}",
                    "type": "runway_warning",
                    "title": f"Estimated Runway: {runway_months} Months",
                    "description": f"At your current monthly net burn rate of ${monthly_burn_minor/100:,.2f}, your available cash reserve (${current_cash_minor/100:,.2f}) will support approximately {runway_months} months of operations.",
                    "severity": severity,
                    "created_at": now.isoformat()
                })
        elif current_month_inc > 0 and net_flow_30d > 0:
            insights.append({
                "id": f"insight-runway-pos-{now.strftime('%Y%m%d')}",
                "type": "positive_growth",
                "title": "Business is Net Cash Flow Positive",
                "description": f"Monthly income (${current_month_inc/100:,.2f}) exceeded total expenditures (${current_month_exp/100:,.2f}) by ${net_flow_30d/100:,.2f}. No active cash burn.",
                "severity": "info",
                "created_at": now.isoformat()
            })

        # Insight D: Upcoming Recurring Payments
        rec_res = await db.execute(
            select(RecurringRule).where(
                RecurringRule.workspace_id == workspace_id,
                RecurringRule.status == "active",
                RecurringRule.next_date <= seven_days_ahead,
                RecurringRule.next_date >= now - timedelta(days=1)
            )
        )
        upcoming_recs = rec_res.scalars().all()
        if upcoming_recs:
            total_rec_minor = sum(r.amount_minor for r in upcoming_recs)
            merchants_sample = ", ".join([r.merchant for r in upcoming_recs[:3]])
            insights.append({
                "id": f"insight-rec-due-{now.strftime('%Y%m%d')}",
                "type": "recurring_alert",
                "title": f"{len(upcoming_recs)} Recurring Payment{'s' if len(upcoming_recs)>1 else ''} Due This Week",
                "description": f"${total_rec_minor/100:,.2f} in scheduled recurring charges ({merchants_sample}) are expected within the next 7 days.",
                "severity": "info",
                "created_at": now.isoformat()
            })

        # Insight E: Overdue Payables or Receivables
        pay_res = await db.execute(
            select(Payable).where(
                Payable.workspace_id == workspace_id,
                Payable.status == "overdue"
            )
        )
        overdue_payables = pay_res.scalars().all()
        if overdue_payables:
            tot_p = sum(p.amount_minor - p.amount_paid_minor for p in overdue_payables)
            insights.append({
                "id": f"insight-overdue-pay-{now.strftime('%Y%m%d')}",
                "type": "payables_alert",
                "title": f"${tot_p/100:,.2f} in Overdue Payables",
                "description": f"{len(overdue_payables)} vendor invoice{'s are' if len(overdue_payables)>1 else ' is'} past due date. Review payables to avoid late penalties.",
                "severity": "warning",
                "created_at": now.isoformat()
            })

        rec_res = await db.execute(
            select(Receivable).where(
                Receivable.workspace_id == workspace_id,
                Receivable.status == "overdue"
            )
        )
        overdue_receivables = rec_res.scalars().all()
        if overdue_receivables:
            tot_r = sum(r.amount_minor - r.amount_received_minor for r in overdue_receivables)
            insights.append({
                "id": f"insight-overdue-rec-{now.strftime('%Y%m%d')}",
                "type": "receivables_alert",
                "title": f"${tot_r/100:,.2f} in Outstanding Overdue Receivables",
                "description": f"{len(overdue_receivables)} client payment{'s are' if len(overdue_receivables)>1 else ' is'} past their agreed due date. Consider sending payment reminders.",
                "severity": "warning",
                "created_at": now.isoformat()
            })

        # Persist or update insights in database safely
        for ins in insights:
            existing = await db.execute(
                select(Insight).where(
                    Insight.workspace_id == workspace_id,
                    Insight.type == ins["type"]
                )
            )
            existing_ins = existing.scalars().first()
            if existing_ins:
                existing_ins.title = ins["title"]
                existing_ins.description = ins["description"]
                existing_ins.severity = ins["severity"]
                existing_ins.created_at = now
                ins["id"] = existing_ins.id
            else:
                new_id = str(uuid.uuid4())
                db_ins = Insight(
                    id=new_id,
                    workspace_id=workspace_id,
                    type=ins["type"],
                    title=ins["title"],
                    description=ins["description"],
                    severity=ins["severity"],
                    created_at=now
                )
                db.add(db_ins)
                ins["id"] = new_id
        await db.commit()

        return insights

    @staticmethod
    async def get_all(db: AsyncSession, workspace_id: str) -> List[Dict[str, Any]]:
        insights = await InsightService.generate_insights(db, workspace_id)
        res = await db.execute(
            select(Insight).where(Insight.workspace_id == workspace_id).order_by(Insight.created_at.desc())
        )
        db_insights = res.scalars().all()
        return [
            {
                "id": i.id,
                "type": i.type,
                "title": i.title,
                "description": i.description,
                "severity": i.severity,
                "created_at": i.created_at.isoformat()
            }
            for i in db_insights
        ]
