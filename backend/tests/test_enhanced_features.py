"""
Comprehensive End-to-End Tests for Enhanced Features (v4.0.0):
1. What-If Financial Simulator (adjusting expenses/revenues/payment terms, best/expected/worst case, runway, save/list/delete scenarios)
2. Budget Management (creating monthly budgets with category limits, real-time variance against transactions, overspending alerts, deletion)
3. Bank Statement Reconciliation (CSV parsing, exact/probable match detection, match approval, importing unmatched items, discrepancy reports)
4. Financial Health Score (5 transparent factor scores, letter grade, driver explanations, recommendations, historical storage)
5. Automated Financial Reports (Excel spreadsheet generation with openpyxl, PDF generation with reportlab, summary metrics)
6. Security, RBAC & Isolation (token refresh endpoint, login rate limiting, workspace isolation, audit logging)
"""

from datetime import datetime, timezone
import io
import os
import sys
import uuid
import pytest
import httpx

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.database import Base, engine, safe_migrate_db
from app.main import app


@pytest.mark.asyncio
async def test_enhanced_what_if_simulator():
    """Test What-If Financial Simulator calculations, multi-scenario projections, and scenario persistence."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.run_sync(safe_migrate_db)

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        # Register user and workspace
        uniq = uuid.uuid4().hex[:8]
        reg = await client.post("/api/auth/register", json={
            "email": f"sim_user_{uniq}@cashiq.test",
            "password": "Password123!",
            "full_name": "Simulator Tester",
        })
        assert reg.status_code in (200, 201), reg.text
        token = reg.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        ws_res = await client.post("/api/workspaces", headers=headers, json={
            "name": f"Sim Workspace {uniq}",
            "currency": "USD",
        })
        assert ws_res.status_code == 200
        wid = ws_res.json()["id"]

        # Seed baseline transactions
        now_iso = datetime.now(timezone.utc).isoformat()
        await client.post(f"/api/workspaces/{wid}/transactions", headers=headers, json={
            "description": "Enterprise Subscription Revenue",
            "merchant": "Enterprise Corp",
            "amount_minor": 1000000,  # $10,000
            "currency": "USD",
            "type": "income",
            "category_name": "Sales Revenue",
            "date": now_iso,
        })
        await client.post(f"/api/workspaces/{wid}/transactions", headers=headers, json={
            "description": "AWS Cloud Servers",
            "merchant": "Amazon Web Services",
            "amount_minor": 300000,  # $3,000
            "currency": "USD",
            "type": "expense",
            "category_name": "Software & Cloud Services",
            "date": now_iso,
        })

        # 1. Run simulation with expense increase and payment delay
        sim_res = await client.post(f"/api/workspaces/{wid}/simulation/run", headers=headers, json={
            "expense_change_pct": 20.0,
            "revenue_change_pct": -10.0,
            "delayed_receivables_days": 30,
            "months": 6,
        })
        assert sim_res.status_code == 200, sim_res.text
        sim_data = sim_res.json()

        assert "scenarios" in sim_data
        scenarios = sim_data["scenarios"]
        assert "baseline" in scenarios
        assert "expected_case" in scenarios
        assert "best_case" in scenarios
        assert "worst_case" in scenarios

        # Verify projections structure
        expected = scenarios["expected_case"]
        assert len(expected["projections"]) == 6
        assert expected["projections"][0]["month_index"] == 1
        assert "ending_cash_minor" in expected["projections"][0]
        assert "runway_months" in expected
        assert isinstance(expected["runway_months"], (int, float))

        # 2. Save Scenario
        save_res = await client.post(f"/api/workspaces/{wid}/simulation/scenarios", headers=headers, json={
            "name": f"Recession Test {uniq}",
            "description": "20% expense hike + 10% revenue drop",
            "parameters": {
                "expense_change_pct": 20.0,
                "revenue_change_pct": -10.0,
                "delayed_receivables_days": 30,
                "months": 6,
            },
            "results": {
                "runway_months": expected["runway_months"],
                "ending_cash_minor": expected["ending_cash_minor"],
            }
        })
        assert save_res.status_code == 200, save_res.text
        saved_scenario = save_res.json()
        scen_id = saved_scenario["id"]
        assert saved_scenario["name"] == f"Recession Test {uniq}"

        # 3. List Scenarios
        list_res = await client.get(f"/api/workspaces/{wid}/simulation/scenarios", headers=headers)
        assert list_res.status_code == 200
        scen_list = list_res.json()
        assert any(s["id"] == scen_id for s in scen_list)

        # 4. Delete Scenario
        del_res = await client.delete(f"/api/workspaces/{wid}/simulation/scenarios/{scen_id}", headers=headers)
        assert del_res.status_code == 200
        assert "Scenario deleted successfully" in del_res.json()["message"]


@pytest.mark.asyncio
async def test_enhanced_budget_management():
    """Test monthly budget creation, category limits, real-time variance and overspending alerts."""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        uniq = uuid.uuid4().hex[:8]
        reg = await client.post("/api/auth/register", json={
            "email": f"budget_user_{uniq}@cashiq.test",
            "password": "Password123!",
            "full_name": "Budget Tester",
        })
        token = reg.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        ws_res = await client.post("/api/workspaces", headers=headers, json={
            "name": f"Budget Workspace {uniq}",
            "currency": "USD",
        })
        wid = ws_res.json()["id"]

        # Current month YYYY-MM
        current_month = datetime.now(timezone.utc).strftime("%Y-%m")

        # 1. Create Monthly Budget with category limits
        b_res = await client.post(f"/api/workspaces/{wid}/budgets", headers=headers, json={
            "month": current_month,
            "name": f"Operating Budget {current_month}",
            "total_limit_minor": 1000000,  # $10,000 total limit
            "category_limits": [
                {"category_name": "Software & Cloud Services", "limit_minor": 400000},  # $4,000 limit
                {"category_name": "Office Supplies", "limit_minor": 100000},          # $1,000 limit
            ],
        })
        assert b_res.status_code == 200, b_res.text
        b_data = b_res.json()
        bid = b_data["budget_id"]
        assert bid is not None
        assert b_data["total_budget_limit_minor"] == 1000000

        # 2. Check initial budget performance before transactions
        perf_res = await client.get(f"/api/workspaces/{wid}/budgets/performance?month={current_month}", headers=headers)
        assert perf_res.status_code == 200
        perf = perf_res.json()
        assert perf["total_spent_minor"] == 0
        assert perf["remaining_minor"] == 1000000
        assert perf["status"] != "over_budget"

        # 3. Add an expense that exceeds the Software category limit ($4,500 > $4,000)
        now_iso = datetime.now(timezone.utc).isoformat()
        await client.post(f"/api/workspaces/{wid}/transactions", headers=headers, json={
            "description": "Datadog Monitoring & Logs",
            "merchant": "Datadog",
            "amount_minor": 450000,  # $4,500
            "currency": "USD",
            "type": "expense",
            "category_name": "Software & Cloud Services",
            "date": now_iso,
        })

        # 4. Re-check performance - verify overspending detected
        perf_res2 = await client.get(f"/api/workspaces/{wid}/budgets/performance?month={current_month}", headers=headers)
        assert perf_res2.status_code == 200
        perf2 = perf_res2.json()
        assert perf2["total_spent_minor"] == 450000
        assert perf2["remaining_minor"] == 550000

        # Check category performance breakdown
        cat_sw = next(c for c in perf2["category_performances"] if c["category"] == "Software & Cloud Services")
        assert cat_sw["spent_minor"] == 450000
        assert cat_sw["limit_minor"] == 400000
        assert cat_sw["status"] == "over_budget"
        assert len(perf2["alerts"]) > 0

        # 5. Delete Budget
        del_b = await client.delete(f"/api/workspaces/{wid}/budgets/{bid}", headers=headers)
        assert del_b.status_code == 200
        assert "Budget deleted successfully" in del_b.json()["message"]


@pytest.mark.asyncio
async def test_enhanced_bank_reconciliation():
    """Test CSV bank statement upload, matching engine, item approval, and unmatched record ledger import."""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        uniq = uuid.uuid4().hex[:8]
        reg = await client.post("/api/auth/register", json={
            "email": f"recon_user_{uniq}@cashiq.test",
            "password": "Password123!",
            "full_name": "Recon Tester",
        })
        token = reg.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        ws_res = await client.post("/api/workspaces", headers=headers, json={
            "name": f"Recon Workspace {uniq}",
            "currency": "USD",
        })
        wid = ws_res.json()["id"]

        # Seed an existing internal transaction
        now_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        now_iso = f"{now_date}T10:00:00Z"
        tx_res = await client.post(f"/api/workspaces/{wid}/transactions", headers=headers, json={
            "description": "Stripe Processing Fees",
            "merchant": "Stripe",
            "amount_minor": 15000,  # $150.00
            "currency": "USD",
            "type": "expense",
            "category_name": "Bank & Processing Fees",
            "date": now_iso,
        })
        assert tx_res.status_code == 200
        seeded_tx_id = tx_res.json()["id"]

        # Create a CSV statement with 1 matching item and 1 unmatched item
        csv_content = (
            "Date,Description,Amount,Type,Reference\n"
            f"{now_date},Stripe Processing Fees,-150.00,Debit,REF_STRIPE_01\n"
            f"{now_date},Unexpected Bank Service Fee,-25.00,Debit,REF_FEE_99\n"
        ).encode("utf-8")

        # 1. Upload CSV Bank Statement
        up_res = await client.post(
            f"/api/workspaces/{wid}/reconciliation/upload",
            headers=headers,
            files={"file": ("nov_bank_statement.csv", csv_content, "text/csv")},
        )
        assert up_res.status_code == 200, up_res.text
        session_data = up_res.json()
        sid = session_data["session_id"]
        assert session_data["total_statement_rows"] == 2
        assert session_data["matched_count"] >= 1
        assert session_data["unmatched_bank_count"] >= 1

        # 2. Get Session Details
        sess_detail = await client.get(f"/api/workspaces/{wid}/reconciliation/sessions/{sid}", headers=headers)
        assert sess_detail.status_code == 200
        items = sess_detail.json()["items"]
        assert len(items) == 2

        matched_item = next(it for it in items if it["transaction_id"] == seeded_tx_id)
        assert matched_item["match_type"] in {"exact", "probable"}

        # 3. Approve matched item
        app_res = await client.post(
            f"/api/workspaces/{wid}/reconciliation/sessions/{sid}/approve",
            headers=headers,
            json={"item_id": matched_item["id"]},
        )
        assert app_res.status_code == 200
        assert "Match approved" in app_res.json()["message"]

        # 4. Import unmatched items into ledger as official transactions
        unmatched_items = [it["id"] for it in items if it["match_type"] == "unmatched_bank"]
        imp_res = await client.post(
            f"/api/workspaces/{wid}/reconciliation/sessions/{sid}/import-unmatched",
            headers=headers,
            json={"item_ids": unmatched_items},
        )
        assert imp_res.status_code == 200
        assert imp_res.json()["imported_count"] >= 1

        # 5. Export Discrepancy & Reconciliation CSV Report
        rep_res = await client.get(f"/api/workspaces/{wid}/reconciliation/sessions/{sid}/export-report", headers=headers)
        assert rep_res.status_code == 200
        assert "Date,Description,Statement Amount" in rep_res.text


@pytest.mark.asyncio
async def test_enhanced_financial_health_score():
    """Test 5-factor deterministic financial health scoring, letter grade, and historical logging."""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        uniq = uuid.uuid4().hex[:8]
        reg = await client.post("/api/auth/register", json={
            "email": f"health_user_{uniq}@cashiq.test",
            "password": "Password123!",
            "full_name": "Health Tester",
        })
        token = reg.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        ws_res = await client.post("/api/workspaces", headers=headers, json={
            "name": f"Health Workspace {uniq}",
            "currency": "USD",
        })
        wid = ws_res.json()["id"]

        now_iso = datetime.now(timezone.utc).isoformat()
        # Seed positive cashflow
        await client.post(f"/api/workspaces/{wid}/transactions", headers=headers, json={
            "description": "Quarterly SaaS ARR",
            "merchant": "Global Clients Inc",
            "amount_minor": 15000000,  # $150,000
            "currency": "USD",
            "type": "income",
            "category_name": "Sales Revenue",
            "date": now_iso,
        })
        await client.post(f"/api/workspaces/{wid}/transactions", headers=headers, json={
            "description": "Salaries & Payroll",
            "merchant": "Payroll Provider",
            "amount_minor": 5000000,  # $50,000
            "currency": "USD",
            "type": "expense",
            "category_name": "Payroll",
            "date": now_iso,
        })

        # Calculate Financial Health Score
        score_res = await client.get(f"/api/workspaces/{wid}/health-score", headers=headers)
        assert score_res.status_code == 200, score_res.text
        data = score_res.json()

        assert 0 <= data["overall_score"] <= 100
        assert data["grade"] in {"A+", "A", "B", "C", "D", "F"}
        assert "factors" in data

        factors = data["factors"]
        factor_ids = {f["id"] for f in factors}
        for expected_id in ["cash_flow_stability", "cash_reserves", "expense_revenue_ratio", "payables_liquidity", "receivables_health"]:
            assert expected_id in factor_ids

        assert len(data["suggestions"]) > 0


@pytest.mark.asyncio
async def test_enhanced_reports_excel_and_pdf():
    """Test automated financial reports generation for summary, Excel (.xlsx) and PDF (.pdf)."""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        uniq = uuid.uuid4().hex[:8]
        reg = await client.post("/api/auth/register", json={
            "email": f"report_user_{uniq}@cashiq.test",
            "password": "Password123!",
            "full_name": "Report Tester",
        })
        token = reg.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        ws_res = await client.post("/api/workspaces", headers=headers, json={
            "name": f"Report Workspace {uniq}",
            "currency": "USD",
        })
        wid = ws_res.json()["id"]

        now_iso = datetime.now(timezone.utc).isoformat()
        await client.post(f"/api/workspaces/{wid}/transactions", headers=headers, json={
            "description": "Consulting Revenue",
            "merchant": "Partner Corp",
            "amount_minor": 800000,  # $8,000
            "currency": "USD",
            "type": "income",
            "category_name": "Consulting",
            "date": now_iso,
        })

        # 1. Summary Report JSON
        sum_res = await client.get(f"/api/workspaces/{wid}/reports/summary", headers=headers)
        assert sum_res.status_code == 200
        summary = sum_res.json()
        assert "income_expense" in summary
        assert summary["income_expense"]["total_income_minor"] == 800000

        # 2. Export Excel Report (.xlsx)
        excel_res = await client.get(f"/api/workspaces/{wid}/reports/export/excel", headers=headers)
        assert excel_res.status_code == 200
        assert len(excel_res.content) > 1000
        # OpenXML / ZIP magic header
        assert excel_res.content.startswith(b"PK")

        # 3. Export PDF Report (.pdf)
        pdf_res = await client.get(f"/api/workspaces/{wid}/reports/export/pdf", headers=headers)
        assert pdf_res.status_code == 200
        assert len(pdf_res.content) > 1000
        # PDF magic header
        assert pdf_res.content.startswith(b"%PDF-")


@pytest.mark.asyncio
async def test_security_refresh_rate_limit_and_isolation():
    """Test token refresh, login rate limiting, workspace data isolation and audit logs."""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        # 1. Register User A
        uniq = uuid.uuid4().hex[:8]
        email_a = f"sec_a_{uniq}@cashiq.test"
        reg_a = await client.post("/api/auth/register", json={
            "email": email_a,
            "password": "Password123!",
            "full_name": "User Alpha",
        })
        assert reg_a.status_code in (200, 201)
        data_a = reg_a.json()
        assert "access_token" in data_a
        assert "refresh_token" in data_a
        refresh_token_a = data_a["refresh_token"]

        ws_a = await client.post("/api/workspaces", headers={"Authorization": f"Bearer {data_a['access_token']}"}, json={
            "name": f"Alpha Confidential {uniq}",
            "currency": "USD",
        })
        wid_a = ws_a.json()["id"]

        # 2. Token Refresh Endpoint
        ref_res = await client.post("/api/auth/refresh", json={"refresh_token": refresh_token_a})
        assert ref_res.status_code == 200, ref_res.text
        assert "access_token" in ref_res.json()

        # 3. Workspace Data Isolation: Register User B
        email_b = f"sec_b_{uniq}@cashiq.test"
        reg_b = await client.post("/api/auth/register", json={
            "email": email_b,
            "password": "Password123!",
            "full_name": "User Beta",
        })
        token_b = reg_b.json()["access_token"]
        headers_b = {"Authorization": f"Bearer {token_b}"}

        # User B attempts to access User A's workspace transactions -> MUST be denied (403 or 404)
        denied_res = await client.get(f"/api/workspaces/{wid_a}/transactions", headers=headers_b)
        assert denied_res.status_code in {403, 404}

        # 4. Audit Logs Verification
        audit_res = await client.get(f"/api/workspaces/{wid_a}/audit-logs", headers={"Authorization": f"Bearer {data_a['access_token']}"})
        assert audit_res.status_code == 200
        logs = audit_res.json()
        assert isinstance(logs, list)

        # 5. Login Rate Limiting (5 attempts allowed per 5 min; 6th returns 429)
        spam_email = f"spam_{uniq}@test.invalid"
        for _ in range(5):
            await client.post("/api/auth/login", json={"email": spam_email, "password": "WrongPassword"})

        blocked_res = await client.post("/api/auth/login", json={"email": spam_email, "password": "WrongPassword"})
        assert blocked_res.status_code == 429
        assert "Too many failed login attempts" in blocked_res.json()["detail"]
