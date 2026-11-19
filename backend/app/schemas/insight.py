from pydantic import BaseModel, ConfigDict
from typing import Optional, Dict, Any
from datetime import datetime

class InsightBase(BaseModel):
    title: str
    content: str
    insight_type: str
    metadata_json: Optional[Dict[str, Any]] = None
    is_read: str = "FALSE"

class InsightCreate(InsightBase):
    pass

class InsightUpdate(BaseModel):
    title: Optional[str] = None
    content: Optional[str] = None
    insight_type: Optional[str] = None
    metadata_json: Optional[Dict[str, Any]] = None
    is_read: Optional[str] = None

class InsightResponse(InsightBase):
    id: str
    workspace_id: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
