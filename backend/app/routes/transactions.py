from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func, or_
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional
from datetime import datetime
from app.database import get_db
from app.auth.dependencies import verify_workspace_access
from app.models.transaction import Transaction
from app.schemas.transaction import (
    TransactionCreate, TransactionUpdate, TransactionResponse,
    TransactionListResponse, CategoryCorrection, AnomalyFeedbackCreate
)
from app.ml.categorizer import TransactionCategorizer
from app.ml.anomaly_detector import anomaly_detector_instance
from app.ml.architecture.orchestrator import ml_orchestrator
import json
import uuid

router = APIRouter(prefix="/workspaces/{wid}/transactions", tags=["transactions"])
categorizer = TransactionCategorizer()


@router.get("", response_model=TransactionListResponse)
async def list_transactions(
    wid: str,
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    category: Optional[str] = None,
    transaction_type: Optional[str] = Query(None, alias="type"),
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None,
    search: Optional[str] = None,
    account_id: Optional[str] = None,
    sort_by: str = "date",
    sort_dir: str = "desc",
    ctx: dict = Depends(verify_workspace_access),
    db: AsyncSession = Depends(get_db),
):
    query = select(Transaction).where(Transaction.workspace_id == wid)

    if category:
        query = query.where(Transaction.category_name == category)
    if transaction_type:
        query = query.where(Transaction.transaction_type == transaction_type)
    if date_from:
        query = query.where(Transaction.date >= date_from)
    if date_to:
        query = query.where(Transaction.date <= date_to)
    if account_id:
        query = query.where(Transaction.account_id == account_id)
    if search:
        term = f"%{search}%"
        query = query.where(
            or_(
                Transaction.description.ilike(term),
                Transaction.merchant.ilike(term),
                Transaction.notes.ilike(term),
            )
        )

    # Count
    count_q = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_q)).scalar() or 0

    # Sort
    sort_col = getattr(Transaction, sort_by, Transaction.date)
    query = query.order_by(sort_col.desc() if sort_dir == "desc" else sort_col.asc())

    # Paginate
    query = query.offset((page - 1) * per_page).limit(per_page)
    result = await db.execute(query)
    transactions = result.scalars().all()

    return TransactionListResponse(
        transactions=[TransactionResponse.model_validate(t) for t in transactions],
        total=total,
        page=page,
        per_page=per_page,
        total_pages=max(1, (total + per_page - 1) // per_page),
    )


@router.post("", response_model=TransactionResponse, status_code=201)
async def create_transaction(
    wid: str,
    data: TransactionCreate,
    ctx: dict = Depends(verify_workspace_access),
    db: AsyncSession = Depends(get_db),
):
    # Auto-categorize if no category provided
    cat_name = data.category_name
    confidence = None
    model_ver = None
    needs_review = False

    if not cat_name and data.description:
        cat_result = categorizer.categorize(data.description)
        cat_name = cat_result["category"]
        confidence = cat_result["confidence"]
        model_ver = cat_result["model_version"]
        needs_review = cat_result["needs_review"]

    # History & workspace context for business-context-aware anomaly detection
    ctx_ml = await ml_orchestrator.load_workspace_context(db, wid)
    hist_res = await db.execute(
        select(Transaction).where(Transaction.workspace_id == wid).order_by(Transaction.date.desc()).limit(120)
    )
    history = hist_res.scalars().all()
    anomaly_res = anomaly_detector_instance.analyze_transaction(
        current_amount_minor=data.amount_minor,
        category=cat_name or "Miscellaneous",
        merchant=data.merchant,
        historical_transactions=history,
        date=data.date,
        transaction_type=data.transaction_type,
        currency=data.currency,
        workspace_id=wid,
        business_profile=ctx_ml["business_profile"],
        description=data.description,
        learned_profiles=ctx_ml["learned_profiles"],
    )

    txn = Transaction(
        id=str(uuid.uuid4()),
        workspace_id=wid,
        account_id=data.account_id,
        amount_minor=data.amount_minor,
        currency=data.currency,
        transaction_type=data.transaction_type,
        date=data.date,
        description=data.description,
        merchant=data.merchant,
        notes=data.notes,
        source=data.source,
        category_name=cat_name,
        confidence=confidence,
        model_version=model_ver,
        needs_review=needs_review,
        is_confirmed=bool(data.category_name),  # confirmed if user provided category
        is_anomaly=anomaly_res["is_anomaly"],
        anomaly_score=anomaly_res["anomaly_score"],
        anomaly_severity=anomaly_res["severity"],
        anomaly_reason=anomaly_res["reason"],
        anomaly_explanation=json.dumps(anomaly_res.get("explanation_details", {}))
    )
    db.add(txn)
    await db.commit()
    await db.refresh(txn)
    return TransactionResponse.model_validate(txn)


@router.get("/{tid}", response_model=TransactionResponse)
async def get_transaction(
    wid: str,
    tid: str,
    ctx: dict = Depends(verify_workspace_access),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Transaction).where(Transaction.id == tid, Transaction.workspace_id == wid)
    )
    txn = result.scalar_one_or_none()
    if not txn:
        raise HTTPException(status_code=404, detail="Transaction not found")
    return TransactionResponse.model_validate(txn)


@router.put("/{tid}", response_model=TransactionResponse)
async def update_transaction(
    wid: str,
    tid: str,
    data: TransactionUpdate,
    ctx: dict = Depends(verify_workspace_access),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Transaction).where(Transaction.id == tid, Transaction.workspace_id == wid)
    )
    txn = result.scalar_one_or_none()
    if not txn:
        raise HTTPException(status_code=404, detail="Transaction not found")

    update_data = data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(txn, key, value)

    await db.commit()
    await db.refresh(txn)
    return TransactionResponse.model_validate(txn)


@router.delete("/{tid}")
async def delete_transaction(
    wid: str,
    tid: str,
    ctx: dict = Depends(verify_workspace_access),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Transaction).where(Transaction.id == tid, Transaction.workspace_id == wid)
    )
    txn = result.scalar_one_or_none()
    if not txn:
        raise HTTPException(status_code=404, detail="Transaction not found")
    await db.delete(txn)
    await db.commit()
    return {"ok": True}


@router.post("/{tid}/confirm-category", response_model=TransactionResponse)
async def confirm_category(
    wid: str,
    tid: str,
    data: CategoryCorrection,
    ctx: dict = Depends(verify_workspace_access),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Transaction).where(Transaction.id == tid, Transaction.workspace_id == wid)
    )
    txn = result.scalar_one_or_none()
    if not txn:
        raise HTTPException(status_code=404, detail="Transaction not found")

    txn.category_name = data.category_name
    txn.is_confirmed = True
    txn.needs_review = False
    await db.commit()
    await db.refresh(txn)
    return TransactionResponse.model_validate(txn)


@router.post("/{tid}/anomaly-feedback", response_model=TransactionResponse)
async def submit_anomaly_feedback(
    wid: str,
    tid: str,
    data: AnomalyFeedbackCreate,
    ctx: dict = Depends(verify_workspace_access),
    db: AsyncSession = Depends(get_db),
):
    await ml_orchestrator.handle_anomaly_feedback(
        db=db,
        workspace_id=wid,
        transaction_id=tid,
        feedback=data.feedback,
        notes=data.notes,
        confirmed_category=data.confirmed_category,
        user_id=ctx.get("user_id") if isinstance(ctx, dict) else None
    )
    res = await db.execute(
        select(Transaction).where(Transaction.id == tid, Transaction.workspace_id == wid)
    )
    txn = res.scalar_one_or_none()
    if not txn:
        raise HTTPException(status_code=404, detail="Transaction not found")
    return TransactionResponse.model_validate(txn)
