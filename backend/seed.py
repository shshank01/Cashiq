import asyncio
import os
import uuid
import bcrypt
from datetime import datetime, timedelta, timezone

from app.database import engine, Base, AsyncSessionLocal
from app.models.user import User
from app.models.workspace import Workspace, WorkspaceMembership
from app.models.account import Account
from app.models.category import Category
from app.models.transaction import Transaction
from app.models.payable import Payable
from app.models.receivable import Receivable
from app.models.recurring import RecurringRule
from app.models.business_profile import BusinessProfile
from app.ml.business_taxonomy import derive_initial_expense_profile
from app.services.insight_service import InsightService
from app.services.forecast_service import ForecastService
from app.models.budget import Budget, CategoryBudget
from app.models.simulation import SimulationScenario
from app.models.reconciliation import ReconciliationSession, ReconciliationItem
from app.services.health_score_service import HealthScoreService

def get_hash(pwd: str) -> str:
    return bcrypt.hashpw(pwd.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

async def seed_database():
    print("Initializing database tables...")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    async with AsyncSessionLocal() as session:
        print("Seeding demo user and workspace...")
        # 1. User
        user = User(
            email="demo@cashiq.io",
            hashed_password=get_hash("password123"),
            full_name="Alex Vance"
        )
        session.add(user)
        await session.flush()

        # 2. Workspace
        workspace = Workspace(
            name="Apex Cloud Technologies",
            currency="USD",
            owner_id=user.id
        )
        session.add(workspace)
        await session.flush()

        # Membership
        membership = WorkspaceMembership(
            workspace_id=workspace.id,
            user_id=user.id,
            role="owner"
        )
        session.add(membership)

        # 3. Accounts
        svb_acct = Account(
            workspace_id=workspace.id,
            name="SVB Operating Checking",
            account_type="checking",
            balance_minor=16845000, # $168,450.00
            currency="USD"
        )
        chase_acct = Account(
            workspace_id=workspace.id,
            name="Chase Business Sapphire",
            account_type="credit",
            balance_minor=425000, # $4,250.00
            currency="USD"
        )
        stripe_acct = Account(
            workspace_id=workspace.id,
            name="Stripe Clearing Account",
            account_type="cash",
            balance_minor=2480000, # $24,800.00
            currency="USD"
        )
        session.add_all([svb_acct, chase_acct, stripe_acct])
        await session.flush()

        # 4. Standard Categories
        cat_names = [
            "Software & Cloud Services",
            "Payroll & Wages",
            "Rent & Facilities",
            "Marketing & Advertising",
            "Professional & Legal",
            "Meals & Entertainment",
            "Office Supplies & Equipment",
            "Travel & Transportation",
            "Client Revenue",
            "Loans & Financing",
            "Miscellaneous"
        ]
        cats = {}
        for c in cat_names:
            category = Category(workspace_id=workspace.id, name=c)
            session.add(category)
            cats[c] = category
        await session.flush()

        # 5. Business Data Profile (Section 10 Cold Start)
        profile = BusinessProfile(
            workspace_id=workspace.id,
            company_name=workspace.name,
            business_type="B2B SaaS",
            industry="Cloud Computing",
            operating_model="B2B",
            relevant_expense_categories=derive_initial_expense_profile(
                industry="Cloud Computing",
                business_type="B2B SaaS",
                operating_model="B2B",
            ),
            business_age_months=18,
            approx_monthly_revenue_minor=5500000, # $55,000.00
            approx_monthly_expenses_minor=3800000, # $38,000.00
            employee_count=8,
            expected_growth_pct=14.5,
            major_recurring_expenses=[
                {"name": "Payroll", "amount_minor": 2500000},
                {"name": "AWS Hosting", "amount_minor": 380000}
            ],
            known_future_payments_minor=620000,
            expected_receivables_minor=4450000
        )
        session.add(profile)

        # 6. Realistic Historical Transactions (past 150 days)
        now = datetime.now(timezone.utc)
        print("Generating 150 days of realistic business transactions...")
        
        tx_list = []
        for month_offset in range(5, -1, -1):
            base_date = now - timedelta(days=month_offset * 30)

            # Revenue inflows
            tx_list.append(Transaction(
                workspace_id=workspace.id,
                account_id=stripe_acct.id,
                date=base_date + timedelta(days=2),
                amount_minor=2800000 + (5 - month_offset) * 200000, # $28k - $38k growing MRR
                currency="USD",
                description="Stripe Monthly Recurring SaaS Inflow",
                merchant="Stripe Payments",
                category_name="Client Revenue",
                type="income",
                source="bank_sync",
                confidence=0.98,
                model_version="v1.2.0-kaggle-tfidf-logreg",
                review_required=False
            ))

            tx_list.append(Transaction(
                workspace_id=workspace.id,
                account_id=svb_acct.id,
                date=base_date + timedelta(days=15),
                amount_minor=1450000, # $14,500.00
                currency="USD",
                description="Enterprise Client Annual Contract Wire - Acme Corp",
                merchant="Acme Corp",
                category_name="Client Revenue",
                type="income",
                source="bank_sync",
                confidence=0.95,
                model_version="v1.2.0-kaggle-tfidf-logreg",
                review_required=False
            ))

            # Bi-weekly Payroll
            tx_list.append(Transaction(
                workspace_id=workspace.id,
                account_id=svb_acct.id,
                date=base_date + timedelta(days=5),
                amount_minor=1250000, # $12,500.00
                currency="USD",
                description="Gusto Payroll Direct Deposit Batch",
                merchant="Gusto Payroll",
                category_name="Payroll & Wages",
                type="expense",
                source="bank_sync",
                confidence=0.99,
                model_version="v1.2.0-kaggle-tfidf-logreg",
                review_required=False
            ))

            tx_list.append(Transaction(
                workspace_id=workspace.id,
                account_id=svb_acct.id,
                date=base_date + timedelta(days=20),
                amount_minor=1250000, # $12,500.00
                currency="USD",
                description="Gusto Payroll Direct Deposit Batch",
                merchant="Gusto Payroll",
                category_name="Payroll & Wages",
                type="expense",
                source="bank_sync",
                confidence=0.99,
                model_version="v1.2.0-kaggle-tfidf-logreg",
                review_required=False
            ))

            # Rent
            tx_list.append(Transaction(
                workspace_id=workspace.id,
                account_id=svb_acct.id,
                date=base_date + timedelta(days=1),
                amount_minor=240000, # $2,400.00
                currency="USD",
                description="WeWork Dedicated Office Suite Lease",
                merchant="WeWork",
                category_name="Rent & Facilities",
                type="expense",
                source="bank_sync",
                confidence=0.94,
                model_version="v1.2.0-kaggle-tfidf-logreg",
                review_required=False
            ))

            # Monthly AWS Infrastructure
            aws_amt = 360000 + (5 - month_offset) * 25000 # ~$3,600 to $4,850
            tx_list.append(Transaction(
                workspace_id=workspace.id,
                account_id=chase_acct.id,
                date=base_date + timedelta(days=10),
                amount_minor=aws_amt,
                currency="USD",
                description="AWS EMEA Cloud Compute Infrastructure",
                merchant="Amazon Web Services",
                category_name="Software & Cloud Services",
                type="expense",
                source="bank_sync",
                confidence=0.96,
                model_version="v1.2.0-kaggle-tfidf-logreg",
                review_required=False
            ))

            # SaaS Tools (Datadog, Slack, GitHub, Google Workspace)
            tx_list.append(Transaction(
                workspace_id=workspace.id,
                account_id=chase_acct.id,
                date=base_date + timedelta(days=12),
                amount_minor=62000, # $620.00
                currency="USD",
                description="Datadog APM and Log Management",
                merchant="Datadog",
                category_name="Software & Cloud Services",
                type="expense",
                source="bank_sync",
                confidence=0.93,
                model_version="v1.2.0-kaggle-tfidf-logreg",
                review_required=False
            ))

            tx_list.append(Transaction(
                workspace_id=workspace.id,
                account_id=chase_acct.id,
                date=base_date + timedelta(days=14),
                amount_minor=21000, # $210.00
                currency="USD",
                description="GitHub Enterprise Team Billing",
                merchant="GitHub",
                category_name="Software & Cloud Services",
                type="expense",
                source="bank_sync",
                confidence=0.92,
                model_version="v1.2.0-kaggle-tfidf-logreg",
                review_required=False
            ))

            # Marketing & Ads
            tx_list.append(Transaction(
                workspace_id=workspace.id,
                account_id=chase_acct.id,
                date=base_date + timedelta(days=18),
                amount_minor=185000, # $1,850.00
                currency="USD",
                description="Google Ads Online Search Marketing",
                merchant="Google Ads",
                category_name="Marketing & Advertising",
                type="expense",
                source="bank_sync",
                confidence=0.94,
                model_version="v1.2.0-kaggle-tfidf-logreg",
                review_required=False
            ))

            # Team meals & travel
            tx_list.append(Transaction(
                workspace_id=workspace.id,
                account_id=chase_acct.id,
                date=base_date + timedelta(days=22),
                amount_minor=42000, # $420.00
                currency="USD",
                description="Team Dinner & Client Lunch",
                merchant="Local Kitchen & Wine",
                category_name="Meals & Entertainment",
                type="expense",
                source="bank_sync",
                confidence=0.88,
                model_version="v1.2.0-kaggle-tfidf-logreg",
                review_required=False
            ))

        # Add explicit Section 8 Anomaly:
        # "Software expense is 3.8x higher than normal monthly spending"
        tx_list.append(Transaction(
            workspace_id=workspace.id,
            account_id=chase_acct.id,
            date=now - timedelta(days=4),
            amount_minor=1580000, # $15,800.00 (vs normal ~$4,000)
            currency="USD",
            description="AWS Cloud GPU Cluster Spike - Model Fine-Tuning",
            merchant="Amazon Web Services",
            category_name="Software & Cloud Services",
            type="expense",
            source="bank_sync",
            confidence=0.96,
            model_version="v1.2.0-kaggle-tfidf-logreg",
            review_required=False,
            is_anomaly=True,
            anomaly_score=0.88,
            anomaly_severity="critical",
            anomaly_reason="Software & Cloud Services expense is 3.8× higher than the business's normal monthly average of $4,120.00."
        ))

        # Unscheduled legal retainer anomaly
        tx_list.append(Transaction(
            workspace_id=workspace.id,
            account_id=svb_acct.id,
            date=now - timedelta(days=12),
            amount_minor=1250000, # $12,500.00
            currency="USD",
            description="Wilson Sonsini Goodrich & Rosati Legal Retainer",
            merchant="Wilson Sonsini",
            category_name="Professional & Legal",
            type="expense",
            source="manual",
            confidence=0.91,
            model_version="v1.2.0-kaggle-tfidf-logreg",
            review_required=False,
            is_anomaly=True,
            anomaly_score=0.74,
            anomaly_severity="high",
            anomaly_reason="Transaction amount of $12,500.00 is significantly above typical spending (2.8× IQR outlier) for Professional & Legal."
        ))

        session.add_all(tx_list)

        # 7. Recurring Rules (Section 11)
        recurring_items = [
            RecurringRule(
                workspace_id=workspace.id,
                merchant="Amazon Web Services",
                description="Monthly Cloud Compute Infrastructure",
                amount_minor=420000, # $4,200.00
                currency="USD",
                frequency="monthly",
                next_date=now + timedelta(days=5),
                confidence=0.98,
                type="expense",
                status="active",
                category_name="Software & Cloud Services"
            ),
            RecurringRule(
                workspace_id=workspace.id,
                merchant="Gusto Payroll",
                description="Bi-Weekly Employee Salaries & Taxes",
                amount_minor=1250000, # $12,500.00
                currency="USD",
                frequency="bi-weekly",
                next_date=now + timedelta(days=3),
                confidence=0.99,
                type="expense",
                status="active",
                category_name="Payroll & Wages"
            ),
            RecurringRule(
                workspace_id=workspace.id,
                merchant="WeWork",
                description="Dedicated Office Suite Lease",
                amount_minor=240000, # $2,400.00
                currency="USD",
                frequency="monthly",
                next_date=now + timedelta(days=11),
                confidence=0.95,
                type="expense",
                status="active",
                category_name="Rent & Facilities"
            ),
            RecurringRule(
                workspace_id=workspace.id,
                merchant="Datadog",
                description="Application APM & Monitoring",
                amount_minor=62000, # $620.00
                currency="USD",
                frequency="monthly",
                next_date=now + timedelta(days=8),
                confidence=0.94,
                type="expense",
                status="active",
                category_name="Software & Cloud Services"
            )
        ]
        session.add_all(recurring_items)

        # 8. Payables & Receivables (Section 12)
        payables = [
            Payable(
                workspace_id=workspace.id,
                vendor="Amazon Web Services",
                description="Cloud Compute Monthly Statement",
                amount_minor=420000,
                amount_paid_minor=0,
                currency="USD",
                due_date=now + timedelta(days=5),
                status="pending"
            ),
            Payable(
                workspace_id=workspace.id,
                vendor="WeWork Commercial Properties",
                description="Next Month Office Space License",
                amount_minor=240000,
                amount_paid_minor=0,
                currency="USD",
                due_date=now + timedelta(days=11),
                status="pending"
            ),
            Payable(
                workspace_id=workspace.id,
                vendor="Wilson Sonsini Goodrich & Rosati",
                description="Corporate Advisory Statement INV-8821",
                amount_minor=450000,
                amount_paid_minor=0,
                currency="USD",
                due_date=now - timedelta(days=4), # Overdue
                status="overdue"
            )
        ]
        session.add_all(payables)

        receivables = [
            Receivable(
                workspace_id=workspace.id,
                client="Acme Corporation",
                description="Enterprise Platform License Q4",
                amount_minor=2800000, # $28,000.00
                amount_received_minor=0,
                currency="USD",
                due_date=now + timedelta(days=7),
                status="pending"
            ),
            Receivable(
                workspace_id=workspace.id,
                client="Vertex Global Systems",
                description="API Integration Milestone Payment",
                amount_minor=1650000, # $16,500.00
                amount_received_minor=0,
                currency="USD",
                due_date=now + timedelta(days=16),
                status="pending"
            ),
            Receivable(
                workspace_id=workspace.id,
                client="Helix Dynamics Inc",
                description="Consulting Advisory Services",
                amount_minor=750000, # $7,500.00
                amount_received_minor=0,
                currency="USD",
                due_date=now - timedelta(days=5), # Overdue
                status="overdue"
            )
        ]
        session.add_all(receivables)

        # 10. Budgets
        current_month = now.strftime("%Y-%m")
        budget = Budget(
            workspace_id=workspace.id,
            name=f"Operating Budget {now.strftime('%B %Y')}",
            month=current_month,
            total_limit_minor=2000000,  # $20,000.00
            currency="USD",
        )
        session.add(budget)
        await session.flush()

        cat_budgets = [
            CategoryBudget(
                budget_id=budget.id,
                category_name="Software & Cloud Services",
                limit_minor=600000,  # $6,000.00
                alert_threshold_pct=80.0,
            ),
            CategoryBudget(
                budget_id=budget.id,
                category_name="Marketing & Advertising",
                limit_minor=300000,  # $3,000.00
                alert_threshold_pct=80.0,
            ),
            CategoryBudget(
                budget_id=budget.id,
                category_name="Rent & Facilities",
                limit_minor=300000,  # $3,000.00
                alert_threshold_pct=80.0,
            ),
            CategoryBudget(
                budget_id=budget.id,
                category_name="Office Supplies & Equipment",
                limit_minor=100000,  # $1,000.00
                alert_threshold_pct=80.0,
            ),
            CategoryBudget(
                budget_id=budget.id,
                category_name="Meals & Entertainment",
                limit_minor=50000,   # $500.00
                alert_threshold_pct=80.0,
            ),
        ]
        session.add_all(cat_budgets)

        # 11. What-If Financial Simulator Scenario
        sim_scenario = SimulationScenario(
            workspace_id=workspace.id,
            name="Q1 Conservative Growth Scenario",
            description="5% revenue drop buffer, 10% expense reduction target, 15-day payment delay buffer.",
            parameters={
                "revenue_change_pct": -5.0,
                "expense_change_pct": -10.0,
                "delayed_receivables_days": 15,
                "months": 6,
            },
            results={
                "baseline": {"runway_months": 18.4, "runway_category": "healthy"},
                "expected_case": {"runway_months": 22.1, "runway_category": "healthy"},
                "best_case": {"runway_months": 28.5, "runway_category": "healthy"},
                "worst_case": {"runway_months": 14.2, "runway_category": "healthy"},
            }
        )
        session.add(sim_scenario)

        # 12. Bank Statement Reconciliation Session
        recon_session = ReconciliationSession(
            workspace_id=workspace.id,
            account_id=svb_acct.id,
            filename="svb_statement_nov2026.csv",
            total_statement_rows=4,
            matched_count=3,
            unmatched_bank_count=1,
            unmatched_ledger_count=0,
            status="completed",
            summary={
                "total_rows": 4,
                "matched": 3,
                "unmatched_bank": 1,
                "unmatched_ledger": 0,
                "match_rate": 75.0,
            }
        )
        session.add(recon_session)
        await session.flush()

        # Seed reconciliation items
        recon_items = [
            ReconciliationItem(
                session_id=recon_session.id,
                statement_date=now - timedelta(days=2),
                statement_description="AMZN MKTP US*CLOUD SVCS",
                statement_amount_minor=-420000,  # -$4,200
                statement_reference="TXN-SVB-88120",
                match_type="exact",
                status="approved",
            ),
            ReconciliationItem(
                session_id=recon_session.id,
                statement_date=now - timedelta(days=3),
                statement_description="GOOGLE *WORKSPACE APPS",
                statement_amount_minor=-36000,   # -$360
                statement_reference="TXN-SVB-88121",
                match_type="exact",
                status="approved",
            ),
            ReconciliationItem(
                session_id=recon_session.id,
                statement_date=now - timedelta(days=5),
                statement_description="STRIPE PAYOUT CLIENT REVENUE",
                statement_amount_minor=1250000,  # +$12,500
                statement_reference="TXN-SVB-88122",
                match_type="probable",
                status="pending",
                discrepancy_details={"reason": "Amount match within 1% fee variance"}
            ),
            ReconciliationItem(
                session_id=recon_session.id,
                statement_date=now - timedelta(days=1),
                statement_description="SVB WIRE FEE SERVICE CHG",
                statement_amount_minor=-2500,    # -$25
                statement_reference="TXN-SVB-88123",
                match_type="unmatched_bank",
                status="pending",
                discrepancy_details={"reason": "Bank charge not yet recorded in internal ledger"}
            )
        ]
        session.add_all(recon_items)

        await session.commit()
        print("Initial database models successfully committed.")

        # 13. Financial Health Score
        print("Calculating initial Financial Health Score...")
        await HealthScoreService.calculate_health_score(session, workspace.id, persist=True)

        # 9. Generate Insights and Forecast
        print("Generating deterministic insights and cash flow forecast...")
        await InsightService.generate_insights(session, workspace.id)
        await ForecastService.get_or_generate_forecast(session, workspace.id, 30)

        print("\n" + "="*50)
        print("CASHIQ DATABASE SEEDED SUCCESSFULLY!")
        print(f"Login Email:     demo@cashiq.io")
        print(f"Login Password:  password123")
        print(f"Workspace Name:  {workspace.name}")
        print(f"Total Cash:      ${(svb_acct.balance_minor + chase_acct.balance_minor + stripe_acct.balance_minor)/100:,.2f}")
        print("="*50 + "\n")

if __name__ == "__main__":
    asyncio.run(seed_database())
