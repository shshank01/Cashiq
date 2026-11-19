from pydantic import BaseModel, ConfigDict
from typing import Optional, Dict, Any
from datetime import datetime

class BusinessProfileBase(BaseModel):
    company_name: str
    business_type: Optional[str] = "B2B SaaS"
    industry: Optional[str] = "Technology"
    operating_model: Optional[str] = "B2B"
    relevant_expense_categories: Optional[Dict[str, Any]] = None
    tax_id: Optional[str] = None
    address: Optional[str] = None
    settings: Optional[Dict[str, Any]] = None

class BusinessProfileCreate(BusinessProfileBase):
    pass

class BusinessProfileUpdate(BaseModel):
    company_name: Optional[str] = None
    business_type: Optional[str] = None
    industry: Optional[str] = None
    operating_model: Optional[str] = None
    relevant_expense_categories: Optional[Dict[str, Any]] = None
    tax_id: Optional[str] = None
    address: Optional[str] = None
    settings: Optional[Dict[str, Any]] = None

class BusinessProfileResponse(BusinessProfileBase):
    id: str
    workspace_id: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
