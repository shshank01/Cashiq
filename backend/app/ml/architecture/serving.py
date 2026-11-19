"""
Component 10: Model Serving
Provides high-performance inference APIs and REST endpoints to the FastAPI backend.
"""

import json
from datetime import datetime
from typing import Dict, Any, List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.ml.architecture.orchestrator import ml_orchestrator
from app.ml.forecaster import forecaster_instance
from app.models.transaction import Transaction
from app.models.workspace import Workspace


class ModelServing:
    def predict_category(
        self,
        text: str,
        workspace_id: Optional[str] = None,
        merchant: Optional[str] = None,
        workspace_merchant_map: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        """Serves real-time transaction category prediction."""
        return ml_orchestrator.predict_category(
            text,
            workspace_id=workspace_id,
            merchant=merchant,
            workspace_merchant_map=workspace_merchant_map,
        )

    def analyze_anomaly(
        self,
        amount_minor: int,
        category: str,
        merchant: Optional[str] = None,
        historical_transactions: Optional[List[Any]] = None,
        date: Optional[datetime] = None,
        transaction_type: str = "expense",
        currency: str = "USD",
        feedback_status: Optional[str] = None,
        workspace_id: Optional[str] = None,
        business_profile: Optional[Any] = None,
        description: Optional[str] = None,
        learned_profiles: Optional[List[Dict[str, Any]]] = None,
        workspace_currency: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Serves real-time business-context-aware multivariate anomaly detection."""
        return ml_orchestrator.detect_anomaly(
            current_amount_minor=amount_minor,
            category=category,
            merchant=merchant,
            historical_transactions=historical_transactions,
            date=date,
            transaction_type=transaction_type,
            currency=currency,
            feedback_status=feedback_status,
            workspace_id=workspace_id,
            business_profile=business_profile,
            description=description,
            learned_profiles=learned_profiles,
            workspace_currency=workspace_currency,
        )

    def generate_forecast(
        self,
        current_cash_minor: int,
        transactions: List[Any],
        business_profile: Optional[Any] = None,
        known_payables: Optional[List[Any]] = None,
        known_receivables: Optional[List[Any]] = None,
        forecast_days: int = 30
    ) -> Dict[str, Any]:
        """Serves cash flow time-series forecasting with cold-start fallback."""
        return forecaster_instance.forecast_cash_flow(
            current_cash_minor=current_cash_minor,
            transactions=transactions,
            business_profile=business_profile,
            known_payables=known_payables,
            known_receivables=known_receivables,
            forecast_days=forecast_days
        )

    async def scan_workspace_anomalies(
        self,
        db: AsyncSession,
        workspace_id: str
    ) -> Dict[str, Any]:
        """
        Batch-scans all transactions in a workspace using business-context-aware
        multivariate detection, updating records and structured explainable factors.
        """
        ctx = await ml_orchestrator.load_workspace_context(db, workspace_id)
        ws_res = await db.execute(select(Workspace).where(Workspace.id == workspace_id))
        ws = ws_res.scalar_one_or_none()
        ws_currency = ws.currency if ws else None

        res = await db.execute(
            select(Transaction).where(Transaction.workspace_id == workspace_id).order_by(Transaction.date.desc())
        )
        txs = res.scalars().all()

        flagged_count = 0
        resolved_count = 0
        alert_type_counts: Dict[str, int] = {}

        for t in txs:
            if getattr(t, 'anomaly_feedback_status', None) == 'legitimate':
                resolved_count += 1
                continue

            other_txs = [ot for ot in txs if ot.id != t.id]
            analysis = self.analyze_anomaly(
                amount_minor=t.amount_minor,
                category=t.category_name or "Miscellaneous",
                merchant=t.merchant,
                historical_transactions=other_txs,
                date=t.date,
                transaction_type=t.type,
                currency=t.currency,
                feedback_status=t.anomaly_feedback_status,
                workspace_id=workspace_id,
                business_profile=ctx["business_profile"],
                description=t.description,
                learned_profiles=ctx["learned_profiles"],
                workspace_currency=ws_currency,
            )

            t.is_anomaly = analysis["is_anomaly"]
            t.anomaly_score = analysis["anomaly_score"]
            t.anomaly_severity = analysis["severity"]
            t.anomaly_reason = analysis["reason"]
            t.anomaly_explanation = json.dumps(analysis.get("explanation_details", {}))
            if t.is_anomaly:
                flagged_count += 1
                atype = analysis.get("alert_type", "multivariate")
                alert_type_counts[atype] = alert_type_counts.get(atype, 0) + 1

        await db.commit()
        return {
            "total_scanned": len(txs),
            "flagged_anomalies": flagged_count,
            "resolved_by_feedback": resolved_count,
            "alert_types": alert_type_counts,
        }


model_serving = ModelServing()
