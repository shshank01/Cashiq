import math
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc

from app.models.account import Account
from app.models.transaction import Transaction
from app.models.payable import Payable
from app.models.receivable import Receivable
from app.models.recurring import RecurringRule
from app.models.simulation import SimulationScenario
from app.services.audit_service import AuditService

class SimulationService:
    """
    What-If Financial Simulation Engine.
    Simulates revenue adjustments, expense adjustments, payment delays,
    and calculates multi-scenario runway and monthly cash trajectory.
    """

    @staticmethod
    async def run_simulation(
        db: AsyncSession,
        workspace_id: str,
        revenue_change_pct: float = 0.0,      # e.g. -15.0 for 15% revenue drop
        expense_change_pct: float = 0.0,      # e.g. +10.0 for 10% cost increase
        delayed_receivables_days: int = 0,    # e.g. 30 days delayed collections
        months: int = 6,                      # 3, 6, or 12 months horizon
        custom_events: Optional[List[Dict[str, Any]]] = None # one-off capital expenses or hires
    ) -> Dict[str, Any]:
        months = max(1, min(24, months))
        custom_events = custom_events or []

        # 1. Starting cash balance from active accounts
        acct_res = await db.execute(
            select(Account).where(Account.workspace_id == workspace_id, Account.is_active == True)
        )
        accounts = acct_res.scalars().all()
        starting_cash_minor = sum(a.balance_minor for a in accounts)

        # 2. Historical baseline monthly revenue and expenses (past 90 days)
        now = datetime.now(timezone.utc)
        ninety_days_ago = now - timedelta(days=90)
        tx_res = await db.execute(
            select(Transaction).where(
                Transaction.workspace_id == workspace_id,
                Transaction.date >= ninety_days_ago
            )
        )
        txs = tx_res.scalars().all()

        total_hist_income = sum(abs(t.amount_minor) for t in txs if t.type == "income")
        total_hist_expense = sum(abs(t.amount_minor) for t in txs if t.type == "expense")

        # Normalize to 30-day monthly averages
        baseline_monthly_income = int(round(total_hist_income / 3.0)) if total_hist_income > 0 else 1000000
        baseline_monthly_expense = int(round(total_hist_expense / 3.0)) if total_hist_expense > 0 else 800000

        # 3. Scheduled Payables & Receivables
        pay_res = await db.execute(
            select(Payable).where(Payable.workspace_id == workspace_id, Payable.status != "paid")
        )
        payables = pay_res.scalars().all()

        rec_res = await db.execute(
            select(Receivable).where(Receivable.workspace_id == workspace_id, Receivable.status != "received")
        )
        receivables = rec_res.scalars().all()

        # 4. Recurring rules
        rec_rules_res = await db.execute(
            select(RecurringRule).where(RecurringRule.workspace_id == workspace_id, RecurringRule.status == "active")
        )
        recurring_rules = rec_rules_res.scalars().all()
        recurring_monthly_expense = sum(
            r.amount_minor for r in recurring_rules if (r.type or "expense") == "expense" and r.frequency == "monthly"
        )
        recurring_monthly_income = sum(
            r.amount_minor for r in recurring_rules if (r.type or "expense") == "income" and r.frequency == "monthly"
        )

        def project_scenario(rev_pct: float, exp_pct: float, rec_delay: int, label: str) -> Dict[str, Any]:
            current_cash = starting_cash_minor
            monthly_projections = []
            lowest_cash = starting_cash_minor
            zero_cash_month = None

            simulated_monthly_income = max(0, int(round(baseline_monthly_income * (1.0 + rev_pct / 100.0))))
            simulated_monthly_expense = max(0, int(round(baseline_monthly_expense * (1.0 + exp_pct / 100.0))))

            for m in range(1, months + 1):
                m_start = now + timedelta(days=(m - 1) * 30)
                m_end = now + timedelta(days=m * 30)
                month_label = m_start.strftime("%b %Y")

                # Income base
                m_income = simulated_monthly_income

                # Add receivables falling in this month (taking delay into account)
                for r in receivables:
                    r_date = r.due_date if r.due_date.tzinfo else r.due_date.replace(tzinfo=timezone.utc)
                    effective_date = r_date + timedelta(days=rec_delay)
                    if m_start <= effective_date < m_end:
                        m_income += (r.amount_minor - (r.amount_received_minor or 0))

                # Expense base
                m_expense = simulated_monthly_expense

                # Add payables falling in this month
                for p in payables:
                    p_date = p.due_date if p.due_date.tzinfo else p.due_date.replace(tzinfo=timezone.utc)
                    if m_start <= p_date < m_end:
                        m_expense += (p.amount_minor - (p.amount_paid_minor or 0))

                # Add custom events scheduled for this month
                for ev in custom_events:
                    ev_month = int(ev.get("month", 1))
                    if ev_month == m:
                        ev_amt = int(ev.get("amount_minor", 0))
                        ev_type = ev.get("type", "expense")
                        if ev_type == "income":
                            m_income += ev_amt
                        else:
                            m_expense += ev_amt

                net_flow = m_income - m_expense
                current_cash += net_flow

                if current_cash < lowest_cash:
                    lowest_cash = current_cash

                if current_cash <= 0 and zero_cash_month is None:
                    zero_cash_month = m

                monthly_projections.append({
                    "month_index": m,
                    "month_label": month_label,
                    "projected_income_minor": m_income,
                    "projected_expense_minor": m_expense,
                    "net_cash_flow_minor": net_flow,
                    "ending_cash_minor": current_cash,
                })

            # Calculate runway in months
            avg_monthly_net = sum(p["net_cash_flow_minor"] for p in monthly_projections) / len(monthly_projections)
            if zero_cash_month is not None:
                # Fractional runway
                prev_cash = starting_cash_minor if zero_cash_month == 1 else monthly_projections[zero_cash_month - 2]["ending_cash_minor"]
                drop_in_month = abs(monthly_projections[zero_cash_month - 1]["net_cash_flow_minor"])
                fraction = max(0.0, min(1.0, prev_cash / drop_in_month)) if drop_in_month > 0 else 0.0
                runway_months = round((zero_cash_month - 1) + fraction, 1)
            elif avg_monthly_net >= 0:
                runway_months = 999.0  # Profitable / Sustainable
            else:
                net_burn = abs(avg_monthly_net)
                runway_months = round(starting_cash_minor / net_burn, 1) if net_burn > 0 else 999.0

            return {
                "label": label,
                "revenue_change_pct": rev_pct,
                "expense_change_pct": exp_pct,
                "delayed_receivables_days": rec_delay,
                "ending_cash_minor": current_cash,
                "lowest_cash_minor": lowest_cash,
                "runway_months": runway_months,
                "is_sustainable": avg_monthly_net >= 0 and current_cash > 0,
                "projections": monthly_projections,
            }

        # Calculate all 4 scenarios:
        baseline = project_scenario(0.0, 0.0, 0, "Baseline (Current Trend)")
        expected_case = project_scenario(revenue_change_pct, expense_change_pct, delayed_receivables_days, "Expected Case (Simulated)")
        best_case = project_scenario(
            max(revenue_change_pct, 0.0) + 10.0,
            min(expense_change_pct, 0.0) - 5.0,
            0,
            "Best Case (Optimistic)"
        )
        worst_case = project_scenario(
            min(revenue_change_pct, 0.0) - 15.0,
            max(expense_change_pct, 0.0) + 12.0,
            delayed_receivables_days + 30,
            "Worst Case (Stress Test)"
        )

        # Merge monthly comparison chart data for Recharts
        comparison_chart = []
        for i in range(months):
            b_item = baseline["projections"][i]
            e_item = expected_case["projections"][i]
            bc_item = best_case["projections"][i]
            wc_item = worst_case["projections"][i]
            comparison_chart.append({
                "month_index": i + 1,
                "month_label": b_item["month_label"],
                "baseline_cash_minor": b_item["ending_cash_minor"],
                "expected_cash_minor": e_item["ending_cash_minor"],
                "best_cash_minor": bc_item["ending_cash_minor"],
                "worst_cash_minor": wc_item["ending_cash_minor"],
                "expected_net_flow_minor": e_item["net_cash_flow_minor"],
                "baseline_net_flow_minor": b_item["net_cash_flow_minor"],
            })

        return {
            "starting_cash_minor": starting_cash_minor,
            "baseline_monthly_income_minor": baseline_monthly_income,
            "baseline_monthly_expense_minor": baseline_monthly_expense,
            "horizon_months": months,
            "inputs": {
                "revenue_change_pct": revenue_change_pct,
                "expense_change_pct": expense_change_pct,
                "delayed_receivables_days": delayed_receivables_days,
                "custom_events": custom_events,
            },
            "scenarios": {
                "baseline": baseline,
                "expected_case": expected_case,
                "best_case": best_case,
                "worst_case": worst_case,
            },
            "comparison_chart": comparison_chart,
        }

    @staticmethod
    async def save_scenario(
        db: AsyncSession,
        workspace_id: str,
        name: str,
        description: Optional[str],
        parameters: Dict[str, Any],
        results: Dict[str, Any],
        user_id: Optional[str] = None
    ) -> SimulationScenario:
        scenario = SimulationScenario(
            workspace_id=workspace_id,
            name=name,
            description=description,
            parameters=parameters,
            results=results
        )
        db.add(scenario)
        await db.commit()
        await db.refresh(scenario)

        await AuditService.log_event(
            db,
            workspace_id=workspace_id,
            user_id=user_id,
            action="simulation_scenario_created",
            resource_type="simulation_scenario",
            resource_id=scenario.id,
            details={"name": name, "parameters": parameters}
        )
        return scenario

    @staticmethod
    async def list_scenarios(db: AsyncSession, workspace_id: str) -> List[SimulationScenario]:
        result = await db.execute(
            select(SimulationScenario)
            .where(SimulationScenario.workspace_id == workspace_id)
            .order_by(desc(SimulationScenario.created_at))
        )
        return result.scalars().all()

    @staticmethod
    async def delete_scenario(db: AsyncSession, workspace_id: str, scenario_id: str) -> bool:
        result = await db.execute(
            select(SimulationScenario).where(
                SimulationScenario.id == scenario_id,
                SimulationScenario.workspace_id == workspace_id
            )
        )
        item = result.scalar_one_or_none()
        if not item:
            return False
        await db.delete(item)
        await db.commit()
        return True
