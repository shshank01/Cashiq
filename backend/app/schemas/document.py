from pydantic import BaseModel, ConfigDict
from typing import Optional
from datetime import datetime

class DocumentBase(BaseModel):
    filename: str
    file_path: str
    mime_type: str
    size_bytes: int
    document_type: Optional[str] = None
    reference_id: Optional[str] = None

class DocumentCreate(DocumentBase):
    pass

class DocumentUpdate(BaseModel):
    filename: Optional[str] = None
    file_path: Optional[str] = None
    mime_type: Optional[str] = None
    size_bytes: Optional[int] = None
    document_type: Optional[str] = None
    reference_id: Optional[str] = None

class DocumentResponse(DocumentBase):
    id: str
    workspace_id: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
