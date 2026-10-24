import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, Integer, Float, DateTime, ForeignKey, Boolean, Text
from sqlalchemy.orm import relationship, synonym
from app.database import Base


def generate_uuid():
    return str(uuid.uuid4())


def utc_now():
    return datetime.now(timezone.utc)


class Transaction(Base):
    __tablename__ = "transactions"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    workspace_id = Column(String(36), ForeignKey("workspaces.id"), nullable=False, index=True)
    account_id = Column(String(36), ForeignKey("accounts.id"), nullable=True)
    category_id = Column(String(36), ForeignKey("categories.id"), nullable=True)

    amount_minor = Column(Integer, nullable=False)  # integer minor units (cents)
    currency = Column(String(3), default="USD", nullable=False)
    type = Column("type", String(20), nullable=False, default="expense")  # income / expense
    transaction_type = synonym("type")

    date = Column(DateTime, nullable=False)
    description = Column(String(500), nullable=True)
    merchant = Column(String(255), nullable=True)
    notes = Column(Text, nullable=True)
    source = Column(String(50), default="manual", nullable=False)  # manual, csv, pdf, receipt, api

    # ML categorization fields
    category_name = Column(String(255), nullable=True)
    confidence = Column(Float, nullable=True)
    model_version = Column(String(50), nullable=True)
    review_required = Column(Boolean, default=False, nullable=False)
    needs_review = synonym("review_required")
    is_confirmed = Column(Boolean, default=False, nullable=False)
    verified_label = Column(String(255), nullable=True)
    verified_at = Column(DateTime, nullable=True)

    # Anomaly detection fields
    is_anomaly = Column(Boolean, default=False, nullable=False)
    anomaly_score = Column(Float, nullable=True)
    anomaly_severity = Column(String(20), nullable=True)  # low, medium, high
    anomaly_reason = Column(String(500), nullable=True)

    created_at = Column(DateTime, default=utc_now, nullable=False)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now, nullable=False)

    workspace = relationship("Workspace", back_populates="transactions")
    account = relationship("Account", back_populates="transactions")
    category = relationship("Category", back_populates="transactions")
