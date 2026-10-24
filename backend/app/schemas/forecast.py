from pydantic import BaseModel, ConfigDict
from typing import Any, Dict, Optional
from datetime import datetime

class ForecastBase(BaseModel):
    name: str
    start_date: datetime
    end_date: datetime
    data: Dict[str, Any]

class ForecastCreate(ForecastBase):
    pass

class ForecastUpdate(BaseModel):
    name: Optional[str] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    data: Optional[Dict[str, Any]] = None

class ForecastResponse(ForecastBase):
    id: str
    workspace_id: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
