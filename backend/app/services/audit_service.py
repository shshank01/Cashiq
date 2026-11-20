from typing import Any, Dict, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from app.models.audit import Audit

class AuditService:
    @staticmethod
    async def log_event(
        db: AsyncSession,
        workspace_id: str,
        user_id: Optional[str],
        action: str,
        resource_type: str,
        resource_id: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ) -> Audit:
        audit = Audit(
            workspace_id=workspace_id,
            user_id=user_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            details=details or {},
        )
        db.add(audit)
        try:
            await db.flush()
        except Exception as e:
            print(f"[AuditService] Warning: could not flush audit log: {e}")
        return audit

    @staticmethod
    async def list_events(
        db: AsyncSession,
        workspace_id: str,
        limit: int = 50,
    ) -> list[Dict[str, Any]]:
        result = await db.execute(
            select(Audit)
            .where(Audit.workspace_id == workspace_id)
            .order_by(desc(Audit.created_at))
            .limit(limit)
        )
        events = result.scalars().all()
        return [
            {
                "id": e.id,
                "action": e.action,
                "resource_type": e.resource_type,
                "resource_id": e.resource_id,
                "details": e.details,
                "created_at": e.created_at.isoformat() if e.created_at else None,
                "user_id": e.user_id,
            }
            for e in events
        ]
