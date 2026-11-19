"""
Component 3: Labelizer
Maintains verified labels and distinguishes confirmed, unverified,
and model-predicted records for supervised pipelines and behavioural profiling.
"""

from enum import Enum
from typing import Dict, Any, List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_

from app.models.transaction import Transaction


class LabelStatus(str, Enum):
    UNVERIFIED = "unverified"
    MODEL_PREDICTED = "model_predicted"
    CONFIRMED = "confirmed"
    RESOLVED_LEGITIMATE = "resolved_legitimate"
    CONFIRMED_ANOMALY = "confirmed_anomaly"


class Labelizer:
    @staticmethod
    def get_transaction_label_status(tx: Any) -> LabelStatus:
        """Determines the exact labeling state of a transaction."""
        fb = getattr(tx, "anomaly_feedback_status", None)
        if fb == "legitimate":
            return LabelStatus.RESOLVED_LEGITIMATE
        elif fb == "suspicious":
            return LabelStatus.CONFIRMED_ANOMALY

        is_confirmed = getattr(tx, "is_confirmed", False)
        verified_label = getattr(tx, "verified_label", None)
        if is_confirmed or verified_label:
            return LabelStatus.CONFIRMED

        confidence = getattr(tx, "confidence", None)
        model_version = getattr(tx, "model_version", None)
        if confidence is not None or model_version:
            return LabelStatus.MODEL_PREDICTED

        return LabelStatus.UNVERIFIED

    async def get_label_audit(self, db: AsyncSession, workspace_id: str) -> Dict[str, Any]:
        """Provides a breakdown of verified vs unverified records in the workspace."""
        res = await db.execute(
            select(Transaction).where(Transaction.workspace_id == workspace_id)
        )
        txs = res.scalars().all()

        counts = {
            LabelStatus.UNVERIFIED.value: 0,
            LabelStatus.MODEL_PREDICTED.value: 0,
            LabelStatus.CONFIRMED.value: 0,
            LabelStatus.RESOLVED_LEGITIMATE.value: 0,
            LabelStatus.CONFIRMED_ANOMALY.value: 0,
        }

        for t in txs:
            status = self.get_transaction_label_status(t)
            counts[status.value] += 1

        total = len(txs)
        confirmed_total = counts[LabelStatus.CONFIRMED.value] + counts[LabelStatus.RESOLVED_LEGITIMATE.value]
        ratio = (confirmed_total / total) if total > 0 else 0.0

        return {
            "total_transactions": total,
            "counts": counts,
            "verified_ratio": round(ratio, 3),
            "is_retraining_ready": confirmed_total >= 5
        }

    async def get_training_dataset(
        self,
        db: AsyncSession,
        workspace_id: Optional[str] = None,
        only_confirmed: bool = True
    ) -> List[Dict[str, Any]]:
        """
        Extracts high-quality training pairs (text, label) for model fine-tuning.
        If only_confirmed is True, only user-confirmed labels are included.
        """
        q = select(Transaction)
        if workspace_id:
            q = q.where(Transaction.workspace_id == workspace_id)
        if only_confirmed:
            q = q.where(Transaction.is_confirmed == True, Transaction.category_name != None)

        res = await db.execute(q)
        txs = res.scalars().all()

        dataset = []
        for t in txs:
            label = t.verified_label or t.category_name
            if not label or label == "Miscellaneous":
                continue
            text = f"{t.merchant or ''} {t.description or ''}".strip()
            if text:
                dataset.append({
                    "text": text,
                    "label": label,
                    "amount_minor": t.amount_minor,
                    "type": t.type,
                    "currency": t.currency,
                    "date": t.date.isoformat() if t.date else None,
                    "source": t.source,
                    "is_confirmed": t.is_confirmed
                })
        return dataset


labelizer = Labelizer()
