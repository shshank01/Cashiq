import io
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, desc

from app.models.transaction import Transaction
from app.models.account import Account
from app.models.workspace import Workspace
from app.models.payable import Payable
from app.models.receivable import Receivable
from app.models.budget import Budget, CategoryBudget

import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

class ReportService:
    @staticmethod
    def _parse_dates(start_date: Optional[str], end_date: Optional[str]) -> tuple[datetime, datetime]:
        now = datetime.now(timezone.utc)
        if start_date:
            try:
                s_dt = datetime.fromisoformat(start_date.replace("Z", "+00:00"))
                if s_dt.tzinfo is None:
                    s_dt = s_dt.replace(tzinfo=timezone.utc)
            except Exception:
                s_dt = now - timedelta(days=90)
        else:
            s_dt = now - timedelta(days=90)

        if end_date:
            try:
                e_dt = datetime.fromisoformat(end_date.replace("Z", "+00:00"))
                if e_dt.tzinfo is None:
                    e_dt = e_dt.replace(tzinfo=timezone.utc)
            except Exception:
                e_dt = now
        else:
            e_dt = now

        return s_dt, e_dt

    @staticmethod
    async def get_income_expense_report(
        db: AsyncSession,
        workspace_id: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None
    ) -> Dict[str, Any]:
        s_dt, e_dt = ReportService._parse_dates(start_date, end_date)

        tx_res = await db.execute(
            select(Transaction).where(
                Transaction.workspace_id == workspace_id,
                Transaction.date >= s_dt,
                Transaction.date <= e_dt
            )
        )
        txs = tx_res.scalars().all()

        revenue_by_cat = {}
        expense_by_cat = {}

        for t in txs:
            amt = abs(t.amount_minor)
            cat = t.category_name or "Miscellaneous"
            if t.type == "income":
                revenue_by_cat[cat] = revenue_by_cat.get(cat, 0) + amt
            else:
                expense_by_cat[cat] = expense_by_cat.get(cat, 0) + amt

        total_income = sum(revenue_by_cat.values())
        total_expenses = sum(expense_by_cat.values())
        net_income = total_income - total_expenses
        margin_pct = round((net_income / total_income * 100.0), 1) if total_income > 0 else 0.0

        return {
            "period": {
                "start_date": s_dt.strftime("%Y-%m-%d"),
                "end_date": e_dt.strftime("%Y-%m-%d")
            },
            "total_income_minor": total_income,
            "total_expenses_minor": total_expenses,
            "net_income_minor": net_income,
            "net_profit_margin_pct": margin_pct,
            "revenue_breakdown": [
                {"category": k, "amount_minor": v, "percentage": round((v / total_income) * 100, 1) if total_income > 0 else 0}
                for k, v in sorted(revenue_by_cat.items(), key=lambda x: x[1], reverse=True)
            ],
            "expense_breakdown": [
                {"category": k, "amount_minor": v, "percentage": round((v / total_expenses) * 100, 1) if total_expenses > 0 else 0}
                for k, v in sorted(expense_by_cat.items(), key=lambda x: x[1], reverse=True)
            ]
        }

    @staticmethod
    async def get_category_spend_report(
        db: AsyncSession,
        workspace_id: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None
    ) -> Dict[str, Any]:
        s_dt, e_dt = ReportService._parse_dates(start_date, end_date)

        tx_res = await db.execute(
            select(Transaction).where(
                Transaction.workspace_id == workspace_id,
                Transaction.type == "expense",
                Transaction.date >= s_dt,
                Transaction.date <= e_dt
            )
        )
        txs = tx_res.scalars().all()

        cats = {}
        for t in txs:
            cat = t.category_name or "Miscellaneous"
            if cat not in cats:
                cats[cat] = {"amount_minor": 0, "count": 0}
            cats[cat]["amount_minor"] += abs(t.amount_minor)
            cats[cat]["count"] += 1

        total_exp = sum(c["amount_minor"] for c in cats.values()) or 1

        items = [
            {
                "category": k,
                "amount_minor": v["amount_minor"],
                "transaction_count": v["count"],
                "percentage": round((v["amount_minor"] / total_exp) * 100, 1)
            }
            for k, v in sorted(cats.items(), key=lambda x: x[1]["amount_minor"], reverse=True)
        ]

        return {
            "period": {
                "start_date": s_dt.strftime("%Y-%m-%d"),
                "end_date": e_dt.strftime("%Y-%m-%d")
            },
            "total_spend_minor": total_exp if total_exp != 1 else 0,
            "categories": items
        }

    @staticmethod
    async def get_cash_flow_statement(
        db: AsyncSession,
        workspace_id: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None
    ) -> Dict[str, Any]:
        s_dt, e_dt = ReportService._parse_dates(start_date, end_date)

        acct_res = await db.execute(
            select(Account).where(Account.workspace_id == workspace_id, Account.is_active == True)
        )
        accounts = acct_res.scalars().all()
        ending_cash = sum(a.balance_minor for a in accounts)

        tx_res = await db.execute(
            select(Transaction).where(
                Transaction.workspace_id == workspace_id,
                Transaction.date >= s_dt,
                Transaction.date <= e_dt
            ).order_by(Transaction.date.asc())
        )
        txs = tx_res.scalars().all()

        operating_inflows = 0
        operating_outflows = 0
        investing_financing_flow = 0

        for t in txs:
            amt = abs(t.amount_minor)
            cat = (t.category_name or "").lower()
            if "investment" in cat or "loan" in cat or "financing" in cat or "equity" in cat:
                if t.type == "income":
                    investing_financing_flow += amt
                else:
                    investing_financing_flow -= amt
            else:
                if t.type == "income":
                    operating_inflows += amt
                else:
                    operating_outflows += amt

        net_operating_flow = operating_inflows - operating_outflows
        net_cash_change = net_operating_flow + investing_financing_flow
        beginning_cash = ending_cash - net_cash_change

        return {
            "period": {
                "start_date": s_dt.strftime("%Y-%m-%d"),
                "end_date": e_dt.strftime("%Y-%m-%d")
            },
            "beginning_cash_minor": beginning_cash,
            "operating_cash_inflows_minor": operating_inflows,
            "operating_cash_outflows_minor": operating_outflows,
            "net_operating_cash_flow_minor": net_operating_flow,
            "investing_financing_cash_flow_minor": investing_financing_flow,
            "net_change_in_cash_minor": net_cash_change,
            "ending_cash_minor": ending_cash
        }

    @staticmethod
    async def get_comprehensive_financial_data(
        db: AsyncSession,
        workspace_id: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None
    ) -> Dict[str, Any]:
        s_dt, e_dt = ReportService._parse_dates(start_date, end_date)

        # Workspace
        w_res = await db.execute(select(Workspace).where(Workspace.id == workspace_id))
        workspace = w_res.scalar_one_or_none()
        ws_name = workspace.name if workspace else "Business Workspace"
        currency = workspace.currency if workspace else "USD"

        # Core sub-reports
        inc_exp = await ReportService.get_income_expense_report(db, workspace_id, start_date, end_date)
        cat_spend = await ReportService.get_category_spend_report(db, workspace_id, start_date, end_date)
        cash_flow = await ReportService.get_cash_flow_statement(db, workspace_id, start_date, end_date)

        # Anomalies in period
        anom_res = await db.execute(
            select(Transaction).where(
                Transaction.workspace_id == workspace_id,
                Transaction.is_anomaly == True,
                Transaction.date >= s_dt,
                Transaction.date <= e_dt
            ).order_by(desc(Transaction.date))
        )
        anomalies = [
            {
                "date": a.date.strftime("%Y-%m-%d"),
                "description": a.description or a.merchant,
                "amount_minor": a.amount_minor,
                "category": a.category_name or "Miscellaneous",
                "severity": a.anomaly_severity or "medium",
                "reason": a.anomaly_reason or "Flagged by AI Anomaly Detector",
            }
            for a in anom_res.scalars().all()
        ]

        # Receivables & Payables
        p_res = await db.execute(
            select(Payable).where(Payable.workspace_id == workspace_id).order_by(Payable.due_date.asc())
        )
        payables = [
            {
                "vendor": p.vendor,
                "amount_minor": p.amount_minor,
                "due_date": p.due_date.strftime("%Y-%m-%d"),
                "status": p.status,
            }
            for p in p_res.scalars().all()
        ]

        r_res = await db.execute(
            select(Receivable).where(Receivable.workspace_id == workspace_id).order_by(Receivable.due_date.asc())
        )
        receivables = [
            {
                "client": r.client,
                "amount_minor": r.amount_minor,
                "due_date": r.due_date.strftime("%Y-%m-%d"),
                "status": r.status,
            }
            for r in r_res.scalars().all()
        ]

        # Active Budget Performance
        from app.services.budget_service import BudgetService
        budget_perf = await BudgetService.get_budget_performance(db, workspace_id, s_dt.strftime("%Y-%m"))

        return {
            "workspace_name": ws_name,
            "currency": currency,
            "period": {
                "start_date": s_dt.strftime("%Y-%m-%d"),
                "end_date": e_dt.strftime("%Y-%m-%d"),
            },
            "income_expense": inc_exp,
            "category_spend": cat_spend,
            "cash_flow": cash_flow,
            "anomalies": anomalies,
            "payables": payables,
            "receivables": receivables,
            "budget_performance": budget_perf,
        }

    @staticmethod
    async def export_excel_report(
        db: AsyncSession,
        workspace_id: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None
    ) -> bytes:
        data = await ReportService.get_comprehensive_financial_data(db, workspace_id, start_date, end_date)
        wb = openpyxl.Workbook()

        # Styles
        header_fill = PatternFill(start_color="0F766E", end_color="0F766E", fill_type="solid") # Teal 700
        subhead_fill = PatternFill(start_color="CCFBF1", end_color="CCFBF1", fill_type="solid") # Teal 100
        header_font = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
        title_font = Font(name="Calibri", size=14, bold=True, color="1C1917")
        bold_font = Font(name="Calibri", size=11, bold=True)
        regular_font = Font(name="Calibri", size=11)
        money_fmt = '$#,##0.00'

        thin_border = Border(
            left=Side(style='thin', color='E7E5E4'),
            right=Side(style='thin', color='E7E5E4'),
            top=Side(style='thin', color='E7E5E4'),
            bottom=Side(style='thin', color='E7E5E4')
        )

        def style_header_row(ws, row_idx, max_col):
            for col in range(1, max_col + 1):
                cell = ws.cell(row=row_idx, column=col)
                cell.fill = header_fill
                cell.font = header_font
                cell.alignment = Alignment(horizontal="center", vertical="center")

        def autofit_cols(ws):
            for col in ws.columns:
                max_len = max(len(str(cell.value or '')) for cell in col)
                col_letter = col[0].column_letter
                ws.column_dimensions[col_letter].width = max(14, min(40, max_len + 3))

        # ---------------- SHEET 1: Executive Summary ----------------
        ws1 = wb.active
        ws1.title = "Executive Summary"
        ws1["A1"] = f"CashIQ Financial Intelligence Report - {data['workspace_name']}"
        ws1["A1"].font = title_font
        ws1["A2"] = f"Reporting Period: {data['period']['start_date']} to {data['period']['end_date']}"
        ws1["A2"].font = regular_font

        ws1["A4"] = "Core Financial Metric"
        ws1["B4"] = "Amount"
        style_header_row(ws1, 4, 2)

        summary_rows = [
            ("Beginning Cash Balance", data["cash_flow"]["beginning_cash_minor"] / 100.0),
            ("Total Operating Revenue", data["income_expense"]["total_income_minor"] / 100.0),
            ("Total Operating Expenses", data["income_expense"]["total_expenses_minor"] / 100.0),
            ("Net Operating Cash Flow", data["cash_flow"]["net_operating_cash_flow_minor"] / 100.0),
            ("Net Change in Cash", data["cash_flow"]["net_change_in_cash_minor"] / 100.0),
            ("Ending Cash Balance", data["cash_flow"]["ending_cash_minor"] / 100.0),
            ("Net Profit Margin (%)", f"{data['income_expense']['net_profit_margin_pct']}%"),
            ("Active Payables Total", sum(p['amount_minor'] for p in data['payables']) / 100.0),
            ("Active Receivables Total", sum(r['amount_minor'] for r in data['receivables']) / 100.0),
            ("Flagged Anomalies Count", len(data["anomalies"])),
        ]

        for i, (metric, val) in enumerate(summary_rows, start=5):
            ws1.cell(row=i, column=1, value=metric).font = bold_font if "Balance" in metric or "Net" in metric else regular_font
            v_cell = ws1.cell(row=i, column=2, value=val)
            v_cell.font = bold_font if "Balance" in metric or "Net" in metric else regular_font
            if isinstance(val, (int, float)):
                v_cell.number_format = money_fmt
            ws1.cell(row=i, column=1).border = thin_border
            v_cell.border = thin_border
        autofit_cols(ws1)

        # ---------------- SHEET 2: Income & Expenses ----------------
        ws2 = wb.create_sheet(title="Income vs Expenses")
        ws2["A1"] = "Operating Revenue Breakdown"
        ws2["A1"].font = title_font
        ws2["A2"] = "Category"
        ws2["B2"] = "Amount"
        ws2["C2"] = "Share (%)"
        style_header_row(ws2, 2, 3)

        curr_r = 3
        for r_item in data["income_expense"]["revenue_breakdown"]:
            ws2.cell(row=curr_r, column=1, value=r_item["category"]).font = regular_font
            c2 = ws2.cell(row=curr_r, column=2, value=r_item["amount_minor"] / 100.0)
            c2.number_format = money_fmt
            ws2.cell(row=curr_r, column=3, value=f"{r_item['percentage']}%").font = regular_font
            curr_r += 1

        curr_r += 2
        ws2.cell(row=curr_r, column=1, value="Operating Expense Breakdown").font = title_font
        curr_r += 1
        ws2.cell(row=curr_r, column=1, value="Category")
        ws2.cell(row=curr_r, column=2, value="Amount")
        ws2.cell(row=curr_r, column=3, value="Share (%)")
        style_header_row(ws2, curr_r, 3)
        curr_r += 1

        for e_item in data["income_expense"]["expense_breakdown"]:
            ws2.cell(row=curr_r, column=1, value=e_item["category"]).font = regular_font
            c2 = ws2.cell(row=curr_r, column=2, value=e_item["amount_minor"] / 100.0)
            c2.number_format = money_fmt
            ws2.cell(row=curr_r, column=3, value=f"{e_item['percentage']}%").font = regular_font
            curr_r += 1
        autofit_cols(ws2)

        # ---------------- SHEET 3: Cash Flow Statement ----------------
        ws3 = wb.create_sheet(title="Cash Flow Statement")
        ws3["A1"] = "Statement of Cash Flows"
        ws3["A1"].font = title_font
        ws3["A3"] = "Cash Flow Line Item"
        ws3["B3"] = "Amount"
        style_header_row(ws3, 3, 2)

        cf_items = [
            ("Beginning Cash Balance", data["cash_flow"]["beginning_cash_minor"] / 100.0),
            ("Operating Cash Inflows", data["cash_flow"]["operating_cash_inflows_minor"] / 100.0),
            ("Operating Cash Outflows", -abs(data["cash_flow"]["operating_cash_outflows_minor"] / 100.0)),
            ("Net Operating Cash Flow", data["cash_flow"]["net_operating_cash_flow_minor"] / 100.0),
            ("Investing & Financing Cash Flow", data["cash_flow"]["investing_financing_cash_flow_minor"] / 100.0),
            ("Net Change in Cash", data["cash_flow"]["net_change_in_cash_minor"] / 100.0),
            ("Ending Cash Position", data["cash_flow"]["ending_cash_minor"] / 100.0),
        ]
        for idx, (lbl, val) in enumerate(cf_items, start=4):
            ws3.cell(row=idx, column=1, value=lbl).font = bold_font if "Net" in lbl or "Ending" in lbl else regular_font
            v = ws3.cell(row=idx, column=2, value=val)
            v.number_format = money_fmt
            v.font = bold_font if "Net" in lbl or "Ending" in lbl else regular_font
        autofit_cols(ws3)

        # ---------------- SHEET 4: Budget Performance ----------------
        ws4 = wb.create_sheet(title="Budget Performance")
        ws4["A1"] = f"Budget Performance ({data['budget_performance']['month']})"
        ws4["A1"].font = title_font
        ws4["A3"] = "Category"
        ws4["B3"] = "Budget Limit"
        ws4["C3"] = "Actual Spent"
        ws4["D3"] = "Variance / Remaining"
        ws4["E3"] = "Spent (%)"
        ws4["F3"] = "Status"
        style_header_row(ws4, 3, 6)

        for i, cp in enumerate(data["budget_performance"]["category_performances"], start=4):
            ws4.cell(row=i, column=1, value=cp["category"]).font = regular_font
            ws4.cell(row=i, column=2, value=cp["limit_minor"] / 100.0).number_format = money_fmt
            ws4.cell(row=i, column=3, value=cp["spent_minor"] / 100.0).number_format = money_fmt
            ws4.cell(row=i, column=4, value=cp["remaining_minor"] / 100.0).number_format = money_fmt
            ws4.cell(row=i, column=5, value=f"{cp['spent_pct']}%").font = regular_font
            ws4.cell(row=i, column=6, value=cp["status"]).font = regular_font
        autofit_cols(ws4)

        # ---------------- SHEET 5: Anomalies ----------------
        ws5 = wb.create_sheet(title="Flagged Anomalies")
        ws5["A1"] = "Flagged Anomaly Audit"
        ws5["A1"].font = title_font
        ws5["A3"] = "Date"
        ws5["B3"] = "Description"
        ws5["C3"] = "Category"
        ws5["D3"] = "Amount"
        ws5["E3"] = "Severity"
        ws5["F3"] = "Flagged Reason"
        style_header_row(ws5, 3, 6)

        for i, an in enumerate(data["anomalies"], start=4):
            ws5.cell(row=i, column=1, value=an["date"]).font = regular_font
            ws5.cell(row=i, column=2, value=an["description"]).font = regular_font
            ws5.cell(row=i, column=3, value=an["category"]).font = regular_font
            ws5.cell(row=i, column=4, value=an["amount_minor"] / 100.0).number_format = money_fmt
            ws5.cell(row=i, column=5, value=an["severity"]).font = bold_font
            ws5.cell(row=i, column=6, value=an["reason"]).font = regular_font
        autofit_cols(ws5)

        # ---------------- SHEET 6: Payables & Receivables ----------------
        ws6 = wb.create_sheet(title="Payables & Receivables")
        ws6["A1"] = "Pending Vendor Payables"
        ws6["A1"].font = title_font
        ws6["A2"] = "Vendor"
        ws6["B2"] = "Amount"
        ws6["C2"] = "Due Date"
        ws6["D2"] = "Status"
        style_header_row(ws6, 2, 4)

        curr_r = 3
        for p in data["payables"]:
            ws6.cell(row=curr_r, column=1, value=p["vendor"]).font = regular_font
            ws6.cell(row=curr_r, column=2, value=p["amount_minor"] / 100.0).number_format = money_fmt
            ws6.cell(row=curr_r, column=3, value=p["due_date"]).font = regular_font
            ws6.cell(row=curr_r, column=4, value=p["status"]).font = regular_font
            curr_r += 1

        curr_r += 2
        ws6.cell(row=curr_r, column=1, value="Pending Client Receivables").font = title_font
        curr_r += 1
        ws6.cell(row=curr_r, column=1, value="Client")
        ws6.cell(row=curr_r, column=2, value="Amount")
        ws6.cell(row=curr_r, column=3, value="Due Date")
        ws6.cell(row=curr_r, column=4, value="Status")
        style_header_row(ws6, curr_r, 4)
        curr_r += 1

        for r in data["receivables"]:
            ws6.cell(row=curr_r, column=1, value=r["client"]).font = regular_font
            ws6.cell(row=curr_r, column=2, value=r["amount_minor"] / 100.0).number_format = money_fmt
            ws6.cell(row=curr_r, column=3, value=r["due_date"]).font = regular_font
            ws6.cell(row=curr_r, column=4, value=r["status"]).font = regular_font
            curr_r += 1
        autofit_cols(ws6)

        out = io.BytesIO()
        wb.save(out)
        return out.getvalue()

    @staticmethod
    async def export_pdf_report(
        db: AsyncSession,
        workspace_id: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None
    ) -> bytes:
        data = await ReportService.get_comprehensive_financial_data(db, workspace_id, start_date, end_date)
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=letter,
            rightMargin=36,
            leftMargin=36,
            topMargin=36,
            bottomMargin=36
        )

        styles = getSampleStyleSheet()
        title_style = ParagraphStyle(
            'DocTitle',
            parent=styles['Heading1'],
            fontSize=20,
            leading=24,
            textColor=colors.HexColor('#0F766E'),
            fontName='Helvetica-Bold'
        )
        subtitle_style = ParagraphStyle(
            'DocSubtitle',
            parent=styles['Normal'],
            fontSize=10,
            leading=14,
            textColor=colors.HexColor('#78716C'),
            fontName='Helvetica'
        )
        h2_style = ParagraphStyle(
            'H2',
            parent=styles['Heading2'],
            fontSize=13,
            leading=16,
            textColor=colors.HexColor('#1C1917'),
            fontName='Helvetica-Bold',
            spaceBefore=14,
            spaceAfter=6
        )
        body_style = ParagraphStyle(
            'Body',
            parent=styles['Normal'],
            fontSize=9,
            leading=12,
            textColor=colors.HexColor('#292524'),
            fontName='Helvetica'
        )
        cell_bold = ParagraphStyle(
            'CellBold',
            parent=body_style,
            fontName='Helvetica-Bold'
        )

        elements = []

        # Header
        elements.append(Paragraph(f"CashIQ Financial Intelligence Report", title_style))
        elements.append(Paragraph(f"<b>Workspace:</b> {data['workspace_name']} | <b>Period:</b> {data['period']['start_date']} to {data['period']['end_date']} | <b>Currency:</b> {data['currency']}", subtitle_style))
        elements.append(Spacer(1, 10))

        # 1. Executive Summary Table
        elements.append(Paragraph("1. Executive Summary & Core KPIs", h2_style))
        cf = data["cash_flow"]
        ie = data["income_expense"]
        summary_table_data = [
            [Paragraph("<b>Metric</b>", cell_bold), Paragraph("<b>Amount</b>", cell_bold), Paragraph("<b>Metric</b>", cell_bold), Paragraph("<b>Amount</b>", cell_bold)],
            ["Beginning Cash Balance", f"${cf['beginning_cash_minor']/100:,.2f}", "Total Operating Revenue", f"${ie['total_income_minor']/100:,.2f}"],
            ["Total Operating Expenses", f"${ie['total_expenses_minor']/100:,.2f}", "Net Cash Flow", f"${cf['net_change_in_cash_minor']/100:,.2f}"],
            ["Ending Cash Balance", f"${cf['ending_cash_minor']/100:,.2f}", "Net Profit Margin", f"{ie['net_profit_margin_pct']}%"],
            ["Pending Payables", f"${sum(p['amount_minor'] for p in data['payables'])/100:,.2f}", "Pending Receivables", f"${sum(r['amount_minor'] for r in data['receivables'])/100:,.2f}"],
        ]
        t1 = Table(summary_table_data, colWidths=[140, 130, 140, 130])
        t1.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#0F766E')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#E7E5E4')),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 9),
            ('TOPPADDING', (0, 0), (-1, -1), 5),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ]))
        elements.append(t1)
        elements.append(Spacer(1, 12))

        # 2. Income vs Expenses
        elements.append(Paragraph("2. Top Expense Categories", h2_style))
        exp_table_data = [[Paragraph("<b>Category</b>", cell_bold), Paragraph("<b>Amount</b>", cell_bold), Paragraph("<b>Share (%)</b>", cell_bold)]]
        for exp in data["income_expense"]["expense_breakdown"][:6]:
            exp_table_data.append([
                exp["category"],
                f"${exp['amount_minor']/100:,.2f}",
                f"{exp['percentage']}%"
            ])
        t2 = Table(exp_table_data, colWidths=[260, 140, 140])
        t2.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#F5F5F4')),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#E7E5E4')),
            ('FONTSIZE', (0, 0), (-1, -1), 9),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ]))
        elements.append(t2)
        elements.append(Spacer(1, 12))

        # 3. Statement of Cash Flows
        elements.append(Paragraph("3. Statement of Cash Flows", h2_style))
        cf_table_data = [
            [Paragraph("<b>Cash Flow Activity</b>", cell_bold), Paragraph("<b>Amount</b>", cell_bold)],
            ["Cash Flows from Operating Inflows", f"${cf['operating_cash_inflows_minor']/100:,.2f}"],
            ["Cash Flows for Operating Expenses", f"-${cf['operating_cash_outflows_minor']/100:,.2f}"],
            ["Net Operating Cash Flow", f"${cf['net_operating_cash_flow_minor']/100:,.2f}"],
            ["Investing & Financing Activities", f"${cf['investing_financing_cash_flow_minor']/100:,.2f}"],
            ["Net Increase / Decrease in Cash", f"${cf['net_change_in_cash_minor']/100:,.2f}"],
            ["Ending Cash & Cash Equivalents", f"${cf['ending_cash_minor']/100:,.2f}"],
        ]
        t3 = Table(cf_table_data, colWidths=[380, 160])
        t3.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#F5F5F4')),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#E7E5E4')),
            ('LINEBELOW', (0, 3), (-1, 3), 1, colors.HexColor('#0F766E')),
            ('LINEBELOW', (0, 6), (-1, 6), 1.5, colors.HexColor('#0F766E')),
            ('FONTSIZE', (0, 0), (-1, -1), 9),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ]))
        elements.append(t3)
        elements.append(Spacer(1, 12))

        # 4. Flagged Anomalies
        if data["anomalies"]:
            elements.append(Paragraph(f"4. Flagged Anomalies Audit ({len(data['anomalies'])} detected)", h2_style))
            anom_table = [[Paragraph("<b>Date</b>", cell_bold), Paragraph("<b>Description</b>", cell_bold), Paragraph("<b>Amount</b>", cell_bold), Paragraph("<b>Severity</b>", cell_bold), Paragraph("<b>Reason</b>", cell_bold)]]
            for a in data["anomalies"][:5]:
                anom_table.append([
                    a["date"],
                    a["description"][:30],
                    f"${a['amount_minor']/100:,.2f}",
                    a["severity"].capitalize(),
                    Paragraph(a["reason"][:60] + "...", body_style)
                ])
            t4 = Table(anom_table, colWidths=[65, 115, 75, 65, 220])
            t4.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#F5F5F4')),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#E7E5E4')),
                ('FONTSIZE', (0, 0), (-1, -1), 8),
                ('TOPPADDING', (0, 0), (-1, -1), 4),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
            ]))
            elements.append(t4)

        doc.build(elements)
        return buffer.getvalue()
