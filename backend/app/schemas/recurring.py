from pydantic import BaseModel, ConfigDict
from typing import Optional
from datetime import datetime
from app.models.recurring import Frequency

class RecurringBase(BaseModel):
    name: str
    amount_minor: int
    transaction_type: str
    frequency: Frequency
    next_due_date: datetime
    end_date: Optional[datetime] = None
    is_active: bool = True
    category_id: Optional[str] = None
    account_id: Optional[str] = None

class RecurringCreate(RecurringBase):
    pass

class RecurringUpdate(BaseModel):
    name: Optional[str] = None
    amount_minor: Optional[int] = None
    transaction_type: Optional[str] = None
    frequency: Optional[Frequency] = None
    next_due_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    is_active: Optional[bool] = None
    category_id: Optional[str] = None
    account_id: Optional[str] = None

class RecurringResponse(RecurringBase):
    id: str
    workspace_id: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
