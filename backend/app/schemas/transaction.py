from pydantic import BaseModel, ConfigDict
from typing import Optional, List
from datetime import datetime


class TransactionCreate(BaseModel):
    amount_minor: int
    transaction_type: str = "expense"
    date: datetime
    description: Optional[str] = None
    merchant: Optional[str] = None
    currency: str = "USD"
    account_id: Optional[str] = None
    category_name: Optional[str] = None
    notes: Optional[str] = None
    source: str = "manual"


class TransactionUpdate(BaseModel):
    amount_minor: Optional[int] = None
    transaction_type: Optional[str] = None
    date: Optional[datetime] = None
    description: Optional[str] = None
    merchant: Optional[str] = None
    currency: Optional[str] = None
    account_id: Optional[str] = None
    category_name: Optional[str] = None
    notes: Optional[str] = None


class CategoryCorrection(BaseModel):
    category_name: str


class TransactionResponse(BaseModel):
    id: str
    workspace_id: str
    account_id: Optional[str] = None
    amount_minor: int
    currency: str
    transaction_type: str
    date: datetime
    description: Optional[str] = None
    merchant: Optional[str] = None
    category_name: Optional[str] = None
    notes: Optional[str] = None
    source: str
    confidence: Optional[float] = None
    model_version: Optional[str] = None
    needs_review: bool = False
    is_confirmed: bool = False
    is_anomaly: bool = False
    anomaly_score: Optional[float] = None
    anomaly_severity: Optional[str] = None
    anomaly_reason: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class TransactionListResponse(BaseModel):
    transactions: List[TransactionResponse]
    total: int
    page: int
    per_page: int
    total_pages: int
