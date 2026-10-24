from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel
from typing import Optional
from app.database import get_db
from app.auth.dependencies import verify_workspace_access
from app.models.account import Account
import uuid

router = APIRouter(prefix="/workspaces/{wid}/accounts", tags=["accounts"])


class AccountCreate(BaseModel):
    name: str
    account_type: str = "checking"
    balance_minor: int = 0
    currency: str = "USD"


class AccountResponse(BaseModel):
    id: str
    workspace_id: str
    name: str
    account_type: str
    balance_minor: int
    currency: str
    is_active: bool

    class Config:
        from_attributes = True


@router.get("")
async def list_accounts(
    wid: str,
    ctx: dict = Depends(verify_workspace_access),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Account).where(Account.workspace_id == wid).order_by(Account.name)
    )
    accounts = result.scalars().all()
    return [AccountResponse.model_validate(a) for a in accounts]


@router.post("", status_code=201)
async def create_account(
    wid: str,
    data: AccountCreate,
    ctx: dict = Depends(verify_workspace_access),
    db: AsyncSession = Depends(get_db),
):
    account = Account(
        id=str(uuid.uuid4()),
        workspace_id=wid,
        **data.model_dump(),
    )
    db.add(account)
    await db.commit()
    await db.refresh(account)
    return AccountResponse.model_validate(account)
