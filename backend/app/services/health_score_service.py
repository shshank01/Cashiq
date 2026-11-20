from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
import numpy as np
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc

from app.models.account import Account
from app.models.transaction import Transaction
from app.models.payable import Payable
from app.models.receivable import Receivable
from app.models.health_score import HealthScoreRecord

class HealthScoreService:
    """
    Transparent, Multi-Factor Financial Health Scoring Engine.
    Evaluates Cash Flow Stability, Expense-to-Revenue Ratio, Cash Reserves,
    Receivables Health, and Payables Load on a 0-100 calibrated scale.
    """

    @staticmethod
    async def calculate_health_score(
        db: AsyncSession,
        workspace_id: str,
        persist: bool = True
    ) -> Dict[str, Any]:
        now = datetime.now(timezone.utc)

        # 1. Accounts & Cash Reserves
        acct_res = await db.execute(
            select(Account).where(Account.workspace_id == workspace_id, Account.is_active == True)
        )
        accounts = acct_res.scalars().all()
        current_cash_minor = sum(a.balance_minor for a in accounts)

        # 2. Historical transactions (past 180 days for trend, past 90 days for current)
        t_180 = now - timedelta(days=180)
        tx_res = await db.execute(
            select(Transaction).where(
                Transaction.workspace_id == workspace_id,
                Transaction.date >= t_180
            ).order_by(Transaction.date.asc())
        )
        all_txs = tx_res.scalars().all()

        # Split into monthly buckets for historical analysis
        monthly_flows: Dict[str, Dict[str, int]] = {}
        for offset in range(5, -1, -1):
            m_dt = now - timedelta(days=offset * 30)
            m_key = m_dt.strftime("%Y-%m")
            monthly_flows[m_key] = {"income": 0, "expense": 0, "net": 0}

        for t in all_txs:
            t_dt = t.date if t.date.tzinfo else t.date.replace(tzinfo=timezone.utc)
            m_key = t_dt.strftime("%Y-%m")
            if m_key in monthly_flows:
                amt = abs(t.amount_minor)
                if t.type == "income":
                    monthly_flows[m_key]["income"] += amt
                else:
                    monthly_flows[m_key]["expense"] += amt
                monthly_flows[m_key]["net"] = monthly_flows[m_key]["income"] - monthly_flows[m_key]["expense"]

        # Last 90 days totals
        t_90 = now - timedelta(days=90)
        recent_txs = [t for t in all_txs if (t.date if t.date.tzinfo else t.date.replace(tzinfo=timezone.utc)) >= t_90]
        recent_income = sum(abs(t.amount_minor) for t in recent_txs if t.type == "income")
        recent_expense = sum(abs(t.amount_minor) for t in recent_txs if t.type == "expense")
        avg_monthly_income = recent_income / 3.0 if recent_income > 0 else 1000000.0
        avg_monthly_expense = recent_expense / 3.0 if recent_expense > 0 else 800000.0
        avg_monthly_burn = max(1.0, avg_monthly_expense - avg_monthly_income) if avg_monthly_expense > avg_monthly_income else 0.0

        # 3. Payables & Receivables
        pay_res = await db.execute(select(Payable).where(Payable.workspace_id == workspace_id))
        all_payables = pay_res.scalars().all()
        unpaid_payables = [p for p in all_payables if p.status != "paid"]
        total_payables_minor = sum(p.amount_minor - (p.amount_paid_minor or 0) for p in unpaid_payables)
        overdue_payables_minor = sum(
            p.amount_minor - (p.amount_paid_minor or 0) for p in unpaid_payables if p.status == "overdue"
        )

        rec_res = await db.execute(select(Receivable).where(Receivable.workspace_id == workspace_id))
        all_receivables = rec_res.scalars().all()
        uncollected_recs = [r for r in all_receivables if r.status != "received"]
        total_recs_minor = sum(r.amount_minor - (r.amount_received_minor or 0) for r in uncollected_recs)
        overdue_recs_minor = sum(
            r.amount_minor - (r.amount_received_minor or 0) for r in uncollected_recs if r.status == "overdue"
        )

        # ------------------- FACTOR 1: Cash Flow Stability (Weight 25%) -------------------
        net_flows = [m["net"] for m in monthly_flows.values()]
        positive_months = sum(1 for f in net_flows if f >= 0)
        pos_ratio = positive_months / max(1, len(net_flows))

        if len(net_flows) >= 3:
            std_flow = float(np.std(net_flows))
            mean_income = max(1.0, float(np.mean([m["income"] for m in monthly_flows.values()])))
            cov = min(2.0, std_flow / mean_income)  # coefficient of variation
            volatility_penalty = cov * 25.0
        else:
            volatility_penalty = 10.0

        cf_stability_score = max(15.0, min(100.0, (pos_ratio * 75.0 + 25.0) - volatility_penalty))

        # ------------------- FACTOR 2: Expense-to-Revenue Ratio (Weight 20%) -------------------
        exp_rev_ratio = avg_monthly_expense / avg_monthly_income if avg_monthly_income > 0 else 1.5
        if exp_rev_ratio <= 0.60:
            exp_rev_score = 98.0
        elif exp_rev_ratio <= 0.75:
            exp_rev_score = 90.0
        elif exp_rev_ratio <= 0.90:
            exp_rev_score = 80.0
        elif exp_rev_ratio <= 1.00:
            exp_rev_score = 70.0
        elif exp_rev_ratio <= 1.15:
            exp_rev_score = 50.0
        elif exp_rev_ratio <= 1.30:
            exp_rev_score = 35.0
        else:
            exp_rev_score = 20.0

        # ------------------- FACTOR 3: Cash Reserves & Runway (Weight 25%) -------------------
        if avg_monthly_burn > 0:
            runway_months = current_cash_minor / avg_monthly_burn
        else:
            # Net profitable, runway based on months of operating expenses in reserve
            runway_months = current_cash_minor / max(1.0, avg_monthly_expense)

        if runway_months >= 12.0:
            reserves_score = 98.0
        elif runway_months >= 6.0:
            reserves_score = 88.0 + (runway_months - 6.0) * 1.5
        elif runway_months >= 3.0:
            reserves_score = 72.0 + (runway_months - 3.0) * 5.0
        elif runway_months >= 1.5:
            reserves_score = 50.0 + (runway_months - 1.5) * 14.0
        elif runway_months >= 0.8:
            reserves_score = 30.0 + (runway_months - 0.8) * 25.0
        else:
            reserves_score = max(10.0, runway_months * 30.0)

        # ------------------- FACTOR 4: Receivables Health (Weight 15%) -------------------
        if total_recs_minor > 0:
            overdue_rec_pct = (overdue_recs_minor / total_recs_minor) * 100.0
            recs_health_score = max(20.0, min(100.0, 100.0 - (overdue_rec_pct * 1.2)))
        else:
            recs_health_score = 85.0  # neutral / clean

        # ------------------- FACTOR 5: Payables Load & Liquidity (Weight 15%) -------------------
        if current_cash_minor > 0:
            pay_coverage = current_cash_minor / max(1, total_payables_minor)
            coverage_pts = min(60.0, pay_coverage * 20.0)
        else:
            coverage_pts = 0.0

        if total_payables_minor > 0:
            overdue_pay_pct = (overdue_payables_minor / total_payables_minor) * 100.0
            overdue_penalty = overdue_pay_pct * 0.4
        else:
            overdue_penalty = 0.0

        payables_score = max(15.0, min(100.0, 40.0 + coverage_pts - overdue_penalty))

        # Overall composite score
        overall_score = int(round(
            cf_stability_score * 0.25 +
            exp_rev_score * 0.20 +
            reserves_score * 0.25 +
            recs_health_score * 0.15 +
            payables_score * 0.15
        ))
        overall_score = max(1, min(100, overall_score))

        # Letter Grade
        if overall_score >= 95:
            grade = "A+"
            status_desc = "Exceptional Financial Health"
        elif overall_score >= 85:
            grade = "A"
            status_desc = "Strong Financial Position"
        elif overall_score >= 70:
            grade = "B"
            status_desc = "Good / Stable Financial Health"
        elif overall_score >= 55:
            grade = "C"
            status_desc = "Fair / Caution Advised"
        elif overall_score >= 40:
            grade = "D"
            status_desc = "At Risk / Structural Pressure"
        else:
            grade = "F"
            status_desc = "Critical Distress"

        # Factor details
        factors = [
            {
                "id": "cash_reserves",
                "name": "Cash Reserves & Runway",
                "score": round(reserves_score, 1),
                "weight": 0.25,
                "status": "strong" if reserves_score >= 75 else ("fair" if reserves_score >= 50 else "weak"),
                "metric_label": f"{round(runway_months, 1)} months runway",
                "detail": f"Current cash reserves of ${(current_cash_minor/100):,.2f} provide {round(runway_months, 1)} months of operational runway."
            },
            {
                "id": "cash_flow_stability",
                "name": "Cash Flow Stability",
                "score": round(cf_stability_score, 1),
                "weight": 0.25,
                "status": "strong" if cf_stability_score >= 75 else ("fair" if cf_stability_score >= 50 else "weak"),
                "metric_label": f"{positive_months}/{len(net_flows)} positive months",
                "detail": f"Net cash flow was positive in {positive_months} of the past {len(net_flows)} monthly cycles."
            },
            {
                "id": "expense_revenue_ratio",
                "name": "Operating Margin & Burn Efficiency",
                "score": round(exp_rev_score, 1),
                "weight": 0.20,
                "status": "strong" if exp_rev_score >= 75 else ("fair" if exp_rev_score >= 50 else "weak"),
                "metric_label": f"{round(exp_rev_ratio * 100, 1)}% expense ratio",
                "detail": f"Operating expenses consume {round(exp_rev_ratio * 100, 1)}% of verified revenues."
            },
            {
                "id": "receivables_health",
                "name": "Receivables & Invoicing Health",
                "score": round(recs_health_score, 1),
                "weight": 0.15,
                "status": "strong" if recs_health_score >= 75 else ("fair" if recs_health_score >= 50 else "weak"),
                "metric_label": f"${(total_recs_minor/100):,.2f} pending",
                "detail": f"${(overdue_recs_minor/100):,.2f} overdue out of ${(total_recs_minor/100):,.2f} pending client invoices."
            },
            {
                "id": "payables_liquidity",
                "name": "Payables Load & Liquidity",
                "score": round(payables_score, 1),
                "weight": 0.15,
                "status": "strong" if payables_score >= 75 else ("fair" if payables_score >= 50 else "weak"),
                "metric_label": f"${(total_payables_minor/100):,.2f} obligations",
                "detail": f"Total active payables are ${(total_payables_minor/100):,.2f} (${(overdue_payables_minor/100):,.2f} overdue) with {round(current_cash_minor / max(1, total_payables_minor), 1)}× cash coverage."
            }
        ]

        # Drivers
        sorted_by_score = sorted(factors, key=lambda f: f["score"])
        negative_drivers = [
            f"{f['name']} ({f['score']}/100): {f['detail']}"
            for f in sorted_by_score if f["score"] < 70
        ][:2]
        positive_drivers = [
            f"{f['name']} ({f['score']}/100): {f['detail']}"
            for f in reversed(sorted_by_score) if f["score"] >= 75
        ][:2]

        # Improvement suggestions
        suggestions = []
        if overdue_recs_minor > 0:
            suggestions.append(f"Accelerate collection of ${(overdue_recs_minor/100):,.2f} in overdue receivables to immediately boost cash reserves.")
        if overdue_payables_minor > 0:
            suggestions.append(f"Settle ${(overdue_payables_minor/100):,.2f} in overdue vendor bills to prevent late penalties and protect credit liquidity.")
        if exp_rev_ratio > 0.85:
            suggestions.append("Operating expenses exceed 85% of monthly revenue. Consider reviewing top recurring software and contractor expenses.")
        if runway_months < 4.0:
            suggestions.append(f"Extend runway from {round(runway_months, 1)} months towards the target 6-month buffer through receivables factoring or expense cuts.")
        if not suggestions:
            suggestions.append("Your financial structure is healthy! Maintain your current disciplined expense controls and monitor incoming collections.")

        # Historical monthly trend (simulated from monthly flows)
        historical_trend = []
        for m_key, flow in monthly_flows.items():
            # Estimate monthly score
            m_net = flow["net"]
            m_inc = flow["income"]
            m_ratio = flow["expense"] / m_inc if m_inc > 0 else 1.2
            est_m_score = int(round(50 + (25 if m_net > 0 else -15) + max(-20, min(25, (1.0 - m_ratio) * 40))))
            historical_trend.append({
                "month": m_key,
                "score": max(20, min(98, est_m_score)),
                "net_flow_minor": m_net,
            })

        result = {
            "overall_score": overall_score,
            "grade": grade,
            "status_description": status_desc,
            "current_cash_minor": current_cash_minor,
            "runway_months": round(runway_months, 1),
            "factors": factors,
            "positive_drivers": positive_drivers,
            "negative_drivers": negative_drivers,
            "suggestions": suggestions,
            "historical_trend": historical_trend,
        }

        # Persist record
        if persist:
            record = HealthScoreRecord(
                workspace_id=workspace_id,
                overall_score=overall_score,
                grade=grade,
                cash_flow_stability_score=cf_stability_score,
                expense_to_revenue_score=exp_rev_score,
                cash_reserves_score=reserves_score,
                receivables_health_score=recs_health_score,
                payables_load_score=payables_score,
                factors=factors,
                historical_trend=historical_trend,
                suggestions=suggestions,
                drivers={"positive": positive_drivers, "negative": negative_drivers}
            )
            db.add(record)
            try:
                await db.commit()
            except Exception as e:
                print(f"[HealthScoreService] Warning persisting health score record: {e}")

        return result
