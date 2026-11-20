from datetime import datetime, timezone
import calendar
from typing import Any, Dict, List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func, desc

from app.models.budget import Budget, CategoryBudget
from app.models.transaction import Transaction
from app.models.category import Category
from app.services.audit_service import AuditService

class BudgetService:
    """
    Budget Management and Real-Time Variance Tracking Engine.
    Tracks monthly category spending against limits, flags overspending,
    and produces budget vs. actual analytics.
    """

    @staticmethod
    async def create_or_update_budget(
        db: AsyncSession,
        workspace_id: str,
        month: str,  # "YYYY-MM"
        name: Optional[str] = None,
        category_limits: Optional[List[Dict[str, Any]]] = None,
        total_limit_minor: Optional[int] = None,
        currency: str = "USD",
        user_id: Optional[str] = None
    ) -> Dict[str, Any]:
        category_limits = category_limits or []
        budget_name = name or f"Budget {month}"

        # Calculate total if not provided
        computed_total = sum(int(c.get("limit_minor", 0)) for c in category_limits)
        final_total = total_limit_minor if (total_limit_minor is not None and total_limit_minor > 0) else computed_total

        # Check existing
        res = await db.execute(
            select(Budget).where(Budget.workspace_id == workspace_id, Budget.month == month)
        )
        budget = res.scalar_one_or_none()

        if budget:
            budget.name = budget_name
            budget.total_limit_minor = final_total
            budget.currency = currency
            # Delete old category budgets to replace with updated list
            old_cats = await db.execute(select(CategoryBudget).where(CategoryBudget.budget_id == budget.id))
            for oc in old_cats.scalars().all():
                await db.delete(oc)
        else:
            budget = Budget(
                workspace_id=workspace_id,
                month=month,
                name=budget_name,
                total_limit_minor=final_total,
                currency=currency
            )
            db.add(budget)
            await db.flush()

        for c in category_limits:
            cat_name = c.get("category_name", "Miscellaneous")
            cat_limit = int(c.get("limit_minor", 0))
            threshold = float(c.get("alert_threshold_pct", 80.0))
            cat_id = c.get("category_id", None)

            cb = CategoryBudget(
                budget_id=budget.id,
                category_id=cat_id,
                category_name=cat_name,
                limit_minor=cat_limit,
                alert_threshold_pct=threshold
            )
            db.add(cb)

        await db.commit()
        await db.refresh(budget)

        await AuditService.log_event(
            db,
            workspace_id=workspace_id,
            user_id=user_id,
            action="budget_saved",
            resource_type="budget",
            resource_id=budget.id,
            details={"month": month, "total_limit_minor": final_total, "categories_count": len(category_limits)}
        )

        return await BudgetService.get_budget_performance(db, workspace_id, month)

    @staticmethod
    async def get_budget_performance(
        db: AsyncSession,
        workspace_id: str,
        month: Optional[str] = None
    ) -> Dict[str, Any]:
        now = datetime.now(timezone.utc)
        target_month = month or now.strftime("%Y-%m")

        # Parse year and month
        try:
            year, m_num = [int(p) for p in target_month.split("-")]
            _, last_day = calendar.monthrange(year, m_num)
            month_start = datetime(year, m_num, 1, 0, 0, 0, tzinfo=timezone.utc)
            month_end = datetime(year, m_num, last_day, 23, 59, 59, tzinfo=timezone.utc)
        except Exception:
            month_start = datetime(now.year, now.month, 1, 0, 0, 0, tzinfo=timezone.utc)
            month_end = now
            target_month = now.strftime("%Y-%m")

        # 1. Fetch budget definition
        b_res = await db.execute(
            select(Budget).where(Budget.workspace_id == workspace_id, Budget.month == target_month)
        )
        budget = b_res.scalar_one_or_none()

        budget_category_map = {}
        total_budget_limit = 0
        budget_id = None
        budget_name = f"Budget {target_month}"

        if budget:
            budget_id = budget.id
            budget_name = budget.name
            total_budget_limit = budget.total_limit_minor
            cb_res = await db.execute(
                select(CategoryBudget).where(CategoryBudget.budget_id == budget.id)
            )
            for cb in cb_res.scalars().all():
                budget_category_map[cb.category_name] = {
                    "limit_minor": cb.limit_minor,
                    "alert_threshold_pct": cb.alert_threshold_pct,
                    "category_id": cb.category_id,
                }

        # 2. Query actual expenses in the month
        tx_res = await db.execute(
            select(Transaction).where(
                Transaction.workspace_id == workspace_id,
                Transaction.type == "expense",
                Transaction.date >= month_start,
                Transaction.date <= month_end
            )
        )
        txs = tx_res.scalars().all()

        actual_by_cat: Dict[str, int] = {}
        for t in txs:
            c_name = t.category_name or "Miscellaneous"
            actual_by_cat[c_name] = actual_by_cat.get(c_name, 0) + abs(t.amount_minor)

        # Merge budgeted and unbudgeted categories
        all_categories = sorted(list(set(list(budget_category_map.keys()) + list(actual_by_cat.keys()))))
        category_performances = []
        alerts = []
        total_spent = sum(actual_by_cat.values())
        overbudget_count = 0

        for cat in all_categories:
            spent = actual_by_cat.get(cat, 0)
            b_info = budget_category_map.get(cat)
            limit = b_info["limit_minor"] if b_info else 0
            threshold = b_info["alert_threshold_pct"] if b_info else 80.0

            pct_spent = round((spent / limit) * 100.0, 1) if limit > 0 else (100.0 if spent > 0 else 0.0)
            remaining = limit - spent

            if limit > 0:
                if spent > limit:
                    status = "over_budget"
                    overbudget_count += 1
                    alerts.append({
                        "category": cat,
                        "severity": "critical",
                        "message": f"Over budget in {cat} by ${(spent - limit)/100:,.2f} ({pct_spent}% of limit spent).",
                        "spent_minor": spent,
                        "limit_minor": limit,
                    })
                elif pct_spent >= threshold:
                    status = "warning"
                    alerts.append({
                        "category": cat,
                        "severity": "warning",
                        "message": f"Approaching limit in {cat}: {pct_spent}% spent (${spent/100:,.2f} of ${(limit/100):,.2f}).",
                        "spent_minor": spent,
                        "limit_minor": limit,
                    })
                else:
                    status = "safe"
            else:
                status = "unbudgeted"
                if spent > 0:
                    alerts.append({
                        "category": cat,
                        "severity": "info",
                        "message": f"Unbudgeted spending of ${(spent/100):,.2f} recorded in {cat}.",
                        "spent_minor": spent,
                        "limit_minor": 0,
                    })

            category_performances.append({
                "category": cat,
                "limit_minor": limit,
                "spent_minor": spent,
                "remaining_minor": remaining,
                "spent_pct": pct_spent,
                "status": status,
                "has_budget": limit > 0,
            })

        # Sort: over budget first, then highest spent
        category_performances.sort(key=lambda x: (x["status"] == "over_budget", x["spent_minor"]), reverse=True)

        overall_pct = round((total_spent / total_budget_limit) * 100.0, 1) if total_budget_limit > 0 else 0.0
        overall_remaining = total_budget_limit - total_spent
        overall_status = "over_budget" if total_spent > total_budget_limit and total_budget_limit > 0 else (
            "warning" if overall_pct >= 80.0 else "safe"
        )

        # Recharts comparison chart
        comparison_chart = [
            {
                "category": cp["category"],
                "budget_minor": cp["limit_minor"],
                "actual_minor": cp["spent_minor"],
                "variance_minor": cp["limit_minor"] - cp["spent_minor"],
                "spent_pct": cp["spent_pct"],
                "status": cp["status"],
            }
            for cp in category_performances if cp["limit_minor"] > 0 or cp["spent_minor"] > 0
        ]

        return {
            "budget_id": budget_id,
            "workspace_id": workspace_id,
            "month": target_month,
            "name": budget_name,
            "total_budget_limit_minor": total_budget_limit,
            "total_spent_minor": total_spent,
            "remaining_minor": overall_remaining,
            "spent_pct": overall_pct,
            "status": overall_status,
            "overbudget_categories_count": overbudget_count,
            "category_performances": category_performances,
            "alerts": alerts,
            "comparison_chart": comparison_chart,
        }

    @staticmethod
    async def list_budgets(db: AsyncSession, workspace_id: str) -> List[Dict[str, Any]]:
        result = await db.execute(
            select(Budget).where(Budget.workspace_id == workspace_id).order_by(desc(Budget.month))
        )
        budgets = result.scalars().all()
        summaries = []
        for b in budgets:
            perf = await BudgetService.get_budget_performance(db, workspace_id, b.month)
            summaries.append({
                "id": b.id,
                "month": b.month,
                "name": b.name,
                "total_limit_minor": b.total_limit_minor,
                "total_spent_minor": perf["total_spent_minor"],
                "spent_pct": perf["spent_pct"],
                "status": perf["status"],
                "overbudget_categories_count": perf["overbudget_categories_count"],
                "created_at": b.created_at.isoformat(),
            })
        return summaries

    @staticmethod
    async def delete_budget(db: AsyncSession, workspace_id: str, budget_id: str) -> bool:
        res = await db.execute(
            select(Budget).where(Budget.id == budget_id, Budget.workspace_id == workspace_id)
        )
        b = res.scalar_one_or_none()
        if not b:
            return False
        await db.delete(b)
        await db.commit()
        return True
