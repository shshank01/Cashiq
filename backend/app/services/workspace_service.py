from typing import Dict, Any, List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.workspace import Workspace, WorkspaceMembership
from app.models.business_profile import BusinessProfile
from app.models.account import Account
from app.models.category import Category
from app.ml.business_taxonomy import derive_initial_expense_profile


def _serialize_business_profile(prof: BusinessProfile) -> Dict[str, Any]:
    derived = derive_initial_expense_profile(
        industry=prof.industry,
        business_type=prof.business_type,
        operating_model=getattr(prof, "operating_model", None),
        custom_categories=getattr(prof, "relevant_expense_categories", None),
    )
    return {
        "id": prof.id,
        "workspace_id": prof.workspace_id,
        "company_name": prof.company_name,
        "business_type": prof.business_type,
        "industry": prof.industry,
        "operating_model": getattr(prof, "operating_model", None) or "B2B",
        "relevant_expense_categories": derived,
        "business_age_months": prof.business_age_months,
        "approx_monthly_revenue_minor": prof.approx_monthly_revenue_minor,
        "approx_monthly_expenses_minor": prof.approx_monthly_expenses_minor,
        "employee_count": prof.employee_count,
        "expected_growth_pct": prof.expected_growth_pct,
        "major_recurring_expenses": prof.major_recurring_expenses,
        "known_future_payments_minor": prof.known_future_payments_minor,
        "expected_receivables_minor": prof.expected_receivables_minor,
    }


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

        acct = Account(
            workspace_id=ws.id,
            name="Primary Checking",
            account_type="checking",
            balance_minor=0,
            currency=ws.currency
        )
        db.add(acct)

        default_categories = [
            "Software & Cloud Services", "Payroll & Wages", "Rent & Facilities",
            "Marketing & Advertising", "Professional & Legal", "Meals & Entertainment",
            "Office Supplies & Equipment", "Travel & Transportation", "Utilities & Telecom",
            "Taxes & Compliance", "Insurance", "Banking & Fees", "Equipment & Hardware",
            "Shipping & Logistics", "Inventory & Raw Materials", "Groceries & Ingredients",
            "Client Revenue", "Loans & Financing", "Miscellaneous"
        ]
        for c in default_categories:
            db.add(Category(workspace_id=ws.id, name=c))

        business_type = data.get("business_type", "B2B SaaS")
        industry = data.get("industry", "Technology")
        operating_model = data.get("operating_model", "B2B")
        rel_cats = derive_initial_expense_profile(
            industry=industry,
            business_type=business_type,
            operating_model=operating_model,
            custom_categories=data.get("relevant_expense_categories"),
        )

        prof = BusinessProfile(
            workspace_id=ws.id,
            company_name=ws.name,
            business_type=business_type,
            industry=industry,
            operating_model=operating_model,
            relevant_expense_categories=rel_cats,
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
    async def get_business_profile(db: AsyncSession, workspace_id: str) -> Dict[str, Any]:
        prof_res = await db.execute(select(BusinessProfile).where(BusinessProfile.workspace_id == workspace_id))
        prof = prof_res.scalar_one_or_none()
        if not prof:
            ws_res = await db.execute(select(Workspace).where(Workspace.id == workspace_id))
            ws = ws_res.scalar_one_or_none()
            return {
                "workspace_id": workspace_id,
                "company_name": ws.name if ws else "Business",
                "business_type": None,
                "industry": None,
                "operating_model": None,
                "relevant_expense_categories": derive_initial_expense_profile(),
                "configured": False,
            }
        data = _serialize_business_profile(prof)
        data["configured"] = True
        return data

    @staticmethod
    async def update_onboarding(db: AsyncSession, workspace_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
        prof_res = await db.execute(select(BusinessProfile).where(BusinessProfile.workspace_id == workspace_id))
        prof = prof_res.scalar_one_or_none()
        ws_res = await db.execute(select(Workspace).where(Workspace.id == workspace_id))
        ws = ws_res.scalar_one()

        if not prof:
            prof = BusinessProfile(workspace_id=workspace_id, company_name=data.get("company_name") or ws.name)
            db.add(prof)

        if "company_name" in data and data["company_name"]:
            prof.company_name = data["company_name"]
        if "business_type" in data and data["business_type"]:
            prof.business_type = data["business_type"]
        if "industry" in data and data["industry"]:
            prof.industry = data["industry"]
        if "operating_model" in data and data["operating_model"]:
            prof.operating_model = data["operating_model"]
        if "business_age_months" in data:
            prof.business_age_months = int(data["business_age_months"])
        if "approx_monthly_revenue_minor" in data:
            prof.approx_monthly_revenue_minor = int(data["approx_monthly_revenue_minor"])
        if "approx_monthly_expenses_minor" in data:
            prof.approx_monthly_expenses_minor = int(data["approx_monthly_expenses_minor"])
        if "employee_count" in data:
            prof.employee_count = int(data["employee_count"])
        if "expected_growth_pct" in data:
            prof.expected_growth_pct = float(data["expected_growth_pct"])
        if "major_recurring_expenses" in data:
            prof.major_recurring_expenses = data["major_recurring_expenses"]
        if "known_future_payments_minor" in data:
            prof.known_future_payments_minor = int(data["known_future_payments_minor"])
        if "expected_receivables_minor" in data:
            prof.expected_receivables_minor = int(data["expected_receivables_minor"])

        # Re-derive relevant expense categories from updated industry/type/model while preserving learned categories
        custom_cats = data.get("relevant_expense_categories") or getattr(prof, "relevant_expense_categories", None)
        prof.relevant_expense_categories = derive_initial_expense_profile(
            industry=prof.industry,
            business_type=prof.business_type,
            operating_model=getattr(prof, "operating_model", None),
            custom_categories=custom_cats if isinstance(custom_cats, dict) else None,
        )

        await db.commit()
        await db.refresh(prof)

        return {
            "workspace": {
                "id": ws.id,
                "name": ws.name,
                "currency": ws.currency
            },
            "profile": _serialize_business_profile(prof)
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
