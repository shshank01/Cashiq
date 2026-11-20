import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, Integer, Float, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from app.database import Base

def generate_uuid():
    return str(uuid.uuid4())

def utc_now():
    return datetime.now(timezone.utc)

class Budget(Base):
    __tablename__ = "budgets"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    workspace_id = Column(String(36), ForeignKey("workspaces.id"), nullable=False, index=True)
    name = Column(String(255), nullable=False)
    month = Column(String(7), nullable=False, index=True)  # YYYY-MM e.g. "2026-11"
    total_limit_minor = Column(Integer, nullable=False, default=0)
    currency = Column(String(3), default="USD", nullable=False)
    created_at = Column(DateTime, default=utc_now, nullable=False)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now, nullable=False)

    workspace = relationship("Workspace", back_populates="budgets")
    category_budgets = relationship("CategoryBudget", back_populates="budget", cascade="all, delete-orphan")

class CategoryBudget(Base):
    __tablename__ = "category_budgets"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    budget_id = Column(String(36), ForeignKey("budgets.id"), nullable=False, index=True)
    category_id = Column(String(36), ForeignKey("categories.id"), nullable=True)
    category_name = Column(String(255), nullable=False)
    limit_minor = Column(Integer, nullable=False, default=0)
    alert_threshold_pct = Column(Float, default=80.0, nullable=False)  # alert when spent > 80%
    created_at = Column(DateTime, default=utc_now, nullable=False)

    budget = relationship("Budget", back_populates="category_budgets")
    category = relationship("Category")
