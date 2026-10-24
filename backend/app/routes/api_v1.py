import os
import json
from typing import Optional, Dict, Any, List
from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.auth.dependencies import get_current_user, get_current_workspace_user
from app.models.user import User

from app.services.workspace_service import WorkspaceService
from app.services.dashboard_service import DashboardService
from app.services.transaction_service import TransactionService
from app.services.payable_service import PayableService
from app.services.receivable_service import ReceivableService
from app.services.recurring_service import RecurringService
from app.services.forecast_service import ForecastService
from app.services.insight_service import InsightService
from app.services.report_service import ReportService
from app.services.assistant_service import FinancialAssistantService
from app.services.document_service import DocumentService
from app.services.fx_service import FxService
from app.config import settings, save_env_variables

api_router = APIRouter()

# ----------------- Workspaces Top-Level -----------------
@api_router.get("/workspaces")
async def list_workspaces(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    return {"workspaces": await WorkspaceService.list_user_workspaces(db, current_user.id)}

@api_router.post("/workspaces")
async def create_workspace(
    payload: Dict[str, Any],
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    return await WorkspaceService.create_workspace(db, current_user.id, payload)

@api_router.post("/workspaces/{workspace_id}/onboarding")
async def onboarding_profile(
    workspace_id: str,
    payload: Dict[str, Any],
    workspace_context: dict = Depends(get_current_workspace_user),
    db: AsyncSession = Depends(get_db)
):
    return await WorkspaceService.update_onboarding(db, workspace_id, payload)

@api_router.patch("/workspaces/{workspace_id}")
@api_router.put("/workspaces/{workspace_id}")
async def update_workspace(
    workspace_id: str,
    payload: Dict[str, Any],
    workspace_context: dict = Depends(get_current_workspace_user),
    db: AsyncSession = Depends(get_db)
):
    return await WorkspaceService.update_workspace(db, workspace_id, payload)


# ----------------- Dashboard -----------------
@api_router.get("/workspaces/{workspace_id}/dashboard")
async def get_dashboard(
    workspace_id: str,
    workspace_context: dict = Depends(get_current_workspace_user),
    db: AsyncSession = Depends(get_db)
):
    return await DashboardService.get_dashboard_data(db, workspace_id)

# ----------------- Transactions -----------------
@api_router.get("/workspaces/{workspace_id}/transactions")
async def list_transactions(
    workspace_id: str,
    page: int = Query(1, ge=1),
    per_page: int = Query(15, ge=1, le=100),
    search: Optional[str] = None,
    category: Optional[str] = None,
    type: Optional[str] = None,
    account_id: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    sort_by: str = "date",
    sort_order: str = "desc",
    workspace_context: dict = Depends(get_current_workspace_user),
    db: AsyncSession = Depends(get_db)
):
    return await TransactionService.get_transactions(
        db, workspace_id, page, per_page, search, category, type, account_id, start_date, end_date, sort_by, sort_order
    )

@api_router.post("/workspaces/{workspace_id}/transactions")
async def create_transaction(
    workspace_id: str,
    payload: Dict[str, Any],
    workspace_context: dict = Depends(get_current_workspace_user),
    db: AsyncSession = Depends(get_db)
):
    return await TransactionService.create_transaction(db, workspace_id, payload)

@api_router.put("/workspaces/{workspace_id}/transactions/{transaction_id}")
async def update_transaction(
    workspace_id: str,
    transaction_id: str,
    payload: Dict[str, Any],
    workspace_context: dict = Depends(get_current_workspace_user),
    db: AsyncSession = Depends(get_db)
):
    return await TransactionService.update_transaction(db, workspace_id, transaction_id, payload)

@api_router.delete("/workspaces/{workspace_id}/transactions/{transaction_id}")
async def delete_transaction(
    workspace_id: str,
    transaction_id: str,
    workspace_context: dict = Depends(get_current_workspace_user),
    db: AsyncSession = Depends(get_db)
):
    await TransactionService.delete_transaction(db, workspace_id, transaction_id)
    return {"status": "success", "message": "Transaction deleted"}

@api_router.post("/workspaces/{workspace_id}/transactions/{transaction_id}/confirm-category")
async def confirm_category(
    workspace_id: str,
    transaction_id: str,
    payload: Optional[Dict[str, Any]] = None,
    workspace_context: dict = Depends(get_current_workspace_user),
    db: AsyncSession = Depends(get_db)
):
    confirmed_category = payload.get("category_name") if payload else None
    return await TransactionService.confirm_category(db, workspace_id, transaction_id, confirmed_category)

# ----------------- Forecast -----------------
@api_router.get("/workspaces/{workspace_id}/forecast")
async def get_forecast(
    workspace_id: str,
    days: int = Query(30, ge=7, le=90),
    workspace_context: dict = Depends(get_current_workspace_user),
    db: AsyncSession = Depends(get_db)
):
    return await ForecastService.get_or_generate_forecast(db, workspace_id, days)

@api_router.post("/workspaces/{workspace_id}/forecast/generate")
async def generate_forecast(
    workspace_id: str,
    payload: Optional[Dict[str, Any]] = None,
    workspace_context: dict = Depends(get_current_workspace_user),
    db: AsyncSession = Depends(get_db)
):
    days = payload.get("days", 30) if payload else 30
    return await ForecastService.get_or_generate_forecast(db, workspace_id, days)

# ----------------- Insights -----------------
@api_router.get("/workspaces/{workspace_id}/insights")
async def list_insights(
    workspace_id: str,
    workspace_context: dict = Depends(get_current_workspace_user),
    db: AsyncSession = Depends(get_db)
):
    insights = await InsightService.get_all(db, workspace_id)
    return {"insights": insights}

@api_router.post("/workspaces/{workspace_id}/insights/generate")
async def generate_insights_now(
    workspace_id: str,
    workspace_context: dict = Depends(get_current_workspace_user),
    db: AsyncSession = Depends(get_db)
):
    insights = await InsightService.generate_insights(db, workspace_id)
    return {"insights": insights}

# ----------------- Payables -----------------
@api_router.get("/workspaces/{workspace_id}/payables")
async def list_payables(
    workspace_id: str,
    workspace_context: dict = Depends(get_current_workspace_user),
    db: AsyncSession = Depends(get_db)
):
    return await PayableService.get_all(db, workspace_id)

@api_router.post("/workspaces/{workspace_id}/payables")
async def create_payable(
    workspace_id: str,
    payload: Dict[str, Any],
    workspace_context: dict = Depends(get_current_workspace_user),
    db: AsyncSession = Depends(get_db)
):
    return await PayableService.create(db, workspace_id, payload)

# ----------------- Receivables -----------------
@api_router.get("/workspaces/{workspace_id}/receivables")
async def list_receivables(
    workspace_id: str,
    workspace_context: dict = Depends(get_current_workspace_user),
    db: AsyncSession = Depends(get_db)
):
    return await ReceivableService.get_all(db, workspace_id)

@api_router.post("/workspaces/{workspace_id}/receivables")
async def create_receivable(
    workspace_id: str,
    payload: Dict[str, Any],
    workspace_context: dict = Depends(get_current_workspace_user),
    db: AsyncSession = Depends(get_db)
):
    return await ReceivableService.create(db, workspace_id, payload)

# ----------------- Recurring Payments -----------------
@api_router.get("/workspaces/{workspace_id}/recurring")
async def list_recurring(
    workspace_id: str,
    workspace_context: dict = Depends(get_current_workspace_user),
    db: AsyncSession = Depends(get_db)
):
    return await RecurringService.get_all(db, workspace_id)

@api_router.post("/workspaces/{workspace_id}/recurring")
async def create_recurring(
    workspace_id: str,
    payload: Dict[str, Any],
    workspace_context: dict = Depends(get_current_workspace_user),
    db: AsyncSession = Depends(get_db)
):
    return await RecurringService.create(db, workspace_id, payload)

@api_router.post("/workspaces/{workspace_id}/recurring/detect")
async def run_recurring_detection(
    workspace_id: str,
    workspace_context: dict = Depends(get_current_workspace_user),
    db: AsyncSession = Depends(get_db)
):
    return await RecurringService.detect_recurring(db, workspace_id)

@api_router.delete("/workspaces/{workspace_id}/recurring/{rule_id}")
async def delete_recurring(
    workspace_id: str,
    rule_id: str,
    workspace_context: dict = Depends(get_current_workspace_user),
    db: AsyncSession = Depends(get_db)
):
    return await RecurringService.delete(db, workspace_id, rule_id)

@api_router.post("/workspaces/{workspace_id}/recurring/{rule_id}/toggle")
async def toggle_recurring(
    workspace_id: str,
    rule_id: str,
    workspace_context: dict = Depends(get_current_workspace_user),
    db: AsyncSession = Depends(get_db)
):
    return await RecurringService.toggle_status(db, workspace_id, rule_id)

@api_router.post("/workspaces/{workspace_id}/recurring/seed-demo")
async def seed_demo_recurring(
    workspace_id: str,
    workspace_context: dict = Depends(get_current_workspace_user),
    db: AsyncSession = Depends(get_db)
):
    return await RecurringService.seed_demo_recurring(db, workspace_id)

# ----------------- Reports -----------------
@api_router.get("/workspaces/{workspace_id}/reports/income-expense")
async def report_income_expense(
    workspace_id: str,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    workspace_context: dict = Depends(get_current_workspace_user),
    db: AsyncSession = Depends(get_db)
):
    return await ReportService.get_income_expense_report(db, workspace_id, start_date, end_date)

@api_router.get("/workspaces/{workspace_id}/reports/category-spend")
async def report_category_spend(
    workspace_id: str,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    workspace_context: dict = Depends(get_current_workspace_user),
    db: AsyncSession = Depends(get_db)
):
    return await ReportService.get_category_spend_report(db, workspace_id, start_date, end_date)

@api_router.get("/workspaces/{workspace_id}/reports/cash-flow")
async def report_cash_flow(
    workspace_id: str,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    workspace_context: dict = Depends(get_current_workspace_user),
    db: AsyncSession = Depends(get_db)
):
    return await ReportService.get_cash_flow_statement(db, workspace_id, start_date, end_date)

# ----------------- AI Assistant -----------------
@api_router.post("/workspaces/{workspace_id}/assistant/chat")
async def assistant_chat(
    workspace_id: str,
    payload: Dict[str, Any],
    workspace_context: dict = Depends(get_current_workspace_user),
    db: AsyncSession = Depends(get_db)
):
    message = payload.get("message", "")
    conversation_id = payload.get("conversation_id")
    return await FinancialAssistantService.chat(db, workspace_id, message, conversation_id)

@api_router.get("/assistant/config")
async def get_assistant_config(current_user: User = Depends(get_current_user)):
    openai_key = (settings.OPENAI_API_KEY or "").strip()
    gemini_key = (settings.GEMINI_API_KEY or "").strip()
    provider = (settings.AI_PROVIDER or "openai").lower()
    is_configured = bool((provider == "gemini" and gemini_key) or (provider == "openai" and openai_key) or openai_key or gemini_key)
    
    masked_key = ""
    active_key = gemini_key if provider == "gemini" else openai_key
    if not active_key:
        active_key = gemini_key or openai_key
    if active_key:
        if len(active_key) > 8:
            masked_key = active_key[:4] + "••••••••" + active_key[-4:]
        else:
            masked_key = "••••••••"

    return {
        "is_configured": is_configured,
        "provider": provider,
        "model": settings.AI_MODEL or ("gemini-1.5-flash" if provider == "gemini" else "gpt-4o-mini"),
        "has_openai_key": bool(openai_key),
        "has_gemini_key": bool(gemini_key),
        "masked_key": masked_key
    }

@api_router.post("/assistant/config")
async def update_assistant_config(
    payload: Dict[str, Any],
    current_user: User = Depends(get_current_user)
):
    provider = payload.get("provider", "openai").lower()
    raw_key = payload.get("api_key")
    cleaned_key = FinancialAssistantService.clean_api_key(raw_key) if raw_key else ""
    model = payload.get("model")

    # Auto-detect if key format clearly implies provider
    if cleaned_key.startswith("AIzaSy") or cleaned_key.startswith("AQ."):
        provider = "gemini"
    elif cleaned_key.startswith("sk-"):
        provider = "openai"

    if not model or model == "gemini-1.5-flash":
        model = "gemini-2.5-flash" if provider == "gemini" else "gpt-4o-mini"

    update_dict = {
        "AI_PROVIDER": provider,
        "AI_MODEL": model
    }
    if raw_key is not None and cleaned_key:
        if provider == "gemini":
            update_dict["GEMINI_API_KEY"] = cleaned_key
        else:
            update_dict["OPENAI_API_KEY"] = cleaned_key

    save_env_variables(update_dict)
    return {
        "success": True,
        "provider": provider,
        "model": model,
        "is_configured": True
    }

@api_router.post("/assistant/test-key")
async def test_assistant_key(
    payload: Dict[str, Any],
    current_user: User = Depends(get_current_user)
):
    provider = payload.get("provider", "openai").lower()
    api_key = payload.get("api_key") or (settings.GEMINI_API_KEY if provider == "gemini" else settings.OPENAI_API_KEY)
    model = payload.get("model")
    return await FinancialAssistantService.test_key(provider, api_key, model)

# ----------------- Document Ingestion -----------------
@api_router.post("/workspaces/{workspace_id}/documents/upload")
async def upload_document(
    workspace_id: str,
    file: UploadFile = File(...),
    workspace_context: dict = Depends(get_current_workspace_user),
    db: AsyncSession = Depends(get_db)
):
    content = await file.read()
    return await DocumentService.process_upload(db, workspace_id, file.filename, content)

@api_router.post("/workspaces/{workspace_id}/documents/{document_id}/confirm")
async def confirm_document_drafts(
    workspace_id: str,
    document_id: str,
    payload: Dict[str, Any],
    workspace_context: dict = Depends(get_current_workspace_user),
    db: AsyncSession = Depends(get_db)
):
    selected_drafts = payload.get("drafts", [])
    return await DocumentService.confirm_drafts(db, workspace_id, document_id, selected_drafts)

# ----------------- ML Evaluation Report -----------------
@api_router.get("/ml/evaluation")
async def get_ml_evaluation():
    report_file = os.path.join(os.path.dirname(__file__), "..", "..", "ml_models", "evaluation_report.json")
    if os.path.exists(report_file):
        with open(report_file, "r") as f:
            return json.load(f)
    return {"message": "Evaluation report not generated yet"}

# ----------------- Currency Exchange & Conversion -----------------
@api_router.get("/fx/rates")
async def get_fx_rates():
    return FxService.get_rates()

@api_router.post("/fx/convert")
async def convert_currency(payload: Dict[str, Any]):
    amount = float(payload.get("amount", 0.0))
    from_curr = payload.get("from_currency", "USD")
    to_curr = payload.get("to_currency", "INR")
    custom_rate = float(payload.get("custom_rate")) if payload.get("custom_rate") else None
    return FxService.convert(amount, from_curr, to_curr, custom_rate)

