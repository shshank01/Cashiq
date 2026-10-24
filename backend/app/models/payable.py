import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, Integer, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from app.database import Base

def generate_uuid():
    return str(uuid.uuid4())

def utc_now():
    return datetime.now(timezone.utc)

class Payable(Base):
    __tablename__ = "payables"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    workspace_id = Column(String(36), ForeignKey("workspaces.id"), nullable=False, index=True)
    vendor = Column(String(255), nullable=False)
    description = Column(String(500), nullable=True)
    amount_minor = Column(Integer, nullable=False)
    amount_paid_minor = Column(Integer, default=0, nullable=False)
    currency = Column(String(3), default="USD", nullable=False)
    due_date = Column(DateTime, nullable=False)
    status = Column(String(50), default="pending", nullable=False) # pending, paid, overdue
    category_id = Column(String(36), ForeignKey("categories.id"), nullable=True)
    created_at = Column(DateTime, default=utc_now, nullable=False)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now, nullable=False)

    workspace = relationship("Workspace", back_populates="payables")
    category = relationship("Category")
