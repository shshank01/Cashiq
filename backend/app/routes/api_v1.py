import os
import json
from typing import Optional, Dict, Any, List
from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.auth.dependencies import get_current_user, get_current_workspace_user, require_workspace_role
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
from app.services.simulation_service import SimulationService
from app.services.budget_service import BudgetService
from app.services.reconciliation_service import ReconciliationService
from app.services.health_score_service import HealthScoreService
from app.services.audit_service import AuditService
from app.config import settings, save_env_variables
from app.ml.architecture import ml_orchestrator, model_serving, ground_truth_collector
from app.ml.business_taxonomy import list_supported_industries, ALL_EXPENSE_CATEGORIES

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

@api_router.get("/workspaces/{workspace_id}/business-profile")
async def get_business_profile(
    workspace_id: str,
    workspace_context: dict = Depends(get_current_workspace_user),
    db: AsyncSession = Depends(get_db)
):
    return await WorkspaceService.get_business_profile(db, workspace_id)

@api_router.put("/workspaces/{workspace_id}/business-profile")
@api_router.patch("/workspaces/{workspace_id}/business-profile")
async def update_business_profile(
    workspace_id: str,
    payload: Dict[str, Any],
    workspace_context: dict = Depends(get_current_workspace_user),
    db: AsyncSession = Depends(get_db)
):
    return await WorkspaceService.update_onboarding(db, workspace_id, payload)

@api_router.get("/ml/industry-taxonomy")
async def get_industry_taxonomy():
    return {
        "industries": list_supported_industries(),
        "categories": ALL_EXPENSE_CATEGORIES,
    }

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

@api_router.post("/workspaces/{workspace_id}/transactions/{transaction_id}/anomaly-feedback")
async def submit_anomaly_feedback(
    workspace_id: str,
    transaction_id: str,
    payload: Dict[str, Any],
    workspace_context: dict = Depends(get_current_workspace_user),
    db: AsyncSession = Depends(get_db)
):
    feedback = payload.get("feedback", "legitimate").lower().strip()
    notes = payload.get("notes")
    confirmed_cat = payload.get("confirmed_category")
    user_id = workspace_context.get("user_id") if isinstance(workspace_context, dict) else None
    return await TransactionService.submit_anomaly_feedback(
        db, workspace_id, transaction_id, feedback, notes, confirmed_cat, user_id
    )

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

@api_router.get("/workspaces/{workspace_id}/reports/summary")
async def report_comprehensive_summary(
    workspace_id: str,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    workspace_context: dict = Depends(get_current_workspace_user),
    db: AsyncSession = Depends(get_db)
):
    return await ReportService.get_comprehensive_financial_data(db, workspace_id, start_date, end_date)

@api_router.get("/workspaces/{workspace_id}/reports/export/excel")
async def export_excel_report(
    workspace_id: str,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    workspace_context: dict = Depends(get_current_workspace_user),
    db: AsyncSession = Depends(get_db)
):
    excel_bytes = await ReportService.export_excel_report(db, workspace_id, start_date, end_date)
    return Response(
        content=excel_bytes,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="CashIQ_Report_{workspace_id[:8]}.xlsx"'}
    )

@api_router.get("/workspaces/{workspace_id}/reports/export/pdf")
async def export_pdf_report(
    workspace_id: str,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    workspace_context: dict = Depends(get_current_workspace_user),
    db: AsyncSession = Depends(get_db)
):
    pdf_bytes = await ReportService.export_pdf_report(db, workspace_id, start_date, end_date)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="CashIQ_Report_{workspace_id[:8]}.pdf"'}
    )

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

# ----------------- ML System Architecture & Serving -----------------
@api_router.get("/workspaces/{workspace_id}/ml/status")
async def get_workspace_ml_status(
    workspace_id: str,
    workspace_context: dict = Depends(get_current_workspace_user),
    db: AsyncSession = Depends(get_db)
):
    return await ml_orchestrator.get_system_status(db, workspace_id)

@api_router.post("/workspaces/{workspace_id}/ml/retrain")
async def retrain_workspace_ml(
    workspace_id: str,
    workspace_context: dict = Depends(get_current_workspace_user),
    db: AsyncSession = Depends(get_db)
):
    return await ml_orchestrator.retrain_workspace_models(db, workspace_id)

@api_router.post("/workspaces/{workspace_id}/ml/scan-anomalies")
async def scan_workspace_anomalies(
    workspace_id: str,
    workspace_context: dict = Depends(get_current_workspace_user),
    db: AsyncSession = Depends(get_db)
):
    return await model_serving.scan_workspace_anomalies(db, workspace_id)

@api_router.get("/workspaces/{workspace_id}/ml/ground-truth")
async def list_workspace_ground_truth(
    workspace_id: str,
    feedback_type: Optional[str] = None,
    limit: int = Query(50, ge=1, le=200),
    workspace_context: dict = Depends(get_current_workspace_user),
    db: AsyncSession = Depends(get_db)
):
    return await ground_truth_collector.get_verified_ground_truth(db, workspace_id, feedback_type, limit)

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

# ----------------- What-If Financial Simulator -----------------
@api_router.post("/workspaces/{workspace_id}/simulation/run")
async def run_financial_simulation(
    workspace_id: str,
    payload: Dict[str, Any],
    workspace_context: dict = Depends(get_current_workspace_user),
    db: AsyncSession = Depends(get_db)
):
    rev_pct = float(payload.get("revenue_change_pct", 0.0))
    exp_pct = float(payload.get("expense_change_pct", 0.0))
    delay_days = int(payload.get("delayed_receivables_days", 0))
    months = int(payload.get("months", 6))
    custom_events = payload.get("custom_events", [])
    return await SimulationService.run_simulation(
        db,
        workspace_id=workspace_id,
        revenue_change_pct=rev_pct,
        expense_change_pct=exp_pct,
        delayed_receivables_days=delay_days,
        months=months,
        custom_events=custom_events
    )

@api_router.get("/workspaces/{workspace_id}/simulation/scenarios")
async def list_simulation_scenarios(
    workspace_id: str,
    workspace_context: dict = Depends(get_current_workspace_user),
    db: AsyncSession = Depends(get_db)
):
    scenarios = await SimulationService.list_scenarios(db, workspace_id)
    return [
        {
            "id": s.id,
            "name": s.name,
            "description": s.description,
            "parameters": s.parameters,
            "results": s.results,
            "created_at": s.created_at.isoformat(),
        }
        for s in scenarios
    ]

@api_router.post("/workspaces/{workspace_id}/simulation/scenarios")
async def save_simulation_scenario(
    workspace_id: str,
    payload: Dict[str, Any],
    workspace_context: dict = Depends(require_workspace_role(["owner", "admin", "accountant"])),
    db: AsyncSession = Depends(get_db)
):
    name = payload.get("name")
    if not name:
        raise HTTPException(status_code=400, detail="Scenario name is required")
    description = payload.get("description")
    parameters = payload.get("parameters", {})
    results = payload.get("results", {})
    scenario = await SimulationService.save_scenario(
        db,
        workspace_id=workspace_id,
        name=name,
        description=description,
        parameters=parameters,
        results=results,
        user_id=workspace_context["user"].id
    )
    return {
        "id": scenario.id,
        "name": scenario.name,
        "description": scenario.description,
        "parameters": scenario.parameters,
        "results": scenario.results,
        "created_at": scenario.created_at.isoformat(),
    }

@api_router.delete("/workspaces/{workspace_id}/simulation/scenarios/{scenario_id}")
async def delete_simulation_scenario(
    workspace_id: str,
    scenario_id: str,
    workspace_context: dict = Depends(require_workspace_role(["owner", "admin"])),
    db: AsyncSession = Depends(get_db)
):
    success = await SimulationService.delete_scenario(db, workspace_id, scenario_id)
    if not success:
        raise HTTPException(status_code=404, detail="Scenario not found")
    return {"message": "Scenario deleted successfully"}

# ----------------- Budget Management -----------------
@api_router.get("/workspaces/{workspace_id}/budgets")
async def list_workspace_budgets(
    workspace_id: str,
    workspace_context: dict = Depends(get_current_workspace_user),
    db: AsyncSession = Depends(get_db)
):
    return await BudgetService.list_budgets(db, workspace_id)

@api_router.post("/workspaces/{workspace_id}/budgets")
async def create_or_update_workspace_budget(
    workspace_id: str,
    payload: Dict[str, Any],
    workspace_context: dict = Depends(require_workspace_role(["owner", "admin", "accountant"])),
    db: AsyncSession = Depends(get_db)
):
    month = payload.get("month")
    if not month:
        raise HTTPException(status_code=400, detail="Month is required in YYYY-MM format")
    name = payload.get("name")
    category_limits = payload.get("category_limits", [])
    total_limit = payload.get("total_limit_minor")
    currency = payload.get("currency", "USD")
    return await BudgetService.create_or_update_budget(
        db,
        workspace_id=workspace_id,
        month=month,
        name=name,
        category_limits=category_limits,
        total_limit_minor=total_limit,
        currency=currency,
        user_id=workspace_context["user"].id
    )

@api_router.get("/workspaces/{workspace_id}/budgets/performance")
async def get_workspace_budget_performance(
    workspace_id: str,
    month: Optional[str] = None,
    workspace_context: dict = Depends(get_current_workspace_user),
    db: AsyncSession = Depends(get_db)
):
    return await BudgetService.get_budget_performance(db, workspace_id, month)

@api_router.delete("/workspaces/{workspace_id}/budgets/{budget_id}")
async def delete_workspace_budget(
    workspace_id: str,
    budget_id: str,
    workspace_context: dict = Depends(require_workspace_role(["owner", "admin"])),
    db: AsyncSession = Depends(get_db)
):
    success = await BudgetService.delete_budget(db, workspace_id, budget_id)
    if not success:
        raise HTTPException(status_code=404, detail="Budget not found")
    return {"message": "Budget deleted successfully"}

# ----------------- Bank Statement Reconciliation -----------------
@api_router.post("/workspaces/{workspace_id}/reconciliation/upload")
async def upload_bank_statement_reconciliation(
    workspace_id: str,
    file: UploadFile = File(...),
    account_id: Optional[str] = None,
    workspace_context: dict = Depends(require_workspace_role(["owner", "admin", "accountant"])),
    db: AsyncSession = Depends(get_db)
):
    if not file.filename.lower().endswith((".csv", ".txt")):
        raise HTTPException(status_code=400, detail="Only CSV bank statements are supported for reconciliation.")
    
    content_bytes = await file.read()
    try:
        content_str = content_bytes.decode("utf-8")
    except UnicodeDecodeError:
        content_str = content_bytes.decode("latin-1")

    try:
        result = await ReconciliationService.process_reconciliation(
            db,
            workspace_id=workspace_id,
            filename=file.filename,
            file_content=content_str,
            account_id=account_id,
            user_id=workspace_context["user"].id
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@api_router.get("/workspaces/{workspace_id}/reconciliation/sessions")
async def list_reconciliation_sessions(
    workspace_id: str,
    workspace_context: dict = Depends(get_current_workspace_user),
    db: AsyncSession = Depends(get_db)
):
    return await ReconciliationService.list_sessions(db, workspace_id)

@api_router.get("/workspaces/{workspace_id}/reconciliation/sessions/{session_id}")
async def get_reconciliation_session(
    workspace_id: str,
    session_id: str,
    workspace_context: dict = Depends(get_current_workspace_user),
    db: AsyncSession = Depends(get_db)
):
    sess = await ReconciliationService.get_session(db, workspace_id, session_id)
    if not sess:
        raise HTTPException(status_code=404, detail="Reconciliation session not found")
    return sess

@api_router.post("/workspaces/{workspace_id}/reconciliation/sessions/{session_id}/approve")
async def approve_reconciliation_match(
    workspace_id: str,
    session_id: str,
    payload: Dict[str, Any],
    workspace_context: dict = Depends(require_workspace_role(["owner", "admin", "accountant"])),
    db: AsyncSession = Depends(get_db)
):
    item_id = payload.get("item_id")
    if not item_id:
        raise HTTPException(status_code=400, detail="item_id is required")
    success = await ReconciliationService.approve_match(db, workspace_id, session_id, item_id)
    if not success:
        raise HTTPException(status_code=404, detail="Reconciliation item not found")
    return {"message": "Match approved"}

@api_router.post("/workspaces/{workspace_id}/reconciliation/sessions/{session_id}/import-unmatched")
async def import_unmatched_reconciliation(
    workspace_id: str,
    session_id: str,
    payload: Dict[str, Any],
    workspace_context: dict = Depends(require_workspace_role(["owner", "admin", "accountant"])),
    db: AsyncSession = Depends(get_db)
):
    item_ids = payload.get("item_ids", [])
    if not item_ids:
        raise HTTPException(status_code=400, detail="item_ids array is required")
    imported = await ReconciliationService.import_unmatched_to_ledger(
        db,
        workspace_id=workspace_id,
        session_id=session_id,
        item_ids=item_ids,
        user_id=workspace_context["user"].id
    )
    return {"imported_count": imported, "message": f"Successfully imported {imported} transactions to ledger."}

@api_router.get("/workspaces/{workspace_id}/reconciliation/sessions/{session_id}/export-report")
async def export_reconciliation_report(
    workspace_id: str,
    session_id: str,
    workspace_context: dict = Depends(get_current_workspace_user),
    db: AsyncSession = Depends(get_db)
):
    sess = await ReconciliationService.get_session(db, workspace_id, session_id)
    if not sess:
        raise HTTPException(status_code=404, detail="Session not found")

    import csv, io
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(["Date", "Description", "Statement Amount", "Match Type", "Status", "Discrepancy Details", "CashIQ Transaction ID"])
    for it in sess["items"]:
        amt = f"${(it['amount_minor']/100):,.2f}"
        discr = (it.get("discrepancy_details") or {}).get("reason", "")
        writer.writerow([
            it["date"],
            it["description"],
            amt,
            it["match_type"],
            it["status"],
            discr,
            it.get("transaction_id") or ""
        ])

    csv_bytes = out.getvalue().encode("utf-8")
    return Response(
        content=csv_bytes,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="reconciliation_report_{session_id[:8]}.csv"'}
    )

# ----------------- Financial Health Score -----------------
@api_router.get("/workspaces/{workspace_id}/health-score")
async def get_financial_health_score(
    workspace_id: str,
    workspace_context: dict = Depends(get_current_workspace_user),
    db: AsyncSession = Depends(get_db)
):
    return await HealthScoreService.calculate_health_score(db, workspace_id, persist=True)

# ----------------- Audit Logs -----------------
@api_router.get("/workspaces/{workspace_id}/audit-logs")
async def get_workspace_audit_logs(
    workspace_id: str,
    limit: int = Query(50, ge=1, le=200),
    workspace_context: dict = Depends(require_workspace_role(["owner", "admin"])),
    db: AsyncSession = Depends(get_db)
):
    return await AuditService.list_events(db, workspace_id, limit=limit)

# ----------------- Anomalies Management -----------------
@api_router.get("/workspaces/{workspace_id}/anomalies")
async def list_workspace_anomalies(
    workspace_id: str,
    severity: Optional[str] = Query(None, description="all, high, medium, low"),
    feedback_status: Optional[str] = Query(None, description="pending, legitimate, genuine_anomaly"),
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=100),
    workspace_context: dict = Depends(get_current_workspace_user),
    db: AsyncSession = Depends(get_db)
):
    from sqlalchemy import and_, select, func
    from app.models.transaction import Transaction

    query = select(Transaction).where(
        Transaction.workspace_id == workspace_id,
        Transaction.is_anomaly == True
    )

    if severity and severity.lower() != "all":
        sev = severity.lower()
        if sev == "high":
            query = query.where(Transaction.anomaly_severity.in_(["critical", "high"]))
        elif sev == "medium":
            query = query.where(Transaction.anomaly_severity == "medium")
        elif sev == "low":
            query = query.where(Transaction.anomaly_severity == "low")

    if feedback_status:
        if feedback_status == "pending":
            query = query.where(Transaction.anomaly_feedback_status.is_(None))
        else:
            query = query.where(Transaction.anomaly_feedback_status == feedback_status)

    # Count total
    count_q = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_q)).scalar() or 0

    # Paginate
    query = query.order_by(Transaction.date.desc()).offset((page - 1) * per_page).limit(per_page)
    res = await db.execute(query)
    txs = res.scalars().all()

    import json
    items = []
    for t in txs:
        parsed_expl = None
        if t.anomaly_explanation:
            try:
                parsed_expl = json.loads(t.anomaly_explanation)
            except Exception:
                parsed_expl = None

        items.append({
            "id": t.id,
            "date": t.date.strftime("%Y-%m-%d"),
            "description": t.description,
            "merchant": t.merchant,
            "amount_minor": t.amount_minor,
            "currency": t.currency,
            "category_name": t.category_name,
            "type": t.type,
            "anomaly_score": t.anomaly_score,
            "anomaly_severity": "high" if t.anomaly_severity in ["critical", "high"] else (t.anomaly_severity or "medium"),
            "anomaly_reason": t.anomaly_reason,
            "anomaly_feedback_status": t.anomaly_feedback_status,
            "anomaly_explanation_details": parsed_expl,
        })

    return {
        "items": items,
        "total": total,
        "page": page,
        "per_page": per_page,
        "total_pages": max(1, (total + per_page - 1) // per_page)
    }


