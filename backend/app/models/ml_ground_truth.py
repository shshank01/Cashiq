import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, Integer, Float, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship
from app.database import Base


def generate_uuid():
    return str(uuid.uuid4())


def utc_now():
    return datetime.now(timezone.utc)


class MLGroundTruth(Base):
    __tablename__ = "ml_ground_truth"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    workspace_id = Column(String(36), ForeignKey("workspaces.id"), nullable=False, index=True)
    transaction_id = Column(String(36), ForeignKey("transactions.id"), nullable=False, index=True)

    feedback_type = Column(String(50), nullable=False)  # "legitimate", "suspicious", "category_correction"
    original_category = Column(String(255), nullable=True)
    verified_category = Column(String(255), nullable=True)
    original_anomaly_score = Column(Float, nullable=True)
    original_anomaly_reason = Column(String(500), nullable=True)
    user_notes = Column(Text, nullable=True)
    reviewed_by_user_id = Column(String(36), nullable=True)

    created_at = Column(DateTime, default=utc_now, nullable=False)


class BehavioralProfileModel(Base):
    __tablename__ = "ml_behavioral_profiles"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    workspace_id = Column(String(36), ForeignKey("workspaces.id"), nullable=False, index=True)

    profile_type = Column(String(50), nullable=False)  # "category", "merchant", "workspace", "type"
    profile_key = Column(String(255), nullable=False)  # e.g. "Software & Cloud Services", or merchant name
    stats_json = Column(Text, nullable=False)  # JSON serialized metrics and baselines

    created_at = Column(DateTime, default=utc_now, nullable=False)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now, nullable=False)


class MLModelRegistryEntry(Base):
    __tablename__ = "ml_model_registry"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    workspace_id = Column(String(36), nullable=True)  # None for global models, or workspace ID

    model_name = Column(String(100), nullable=False)  # "anomaly_detector", "categorizer", "forecaster"
    model_version = Column(String(100), nullable=False)
    status = Column(String(50), default="active", nullable=False)  # "active", "candidate", "retired"
    metrics_json = Column(Text, nullable=True)
    parameters_json = Column(Text, nullable=True)

    created_at = Column(DateTime, default=utc_now, nullable=False)
