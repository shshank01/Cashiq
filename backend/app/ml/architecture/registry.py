"""
Component 8: Model Registry
Maintains model versions, metadata, hyperparameters, and active status
for Categorizer, Anomaly Detector, and Cash Flow Forecaster models.
"""

from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
import json
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, desc

from app.models.ml_ground_truth import MLModelRegistryEntry


class ModelRegistry:
    def __init__(self):
        # Default in-memory active versions
        self._active_versions = {
            "categorizer": "v1.3.0-context-tfidf-logreg",
            "anomaly_detector": "v3.0.0-business-context-multivariate",
            "forecaster": "v1.0.0-exponential-smoothing-holtwinters"
        }

    def get_active_version(self, model_name: str) -> str:
        return self._active_versions.get(model_name, "v1.0.0")

    def set_active_version(self, model_name: str, version: str):
        self._active_versions[model_name] = version

    async def register_model(
        self,
        db: AsyncSession,
        model_name: str,
        model_version: str,
        metrics: Dict[str, Any],
        parameters: Optional[Dict[str, Any]] = None,
        workspace_id: Optional[str] = None,
        status: str = "active"
    ) -> Dict[str, Any]:
        """Registers a new model version in the database registry."""
        entry = MLModelRegistryEntry(
            workspace_id=workspace_id,
            model_name=model_name,
            model_version=model_version,
            status=status,
            metrics_json=json.dumps(metrics),
            parameters_json=json.dumps(parameters or {}),
            created_at=datetime.now(timezone.utc)
        )
        db.add(entry)
        await db.commit()
        await db.refresh(entry)

        if status == "active":
            self.set_active_version(model_name, model_version)

        return {
            "id": entry.id,
            "model_name": entry.model_name,
            "model_version": entry.model_version,
            "status": entry.status,
            "created_at": entry.created_at.isoformat()
        }

    async def list_models(
        self,
        db: AsyncSession,
        model_name: Optional[str] = None,
        workspace_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Lists registered models and versions."""
        q = select(MLModelRegistryEntry)
        if model_name:
            q = q.where(MLModelRegistryEntry.model_name == model_name)
        if workspace_id:
            q = q.where(MLModelRegistryEntry.workspace_id == workspace_id)
        q = q.order_by(desc(MLModelRegistryEntry.created_at)).limit(50)

        res = await db.execute(q)
        items = res.scalars().all()
        return [
            {
                "id": m.id,
                "model_name": m.model_name,
                "model_version": m.model_version,
                "status": m.status,
                "metrics": json.loads(m.metrics_json) if m.metrics_json else {},
                "parameters": json.loads(m.parameters_json) if m.parameters_json else {},
                "created_at": m.created_at.isoformat() if m.created_at else None
            }
            for m in items
        ]


model_registry = ModelRegistry()
