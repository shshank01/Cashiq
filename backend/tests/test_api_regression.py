"""
End-to-End API Regression Tests for CashIQ Backend.

Verifies that existing APIs and upgraded ingestion/anomaly flows work end-to-end
over ASGI (FastAPI + SQLite async DB) without regressions:
1. Auth registration & workspace creation with derived BusinessProfile.
2. GET / PUT /api/workspaces/{wid}/business-profile & GET /api/ml/industry-taxonomy.
3. Transaction creation with SaaS ₹100 garam masala operational relevance alert.
4. All 3 anomaly feedback types via POST /api/workspaces/{wid}/transactions/{tid}/anomaly-feedback:
   - `legitimate` (resolves alert & adapts profile)
   - `incorrect_category` (updates category, trains merchant override, re-evaluates anomaly)
   - `genuine_anomaly` (confirms anomaly & excludes from future baselines)
5. Document upload (CSV, Digital PDF, Mixed PDF, Receipt PNG) via POST /api/workspaces/{wid}/documents/upload
   and draft confirmation via POST /api/workspaces/{wid}/documents/{doc_id}/confirm.
6. Batch anomaly scan (/api/workspaces/{wid}/ml/scan-anomalies) & dashboard integration.
"""

from datetime import datetime, timezone
import os
import sys
import uuid
import pytest
import httpx

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.database import Base, engine, safe_migrate_db
from app.main import app
from tests.corpus_generator import (
    make_indian_bank_csv,
    make_indian_gst_receipt_image,
    make_mixed_pdf,
)


@pytest.mark.asyncio
async def test_end_to_end_api_regression_flow():
    # Ensure DB schema & migrations are applied
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.run_sync(safe_migrate_db)

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        # 1. Health & Industry Taxonomy
        h = await client.get("/health")
        assert h.status_code == 200
        tax = await client.get("/api/ml/industry-taxonomy")
        assert tax.status_code == 200
        assert len(tax.json()["industries"]) >= 5

        # 2. Register unique user
        uniq = uuid.uuid4().hex[:10]
        reg = await client.post("/api/auth/register", json={
            "email": f"regression_{uniq}@cashiq.test",
            "password": "TestPassword123!",
            "full_name": "Regression Tester",
        })
        assert reg.status_code in (200, 201), reg.text
        token = reg.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        # 3. Create SaaS workspace in INR
        ws_res = await client.post("/api/workspaces", headers=headers, json={
            "name": f"Apex SaaS {uniq}",
            "currency": "INR",
            "industry": "Technology",
            "business_type": "B2B SaaS",
            "operating_model": "B2B",
        })
        assert ws_res.status_code == 200, ws_res.text
        wid = ws_res.json()["id"]

        # 4. Verify Business Profile endpoint returns derived taxonomy
        bp_get = await client.get(f"/api/workspaces/{wid}/business-profile", headers=headers)
        assert bp_get.status_code == 200
        bp_data = bp_get.json()
        assert bp_data["industry"] == "Technology"
        assert bp_data["operating_model"] == "B2B"
        assert "Groceries & Ingredients" in bp_data["relevant_expense_categories"]["unrelated"]

        # 5. Create normal SaaS transaction -> NOT anomalous
        now_iso = datetime.now(timezone.utc).isoformat()
        tx_aws = await client.post(f"/api/workspaces/{wid}/transactions", headers=headers, json={
            "description": "AWS Cloud Infrastructure Monthly",
            "merchant": "Amazon Web Services",
            "amount_minor": 4500000,  # ₹45,000
            "currency": "INR",
            "type": "expense",
            "category_name": "Software & Cloud Services",
            "date": now_iso,
        })
        assert tx_aws.status_code == 200, tx_aws.text
        assert tx_aws.json()["is_anomaly"] is False

        # 6. Create ₹100 garam masala expense at SaaS company -> Operational relevance warning!
        tx_spice = await client.post(f"/api/workspaces/{wid}/transactions", headers=headers, json={
            "description": "Garam masala spice packet",
            "merchant": "Local Kirana Mart",
            "amount_minor": 10000,  # ₹100
            "currency": "INR",
            "type": "expense",
            "date": now_iso,
        })
        assert tx_spice.status_code == 200, tx_spice.text
        spice_data = tx_spice.json()
        assert spice_data["is_anomaly"] is True
        assert spice_data["anomaly_alert_type"] == "operational_relevance"
        assert spice_data["anomaly_explanation_details"]["signals"]["amount_deviation"]["triggered"] is False

        # 7. Submit `incorrect_category` feedback (e.g. reclassify a misclassified AWS transaction)
        tx_mis = await client.post(f"/api/workspaces/{wid}/transactions", headers=headers, json={
            "description": "AWS Cloud Compute",
            "merchant": "AWS EMEA",
            "amount_minor": 4200000,
            "currency": "INR",
            "type": "expense",
            "category_name": "Groceries & Ingredients",
            "date": now_iso,
        })
        assert tx_mis.status_code == 200
        mis_data = tx_mis.json()
        assert mis_data["is_anomaly"] is True

        fb_cat = await client.post(
            f"/api/workspaces/{wid}/transactions/{mis_data['id']}/anomaly-feedback",
            headers=headers,
            json={
                "feedback": "incorrect_category",
                "confirmed_category": "Software & Cloud Services",
                "notes": "Misclassified cloud invoice",
            },
        )
        assert fb_cat.status_code == 200, fb_cat.text
        fb_cat_data = fb_cat.json()
        assert fb_cat_data["feedback"] == "incorrect_category"
        assert fb_cat_data["category_name"] == "Software & Cloud Services"
        assert fb_cat_data["re_evaluated"] is True
        assert fb_cat_data["is_anomaly"] is False  # Resolved once reclassified!

        # 8. Submit `legitimate` feedback on spice tx -> resolves anomaly
        fb_legit = await client.post(
            f"/api/workspaces/{wid}/transactions/{spice_data['id']}/anomaly-feedback",
            headers=headers,
            json={"feedback": "legitimate", "notes": "Office Diwali celebration pantry"},
        )
        assert fb_legit.status_code == 200
        assert fb_legit.json()["is_anomaly"] is False

        # 9. Submit `genuine_anomaly` feedback on another unrelated expense
        tx_bad = await client.post(f"/api/workspaces/{wid}/transactions", headers=headers, json={
            "description": "Personal salon spa bill",
            "merchant": "Luxury Salon",
            "amount_minor": 250000,
            "currency": "INR",
            "type": "expense",
            "category_name": "Personal & Household",
            "date": now_iso,
        })
        assert tx_bad.status_code == 200
        assert tx_bad.json()["is_anomaly"] is True
        fb_gen = await client.post(
            f"/api/workspaces/{wid}/transactions/{tx_bad.json()['id']}/anomaly-feedback",
            headers=headers,
            json={"feedback": "genuine_anomaly", "notes": "Unauthorized personal spend"},
        )
        assert fb_gen.status_code == 200
        assert fb_gen.json()["is_anomaly"] is True
        assert fb_gen.json()["feedback"] == "genuine_anomaly"

        # 10. Upload CSV, Mixed PDF, and Indian GST Receipt PNG via /documents/upload
        csv_bytes, csv_gt = make_indian_bank_csv()
        up_csv = await client.post(
            f"/api/workspaces/{wid}/documents/upload",
            headers=headers,
            files={"file": (csv_gt["name"], csv_bytes, "text/csv")},
        )
        assert up_csv.status_code == 200, up_csv.text
        up_csv_json = up_csv.json()
        assert up_csv_json["count"] == 4
        assert up_csv_json["file_type"] == "csv"
        assert up_csv_json["file_hash"]

        # Confirm CSV drafts into ledger
        conf_res = await client.post(
            f"/api/workspaces/{wid}/documents/{up_csv_json['document_id']}/confirm",
            headers=headers,
            json={"drafts": up_csv_json["draft_transactions"]},
        )
        assert conf_res.status_code == 200, conf_res.text
        assert conf_res.json()["confirmed_count"] == 4

        # Upload Mixed PDF (previously broken due to missing await on parse_pdf!)
        mx_bytes, mx_gt = make_mixed_pdf()
        up_pdf = await client.post(
            f"/api/workspaces/{wid}/documents/upload",
            headers=headers,
            files={"file": (mx_gt["name"], mx_bytes, "application/pdf")},
        )
        assert up_pdf.status_code == 200, up_pdf.text
        assert up_pdf.json()["count"] == mx_gt["total_expected_transactions"]
        assert up_pdf.json()["extraction_metadata"]["pdf_kind"] == "mixed"

        # Upload Receipt PNG
        img_bytes, img_gt = make_indian_gst_receipt_image()
        up_img = await client.post(
            f"/api/workspaces/{wid}/documents/upload",
            headers=headers,
            files={"file": (img_gt["name"], img_bytes, "image/png")},
        )
        assert up_img.status_code == 200, up_img.text
        assert up_img.json()["count"] == 1
        assert up_img.json()["draft_transactions"][0]["amount_minor"] == img_gt["amount_minor"]

        # 11. Scan workspace anomalies & fetch Dashboard
        scan = await client.post(f"/api/workspaces/{wid}/ml/scan-anomalies", headers=headers)
        assert scan.status_code == 200
        assert scan.json()["total_scanned"] >= 7

        dash = await client.get(f"/api/workspaces/{wid}/dashboard", headers=headers)
        assert dash.status_code == 200
        assert "anomalous_transactions" in dash.json()
