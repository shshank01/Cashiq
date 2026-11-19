import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, DateTime, ForeignKey, JSON, Text
from sqlalchemy.orm import relationship
from app.database import Base

def generate_uuid():
    return str(uuid.uuid4())

def utc_now():
    return datetime.now(timezone.utc)

class Document(Base):
    __tablename__ = "documents"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    workspace_id = Column(String(36), ForeignKey("workspaces.id"), nullable=False, index=True)
    filename = Column(String(255), nullable=False)
    file_path = Column(String(500), nullable=True)
    file_type = Column(String(50), nullable=False) # csv, pdf, receipt
    file_hash = Column(String(64), nullable=True, index=True) # SHA-256 content hash for caching & audit
    status = Column(String(50), default="processed", nullable=False) # processing, processed, failed
    extracted_data = Column(JSON, nullable=True) # Draft transactions extracted
    raw_text = Column(Text, nullable=True) # Preserved original extracted text for auditability
    extraction_metadata = Column(JSON, nullable=True) # Engine, timings, validation & page summary
    uploaded_at = Column(DateTime, default=utc_now, nullable=False)

    workspace = relationship("Workspace", back_populates="documents")
