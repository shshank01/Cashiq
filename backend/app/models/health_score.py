import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, Integer, Float, DateTime, ForeignKey, JSON
from sqlalchemy.orm import relationship
from app.database import Base

def generate_uuid():
    return str(uuid.uuid4())

def utc_now():
    return datetime.now(timezone.utc)

class HealthScoreRecord(Base):
    __tablename__ = "health_score_records"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    workspace_id = Column(String(36), ForeignKey("workspaces.id"), nullable=False, index=True)
    overall_score = Column(Integer, nullable=False)  # 0-100
    grade = Column(String(5), nullable=False)        # A+, A, B, C, D, F
    cash_flow_stability_score = Column(Float, nullable=False)
    expense_to_revenue_score = Column(Float, nullable=False)
    cash_reserves_score = Column(Float, nullable=False)
    receivables_health_score = Column(Float, nullable=False)
    payables_load_score = Column(Float, nullable=False)
    factors = Column(JSON, nullable=False)
    historical_trend = Column(JSON, nullable=True)
    suggestions = Column(JSON, nullable=True)
    drivers = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=utc_now, nullable=False)

    workspace = relationship("Workspace", back_populates="health_scores")
