import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, Integer, Float, DateTime, ForeignKey, Boolean
from sqlalchemy.orm import relationship
from app.database import Base

def generate_uuid():
    return str(uuid.uuid4())

def utc_now():
    return datetime.now(timezone.utc)

class RecurringRule(Base):
    __tablename__ = "recurring_rules"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    workspace_id = Column(String(36), ForeignKey("workspaces.id"), nullable=False, index=True)
    merchant = Column(String(255), nullable=False)
    description = Column(String(500), nullable=True)
    amount_minor = Column(Integer, nullable=False)
    currency = Column(String(3), default="USD", nullable=False)
    frequency = Column(String(50), nullable=False, default="monthly") # daily, weekly, monthly, yearly
    next_date = Column(DateTime, nullable=False)
    confidence = Column(Float, default=1.0, nullable=False)
    type = Column(String(50), default="expense", nullable=False) # income, expense
    status = Column(String(50), default="active", nullable=False) # active, paused, cancelled
    category_name = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=utc_now, nullable=False)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now, nullable=False)

    workspace = relationship("Workspace", back_populates="recurrings")
