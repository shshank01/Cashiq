import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, DateTime, ForeignKey, JSON
from sqlalchemy.orm import relationship
from app.database import Base

def generate_uuid():
    return str(uuid.uuid4())

def utc_now():
    return datetime.now(timezone.utc)

class SimulationScenario(Base):
    __tablename__ = "simulation_scenarios"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    workspace_id = Column(String(36), ForeignKey("workspaces.id"), nullable=False, index=True)
    name = Column(String(255), nullable=False)
    description = Column(String(500), nullable=True)
    parameters = Column(JSON, nullable=False)  # {revenue_change_pct, expense_change_pct, delayed_receivables_days, months, custom_events}
    results = Column(JSON, nullable=False)     # {baseline, best_case, expected_case, worst_case, runway_months, etc.}
    created_at = Column(DateTime, default=utc_now, nullable=False)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now, nullable=False)

    workspace = relationship("Workspace", back_populates="simulations")
