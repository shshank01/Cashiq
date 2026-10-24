from pydantic import BaseModel, ConfigDict
from typing import Optional, Dict, Any
from datetime import datetime

class BusinessProfileBase(BaseModel):
    company_name: str
    industry: Optional[str] = None
    tax_id: Optional[str] = None
    address: Optional[str] = None
    settings: Optional[Dict[str, Any]] = None

class BusinessProfileCreate(BusinessProfileBase):
    pass

class BusinessProfileUpdate(BaseModel):
    company_name: Optional[str] = None
    industry: Optional[str] = None
    tax_id: Optional[str] = None
    address: Optional[str] = None
    settings: Optional[Dict[str, Any]] = None

class BusinessProfileResponse(BusinessProfileBase):
    id: str
    workspace_id: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
