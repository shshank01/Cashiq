import uuid
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.recurring import RecurringRule
from app.models.transaction import Transaction
from app.models.account import Account
from app.ml.recurring_detector import recurring_detector_instance

def to_iso_date(dt: Any) -> str:
    if not dt:
        return ""
    if hasattr(dt, "strftime"):
        return dt.strftime("%Y-%m-%d")
    return str(dt).split("T")[0].split(" ")[0]

class RecurringService:
    @staticmethod
    async def get_all(db: AsyncSession, workspace_id: str) -> Dict[str, Any]:
        res = await db.execute(
            select(RecurringRule).where(RecurringRule.workspace_id == workspace_id).order_by(RecurringRule.next_date.asc())
        )
        rules = res.scalars().all()
        return {
            "recurring_payments": [
                {
                    "id": r.id,
                    "merchant": r.merchant,
                    "description": r.description,
                    "amount_minor": r.amount_minor,
                    "currency": r.currency,
                    "frequency": r.frequency,
                    "next_date": to_iso_date(r.next_date),
                    "confidence": r.confidence,
                    "type": r.type,
                    "status": r.status,
                    "category_name": r.category_name
                }
                for r in rules
            ]
        }

    @staticmethod
    async def detect_recurring(db: AsyncSession, workspace_id: str) -> Dict[str, Any]:
        """Runs pattern detector across workspace transactions and registers newly detected rules."""
        tx_res = await db.execute(
            select(Transaction).where(Transaction.workspace_id == workspace_id).order_by(Transaction.date.asc())
        )
        txs = tx_res.scalars().all()

        detected = recurring_detector_instance.detect(txs)
        
        # Save or update recurring rules
        for d in detected:
            existing = await db.execute(
                select(RecurringRule).where(
                    RecurringRule.workspace_id == workspace_id,
                    RecurringRule.merchant == d["merchant"]
                )
            )
            rule = existing.scalar_one_or_none()
            next_dt = datetime.fromisoformat(d["next_date"]) if isinstance(d["next_date"], str) else d["next_date"]
            if hasattr(next_dt, "tzinfo") and next_dt.tzinfo:
                next_dt = next_dt.astimezone(timezone.utc).replace(tzinfo=None)

            if not rule:
                rule = RecurringRule(
                    id=str(uuid.uuid4()),
                    workspace_id=workspace_id,
                    merchant=d["merchant"],
                    description=d.get("description"),
                    amount_minor=d["amount_minor"],
                    currency=d.get("currency", "USD"),
                    frequency=d["frequency"],
                    next_date=next_dt,
                    confidence=d["confidence"],
                    type=d["type"],
                    status="active",
                    category_name=d.get("category_name")
                )
                db.add(rule)
            else:
                rule.amount_minor = d["amount_minor"]
                rule.frequency = d["frequency"]
                rule.next_date = next_dt
                rule.confidence = d["confidence"]
                rule.category_name = d.get("category_name") or rule.category_name

        await db.commit()
        all_rules = await RecurringService.get_all(db, workspace_id)
        
        msg = (
            f"Successfully analyzed {len(txs)} transactions and identified {len(detected)} recurring payment obligations."
            if len(txs) > 0
            else "Workspace currently has 0 transactions. Import or create transactions to analyze cadence patterns."
        )

        return {
            "recurring_payments": all_rules["recurring_payments"],
            "detected_count": len(detected),
            "transactions_analyzed": len(txs),
            "message": msg
        }

    @staticmethod
    async def create(db: AsyncSession, workspace_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """Manually creates a new recurring payment obligation."""
        next_dt = None
        raw_next = data.get("next_date")
        if raw_next:
            try:
                next_dt = datetime.fromisoformat(str(raw_next))
                if hasattr(next_dt, "tzinfo") and next_dt.tzinfo:
                    next_dt = next_dt.astimezone(timezone.utc).replace(tzinfo=None)
            except Exception:
                next_dt = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(days=30)
        else:
            next_dt = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(days=30)

        rule = RecurringRule(
            id=str(uuid.uuid4()),
            workspace_id=workspace_id,
            merchant=data.get("merchant", "Custom Vendor"),
            description=data.get("description") or f"Scheduled {data.get('frequency', 'monthly')} payment",
            amount_minor=int(data.get("amount_minor", 0)),
            currency=data.get("currency", "USD"),
            frequency=data.get("frequency", "monthly"),
            next_date=next_dt,
            confidence=1.0,
            type=data.get("type", "expense"),
            status="active",
            category_name=data.get("category_name", "Software & Cloud Services")
        )
        db.add(rule)
        await db.commit()
        return await RecurringService.get_all(db, workspace_id)

    @staticmethod
    async def delete(db: AsyncSession, workspace_id: str, rule_id: str) -> Dict[str, Any]:
        """Deletes a recurring obligation."""
        res = await db.execute(
            select(RecurringRule).where(
                RecurringRule.id == rule_id,
                RecurringRule.workspace_id == workspace_id
            )
        )
        rule = res.scalar_one_or_none()
        if rule:
            await db.delete(rule)
            await db.commit()
        return await RecurringService.get_all(db, workspace_id)

    @staticmethod
    async def toggle_status(db: AsyncSession, workspace_id: str, rule_id: str) -> Dict[str, Any]:
        """Toggles a recurring obligation between active and paused."""
        res = await db.execute(
            select(RecurringRule).where(
                RecurringRule.id == rule_id,
                RecurringRule.workspace_id == workspace_id
            )
        )
        rule = res.scalar_one_or_none()
        if rule:
            rule.status = "paused" if rule.status == "active" else "active"
            await db.commit()
        return await RecurringService.get_all(db, workspace_id)

    @staticmethod
    async def seed_demo_recurring(db: AsyncSession, workspace_id: str) -> Dict[str, Any]:
        """Seeds realistic recurring obligations and historical transactions for any workspace."""
        # Find or create checking account
        acct_res = await db.execute(select(Account).where(Account.workspace_id == workspace_id))
        acct = acct_res.scalars().first()
        if not acct:
            acct = Account(
                id=str(uuid.uuid4()),
                workspace_id=workspace_id,
                name="Primary Operating Account",
                account_type="checking",
                balance_minor=12500000,
                currency="USD"
            )
            db.add(acct)
            await db.flush()

        now = datetime.now(timezone.utc).replace(tzinfo=None)

        demo_items = [
            {
                "merchant": "AWS Cloud Services",
                "desc": "Production Compute & Database Infrastructure",
                "amount_minor": 450000,
                "type": "expense",
                "frequency": "monthly",
                "category": "Software & Cloud Services",
                "days_ahead": 14,
                "confidence": 0.95
            },
            {
                "merchant": "Gusto Payroll",
                "desc": "Bi-Weekly Employee Salaries & Benefits",
                "amount_minor": 1250000,
                "type": "expense",
                "frequency": "bi-weekly",
                "category": "Payroll & Wages",
                "days_ahead": 5,
                "confidence": 1.0
            },
            {
                "merchant": "WeWork Global",
                "desc": "Dedicated Office Suite Lease",
                "amount_minor": 240000,
                "type": "expense",
                "frequency": "monthly",
                "category": "Rent & Facilities",
                "days_ahead": 18,
                "confidence": 0.95
            },
            {
                "merchant": "Datadog Monitoring",
                "desc": "Application APM & Security Logs",
                "amount_minor": 65000,
                "type": "expense",
                "frequency": "monthly",
                "category": "Software & Cloud Services",
                "days_ahead": 22,
                "confidence": 1.0
            },
            {
                "merchant": "GitHub Enterprise",
                "desc": "Source Code Hosting & CI/CD Runners",
                "amount_minor": 21000,
                "type": "expense",
                "frequency": "monthly",
                "category": "Software & Cloud Services",
                "days_ahead": 25,
                "confidence": 1.0
            },
            {
                "merchant": "Stripe Payments Retainer",
                "desc": "Monthly Enterprise Client Retainer",
                "amount_minor": 3500000,
                "type": "income",
                "frequency": "monthly",
                "category": "Client Revenue",
                "days_ahead": 10,
                "confidence": 0.95
            }
        ]

        # Insert rules
        for item in demo_items:
            existing = await db.execute(
                select(RecurringRule).where(
                    RecurringRule.workspace_id == workspace_id,
                    RecurringRule.merchant == item["merchant"]
                )
            )
            rule = existing.scalar_one_or_none()
            next_date = now + timedelta(days=item["days_ahead"])

            if not rule:
                rule = RecurringRule(
                    id=str(uuid.uuid4()),
                    workspace_id=workspace_id,
                    merchant=item["merchant"],
                    description=item["desc"],
                    amount_minor=item["amount_minor"],
                    currency="USD",
                    frequency=item["frequency"],
                    next_date=next_date,
                    confidence=item["confidence"],
                    type=item["type"],
                    status="active",
                    category_name=item["category"]
                )
                db.add(rule)
            else:
                rule.amount_minor = item["amount_minor"]
                rule.frequency = item["frequency"]
                rule.next_date = next_date
                rule.status = "active"

            # Also create 3 historical transactions for each item so pattern detection recognizes them
            step_days = 14 if item["frequency"] == "bi-weekly" else 30
            for step in range(1, 4):
                tx_date = now - timedelta(days=step * step_days)
                tx_desc = f"{item['merchant']} payment #{step}"
                # Check if exists
                existing_tx = await db.execute(
                    select(Transaction).where(
                        Transaction.workspace_id == workspace_id,
                        Transaction.merchant == item["merchant"],
                        Transaction.description == tx_desc
                    )
                )
                if not existing_tx.scalar_one_or_none():
                    t = Transaction(
                        id=str(uuid.uuid4()),
                        workspace_id=workspace_id,
                        account_id=acct.id,
                        date=tx_date,
                        amount_minor=-item["amount_minor"] if item["type"] == "expense" else item["amount_minor"],
                        currency="USD",
                        description=tx_desc,
                        merchant=item["merchant"],
                        category_name=item["category"],
                        type=item["type"],
                        source="manual",
                        status="posted",
                        confidence=1.0,
                        is_recurring=True,
                        recurring_frequency=item["frequency"],
                        is_anomaly=False
                    )
                    db.add(t)

        await db.commit()
        all_rules = await RecurringService.get_all(db, workspace_id)
        return {
            "recurring_payments": all_rules["recurring_payments"],
            "detected_count": len(all_rules["recurring_payments"]),
            "transactions_analyzed": len(demo_items) * 3,
            "message": "Successfully seeded demo recurring obligations and 18 historical transactions."
        }
