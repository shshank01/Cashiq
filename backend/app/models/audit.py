import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, DateTime, ForeignKey, JSON
from sqlalchemy.orm import relationship
from app.database import Base

def generate_uuid():
    return str(uuid.uuid4())

def utc_now():
    return datetime.now(timezone.utc)

class Audit(Base):
    __tablename__ = "audit_events"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    workspace_id = Column(String(36), ForeignKey("workspaces.id"), nullable=False, index=True)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=True)
    action = Column(String(100), nullable=False) # e.g. "transaction_create", "category_corrected", "forecast_generated"
    resource_type = Column(String(100), nullable=False)
    resource_id = Column(String(36), nullable=True)
    details = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=utc_now, nullable=False)

    workspace = relationship("Workspace", back_populates="audits")
