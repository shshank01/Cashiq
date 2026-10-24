from typing import Dict, Any, List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.workspace import Workspace, WorkspaceMembership
from app.models.business_profile import BusinessProfile
from app.models.account import Account
from app.models.category import Category

class WorkspaceService:
    @staticmethod
    async def list_user_workspaces(db: AsyncSession, user_id: str) -> List[Dict[str, Any]]:
        res = await db.execute(
            select(WorkspaceMembership, Workspace)
            .join(Workspace, WorkspaceMembership.workspace_id == Workspace.id)
            .where(WorkspaceMembership.user_id == user_id)
        )
        workspaces = []
        for mem, ws in res.all():
            workspaces.append({
                "id": ws.id,
                "name": ws.name,
                "currency": ws.currency,
                "role": mem.role,
                "created_at": ws.created_at.isoformat()
            })
        return workspaces

    @staticmethod
    async def create_workspace(db: AsyncSession, user_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
        ws = Workspace(
            name=data.get("name", "New Business"),
            currency=data.get("currency", "USD"),
            owner_id=user_id
        )
        db.add(ws)
        await db.flush()

        mem = WorkspaceMembership(
            workspace_id=ws.id,
            user_id=user_id,
            role="owner"
        )
        db.add(mem)

        # Create checking account
        acct = Account(
            workspace_id=ws.id,
            name="Primary Checking",
            account_type="checking",
            balance_minor=0,
            currency=ws.currency
        )
        db.add(acct)

        # Standard categories
        default_categories = [
            "Software & Cloud Services", "Payroll & Wages", "Rent & Facilities",
            "Marketing & Advertising", "Professional & Legal", "Meals & Entertainment",
            "Office Supplies & Equipment", "Travel & Transportation", "Client Revenue",
            "Loans & Financing", "Miscellaneous"
        ]
        for c in default_categories:
            db.add(Category(workspace_id=ws.id, name=c))

        prof = BusinessProfile(
            workspace_id=ws.id,
            company_name=ws.name,
            business_type=data.get("business_type", "B2B SaaS"),
            industry=data.get("industry", "Technology"),
            approx_monthly_revenue_minor=int(data.get("approx_monthly_revenue_minor", 2000000)),
            approx_monthly_expenses_minor=int(data.get("approx_monthly_expenses_minor", 1500000)),
            employee_count=int(data.get("employee_count", 3))
        )
        db.add(prof)

        await db.commit()
        await db.refresh(ws)
        return {
            "id": ws.id,
            "name": ws.name,
            "currency": ws.currency,
            "role": "owner",
            "created_at": ws.created_at.isoformat()
        }

    @staticmethod
    async def update_onboarding(db: AsyncSession, workspace_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
        prof_res = await db.execute(select(BusinessProfile).where(BusinessProfile.workspace_id == workspace_id))
        prof = prof_res.scalar_one_or_none()
        if not prof:
            prof = BusinessProfile(workspace_id=workspace_id, company_name="Business")
            db.add(prof)

        if "business_type" in data: prof.business_type = data["business_type"]
        if "industry" in data: prof.industry = data["industry"]
        if "business_age_months" in data: prof.business_age_months = int(data["business_age_months"])
        if "approx_monthly_revenue_minor" in data: prof.approx_monthly_revenue_minor = int(data["approx_monthly_revenue_minor"])
        if "approx_monthly_expenses_minor" in data: prof.approx_monthly_expenses_minor = int(data["approx_monthly_expenses_minor"])
        if "employee_count" in data: prof.employee_count = int(data["employee_count"])
        if "expected_growth_pct" in data: prof.expected_growth_pct = float(data["expected_growth_pct"])
        if "major_recurring_expenses" in data: prof.major_recurring_expenses = data["major_recurring_expenses"]
        if "known_future_payments_minor" in data: prof.known_future_payments_minor = int(data["known_future_payments_minor"])
        if "expected_receivables_minor" in data: prof.expected_receivables_minor = int(data["expected_receivables_minor"])

        await db.commit()
        await db.refresh(prof)

        ws_res = await db.execute(select(Workspace).where(Workspace.id == workspace_id))
        ws = ws_res.scalar_one()

        return {
            "workspace": {
                "id": ws.id,
                "name": ws.name,
                "currency": ws.currency
            },
            "profile": {
                "id": prof.id,
                "workspace_id": prof.workspace_id,
                "business_type": prof.business_type,
                "industry": prof.industry,
                "business_age_months": prof.business_age_months,
                "approx_monthly_revenue_minor": prof.approx_monthly_revenue_minor,
                "approx_monthly_expenses_minor": prof.approx_monthly_expenses_minor,
                "employee_count": prof.employee_count,
                "expected_growth_pct": prof.expected_growth_pct
            }
        }

    @staticmethod
    async def update_workspace(db: AsyncSession, workspace_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
        ws_res = await db.execute(select(Workspace).where(Workspace.id == workspace_id))
        ws = ws_res.scalar_one_or_none()
        if not ws:
            return {"error": "Workspace not found"}
        if "currency" in data:
            ws.currency = data["currency"]
        if "name" in data:
            ws.name = data["name"]
        await db.commit()
        await db.refresh(ws)
        return {
            "id": ws.id,
            "name": ws.name,
            "currency": ws.currency,
            "created_at": ws.created_at.isoformat()
        }

