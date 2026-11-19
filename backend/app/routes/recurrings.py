from fastapi import APIRouter, Depends
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime, timezone
from collections import defaultdict
from app.database import get_db
from app.auth.dependencies import verify_workspace_access
from app.models.recurring import RecurringRule
from app.models.transaction import Transaction
import uuid

router = APIRouter(prefix="/workspaces/{wid}/recurring", tags=["recurring"])


@router.get("")
async def list_recurring(
    wid: str,
    ctx: dict = Depends(verify_workspace_access),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(RecurringRule)
        .where(RecurringRule.workspace_id == wid)
        .order_by(RecurringRule.next_date.asc())
    )
    rules = result.scalars().all()
    return {
        "recurring_payments": [
            {
                "id": r.id,
                "merchant": r.merchant,
                "description": r.description,
                "amount_minor": r.amount_minor,
                "currency": r.currency,
                "frequency": r.frequency,
                "next_date": r.next_date.isoformat() if r.next_date else None,
                "confidence": r.confidence,
                "type": r.type,
                "status": r.status,
                "category_name": r.category_name,
            }
            for r in rules
        ]
    }


@router.post("/detect")
async def detect_recurring(
    wid: str,
    ctx: dict = Depends(verify_workspace_access),
    db: AsyncSession = Depends(get_db),
):
    """Detect recurring patterns from transaction history."""
    result = await db.execute(
        select(Transaction)
        .where(Transaction.workspace_id == wid)
        .order_by(Transaction.date.asc())
    )
    transactions = result.scalars().all()

    # Group by merchant
    merchant_txns = defaultdict(list)
    for txn in transactions:
        key = (txn.merchant or txn.description or "Unknown").strip().lower()
        merchant_txns[key].append(txn)

    detected = []
    now = datetime.now(timezone.utc)

    for merchant_key, txns in merchant_txns.items():
        if len(txns) < 2:
            continue

        # Sort by date
        txns.sort(key=lambda t: t.date)

        # Calculate intervals in days
        intervals = []
        for i in range(1, len(txns)):
            delta = (txns[i].date - txns[i - 1].date).days
            if delta > 0:
                intervals.append(delta)

        if not intervals:
            continue

        avg_interval = sum(intervals) / len(intervals)
        amounts = [t.amount_minor for t in txns]
        avg_amount = int(sum(amounts) / len(amounts))

        # Determine frequency
        frequency = None
        confidence = 0.0
        if 5 <= avg_interval <= 10:
            frequency = "weekly"
            confidence = 0.7
        elif 12 <= avg_interval <= 18:
            frequency = "bi-weekly"
            confidence = 0.7
        elif 25 <= avg_interval <= 35:
            frequency = "monthly"
            confidence = 0.8
        elif 85 <= avg_interval <= 100:
            frequency = "quarterly"
            confidence = 0.7
        elif 350 <= avg_interval <= 380:
            frequency = "annual"
            confidence = 0.7

        if not frequency:
            continue

        # Check amount consistency
        if len(set(amounts)) == 1:
            confidence += 0.15
        elif max(amounts) - min(amounts) < avg_amount * 0.1:
            confidence += 0.1

        confidence = min(confidence, 1.0)

        # Calculate next expected date
        last_date = txns[-1].date
        interval_map = {"weekly": 7, "bi-weekly": 14, "monthly": 30, "quarterly": 90, "annual": 365}
        next_date = last_date + __import__("datetime").timedelta(days=interval_map.get(frequency, 30))
        if next_date < now:
            next_date = now + __import__("datetime").timedelta(days=interval_map.get(frequency, 30))

        display_name = txns[-1].merchant or txns[-1].description or merchant_key

        # Check if rule already exists
        existing = await db.execute(
            select(RecurringRule).where(
                RecurringRule.workspace_id == wid,
                RecurringRule.merchant == display_name,
            )
        )
        if existing.scalar_one_or_none():
            continue

        rule = RecurringRule(
            id=str(uuid.uuid4()),
            workspace_id=wid,
            merchant=display_name,
            description=f"Detected {frequency} payment",
            amount_minor=avg_amount,
            frequency=frequency,
            next_date=next_date,
            confidence=round(confidence, 2),
            type=txns[-1].transaction_type,
            category_name=txns[-1].category_name,
        )
        db.add(rule)
        detected.append(rule)

    await db.commit()

    return {
        "recurring_payments": [
            {
                "id": r.id,
                "merchant": r.merchant,
                "amount_minor": r.amount_minor,
                "frequency": r.frequency,
                "next_date": r.next_date.isoformat() if r.next_date else None,
                "confidence": r.confidence,
            }
            for r in detected
        ],
        "detected_count": len(detected),
    }
