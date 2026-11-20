import React, { useEffect, useState } from 'react';
import { useWorkspace } from '../contexts/WorkspaceContext';
import { dashboardApi } from '../api/dashboard';
import { healthScoreApi } from '../api/healthScore';
import { formatMoney } from '../utils/format';
import { DashboardData, HealthScoreData } from '../types';
import LoadingSpinner from '../components/ui/LoadingSpinner';
import ErrorState from '../components/ui/ErrorState';
import EmptyState from '../components/ui/EmptyState';
import Card from '../components/ui/Card';
import CashFlowChart from '../components/charts/CashFlowChart';
import IncomeExpenseChart from '../components/charts/IncomeExpenseChart';
import CategoryPieChart from '../components/charts/CategoryPieChart';
import ForecastChart from '../components/charts/ForecastChart';
import StatusBadge from '../components/ui/StatusBadge';
import { 
  DollarSign, 
  TrendingUp, 
  TrendingDown, 
  Activity, 
  Hourglass, 
  ArrowDownLeft, 
  ArrowUpRight,
  Sparkles,
  RefreshCw,
  AlertTriangle,
  Calendar,
  CheckCircle2,
  ShieldCheck,
  Award,
  Sliders,
  ChevronRight
} from 'lucide-react';
import { Link } from 'react-router-dom';

export const DashboardPage: React.FC = () => {
  const { currentWorkspace, currency: contextCurrency, formatConverted, fxRate, convertWithFx } = useWorkspace();
  const [data, setData] = useState<DashboardData | null>(null);
  const [healthScore, setHealthScore] = useState<HealthScoreData | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!currentWorkspace) return;

    let isMounted = true;
    const fetchDashboard = async () => {
      setIsLoading(true);
      setError(null);
      try {
        const [dashRes, healthRes] = await Promise.allSettled([
          dashboardApi.get(currentWorkspace.id),
          healthScoreApi.get(currentWorkspace.id)
        ]);

        if (dashRes.status === 'fulfilled' && isMounted) {
          setData(dashRes.value);
        } else if (dashRes.status === 'rejected') {
          throw dashRes.reason;
        }

        if (healthRes.status === 'fulfilled' && isMounted) {
          setHealthScore(healthRes.value);
        }
      } catch (err: any) {
        if (isMounted) setError(err.message || 'Failed to load dashboard financial intelligence.');
      } finally {
        if (isMounted) setIsLoading(false);
      }
    };

    fetchDashboard();
    return () => { isMounted = false; };
  }, [currentWorkspace]);

  if (isLoading) return <LoadingSpinner />;
  if (error) return <ErrorState message={error} onRetry={() => window.location.reload()} />;
  if (!data) return <EmptyState title="No Financial Data Available" message="Initialize or connect bank records to view analytics." />;

  const currency = contextCurrency || 'USD';
  const kpis = data.kpis;

  const chartMultiplier = (convertWithFx && currency.toUpperCase() === 'INR')
    ? fxRate
    : 1;

  const cashFlowHistory = (data.cash_flow_history || []).map(d => ({
    ...d,
    net_minor: Math.round((d.net_minor || 0) * chartMultiplier),
  }));

  const incomeVsExpenses = (data.income_vs_expenses || []).map(d => ({
    ...d,
    income_minor: Math.round((d.income_minor || 0) * chartMultiplier),
    expenses_minor: Math.round((d.expenses_minor || 0) * chartMultiplier),
  }));

  const spendingByCategory = (data.spending_by_category || []).map(d => ({
    ...d,
    amount_minor: Math.round((d.amount_minor || 0) * chartMultiplier),
  }));

  const forecastPreview = (data.forecast_preview || []).map((d: any) => {
    const val = d.predicted_minor ?? d.cash_position_minor ?? d.forecast ?? 0;
    const scaledVal = Math.round(val * chartMultiplier);
    return {
      ...d,
      forecast: scaledVal,
      cash_position_minor: scaledVal,
      predicted_minor: scaledVal,
      lower_minor: Math.round((d.lower_minor || 0) * chartMultiplier),
      upper_minor: Math.round((d.upper_minor || 0) * chartMultiplier),
    };
  });

  const renderMoneyValue = (formatted: string) => {
    if (!formatted) return '0.00';
    const lastDot = formatted.lastIndexOf('.');
    if (lastDot !== -1) {
      const main = formatted.slice(0, lastDot);
      const dec = formatted.slice(lastDot);
      return (
        <span className="inline-flex items-baseline whitespace-nowrap">
          <span>{main}</span>
          <span className="text-[0.8em] font-semibold opacity-85 tracking-normal ml-0.5">{dec}</span>
        </span>
      );
    }
    return <span className="whitespace-nowrap">{formatted}</span>;
  };

  return (
    <div className="space-y-8 pb-12">
      {/* Page Title & Business Context */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 border-b border-stone-200 pb-5">
        <div>
          <h1 className="text-2xl sm:text-3xl font-serif font-bold tracking-tight text-stone-900">
            Executive Financial Overview
          </h1>
          <p className="text-xs sm:text-sm text-stone-500 mt-1 font-sans">
            Verified ledger analytics, anomaly detection, and cash projections for <span className="font-semibold text-stone-800">{currentWorkspace?.name}</span>.
          </p>
        </div>
        <div className="flex items-center gap-2 self-start sm:self-auto">
          <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-medium bg-stone-100 text-stone-700 border border-stone-200">
            <Calendar className="w-3.5 h-3.5 text-stone-500" />
            Last 30 Days Window
          </span>
        </div>
      </div>

      {/* 7 Section 4 KPIs */}
      <div className="space-y-3.5">
        {/* Row 1: Primary Operating & Flow Metrics */}
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3.5">
          {/* 1. Current Cash */}
          <div className="bg-white p-4 rounded-xl border border-stone-200 shadow-xs min-w-0">
            <div className="flex items-center justify-between text-stone-500 mb-2">
              <span className="text-[11px] font-semibold uppercase tracking-wider text-stone-500">Current Cash</span>
              <DollarSign className="w-4 h-4 text-teal-700" />
            </div>
            <div 
              className="text-lg sm:text-xl lg:text-2xl font-bold font-mono tracking-tight text-stone-900 truncate"
              title={formatConverted(kpis.current_cash_minor)}
            >
              {renderMoneyValue(formatConverted(kpis.current_cash_minor))}
            </div>
            <p className="text-[10px] text-stone-400 mt-1 truncate">Across all active accounts</p>
          </div>

          {/* 2. Income (30d) */}
          <div className="bg-white p-4 rounded-xl border border-stone-200 shadow-xs min-w-0">
            <div className="flex items-center justify-between text-stone-500 mb-2">
              <span className="text-[11px] font-semibold uppercase tracking-wider text-stone-500">Income (30d)</span>
              <TrendingUp className="w-4 h-4 text-emerald-600" />
            </div>
            <div 
              className="text-lg sm:text-xl lg:text-2xl font-bold font-mono tracking-tight text-emerald-700 truncate"
              title={formatConverted(kpis.income_minor)}
            >
              {renderMoneyValue(formatConverted(kpis.income_minor))}
            </div>
            <p className="text-[10px] text-stone-400 mt-1 truncate">Verified revenues</p>
          </div>

          {/* 3. Expenses (30d) */}
          <div className="bg-white p-4 rounded-xl border border-stone-200 shadow-xs min-w-0">
            <div className="flex items-center justify-between text-stone-500 mb-2">
              <span className="text-[11px] font-semibold uppercase tracking-wider text-stone-500">Expenses (30d)</span>
              <TrendingDown className="w-4 h-4 text-rose-600" />
            </div>
            <div 
              className="text-lg sm:text-xl lg:text-2xl font-bold font-mono tracking-tight text-rose-700 truncate"
              title={formatConverted(kpis.expenses_minor)}
            >
              {renderMoneyValue(formatConverted(kpis.expenses_minor))}
            </div>
            <p className="text-[10px] text-stone-400 mt-1 truncate">Operating disbursements</p>
          </div>

          {/* 4. Net Cash Flow */}
          <div className="bg-white p-4 rounded-xl border border-stone-200 shadow-xs min-w-0">
            <div className="flex items-center justify-between text-stone-500 mb-2">
              <span className="text-[11px] font-semibold uppercase tracking-wider text-stone-500">Net Flow</span>
              <Activity className="w-4 h-4 text-teal-700" />
            </div>
            <div 
              className={`text-lg sm:text-xl lg:text-2xl font-bold font-mono tracking-tight truncate ${kpis.net_cash_flow_minor >= 0 ? 'text-teal-700' : 'text-rose-700'}`}
              title={formatConverted(kpis.net_cash_flow_minor)}
            >
              {renderMoneyValue(formatConverted(kpis.net_cash_flow_minor))}
            </div>
            <p className="text-[10px] text-stone-400 mt-1 truncate">Inflow minus outflow</p>
          </div>
        </div>

        {/* Row 2: Secondary Financial Health & Obligations */}
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3.5">
          {/* 5. Runway */}
          <div className="bg-white p-4 rounded-xl border border-stone-200 shadow-xs min-w-0">
            <div className="flex items-center justify-between text-stone-500 mb-2">
              <span className="text-[11px] font-semibold uppercase tracking-wider text-stone-500">Runway</span>
              <Hourglass className="w-4 h-4 text-amber-600" />
            </div>
            <div className="text-lg sm:text-xl lg:text-2xl font-bold tracking-tight text-stone-900 truncate">
              {kpis.runway_months !== null && kpis.runway_months !== undefined ? (
                <span className="text-amber-700 font-mono">{kpis.runway_months} mo</span>
              ) : (
                <span className="text-teal-700 text-sm font-semibold flex items-center gap-1">
                  <CheckCircle2 className="w-3.5 h-3.5" /> Cash Positive
                </span>
              )}
            </div>
            <p className="text-[10px] text-stone-400 mt-1 truncate">Based on monthly burn rate</p>
          </div>

          {/* 6. Payables */}
          <div className="bg-white p-4 rounded-xl border border-stone-200 shadow-xs min-w-0">
            <div className="flex items-center justify-between text-stone-500 mb-2">
              <span className="text-[11px] font-semibold uppercase tracking-wider text-stone-500">Payables</span>
              <ArrowDownLeft className="w-4 h-4 text-amber-600" />
            </div>
            <div 
              className="text-lg sm:text-xl lg:text-2xl font-bold font-mono tracking-tight text-stone-900 truncate"
              title={formatConverted(kpis.total_payables_minor)}
            >
              {renderMoneyValue(formatConverted(kpis.total_payables_minor))}
            </div>
            <p className="text-[10px] text-stone-400 mt-1 truncate">Pending vendor bills</p>
          </div>

          {/* 7. Receivables */}
          <div className="bg-white p-4 rounded-xl border border-stone-200 shadow-xs min-w-0">
            <div className="flex items-center justify-between text-stone-500 mb-2">
              <span className="text-[11px] font-semibold uppercase tracking-wider text-stone-500">Receivables</span>
              <ArrowUpRight className="w-4 h-4 text-teal-700" />
            </div>
            <div 
              className="text-lg sm:text-xl lg:text-2xl font-bold font-mono tracking-tight text-stone-900 truncate"
              title={formatConverted(kpis.total_receivables_minor)}
            >
              {renderMoneyValue(formatConverted(kpis.total_receivables_minor))}
            </div>
            <p className="text-[10px] text-stone-400 mt-1 truncate">Expected client invoices</p>
          </div>
        </div>
      </div>

      {/* Financial Health Score Banner */}
      {healthScore && (
        <Card className="p-6 bg-gradient-to-r from-stone-900 to-stone-850 text-white rounded-2xl shadow-md border-0">
          <div className="grid grid-cols-1 lg:grid-cols-4 gap-6 items-center">
            {/* Score & Grade */}
            <div className="flex items-center gap-4 lg:border-r lg:border-stone-700/60 lg:pr-6">
              <div className="w-20 h-20 rounded-2xl bg-teal-600/20 border border-teal-500/30 flex flex-col items-center justify-center shrink-0">
                <span className="text-3xl font-serif font-black text-teal-300 leading-none">{healthScore.grade}</span>
                <span className="text-[10px] font-mono text-stone-300 mt-0.5">{healthScore.overall_score}/100</span>
              </div>
              <div className="min-w-0">
                <div className="flex items-center gap-1.5 text-xs font-semibold text-teal-400 uppercase tracking-wider">
                  <Award className="w-3.5 h-3.5" />
                  Financial Health Score
                </div>
                <h3 className="text-base font-semibold text-stone-100 truncate mt-0.5">
                  {healthScore.status_description}
                </h3>
                <p className="text-xs text-stone-400 mt-0.5">
                  Runway: <span className="font-mono text-teal-300 font-semibold">{healthScore.runway_months} months</span>
                </p>
              </div>
            </div>

            {/* 5 Factor Mini Bars */}
            <div className="lg:col-span-2 space-y-2">
              <p className="text-[11px] font-semibold text-stone-400 uppercase tracking-wider mb-1">
                Core Health Factor Breakdown
              </p>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                {healthScore.factors.slice(0, 4).map((f) => (
                  <div key={f.id} className="bg-stone-800/60 p-2 rounded-lg border border-stone-700/40">
                    <div className="flex justify-between text-[11px] mb-1">
                      <span className="text-stone-300 font-medium truncate">{f.name}</span>
                      <span className="font-mono text-teal-300 font-semibold">{Math.round(f.score)}%</span>
                    </div>
                    <div className="w-full bg-stone-700/50 rounded-full h-1 overflow-hidden">
                      <div
                        className={`h-full rounded-full ${
                          f.score >= 75 ? 'bg-teal-400' : f.score >= 50 ? 'bg-amber-400' : 'bg-rose-400'
                        }`}
                        style={{ width: `${Math.min(100, f.score)}%` }}
                      />
                    </div>
                  </div>
                ))}
              </div>
            </div>

            {/* Action Callout */}
            <div className="flex flex-col justify-center items-start lg:items-end gap-3 lg:border-l lg:border-stone-700/60 lg:pl-6">
              <Link
                to="/simulator"
                className="w-full sm:w-auto inline-flex items-center justify-center gap-2 px-4 py-2 rounded-lg text-xs font-semibold bg-teal-600 hover:bg-teal-500 text-white shadow-sm transition-colors cursor-pointer"
              >
                <Sliders className="w-3.5 h-3.5" />
                Run What-If Simulation
                <ChevronRight className="w-3.5 h-3.5" />
              </Link>
              <Link
                to="/budgets"
                className="text-xs text-stone-300 hover:text-teal-300 transition-colors inline-flex items-center gap-1"
              >
                View Category Budgets →
              </Link>
            </div>
          </div>
        </Card>
      )}

      {/* Visualizations Section: 4 Charts */}
      <div className="space-y-6">
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* Chart 1: Cash Flow History */}
          <Card title="Cash-Flow History (Daily Ledger Trends)" subtitle="Daily net inflows and outflows over the past 30 days">
            <CashFlowChart data={cashFlowHistory} currency={currency} />
          </Card>

          {/* Chart 2: Income vs Expenses */}
          <Card title="Income vs. Expenses (Monthly Performance)" subtitle="Historical month-over-month operating comparison">
            <IncomeExpenseChart data={incomeVsExpenses} currency={currency} />
          </Card>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* Chart 3: Spending by Category */}
          <Card title="Spending by Category" subtitle="Top disbursement distributions derived from ML categorization">
            <CategoryPieChart data={spendingByCategory} currency={currency} />
          </Card>

          {/* Chart 4: Forecasted Cash Flow Preview */}
          <Card title="Forecasted Cash Flow (14-Day Trajectory)" subtitle="Time-series projection combining recurring schedules and historical burn">
            <ForecastChart data={forecastPreview} currency={currency} />
          </Card>
        </div>
      </div>

      {/* Secondary Operational Panels: Insights, Recurring, Anomalies, Payables/Receivables */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* 1. Important Insights */}
        <Card title="Algorithmic Financial Insights" subtitle="Deterministic database calculations highlighting critical trends">
          {data.recent_insights && data.recent_insights.length > 0 ? (
            <div className="space-y-3">
              {data.recent_insights.map((insight) => (
                <div key={insight.id} className="p-3 bg-stone-50 border border-stone-200/80 rounded-lg flex items-start gap-3">
                  <div className="p-1.5 rounded-md bg-teal-100 text-teal-800 shrink-0 mt-0.5">
                    <Sparkles className="w-4 h-4" />
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center justify-between gap-2">
                      <h4 className="text-xs font-semibold text-stone-900 truncate">{insight.title}</h4>
                      <StatusBadge status={insight.severity} />
                    </div>
                    <p className="text-xs text-stone-600 mt-1 leading-relaxed">{insight.description}</p>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <p className="text-xs text-stone-500 py-4 text-center">No active alerts. Financial metrics are within baseline parameters.</p>
          )}
        </Card>

        {/* 2. Unusual Transactions (Section 8 Anomaly Detection) */}
        <Card title="Unusual Transactions (Anomaly Detector)" subtitle="Business-context relevance, merchant consistency, robust MAD/IQR, and contextual Isolation Forest">
          {data.anomalous_transactions && data.anomalous_transactions.length > 0 ? (
            <div className="space-y-3">
              {data.anomalous_transactions.map((anom) => {
                const alertLabel =
                  anom.anomaly_alert_type === 'operational_relevance'
                    ? 'Operational Relevance'
                    : anom.anomaly_alert_type === 'merchant_category_mismatch'
                    ? 'Category Mismatch'
                    : anom.anomaly_alert_type === 'amount_anomaly'
                    ? 'Amount Outlier'
                    : anom.anomaly_alert_type === 'merchant_behavior'
                    ? 'Merchant Spike'
                    : 'Anomaly';
                return (
                  <div key={anom.id} className="p-3 bg-amber-50/50 border border-amber-200 rounded-lg flex items-start gap-3">
                    <div className="p-1.5 rounded-md bg-amber-100 text-amber-800 shrink-0 mt-0.5">
                      <AlertTriangle className="w-4 h-4" />
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center justify-between gap-2">
                        <div className="truncate flex items-center gap-1.5 flex-wrap">
                          <span className="text-xs font-semibold text-stone-900">{anom.merchant || 'Unknown Merchant'}</span>
                          <span className="px-1.5 py-0.2 rounded text-[10px] font-semibold bg-amber-100 text-amber-900 border border-amber-300">
                            {alertLabel}
                          </span>
                          <span className="text-[11px] text-stone-500 font-mono">({anom.date})</span>
                        </div>
                        <span className="text-xs font-bold font-mono text-rose-700 shrink-0">
                          {formatConverted(anom.amount_minor, anom.currency)}
                        </span>
                      </div>
                      <p className="text-xs text-stone-700 mt-1">{anom.anomaly_reason}</p>
                    </div>
                  </div>
                );
              })}
            </div>
          ) : (
            <p className="text-xs text-stone-500 py-4 text-center">All transactions conform to normal historical business patterns.</p>
          )}
        </Card>
      </div>

      {/* Tertiary Operational Panels: Recurring + Payables / Receivables */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* 3. Upcoming Recurring Payments */}
        <Card title="Upcoming Recurring Payments" subtitle="Detected recurring patterns with expected debit schedules">
          {data.upcoming_recurring && data.upcoming_recurring.length > 0 ? (
            <div className="divide-y divide-stone-100 border border-stone-200 rounded-lg overflow-hidden">
              {data.upcoming_recurring.map((item, idx) => (
                <div key={idx} className="p-3 bg-white flex items-center justify-between gap-4">
                  <div className="flex items-center gap-3 min-w-0">
                    <div className="p-1.5 bg-stone-100 text-stone-700 rounded-md shrink-0">
                      <RefreshCw className="w-4 h-4" />
                    </div>
                    <div className="min-w-0 truncate">
                      <p className="text-xs font-semibold text-stone-800 truncate">{item.merchant}</p>
                      <p className="text-[10px] text-stone-500 capitalize">{item.frequency} • Expected {item.next_date}</p>
                    </div>
                  </div>
                  <span className="text-xs font-bold font-mono text-stone-900">
                    {formatConverted(item.amount_minor)}
                  </span>
                </div>
              ))}
            </div>
          ) : (
            <p className="text-xs text-stone-500 py-4 text-center">No upcoming recurring obligations detected.</p>
          )}
        </Card>

        {/* 4. Upcoming Payables & Receivables */}
        <Card title="Upcoming Payables & Receivables" subtitle="Deterministic schedule of pending outflows and expected inflows">
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            {/* Payables column */}
            <div>
              <h4 className="text-xs font-semibold text-stone-700 uppercase tracking-wider mb-2 flex items-center gap-1.5">
                <ArrowDownLeft className="w-3.5 h-3.5 text-rose-600" />
                Payables (Due)
              </h4>
              <div className="space-y-2">
                {data.upcoming_payables && data.upcoming_payables.length > 0 ? (
                  data.upcoming_payables.slice(0, 3).map((p) => (
                    <div key={p.id} className="p-2.5 bg-stone-50 border border-stone-200 rounded-md text-xs">
                      <div className="flex justify-between items-center">
                        <span className="font-medium text-stone-800 truncate">{p.vendor}</span>
                        <span className="font-mono font-semibold text-rose-700">{formatConverted(p.amount_minor)}</span>
                      </div>
                      <span className="text-[10px] text-stone-500 mt-0.5 block">Due: {p.due_date}</span>
                    </div>
                  ))
                ) : (
                  <p className="text-xs text-stone-400 py-2">No payables due.</p>
                )}
              </div>
            </div>

            {/* Receivables column */}
            <div>
              <h4 className="text-xs font-semibold text-stone-700 uppercase tracking-wider mb-2 flex items-center gap-1.5">
                <ArrowUpRight className="w-3.5 h-3.5 text-teal-700" />
                Receivables (Expected)
              </h4>
              <div className="space-y-2">
                {data.upcoming_receivables && data.upcoming_receivables.length > 0 ? (
                  data.upcoming_receivables.slice(0, 3).map((r) => (
                    <div key={r.id} className="p-2.5 bg-stone-50 border border-stone-200 rounded-md text-xs">
                      <div className="flex justify-between items-center">
                        <span className="font-medium text-stone-800 truncate">{r.client}</span>
                        <span className="font-mono font-semibold text-teal-700">{formatConverted(r.amount_minor)}</span>
                      </div>
                      <span className="text-[10px] text-stone-500 mt-0.5 block">Due: {r.due_date}</span>
                    </div>
                  ))
                ) : (
                  <p className="text-xs text-stone-400 py-2">No receivables pending.</p>
                )}
              </div>
            </div>
          </div>
        </Card>
      </div>
    </div>
  );
};

export default DashboardPage;
