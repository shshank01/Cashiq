"""
Component 9: Monitoring & Drift Detector
Monitors prediction quality, false positives, behavioural drift,
and model performance per workspace.
"""

from datetime import datetime, timedelta, timezone
from typing import Dict, Any, List, Optional
import numpy as np
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_

from app.models.transaction import Transaction
from app.models.ml_ground_truth import MLGroundTruth, BehavioralProfileModel


class MLMonitor:
    async def get_workspace_ml_health(
        self,
        db: AsyncSession,
        workspace_id: str
    ) -> Dict[str, Any]:
        """Calculates comprehensive health metrics for the workspace ML system."""
        # 1. Total and recent transactions
        res = await db.execute(
            select(Transaction).where(Transaction.workspace_id == workspace_id)
        )
        txs = res.scalars().all()
        total_count = len(txs)

        if total_count == 0:
            return {
                "workspace_id": workspace_id,
                "status": "cold_start",
                "message": "Insufficient transactions for statistical profiling.",
                "total_transactions": 0,
                "anomaly_rate": 0.0,
                "false_positive_rate": 0.0,
                "drift_detected": False,
                "active_categories": 0
            }

        # Anomaly stats
        flagged_anomalies = [t for t in txs if t.is_anomaly]
        flagged_count = len(flagged_anomalies)
        anomaly_rate = flagged_count / total_count if total_count > 0 else 0.0

        # Review required rate
        review_count = sum(1 for t in txs if getattr(t, 'review_required', False))
        review_rate = review_count / total_count if total_count > 0 else 0.0

        # 2. Ground truth feedback false-positive calculation
        gt_res = await db.execute(
            select(MLGroundTruth).where(MLGroundTruth.workspace_id == workspace_id)
        )
        feedbacks = gt_res.scalars().all()
        legit_fb = sum(1 for fb in feedbacks if fb.feedback_type == "legitimate")
        suspicious_fb = sum(1 for fb in feedbacks if fb.feedback_type == "suspicious")
        total_anomaly_fb = legit_fb + suspicious_fb

        fpr = (legit_fb / total_anomaly_fb) if total_anomaly_fb > 0 else 0.0

        # 3. Category drift check
        drift_report = await self.detect_category_drift(db, workspace_id, txs)

        return {
            "workspace_id": workspace_id,
            "status": "healthy" if total_count >= 10 else "initializing",
            "total_transactions": total_count,
            "anomalies_flagged": flagged_count,
            "anomaly_rate": round(anomaly_rate, 4),
            "review_rate": round(review_rate, 4),
            "verified_feedback_count": len(feedbacks),
            "false_positive_rate": round(fpr, 3),
            "drift_detected": drift_report.get("has_drift", False),
            "drift_details": drift_report.get("details", []),
            "last_monitored_at": datetime.now(timezone.utc).isoformat()
        }

    async def detect_category_drift(
        self,
        db: AsyncSession,
        workspace_id: str,
        transactions: Optional[List[Transaction]] = None
    ) -> Dict[str, Any]:
        """
        Detects behavioural shift in category spending: compares recent 30-day spend
        to baseline historical distribution.
        """
        if not transactions:
            res = await db.execute(
                select(Transaction).where(Transaction.workspace_id == workspace_id)
            )
            transactions = res.scalars().all()

        if len(transactions) < 15:
            return {"has_drift": False, "details": []}

        now = datetime.now(timezone.utc)
        recent_cutoff = now - timedelta(days=30)

        recent_txs = [t for t in transactions if (t.date.replace(tzinfo=timezone.utc) if not t.date.tzinfo else t.date) >= recent_cutoff]
        older_txs = [t for t in transactions if (t.date.replace(tzinfo=timezone.utc) if not t.date.tzinfo else t.date) < recent_cutoff]

        if len(older_txs) < 8 or len(recent_txs) < 5:
            return {"has_drift": False, "details": []}

        # Check mean spend drift by category
        drift_details = []
        categories = set(t.category_name for t in transactions if t.category_name)

        has_drift = False
        for cat in categories:
            old_amts = [t.amount_minor for t in older_txs if t.category_name == cat]
            new_amts = [t.amount_minor for t in recent_txs if t.category_name == cat]

            if len(old_amts) >= 3 and len(new_amts) >= 3:
                old_mean = np.mean(old_amts)
                new_mean = np.mean(new_amts)
                if old_mean > 0:
                    ratio = new_mean / old_mean
                    # If average category spending has grown > 2.5x or dropped < 0.3x
                    if ratio >= 2.5 or ratio <= 0.3:
                        has_drift = True
                        drift_details.append({
                            "category": cat,
                            "type": "expansion" if ratio >= 2.5 else "contraction",
                            "historical_mean_minor": int(old_mean),
                            "recent_mean_minor": int(new_mean),
                            "shift_ratio": round(float(ratio), 2)
                        })

        return {
            "has_drift": has_drift,
            "details": drift_details
        }


ml_monitor = MLMonitor()
