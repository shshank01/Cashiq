from datetime import datetime, timedelta, timezone
from typing import Dict, Any, List, Optional
import numpy as np

class ColdStartManager:
    """
    Hybrid cold-start forecasting system for new businesses or limited transaction history.
    Blends business archetype baselines, owner estimates, and known future payables/receivables.
    """
    
    ARCHETYPES = {
        "B2B SaaS": {
            "daily_income_pattern": "smooth_recurring",
            "expense_ratio": 0.65,
            "volatility": 0.08,
            "description": "High recurring revenue, predictable monthly cloud and payroll expenses."
        },
        "Agency / Consulting": {
            "daily_income_pattern": "milestone_spikes",
            "expense_ratio": 0.70,
            "volatility": 0.22,
            "description": "Bi-weekly or monthly milestone invoice collections with contractor payroll."
        },
        "E-Commerce": {
            "daily_income_pattern": "daily_variable",
            "expense_ratio": 0.80,
            "volatility": 0.18,
            "description": "Daily customer orders, seasonal advertising spend, and periodic inventory replenishment."
        },
        "Retail": {
            "daily_income_pattern": "weekly_cycle",
            "expense_ratio": 0.75,
            "volatility": 0.12,
            "description": "Weekend peaks, monthly facility rent, vendor restocking cycles."
        },
        "Healthcare / Services": {
            "daily_income_pattern": "delayed_reimbursement",
            "expense_ratio": 0.68,
            "volatility": 0.10,
            "description": "Steady recurring patient/client appointments with delayed insurer disbursements."
        }
    }

    def generate_cold_start_forecast(
        self,
        current_cash_minor: int,
        business_profile: Optional[Any],
        known_payables: List[Any],
        known_receivables: List[Any],
        forecast_days: int = 30
    ) -> Dict[str, Any]:
        """
        Generates day-by-day projection for businesses with little or no historical data.
        Classified as 'estimated' (archetype-dominated) or 'projected' (known future events + baseline).
        """
        now = datetime.now(timezone.utc)
        
        # Profile extraction or reasonable SME default
        archetype_name = "B2B SaaS"
        monthly_rev_minor = 3500000 # $35,000.00 default
        monthly_exp_minor = 2200000 # $22,000.00 default
        growth_pct = 5.0 # 5% monthly
        
        if business_profile:
            archetype_name = getattr(business_profile, "business_type", "B2B SaaS") or "B2B SaaS"
            monthly_rev_minor = getattr(business_profile, "approx_monthly_revenue_minor", 3500000) or 3500000
            monthly_exp_minor = getattr(business_profile, "approx_monthly_expenses_minor", 2200000) or 2200000
            growth_pct = getattr(business_profile, "expected_growth_pct", 5.0) or 5.0

        archetype = self.ARCHETYPES.get(archetype_name, self.ARCHETYPES["B2B SaaS"])
        
        # Daily baseline amounts in cents
        daily_baseline_rev = int(monthly_rev_minor / 30.0)
        daily_baseline_exp = int(monthly_exp_minor / 30.0)
        
        # Map known payables & receivables to day offsets
        payables_by_day = {}
        for p in known_payables:
            due_dt = p.due_date if hasattr(p, 'due_date') else datetime.fromisoformat(str(p['due_date']))
            diff_days = (due_dt.date() - now.date()).days
            if 0 <= diff_days < forecast_days:
                rem = (p.amount_minor - p.amount_paid_minor) if hasattr(p, 'amount_minor') else p['amount_minor']
                payables_by_day[diff_days] = payables_by_day.get(diff_days, 0) + rem

        receivables_by_day = {}
        for r in known_receivables:
            due_dt = r.due_date if hasattr(r, 'due_date') else datetime.fromisoformat(str(r['due_date']))
            diff_days = (due_dt.date() - now.date()).days
            if 0 <= diff_days < forecast_days:
                rem = (r.amount_minor - r.amount_received_minor) if hasattr(r, 'amount_minor') else r['amount_minor']
                receivables_by_day[diff_days] = receivables_by_day.get(diff_days, 0) + rem

        daily_forecast = []
        running_cash = current_cash_minor
        has_known_future_events = len(payables_by_day) > 0 or len(receivables_by_day) > 0
        forecast_type = "projected" if has_known_future_events else "estimated"

        # Predict each day
        for d in range(1, forecast_days + 1):
            day_date = now + timedelta(days=d)
            # Day of week factor (weekday vs weekend)
            dow = day_date.weekday()
            is_weekend = dow >= 5
            
            # Archetype modulation
            if archetype["daily_income_pattern"] == "weekly_cycle":
                day_factor_rev = 1.4 if is_weekend else 0.85
                day_factor_exp = 1.1 if is_weekend else 0.95
            elif archetype["daily_income_pattern"] == "milestone_spikes":
                # Spikes on 1st, 15th, or Fridays
                day_factor_rev = 2.2 if day_date.day in (1, 15) or dow == 4 else 0.6
                day_factor_exp = 1.8 if day_date.day in (1, 15) else 0.8
            else:
                day_factor_rev = 0.4 if is_weekend else 1.2
                day_factor_exp = 0.5 if is_weekend else 1.15

            # Growth trend over days
            growth_mult = 1.0 + (growth_pct / 100.0) * (d / 30.0)
            
            income_est = int(daily_baseline_rev * day_factor_rev * growth_mult)
            expense_est = int(daily_baseline_exp * day_factor_exp)
            
            # Incorporate known payables and receivables
            known_p = payables_by_day.get(d, 0)
            known_r = receivables_by_day.get(d, 0)
            
            total_income = income_est + known_r
            total_expense = expense_est + known_p
            net = total_income - total_expense
            running_cash += net

            # Confidence bounds widen over time
            spread = int((archetype["volatility"] + (d / forecast_days) * 0.15) * running_cash)
            spread = max(spread, int(0.05 * running_cash))
            
            daily_forecast.append({
                "date": day_date.strftime("%Y-%m-%d"),
                "income_minor": total_income,
                "expenses_minor": total_expense,
                "net_minor": net,
                "cash_position_minor": running_cash,
                "lower_minor": running_cash - spread,
                "upper_minor": running_cash + spread
            })

        total_income_fc = sum(f["income_minor"] for f in daily_forecast)
        total_expense_fc = sum(f["expenses_minor"] for f in daily_forecast)
        min_cash_fc = min(f["cash_position_minor"] for f in daily_forecast)
        end_cash_fc = daily_forecast[-1]["cash_position_minor"] if daily_forecast else current_cash_minor

        return {
            "forecast_type": forecast_type,
            "daily_forecast": daily_forecast,
            "summary": {
                "forecast_days": forecast_days,
                "avg_daily_income_minor": int(total_income_fc / forecast_days),
                "avg_daily_expenses_minor": int(total_expense_fc / forecast_days),
                "end_cash_position_minor": end_cash_fc,
                "lowest_cash_position_minor": min_cash_fc
            },
            "metrics": {
                "mae": None,
                "rmse": None
            },
            "model_info": {
                "method": f"hybrid_cold_start_{archetype_name.lower().replace(' ', '_')}",
                "data_points_used": len(known_payables) + len(known_receivables),
                "description": f"Classified as '{forecast_type}'. Forecast generated using {archetype_name} archetype baselines and verified upcoming payable/receivable schedules."
            }
        }

cold_start_instance = ColdStartManager()
