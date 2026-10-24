from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel
from typing import Optional
from datetime import datetime, timezone
from app.database import get_db
from app.auth.dependencies import verify_workspace_access
from app.models.receivable import Receivable
import uuid

router = APIRouter(prefix="/workspaces/{wid}/receivables", tags=["receivables"])


class ReceivableCreate(BaseModel):
    client: str
    description: Optional[str] = None
    amount_minor: int
    currency: str = "USD"
    due_date: datetime
    status: str = "pending"


class ReceivableResponse(BaseModel):
    id: str
    workspace_id: str
    client: str
    description: Optional[str] = None
    amount_minor: int
    amount_received_minor: int
    currency: str
    due_date: datetime
    status: str
    created_at: datetime

    class Config:
        from_attributes = True


@router.get("")
async def list_receivables(
    wid: str,
    status: Optional[str] = None,
    ctx: dict = Depends(verify_workspace_access),
    db: AsyncSession = Depends(get_db),
):
    query = select(Receivable).where(Receivable.workspace_id == wid)
    if status:
        query = query.where(Receivable.status == status)
    query = query.order_by(Receivable.due_date.asc())
    result = await db.execute(query)
    receivables = result.scalars().all()

    now = datetime.now(timezone.utc)
    total = sum(r.amount_minor - r.amount_received_minor for r in receivables if r.status != "received")
    upcoming = sum(
        r.amount_minor - r.amount_received_minor
        for r in receivables if r.status == "pending" and r.due_date >= now
    )
    overdue = sum(
        r.amount_minor - r.amount_received_minor
        for r in receivables if r.status != "received" and r.due_date < now
    )

    return {
        "receivables": [ReceivableResponse.model_validate(r) for r in receivables],
        "summary": {
            "total_minor": total,
            "upcoming_minor": upcoming,
            "overdue_minor": overdue,
        },
    }


@router.post("", status_code=201)
async def create_receivable(
    wid: str,
    data: ReceivableCreate,
    ctx: dict = Depends(verify_workspace_access),
    db: AsyncSession = Depends(get_db),
):
    receivable = Receivable(
        id=str(uuid.uuid4()),
        workspace_id=wid,
        **data.model_dump(),
    )
    db.add(receivable)
    await db.commit()
    await db.refresh(receivable)
    return ReceivableResponse.model_validate(receivable)


@router.put("/{rid}")
async def update_receivable(
    wid: str, rid: str,
    data: ReceivableCreate,
    ctx: dict = Depends(verify_workspace_access),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Receivable).where(Receivable.id == rid, Receivable.workspace_id == wid)
    )
    recv = result.scalar_one_or_none()
    if not recv:
        raise HTTPException(status_code=404, detail="Receivable not found")
    for key, value in data.model_dump().items():
        setattr(recv, key, value)
    await db.commit()
    await db.refresh(recv)
    return ReceivableResponse.model_validate(recv)


@router.delete("/{rid}")
async def delete_receivable(
    wid: str, rid: str,
    ctx: dict = Depends(verify_workspace_access),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Receivable).where(Receivable.id == rid, Receivable.workspace_id == wid)
    )
    recv = result.scalar_one_or_none()
    if not recv:
        raise HTTPException(status_code=404, detail="Receivable not found")
    await db.delete(recv)
    await db.commit()
    return {"ok": True}


@router.post("/{rid}/mark-received")
async def mark_received(
    wid: str, rid: str,
    ctx: dict = Depends(verify_workspace_access),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Receivable).where(Receivable.id == rid, Receivable.workspace_id == wid)
    )
    recv = result.scalar_one_or_none()
    if not recv:
        raise HTTPException(status_code=404, detail="Receivable not found")
    recv.status = "received"
    recv.amount_received_minor = recv.amount_minor
    await db.commit()
    await db.refresh(recv)
    return ReceivableResponse.model_validate(recv)
