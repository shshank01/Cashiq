"""
Component 5: ML Orchestrator
Coordinates preprocessing, prediction, training, evaluation,
model lifecycle, feedback adaptation, business-profile personalization, and workspace isolation.
"""

import json
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.ml.categorizer import categorizer_instance
from app.ml.business_taxonomy import (
    canonicalize_category,
    derive_initial_expense_profile,
    personalize_expense_profile,
)
from app.ml.merchant_normalizer import normalize_merchant_name
from app.ml.architecture.ground_truth import ground_truth_collector, normalize_feedback_type
from app.ml.architecture.labelizer import labelizer
from app.ml.architecture.model_builder import model_builder
from app.ml.architecture.evaluator import evaluator
from app.ml.architecture.registry import model_registry
from app.ml.architecture.monitoring import ml_monitor
from app.models.business_profile import BusinessProfile
from app.models.ml_ground_truth import BehavioralProfileModel
from app.models.transaction import Transaction


class MLOrchestrator:
    def __init__(self):
        self.orchestrator_version = "v3.0.0-context-orchestrated"

    def predict_category(
        self,
        text: str,
        workspace_id: Optional[str] = None,
        merchant: Optional[str] = None,
        workspace_merchant_map: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        """Classifies transaction text into financial categories."""
        return categorizer_instance.categorize(
            text,
            workspace_id=workspace_id,
            merchant=merchant,
            workspace_merchant_map=workspace_merchant_map,
        )

    def detect_anomaly(
        self,
        current_amount_minor: int,
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
        """Runs business-context-aware multivariate anomaly detection."""
        from app.ml.anomaly_detector import anomaly_detector_instance
        return anomaly_detector_instance.analyze_transaction(
            current_amount_minor=current_amount_minor,
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

    async def load_workspace_context(
        self,
        db: AsyncSession,
        workspace_id: str,
    ) -> Dict[str, Any]:
        """Loads workspace BusinessProfile and persisted BehavioralProfileModel entries."""
        prof_res = await db.execute(
            select(BusinessProfile).where(BusinessProfile.workspace_id == workspace_id)
        )
        biz_profile = prof_res.scalar_one_or_none()

        bp_res = await db.execute(
            select(BehavioralProfileModel).where(BehavioralProfileModel.workspace_id == workspace_id)
        )
        learned_rows = bp_res.scalars().all()
        learned_profiles: List[Dict[str, Any]] = []
        merchant_cat_map: Dict[str, str] = {}

        for row in learned_rows:
            try:
                stats = json.loads(row.stats_json) if row.stats_json else {}
            except Exception:
                stats = {}
            learned_profiles.append({
                "profile_type": row.profile_type,
                "profile_key": row.profile_key,
                "stats": stats,
            })
            if row.profile_type == "merchant" and stats.get("preferred_category"):
                cm = normalize_merchant_name(row.profile_key)["canonical"]
                if cm:
                    merchant_cat_map[cm] = stats["preferred_category"]

        return {
            "business_profile": biz_profile,
            "learned_profiles": learned_profiles,
            "workspace_merchant_map": merchant_cat_map,
        }

    async def update_behavioral_profile_from_feedback(
        self,
        db: AsyncSession,
        workspace_id: str,
        category: str,
        merchant: Optional[str],
        amount_minor: int,
        feedback: str
    ) -> None:
        """
        Dynamically updates the workspace behavioral profile and business expense profile
        from user feedback (`legitimate`, `incorrect_category`, `genuine_anomaly`).
        - `legitimate`: adapts category & merchant baselines, records verified (merchant, category)
          exception, and gradually personalizes BusinessProfile.relevant_expense_categories.
        - `incorrect_category`: updates merchant's preferred category mapping for future predictions
          and consistency checks.
        - `genuine_anomaly` / `suspicious`: never adds transaction to normal baselines.
        """
        canonical_fb = normalize_feedback_type(feedback)
        if canonical_fb not in {"legitimate", "incorrect_category"}:
            return

        now = datetime.now(timezone.utc)
        target_amount = abs(int(amount_minor))
        cat_key = canonicalize_category(category or "Miscellaneous")

        # 1. Update Category Profile on confirmed legitimate feedback
        if canonical_fb == "legitimate":
            res = await db.execute(
                select(BehavioralProfileModel).where(
                    BehavioralProfileModel.workspace_id == workspace_id,
                    BehavioralProfileModel.profile_type == "category",
                    BehavioralProfileModel.profile_key == cat_key
                )
            )
            cat_profile_row = res.scalar_one_or_none()

            if cat_profile_row:
                stats = json.loads(cat_profile_row.stats_json)
                cnt = stats.get("count", 1) + 1
                old_mean = stats.get("mean", target_amount)
                new_mean = (old_mean * (cnt - 1) + target_amount) / cnt
                stats["count"] = cnt
                stats["mean"] = float(new_mean)
                stats["max_legitimate"] = max(float(stats.get("max_legitimate", 0)), float(target_amount))
                stats["max_verified_legitimate"] = max(float(stats.get("max_verified_legitimate", 0)), float(target_amount))
                stats["last_verified_at"] = now.isoformat()
                cat_profile_row.stats_json = json.dumps(stats)
                cat_profile_row.updated_at = now
            else:
                stats = {
                    "count": 1,
                    "mean": float(target_amount),
                    "std": float(target_amount * 0.25),
                    "median": float(target_amount),
                    "max_legitimate": float(target_amount),
                    "max_verified_legitimate": float(target_amount),
                    "last_verified_at": now.isoformat()
                }
                cat_profile_row = BehavioralProfileModel(
                    workspace_id=workspace_id,
                    profile_type="category",
                    profile_key=cat_key,
                    stats_json=json.dumps(stats),
                    created_at=now,
                    updated_at=now
                )
                db.add(cat_profile_row)

            # Personalize BusinessProfile.relevant_expense_categories gradually
            bp_res = await db.execute(
                select(BusinessProfile).where(BusinessProfile.workspace_id == workspace_id)
            )
            biz_prof = bp_res.scalar_one_or_none()
            if biz_prof:
                base_rel = derive_initial_expense_profile(
                    industry=biz_prof.industry,
                    business_type=biz_prof.business_type,
                    operating_model=getattr(biz_prof, "operating_model", None),
                    custom_categories=getattr(biz_prof, "relevant_expense_categories", None),
                )
                existing_learned = (base_rel.get("learned_categories") or {}).get(cat_key)
                prev_cnt = int(existing_learned.get("verified_count", 0)) if isinstance(existing_learned, dict) else 0
                biz_prof.relevant_expense_categories = personalize_expense_profile(
                    base_rel,
                    {cat_key: prev_cnt + 1},
                )

        # 2. Update Merchant Profile & Merchant-Category mapping
        if merchant and str(merchant).strip():
            norm_info = normalize_merchant_name(merchant)
            m_key = norm_info["canonical"] or str(merchant).strip().lower()
            m_res = await db.execute(
                select(BehavioralProfileModel).where(
                    BehavioralProfileModel.workspace_id == workspace_id,
                    BehavioralProfileModel.profile_type == "merchant",
                    BehavioralProfileModel.profile_key == m_key
                )
            )
            m_row = m_res.scalar_one_or_none()
            if m_row:
                m_stats = json.loads(m_row.stats_json)
                m_cnt = m_stats.get("count", 1) + 1
                m_stats["count"] = m_cnt
                if canonical_fb == "legitimate":
                    m_stats["max"] = max(float(m_stats.get("max", 0)), float(target_amount))
                    m_stats["max_verified_legitimate"] = max(float(m_stats.get("max_verified_legitimate", 0)), float(target_amount))
                cats_map = m_stats.get("categories") or {}
                cats_map[cat_key] = int(cats_map.get(cat_key, 0)) + (2 if canonical_fb == "incorrect_category" else 1)
                m_stats["categories"] = cats_map
                m_stats["category"] = cat_key
                if canonical_fb == "incorrect_category":
                    m_stats["preferred_category"] = cat_key
                ver_cats = set(m_stats.get("verified_categories") or [])
                ver_cats.add(cat_key)
                m_stats["verified_categories"] = sorted(list(ver_cats))
                m_stats["last_seen"] = now.isoformat()
                m_row.stats_json = json.dumps(m_stats)
                m_row.updated_at = now
            else:
                m_stats = {
                    "count": 1,
                    "mean": float(target_amount),
                    "max": float(target_amount),
                    "max_verified_legitimate": float(target_amount) if canonical_fb == "legitimate" else 0.0,
                    "category": cat_key,
                    "preferred_category": cat_key if canonical_fb == "incorrect_category" else None,
                    "categories": {cat_key: 2 if canonical_fb == "incorrect_category" else 1},
                    "verified_categories": [cat_key],
                    "last_seen": now.isoformat()
                }
                m_row = BehavioralProfileModel(
                    workspace_id=workspace_id,
                    profile_type="merchant",
                    profile_key=m_key,
                    stats_json=json.dumps(m_stats),
                    created_at=now,
                    updated_at=now
                )
                db.add(m_row)

            # Register workspace merchant override in live categorizer on incorrect_category feedback
            if canonical_fb == "incorrect_category":
                categorizer_instance.register_merchant_override(workspace_id, merchant, cat_key)

        await db.commit()

    async def handle_anomaly_feedback(
        self,
        db: AsyncSession,
        workspace_id: str,
        transaction_id: str,
        feedback: str,
        notes: Optional[str] = None,
        confirmed_category: Optional[str] = None,
        user_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Processes user feedback on an anomaly:
        1. Records verified ground truth (`legitimate`, `incorrect_category`, `genuine_anomaly`).
        2. Dynamically updates behavioral profiles & business expense profile.
        3. On `incorrect_category`, re-evaluates the transaction under the corrected category.
        4. Triggers controlled periodic retraining when threshold is reached.
        """
        canonical_fb = normalize_feedback_type(feedback)

        # 1. Record ground truth
        result = await ground_truth_collector.record_anomaly_feedback(
            db=db,
            workspace_id=workspace_id,
            transaction_id=transaction_id,
            feedback=canonical_fb,
            user_notes=notes,
            confirmed_category=confirmed_category,
            user_id=user_id
        )

        # 2. Fetch transaction details to update behavioral profile
        tx_res = await db.execute(
            select(Transaction).where(Transaction.id == transaction_id, Transaction.workspace_id == workspace_id)
        )
        tx = tx_res.scalar_one_or_none()
        if tx:
            await self.update_behavioral_profile_from_feedback(
                db=db,
                workspace_id=workspace_id,
                category=confirmed_category or tx.category_name,
                merchant=tx.merchant,
                amount_minor=tx.amount_minor,
                feedback=canonical_fb
            )

            # 3. On incorrect_category, re-evaluate transaction under the corrected category
            if canonical_fb == "incorrect_category":
                ctx = await self.load_workspace_context(db, workspace_id)
                hist_res = await db.execute(
                    select(Transaction)
                    .where(Transaction.workspace_id == workspace_id, Transaction.id != tx.id)
                    .order_by(Transaction.date.desc())
                    .limit(120)
                )
                history = hist_res.scalars().all()
                re_eval = self.detect_anomaly(
                    current_amount_minor=tx.amount_minor,
                    category=tx.category_name or "Miscellaneous",
                    merchant=tx.merchant,
                    historical_transactions=history,
                    date=tx.date,
                    transaction_type=tx.type,
                    currency=tx.currency,
                    feedback_status=None,  # re-evaluate freshly under new category
                    workspace_id=workspace_id,
                    business_profile=ctx["business_profile"],
                    description=tx.description,
                    learned_profiles=ctx["learned_profiles"],
                )
                tx.is_anomaly = re_eval["is_anomaly"]
                tx.anomaly_score = re_eval["anomaly_score"]
                tx.anomaly_severity = re_eval["severity"]
                tx.anomaly_reason = re_eval["reason"] or f"Re-evaluated after category correction to '{tx.category_name}'."
                tx.anomaly_explanation = json.dumps(re_eval.get("explanation_details", {}))
                await db.commit()
                await db.refresh(tx)
                result["is_anomaly"] = tx.is_anomaly
                result["anomaly_score"] = tx.anomaly_score
                result["anomaly_reason"] = tx.anomaly_reason
                result["re_evaluated"] = True

        # 4. Check retraining condition
        fb_stats = await ground_truth_collector.get_feedback_metrics(db, workspace_id)
        retraining_performed = False
        if fb_stats.get("total_feedback_count", 0) > 0 and fb_stats.get("total_feedback_count", 0) % 5 == 0:
            await self.retrain_workspace_models(db, workspace_id)
            retraining_performed = True

        result["retraining_performed"] = retraining_performed
        result["feedback_stats"] = fb_stats
        return result

    async def retrain_workspace_models(self, db: AsyncSession, workspace_id: str) -> Dict[str, Any]:
        """
        Controlled periodic retraining:
        Rebuilds category & merchant baselines from all non-anomalous/verified workspace transactions,
        evaluates metrics, and registers model version.
        """
        res = await db.execute(
            select(Transaction).where(Transaction.workspace_id == workspace_id)
        )
        txs = res.scalars().all()

        if len(txs) < 5:
            return {"status": "skipped", "reason": "Insufficient transactions for retraining"}

        clean_txs = [
            t for t in txs
            if (getattr(t, "anomaly_feedback_status", None) not in {"suspicious", "genuine_anomaly"})
        ]
        cat_base, merch_base = model_builder.build_anomaly_baselines(clean_txs)

        scores = [t.anomaly_score or 0.0 for t in txs]
        flags = [t.is_anomaly for t in txs]
        gt_res = await ground_truth_collector.get_verified_ground_truth(db, workspace_id, limit=100)
        eval_metrics = evaluator.evaluate_anomaly_detector(scores, flags, gt_res)

        new_version = f"v3.0.{len(txs)}-workspace-retrained"
        await model_registry.register_model(
            db=db,
            model_name="anomaly_detector",
            model_version=new_version,
            metrics=eval_metrics,
            parameters={"categories_modeled": len(cat_base), "merchants_modeled": len(merch_base)},
            workspace_id=workspace_id,
            status="active"
        )

        return {
            "status": "success",
            "model_version": new_version,
            "metrics": eval_metrics,
            "categories_updated": len(cat_base),
            "merchants_updated": len(merch_base)
        }

    async def get_system_status(self, db: AsyncSession, workspace_id: str) -> Dict[str, Any]:
        """Returns comprehensive ML status across components for this workspace."""
        health = await ml_monitor.get_workspace_ml_health(db, workspace_id)
        audit = await labelizer.get_label_audit(db, workspace_id)
        fb_metrics = await ground_truth_collector.get_feedback_metrics(db, workspace_id)

        active_versions = {
            "categorizer": model_registry.get_active_version("categorizer"),
            "anomaly_detector": model_registry.get_active_version("anomaly_detector"),
            "forecaster": model_registry.get_active_version("forecaster")
        }

        return {
            "workspace_id": workspace_id,
            "active_model_versions": active_versions,
            "health": health,
            "labels": audit,
            "feedback": fb_metrics,
            "orchestrator_version": self.orchestrator_version
        }


ml_orchestrator = MLOrchestrator()
