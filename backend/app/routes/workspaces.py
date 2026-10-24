from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel
from typing import Optional, List
from app.database import get_db
from app.auth.dependencies import get_current_user, verify_workspace_access
from app.models.user import User
from app.models.workspace import Workspace, WorkspaceMembership
from app.models.business_profile import BusinessProfile
from app.models.category import Category
import uuid

router = APIRouter(prefix="/workspaces", tags=["workspaces"])

DEFAULT_CATEGORIES = [
    "Payroll", "Rent", "Utilities", "Software & Services", "Office Supplies",
    "Travel", "Meals & Entertainment", "Marketing", "Insurance", "Professional Services",
    "Equipment", "Taxes", "Banking Fees", "Subscriptions", "Revenue",
    "Client Payment", "Consulting Income", "Other Income", "Other Expense", "Uncategorized",
]


class WorkspaceCreate(BaseModel):
    name: str
    currency: str = "USD"


class WorkspaceResponse(BaseModel):
    id: str
    name: str
    currency: str
    owner_id: str

    class Config:
        from_attributes = True


class OnboardingData(BaseModel):
    company_name: str
    business_type: str = "Consulting"
    industry: str = "Technology"
    business_age_months: int = 12
    approx_monthly_revenue_minor: int = 0
    approx_monthly_expenses_minor: int = 0
    employee_count: int = 1
    expected_growth_pct: float = 0.0


@router.get("", response_model=List[WorkspaceResponse])
async def list_workspaces(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Workspace)
        .join(WorkspaceMembership)
        .where(WorkspaceMembership.user_id == current_user.id)
    )
    workspaces = result.scalars().all()
    return [WorkspaceResponse.model_validate(w) for w in workspaces]


@router.post("", response_model=WorkspaceResponse, status_code=201)
async def create_workspace(
    data: WorkspaceCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    workspace = Workspace(
        id=str(uuid.uuid4()),
        name=data.name,
        currency=data.currency,
        owner_id=current_user.id,
    )
    db.add(workspace)
    await db.flush()

    membership = WorkspaceMembership(
        workspace_id=workspace.id, user_id=current_user.id, role="owner"
    )
    db.add(membership)

    # Create default categories
    for cat_name in DEFAULT_CATEGORIES:
        db.add(Category(workspace_id=workspace.id, name=cat_name))

    await db.commit()
    await db.refresh(workspace)
    return WorkspaceResponse.model_validate(workspace)


@router.get("/{wid}", response_model=WorkspaceResponse)
async def get_workspace(
    wid: str,
    ctx: dict = Depends(verify_workspace_access),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Workspace).where(Workspace.id == wid))
    workspace = result.scalar_one_or_none()
    if not workspace:
        raise HTTPException(status_code=404, detail="Workspace not found")
    return WorkspaceResponse.model_validate(workspace)


@router.put("/{wid}", response_model=WorkspaceResponse)
async def update_workspace(
    wid: str,
    data: WorkspaceCreate,
    ctx: dict = Depends(verify_workspace_access),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Workspace).where(Workspace.id == wid))
    workspace = result.scalar_one_or_none()
    if not workspace:
        raise HTTPException(status_code=404, detail="Workspace not found")
    workspace.name = data.name
    workspace.currency = data.currency
    await db.commit()
    await db.refresh(workspace)
    return WorkspaceResponse.model_validate(workspace)


@router.post("/{wid}/onboarding")
async def submit_onboarding(
    wid: str,
    data: OnboardingData,
    ctx: dict = Depends(verify_workspace_access),
    db: AsyncSession = Depends(get_db),
):
    # Check if profile already exists
    result = await db.execute(
        select(BusinessProfile).where(BusinessProfile.workspace_id == wid)
    )
    profile = result.scalar_one_or_none()

    if profile:
        for key, value in data.model_dump().items():
            setattr(profile, key, value)
    else:
        profile = BusinessProfile(workspace_id=wid, **data.model_dump())
        db.add(profile)

    await db.commit()
    return {"ok": True, "message": "Business profile saved"}
