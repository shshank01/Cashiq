from pydantic import BaseModel, ConfigDict, Field
from typing import Optional
from datetime import datetime
from app.models.account import AccountType

class AccountBase(BaseModel):
    name: str
    account_type: AccountType = AccountType.BANK
    balance_minor: int = 0
    currency: str = "USD"
    is_active: bool = True

class AccountCreate(AccountBase):
    pass

class AccountUpdate(BaseModel):
    name: Optional[str] = None
    account_type: Optional[AccountType] = None
    balance_minor: Optional[int] = None
    currency: Optional[str] = None
    is_active: Optional[bool] = None

class AccountResponse(AccountBase):
    id: str
    workspace_id: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
