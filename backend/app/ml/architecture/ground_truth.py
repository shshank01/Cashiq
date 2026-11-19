"""
Component 2: Ground-Truth Collector
Collects user-confirmed categories, legitimate transactions, and anomaly feedback
(`legitimate`, `incorrect_category`, `genuine_anomaly`, plus legacy `suspicious`).
Persists verified ground truth for model retraining, baseline adaptation, and evaluation.
"""

from datetime import datetime, timezone
from typing import List, Dict, Any, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.models.ml_ground_truth import MLGroundTruth
from app.models.transaction import Transaction


def normalize_feedback_type(raw_feedback: Optional[str]) -> str:
    """Canonicalizes feedback strings while remaining backward compatible with legacy values."""
    fb = str(raw_feedback or "legitimate").lower().strip().replace("-", "_").replace(" ", "_")
    if fb in {"legitimate", "valid", "normal", "expected"}:
        return "legitimate"
    if fb in {"incorrect_category", "wrong_category", "category_correction", "recategorize"}:
        return "incorrect_category"
    if fb in {"genuine_anomaly", "suspicious", "fraud", "anomaly", "confirm_anomaly"}:
        return "genuine_anomaly" if fb != "suspicious" else "suspicious"
    return fb


class GroundTruthCollector:
    async def record_anomaly_feedback(
        self,
        db: AsyncSession,
        workspace_id: str,
        transaction_id: str,
        feedback: str,  # "legitimate", "incorrect_category", "genuine_anomaly", or legacy "suspicious"
        user_notes: Optional[str] = None,
        confirmed_category: Optional[str] = None,
        user_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Records user feedback on an anomaly:
        - `legitimate`: resolves anomaly flag and stores verified ground truth.
        - `incorrect_category`: updates transaction category to `confirmed_category` and stores ground truth.
        - `genuine_anomaly` / `suspicious`: confirms anomaly so it is excluded from future normal baselines.
        """
        canonical_fb = normalize_feedback_type(feedback)

        res = await db.execute(
            select(Transaction).where(
                Transaction.id == transaction_id,
                Transaction.workspace_id == workspace_id
            )
        )
        tx = res.scalar_one_or_none()
        if not tx:
            raise ValueError(f"Transaction {transaction_id} not found in workspace {workspace_id}")

        orig_score = tx.anomaly_score
        orig_reason = tx.anomaly_reason
        orig_cat = tx.category_name
        final_cat = confirmed_category or orig_cat

        gt = MLGroundTruth(
            workspace_id=workspace_id,
            transaction_id=transaction_id,
            feedback_type=canonical_fb,
            original_category=orig_cat,
            verified_category=final_cat,
            original_anomaly_score=orig_score,
            original_anomaly_reason=orig_reason,
            user_notes=user_notes,
            reviewed_by_user_id=user_id,
            created_at=datetime.now(timezone.utc)
        )
        db.add(gt)

        tx.anomaly_feedback_status = canonical_fb
        if canonical_fb == "legitimate":
            tx.is_anomaly = False
            tx.anomaly_severity = None
            note_str = f" [User Note: {user_notes}]" if user_notes else ""
            tx.anomaly_reason = f"Verified legitimate business expense by user{note_str}"
        elif canonical_fb in {"genuine_anomaly", "suspicious"}:
            tx.is_anomaly = True
            note_str = f" [Confirmed Genuine Anomaly: {user_notes}]" if user_notes else " [Confirmed Genuine Anomaly]"
            tx.anomaly_reason = (orig_reason or "Anomalous transaction") + note_str
        elif canonical_fb == "incorrect_category":
            if confirmed_category:
                tx.category_name = confirmed_category
                tx.verified_label = confirmed_category
                tx.is_confirmed = True
                tx.needs_review = False
                tx.verified_at = datetime.now(timezone.utc)
                tx.confidence = 1.0

        if confirmed_category and canonical_fb != "incorrect_category":
            tx.category_name = confirmed_category
            tx.verified_label = confirmed_category
            tx.is_confirmed = True
            tx.needs_review = False
            tx.verified_at = datetime.now(timezone.utc)

        await db.commit()
        await db.refresh(tx)

        return {
            "ground_truth_id": gt.id,
            "transaction_id": tx.id,
            "feedback": canonical_fb,
            "is_anomaly": tx.is_anomaly,
            "anomaly_feedback_status": tx.anomaly_feedback_status,
            "category_name": tx.category_name,
            "anomaly_reason": tx.anomaly_reason,
            "recorded_at": gt.created_at.isoformat()
        }

    async def record_category_confirmation(
        self,
        db: AsyncSession,
        workspace_id: str,
        transaction_id: str,
        verified_category: str,
        user_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Records category confirmation or correction as verified ground truth."""
        res = await db.execute(
            select(Transaction).where(
                Transaction.id == transaction_id,
                Transaction.workspace_id == workspace_id
            )
        )
        tx = res.scalar_one_or_none()
        if not tx:
            raise ValueError(f"Transaction {transaction_id} not found in workspace {workspace_id}")

        gt = MLGroundTruth(
            workspace_id=workspace_id,
            transaction_id=transaction_id,
            feedback_type="category_confirmed",
            original_category=tx.category_name,
            verified_category=verified_category,
            original_anomaly_score=tx.anomaly_score,
            original_anomaly_reason=tx.anomaly_reason,
            reviewed_by_user_id=user_id,
            created_at=datetime.now(timezone.utc)
        )
        db.add(gt)

        tx.category_name = verified_category
        tx.verified_label = verified_category
        tx.is_confirmed = True
        tx.needs_review = False
        tx.verified_at = datetime.now(timezone.utc)
        tx.confidence = 1.0

        await db.commit()
        await db.refresh(tx)

        return {
            "ground_truth_id": gt.id,
            "transaction_id": tx.id,
            "verified_category": verified_category
        }

    async def get_verified_ground_truth(
        self,
        db: AsyncSession,
        workspace_id: Optional[str] = None,
        feedback_type: Optional[str] = None,
        limit: int = 1000
    ) -> List[Dict[str, Any]]:
        """Retrieves verified ground truth samples for training or evaluation."""
        q = select(MLGroundTruth)
        if workspace_id:
            q = q.where(MLGroundTruth.workspace_id == workspace_id)
        if feedback_type:
            q = q.where(MLGroundTruth.feedback_type == feedback_type)
        q = q.order_by(MLGroundTruth.created_at.desc()).limit(limit)

        result = await db.execute(q)
        items = result.scalars().all()
        return [
            {
                "id": g.id,
                "workspace_id": g.workspace_id,
                "transaction_id": g.transaction_id,
                "feedback_type": g.feedback_type,
                "original_category": g.original_category,
                "verified_category": g.verified_category,
                "original_anomaly_score": g.original_anomaly_score,
                "original_anomaly_reason": g.original_anomaly_reason,
                "user_notes": g.user_notes,
                "created_at": g.created_at.isoformat() if g.created_at else None
            }
            for g in items
        ]

    async def get_feedback_metrics(self, db: AsyncSession, workspace_id: str) -> Dict[str, Any]:
        """Returns statistics on verified user feedback."""
        q = select(
            MLGroundTruth.feedback_type,
            func.count(MLGroundTruth.id)
        ).where(MLGroundTruth.workspace_id == workspace_id).group_by(MLGroundTruth.feedback_type)
        res = await db.execute(q)
        counts = dict(res.all())

        legitimate = counts.get("legitimate", 0)
        suspicious = counts.get("suspicious", 0) + counts.get("genuine_anomaly", 0)
        incorrect_cat = counts.get("incorrect_category", 0)
        cat_conf = counts.get("category_confirmed", 0)
        total_anomaly_feedback = legitimate + suspicious + incorrect_cat

        fpr = (legitimate / total_anomaly_feedback) if total_anomaly_feedback > 0 else 0.0

        return {
            "total_feedback_count": sum(counts.values()),
            "legitimate_count": legitimate,
            "suspicious_count": suspicious,
            "genuine_anomaly_count": suspicious,
            "incorrect_category_count": incorrect_cat,
            "category_confirmed_count": cat_conf,
            "false_positive_rate": round(fpr, 3),
            "verification_coverage": total_anomaly_feedback
        }


ground_truth_collector = GroundTruthCollector()
