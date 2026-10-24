import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, Integer, Float, DateTime, ForeignKey, JSON
from sqlalchemy.orm import relationship
from app.database import Base

def generate_uuid():
    return str(uuid.uuid4())

def utc_now():
    return datetime.now(timezone.utc)

class Forecast(Base):
    __tablename__ = "forecasts"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    workspace_id = Column(String(36), ForeignKey("workspaces.id"), nullable=False, index=True)
    forecast_type = Column(String(50), default="forecast", nullable=False) # 'estimated', 'projected', 'forecast'
    current_balance_minor = Column(Integer, default=0, nullable=False)
    projected_balance_30d_minor = Column(Integer, default=0, nullable=False)
    lowest_balance_30d_minor = Column(Integer, default=0, nullable=False)
    data = Column(JSON, nullable=False) # Daily forecasts, summary, metrics, model_info
    metrics_mae = Column(Float, nullable=True)
    metrics_rmse = Column(Float, nullable=True)
    method = Column(String(100), default="exponential_smoothing", nullable=False)
    data_points_used = Column(Integer, default=0, nullable=False)
    created_at = Column(DateTime, default=utc_now, nullable=False)

    workspace = relationship("Workspace", back_populates="forecasts")
