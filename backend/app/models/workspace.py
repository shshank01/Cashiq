import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from app.database import Base

def generate_uuid():
    return str(uuid.uuid4())

def utc_now():
    return datetime.now(timezone.utc)

class Workspace(Base):
    __tablename__ = "workspaces"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    name = Column(String(255), nullable=False)
    currency = Column(String(3), default="USD", nullable=False)
    owner_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, default=utc_now, nullable=False)

    owner = relationship("User", back_populates="owned_workspaces")
    memberships = relationship("WorkspaceMembership", back_populates="workspace", cascade="all, delete-orphan")
    accounts = relationship("Account", back_populates="workspace", cascade="all, delete-orphan")
    categories = relationship("Category", back_populates="workspace", cascade="all, delete-orphan")
    transactions = relationship("Transaction", back_populates="workspace", cascade="all, delete-orphan")
    payables = relationship("Payable", back_populates="workspace", cascade="all, delete-orphan")
    receivables = relationship("Receivable", back_populates="workspace", cascade="all, delete-orphan")
    recurrings = relationship("RecurringRule", back_populates="workspace", cascade="all, delete-orphan")
    forecasts = relationship("Forecast", back_populates="workspace", cascade="all, delete-orphan")
    insights = relationship("Insight", back_populates="workspace", cascade="all, delete-orphan")
    documents = relationship("Document", back_populates="workspace", cascade="all, delete-orphan")
    audits = relationship("Audit", back_populates="workspace", cascade="all, delete-orphan")
    business_profile = relationship("BusinessProfile", back_populates="workspace", uselist=False, cascade="all, delete-orphan")

class WorkspaceMembership(Base):
    __tablename__ = "workspace_memberships"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    workspace_id = Column(String(36), ForeignKey("workspaces.id"), nullable=False, index=True)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    role = Column(String(50), default="owner", nullable=False) # owner, admin, member, viewer
    created_at = Column(DateTime, default=utc_now, nullable=False)

    workspace = relationship("Workspace", back_populates="memberships")
    user = relationship("User", back_populates="memberships")
