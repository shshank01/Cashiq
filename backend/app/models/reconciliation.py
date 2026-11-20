import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, Integer, DateTime, ForeignKey, JSON
from sqlalchemy.orm import relationship
from app.database import Base

def generate_uuid():
    return str(uuid.uuid4())

def utc_now():
    return datetime.now(timezone.utc)

class ReconciliationSession(Base):
    __tablename__ = "reconciliation_sessions"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    workspace_id = Column(String(36), ForeignKey("workspaces.id"), nullable=False, index=True)
    account_id = Column(String(36), ForeignKey("accounts.id"), nullable=True)
    filename = Column(String(255), nullable=False)
    total_statement_rows = Column(Integer, default=0, nullable=False)
    matched_count = Column(Integer, default=0, nullable=False)
    unmatched_bank_count = Column(Integer, default=0, nullable=False)
    unmatched_ledger_count = Column(Integer, default=0, nullable=False)
    status = Column(String(50), default="completed", nullable=False)  # completed, in_review, reconciled
    summary = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=utc_now, nullable=False)

    workspace = relationship("Workspace", back_populates="reconciliations")
    items = relationship("ReconciliationItem", back_populates="session", cascade="all, delete-orphan")

class ReconciliationItem(Base):
    __tablename__ = "reconciliation_items"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    session_id = Column(String(36), ForeignKey("reconciliation_sessions.id"), nullable=False, index=True)
    statement_date = Column(DateTime, nullable=False)
    statement_description = Column(String(500), nullable=False)
    statement_amount_minor = Column(Integer, nullable=False)  # negative for debit, positive for credit
    statement_reference = Column(String(100), nullable=True)

    transaction_id = Column(String(36), ForeignKey("transactions.id"), nullable=True)
    match_type = Column(String(50), default="unmatched_bank", nullable=False)  # exact, probable, difference, unmatched_bank, unmatched_ledger
    status = Column(String(50), default="pending", nullable=False)  # pending, approved, rejected
    discrepancy_details = Column(JSON, nullable=True)  # {amount_diff_minor, date_diff_days, reason}
    created_at = Column(DateTime, default=utc_now, nullable=False)

    session = relationship("ReconciliationSession", back_populates="items")
    transaction = relationship("Transaction")
