from pydantic import BaseModel, ConfigDict
from typing import Optional
from datetime import datetime
from app.models.receivable import ReceivableStatus

class ReceivableBase(BaseModel):
    client_name: str
    amount_minor: int
    amount_received_minor: int = 0
    due_date: datetime
    status: ReceivableStatus = ReceivableStatus.PENDING
    invoice_number: Optional[str] = None
    description: Optional[str] = None
    category_id: Optional[str] = None

class ReceivableCreate(ReceivableBase):
    pass

class ReceivableUpdate(BaseModel):
    client_name: Optional[str] = None
    amount_minor: Optional[int] = None
    amount_received_minor: Optional[int] = None
    due_date: Optional[datetime] = None
    status: Optional[ReceivableStatus] = None
    invoice_number: Optional[str] = None
    description: Optional[str] = None
    category_id: Optional[str] = None

class ReceivableResponse(ReceivableBase):
    id: str
    workspace_id: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
