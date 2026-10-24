import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, Integer, Float, DateTime, ForeignKey, JSON
from sqlalchemy.orm import relationship
from app.database import Base

def generate_uuid():
    return str(uuid.uuid4())

def utc_now():
    return datetime.now(timezone.utc)

class BusinessProfile(Base):
    __tablename__ = "business_profiles"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    workspace_id = Column(String(36), ForeignKey("workspaces.id"), nullable=False, unique=True, index=True)
    company_name = Column(String(255), nullable=False)
    business_type = Column(String(100), default="B2B SaaS", nullable=False) # SaaS, Agency, E-commerce, Retail, Healthcare, Consulting
    industry = Column(String(100), default="Technology", nullable=False)
    business_age_months = Column(Integer, default=12, nullable=False)
    approx_monthly_revenue_minor = Column(Integer, default=2500000, nullable=False) # in cents
    approx_monthly_expenses_minor = Column(Integer, default=1800000, nullable=False) # in cents
    employee_count = Column(Integer, default=5, nullable=False)
    major_recurring_expenses = Column(JSON, nullable=True) # list of items
    expected_growth_pct = Column(Float, default=10.0, nullable=False) # % monthly growth
    known_future_payments_minor = Column(Integer, default=500000, nullable=False)
    expected_receivables_minor = Column(Integer, default=800000, nullable=False)
    created_at = Column(DateTime, default=utc_now, nullable=False)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now, nullable=False)

    workspace = relationship("Workspace", back_populates="business_profile")
