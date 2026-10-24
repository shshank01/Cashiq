from pydantic import BaseModel, ConfigDict
from typing import Optional
from datetime import datetime
from app.models.payable import PayableStatus

class PayableBase(BaseModel):
    vendor_name: str
    amount_minor: int
    amount_paid_minor: int = 0
    due_date: datetime
    status: PayableStatus = PayableStatus.PENDING
    invoice_number: Optional[str] = None
    description: Optional[str] = None
    category_id: Optional[str] = None

class PayableCreate(PayableBase):
    pass

class PayableUpdate(BaseModel):
    vendor_name: Optional[str] = None
    amount_minor: Optional[int] = None
    amount_paid_minor: Optional[int] = None
    due_date: Optional[datetime] = None
    status: Optional[PayableStatus] = None
    invoice_number: Optional[str] = None
    description: Optional[str] = None
    category_id: Optional[str] = None

class PayableResponse(PayableBase):
    id: str
    workspace_id: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
