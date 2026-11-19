from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime
from app.database import get_db
from app.auth.dependencies import verify_workspace_access
from app.models.payable import Payable
import uuid

router = APIRouter(prefix="/workspaces/{wid}/payables", tags=["payables"])


class PayableCreate(BaseModel):
    vendor: str
    description: Optional[str] = None
    amount_minor: int
    currency: str = "USD"
    due_date: datetime
    status: str = "pending"


class PayableResponse(BaseModel):
    id: str
    workspace_id: str
    vendor: str
    description: Optional[str] = None
    amount_minor: int
    amount_paid_minor: int
    currency: str
    due_date: datetime
    status: str
    created_at: datetime

    class Config:
        from_attributes = True


@router.get("")
async def list_payables(
    wid: str,
    status: Optional[str] = None,
    ctx: dict = Depends(verify_workspace_access),
    db: AsyncSession = Depends(get_db),
):
    query = select(Payable).where(Payable.workspace_id == wid)
    if status:
        query = query.where(Payable.status == status)
    query = query.order_by(Payable.due_date.asc())
    result = await db.execute(query)
    payables = result.scalars().all()

    # Summary
    total = sum(p.amount_minor - p.amount_paid_minor for p in payables if p.status != "paid")
    from datetime import timezone
    now = datetime.now(timezone.utc)
    upcoming = sum(
        p.amount_minor - p.amount_paid_minor
        for p in payables
        if p.status == "pending" and p.due_date >= now
    )
    overdue = sum(
        p.amount_minor - p.amount_paid_minor
        for p in payables
        if p.status != "paid" and p.due_date < now
    )

    return {
        "payables": [PayableResponse.model_validate(p) for p in payables],
        "summary": {
            "total_minor": total,
            "upcoming_minor": upcoming,
            "overdue_minor": overdue,
        },
    }


@router.post("", status_code=201)
async def create_payable(
    wid: str,
    data: PayableCreate,
    ctx: dict = Depends(verify_workspace_access),
    db: AsyncSession = Depends(get_db),
):
    payable = Payable(
        id=str(uuid.uuid4()),
        workspace_id=wid,
        **data.model_dump(),
    )
    db.add(payable)
    await db.commit()
    await db.refresh(payable)
    return PayableResponse.model_validate(payable)


@router.put("/{pid}")
async def update_payable(
    wid: str, pid: str,
    data: PayableCreate,
    ctx: dict = Depends(verify_workspace_access),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Payable).where(Payable.id == pid, Payable.workspace_id == wid)
    )
    payable = result.scalar_one_or_none()
    if not payable:
        raise HTTPException(status_code=404, detail="Payable not found")
    for key, value in data.model_dump().items():
        setattr(payable, key, value)
    await db.commit()
    await db.refresh(payable)
    return PayableResponse.model_validate(payable)


@router.delete("/{pid}")
async def delete_payable(
    wid: str, pid: str,
    ctx: dict = Depends(verify_workspace_access),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Payable).where(Payable.id == pid, Payable.workspace_id == wid)
    )
    payable = result.scalar_one_or_none()
    if not payable:
        raise HTTPException(status_code=404, detail="Payable not found")
    await db.delete(payable)
    await db.commit()
    return {"ok": True}


@router.post("/{pid}/mark-paid")
async def mark_paid(
    wid: str, pid: str,
    ctx: dict = Depends(verify_workspace_access),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Payable).where(Payable.id == pid, Payable.workspace_id == wid)
    )
    payable = result.scalar_one_or_none()
    if not payable:
        raise HTTPException(status_code=404, detail="Payable not found")
    payable.status = "paid"
    payable.amount_paid_minor = payable.amount_minor
    await db.commit()
    await db.refresh(payable)
    return PayableResponse.model_validate(payable)
