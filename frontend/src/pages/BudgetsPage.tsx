import React, { useState, useEffect } from 'react';
import { useWorkspace } from '../contexts/WorkspaceContext';
import { budgetsApi } from '../api/budgets';
import { BudgetPerformanceResponse, BudgetSummary } from '../types';
import { formatMoney } from '../utils/format';
import Card from '../components/ui/Card';
import Button from '../components/ui/Button';
import Input from '../components/ui/Input';
import LoadingSpinner from '../components/ui/LoadingSpinner';
import ErrorState from '../components/ui/ErrorState';
import Modal from '../components/ui/Modal';
import { 
  Wallet, 
  AlertTriangle, 
  CheckCircle2, 
  TrendingUp, 
  Plus, 
  Calendar, 
  Sliders, 
  DollarSign, 
  ArrowUpRight,
  ShieldCheck,
  AlertCircle
} from 'lucide-react';
import {
  ResponsiveContainer,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend
} from 'recharts';

export const BudgetsPage: React.FC = () => {
  const { currentWorkspace, currency: contextCurrency } = useWorkspace();
  const currency = contextCurrency || 'USD';

  const now = new Date();
  const defaultMonth = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`;
  const [selectedMonth, setSelectedMonth] = useState<string>(defaultMonth);

  const [performance, setPerformance] = useState<BudgetPerformanceResponse | null>(null);
  const [budgetsList, setBudgetsList] = useState<BudgetSummary[]>([]);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  // Edit/Create Budget Modal
  const [isModalOpen, setIsModalOpen] = useState<boolean>(false);
  const [budgetName, setBudgetName] = useState<string>('');
  const [categoryInputs, setCategoryInputs] = useState<Array<{ category_name: string; limit_dollars: string }>>([]);
  const [isSaving, setIsSaving] = useState<boolean>(false);

  const standardCategories = [
    'Software & Cloud Services',
    'Payroll & Wages',
    'Rent & Facilities',
    'Marketing & Advertising',
    'Professional & Legal',
    'Meals & Entertainment',
    'Office Supplies & Equipment',
    'Travel & Transportation',
    'Utilities & Telecom',
    'Miscellaneous'
  ];

  const fetchBudgetPerformance = async () => {
    if (!currentWorkspace) return;
    setIsLoading(true);
    setError(null);
    try {
      const data = await budgetsApi.getPerformance(currentWorkspace.id, selectedMonth);
      setPerformance(data);
      const list = await budgetsApi.list(currentWorkspace.id);
      setBudgetsList(list);
    } catch (err: any) {
      setError(err.response?.data?.detail || err.message || 'Failed to load budget records.');
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    fetchBudgetPerformance();
  }, [currentWorkspace, selectedMonth]);

  const handleOpenModal = () => {
    setBudgetName(performance?.name || `Budget ${selectedMonth}`);
    // Pre-populate category inputs
    const existingMap = new Map((performance?.category_performances || []).map(cp => [cp.category, cp.limit_minor]));
    const initialInputs = standardCategories.map(cat => ({
      category_name: cat,
      limit_dollars: existingMap.has(cat) ? String((existingMap.get(cat)! / 100).toFixed(0)) : '0'
    }));
    setCategoryInputs(initialInputs);
    setIsModalOpen(true);
  };

  const handleSaveBudget = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!currentWorkspace) return;
    setIsSaving(true);
    try {
      const category_limits = categoryInputs
        .map(ci => ({
          category_name: ci.category_name,
          limit_minor: Math.round(parseFloat(ci.limit_dollars || '0') * 100),
          alert_threshold_pct: 80.0
        }))
        .filter(c => c.limit_minor > 0);

      const total_limit = category_limits.reduce((acc, c) => acc + c.limit_minor, 0);

      await budgetsApi.createOrUpdate(currentWorkspace.id, {
        month: selectedMonth,
        name: budgetName.trim() || `Budget ${selectedMonth}`,
        category_limits,
        total_limit_minor: total_limit,
        currency,
      });

      setIsModalOpen(false);
      fetchBudgetPerformance();
    } catch (err: any) {
      alert('Failed to save budget: ' + (err.message || 'Unknown error'));
    } finally {
      setIsSaving(false);
    }
  };

  if (isLoading && !performance) return <LoadingSpinner />;
  if (error && !performance) return <ErrorState message={error} onRetry={fetchBudgetPerformance} />;

  const totalBudget = performance?.total_budget_limit_minor ?? 0;
  const totalSpent = performance?.total_spent_minor ?? 0;
  const remainingBudget = performance?.remaining_minor ?? 0;
  const overallSpentPct = performance?.spent_pct ?? 0;

  return (
    <div className="space-y-6">
      {/* Header & Controls */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-serif font-bold text-stone-900 tracking-tight flex items-center gap-2">
            <Wallet className="w-6 h-6 text-teal-700" />
            Budget Management
          </h1>
          <p className="text-xs text-stone-500 mt-1">
            Track actual spending against monthly department limits and receive real-time overspending alerts.
          </p>
        </div>

        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2 bg-white px-3 py-1.5 rounded-lg border border-stone-200 shadow-sm">
            <Calendar className="w-4 h-4 text-stone-400" />
            <input
              type="month"
              value={selectedMonth}
              onChange={(e) => setSelectedMonth(e.target.value)}
              className="text-xs font-semibold text-stone-800 bg-transparent focus:outline-none cursor-pointer"
            />
          </div>

          <Button variant="primary" size="sm" onClick={handleOpenModal} className="flex items-center gap-1.5">
            <Plus className="w-3.5 h-3.5" />
            {performance?.budget_id ? 'Edit Budget' : 'Create Budget'}
          </Button>
        </div>
      </div>

      {/* Top Level KPIs */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        <Card className="p-4 bg-white border-stone-200 shadow-sm">
          <span className="text-xs font-semibold text-stone-500 uppercase tracking-wider">Total Monthly Budget</span>
          <p className="text-2xl font-serif font-bold text-stone-900 mt-1 font-mono">
            {formatMoney(totalBudget, currency)}
          </p>
          <p className="text-[11px] text-stone-400 mt-0.5">Approved operational ceiling</p>
        </Card>

        <Card className="p-4 bg-white border-stone-200 shadow-sm">
          <span className="text-xs font-semibold text-stone-500 uppercase tracking-wider">Actual Spend to Date</span>
          <p className={`text-2xl font-serif font-bold mt-1 font-mono ${totalSpent > totalBudget && totalBudget > 0 ? 'text-rose-600' : 'text-stone-900'}`}>
            {formatMoney(totalSpent, currency)}
          </p>
          <div className="w-full bg-stone-100 rounded-full h-1.5 mt-2 overflow-hidden">
            <div
              className={`h-full rounded-full ${
                overallSpentPct > 100 ? 'bg-rose-500' : overallSpentPct >= 80 ? 'bg-amber-500' : 'bg-teal-600'
              }`}
              style={{ width: `${Math.min(100, overallSpentPct)}%` }}
            />
          </div>
          <p className="text-[11px] text-stone-400 mt-1">{overallSpentPct}% of budget utilized</p>
        </Card>

        <Card className="p-4 bg-white border-stone-200 shadow-sm">
          <span className="text-xs font-semibold text-stone-500 uppercase tracking-wider">Remaining Buffer</span>
          <p className={`text-2xl font-serif font-bold mt-1 font-mono ${remainingBudget < 0 ? 'text-rose-600' : 'text-teal-700'}`}>
            {formatMoney(remainingBudget, currency)}
          </p>
          <p className="text-[11px] text-stone-400 mt-0.5">
            {remainingBudget < 0 ? 'Exceeded by ' + formatMoney(Math.abs(remainingBudget), currency) : 'Available for remaining cycle'}
          </p>
        </Card>

        <Card className="p-4 bg-white border-stone-200 shadow-sm">
          <span className="text-xs font-semibold text-stone-500 uppercase tracking-wider">Over-Budget Categories</span>
          <div className="flex items-center gap-2 mt-1">
            <p className={`text-2xl font-serif font-bold font-mono ${performance?.overbudget_categories_count ? 'text-rose-600' : 'text-emerald-700'}`}>
              {performance?.overbudget_categories_count ?? 0}
            </p>
            {performance?.overbudget_categories_count ? (
              <AlertTriangle className="w-5 h-5 text-rose-500" />
            ) : (
              <ShieldCheck className="w-5 h-5 text-emerald-600" />
            )}
          </div>
          <p className="text-[11px] text-stone-400 mt-0.5">
            {performance?.overbudget_categories_count ? 'Requires immediate variance review' : 'All categories within target limits'}
          </p>
        </Card>
      </div>

      {/* Active Alerts */}
      {performance?.alerts && performance.alerts.length > 0 && (
        <Card className="p-4 bg-amber-50/50 border-amber-200 shadow-sm">
          <h3 className="text-xs font-semibold text-amber-900 uppercase tracking-wider flex items-center gap-1.5 mb-2">
            <AlertCircle className="w-4 h-4 text-amber-700" />
            Active Budget Alerts & Overspending Warnings
          </h3>
          <div className="space-y-1.5">
            {performance.alerts.map((a, idx) => (
              <div key={idx} className="text-xs text-amber-900 flex items-start gap-2">
                <span className="text-amber-600 font-bold">•</span>
                <span>{a.message}</span>
              </div>
            ))}
          </div>
        </Card>
      )}

      {/* Budget vs Actual Comparison Chart */}
      <Card className="p-6 bg-white border-stone-200 shadow-sm">
        <h3 className="text-sm font-semibold text-stone-800 mb-1">Budget vs. Actual Spending by Category</h3>
        <p className="text-xs text-stone-500 mb-4">Compare allocated limits against actual posted transactions</p>

        <div className="h-72 w-full">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart
              data={performance?.comparison_chart || []}
              margin={{ top: 10, right: 30, left: 20, bottom: 25 }}
            >
              <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#E7E5E4" />
              <XAxis
                dataKey="category"
                angle={-20}
                textAnchor="end"
                tick={{ fontSize: 10, fill: '#78716C' }}
                interval={0}
              />
              <YAxis
                tick={{ fontSize: 10, fill: '#78716C' }}
                tickFormatter={(v) => `$${(v / 100).toLocaleString()}`}
              />
              <Tooltip
                formatter={(val: number) => [formatMoney(val, currency), '']}
                contentStyle={{ backgroundColor: '#FFFFFF', borderColor: '#E7E5E4', borderRadius: '8px' }}
              />
              <Legend wrapperStyle={{ fontSize: 12, paddingTop: 10 }} />
              <Bar dataKey="budget_minor" name="Budget Limit" fill="#D6D3D1" radius={[4, 4, 0, 0]} />
              <Bar dataKey="actual_minor" name="Actual Spent" fill="#0F766E" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </Card>

      {/* Category Breakdown Table / Grid */}
      <Card className="p-6 bg-white border-stone-200 shadow-sm">
        <h3 className="text-sm font-semibold text-stone-800 mb-4">Category-Wise Spending Limits & Status</h3>

        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {(performance?.category_performances || []).map((cp) => {
            const isOver = cp.status === 'over_budget';
            const isWarn = cp.status === 'warning';
            return (
              <div
                key={cp.category}
                className={`p-4 rounded-xl border transition-all ${
                  isOver
                    ? 'border-rose-300 bg-rose-50/40'
                    : isWarn
                    ? 'border-amber-300 bg-amber-50/30'
                    : 'border-stone-200 bg-stone-50/50 hover:bg-stone-50'
                }`}
              >
                <div className="flex items-center justify-between mb-2">
                  <span className="text-xs font-semibold text-stone-900 truncate" title={cp.category}>
                    {cp.category}
                  </span>
                  <span
                    className={`text-[10px] px-2 py-0.5 rounded-full font-semibold uppercase ${
                      isOver
                        ? 'bg-rose-100 text-rose-700'
                        : isWarn
                        ? 'bg-amber-100 text-amber-700'
                        : cp.has_budget
                        ? 'bg-emerald-100 text-emerald-700'
                        : 'bg-stone-200 text-stone-600'
                    }`}
                  >
                    {cp.status.replace('_', ' ')}
                  </span>
                </div>

                <div className="flex items-baseline justify-between text-xs mt-3">
                  <span className="text-stone-500">Spent:</span>
                  <span className="font-mono font-bold text-stone-900">{formatMoney(cp.spent_minor, currency)}</span>
                </div>
                <div className="flex items-baseline justify-between text-xs mt-1">
                  <span className="text-stone-500">Budget Limit:</span>
                  <span className="font-mono font-medium text-stone-700">{formatMoney(cp.limit_minor, currency)}</span>
                </div>

                {/* Progress Bar */}
                <div className="w-full bg-stone-200 rounded-full h-1.5 mt-3 overflow-hidden">
                  <div
                    className={`h-full rounded-full ${
                      isOver ? 'bg-rose-500' : isWarn ? 'bg-amber-500' : 'bg-teal-600'
                    }`}
                    style={{ width: `${Math.min(100, cp.spent_pct)}%` }}
                  />
                </div>

                <div className="flex justify-between items-center text-[10px] text-stone-500 mt-1.5">
                  <span>{cp.spent_pct}% used</span>
                  <span>
                    {cp.remaining_minor >= 0
                      ? `${formatMoney(cp.remaining_minor, currency)} remaining`
                      : `${formatMoney(Math.abs(cp.remaining_minor), currency)} over limit`}
                  </span>
                </div>
              </div>
            );
          })}
        </div>
      </Card>

      {/* Edit Budget Modal */}
      <Modal
        isOpen={isModalOpen}
        onClose={() => setIsModalOpen(false)}
        title={`Configure Monthly Budget (${selectedMonth})`}
      >
        <form onSubmit={handleSaveBudget} className="space-y-4">
          <div>
            <label className="block text-xs font-semibold text-stone-700 mb-1">Budget Title</label>
            <Input
              value={budgetName}
              onChange={(e) => setBudgetName(e.target.value)}
              placeholder="e.g. Q4 Operating Budget"
              required
            />
          </div>

          <div>
            <label className="block text-xs font-semibold text-stone-700 mb-2">Category Spending Limits ({currency})</label>
            <div className="space-y-2 max-h-72 overflow-y-auto pr-1">
              {categoryInputs.map((ci, idx) => (
                <div key={ci.category_name} className="flex items-center justify-between gap-3 p-2 bg-stone-50 rounded-lg border border-stone-200">
                  <span className="text-xs font-medium text-stone-800 truncate flex-1">{ci.category_name}</span>
                  <div className="w-32">
                    <Input
                      type="number"
                      min="0"
                      step="10"
                      value={ci.limit_dollars}
                      onChange={(e) => {
                        const val = e.target.value;
                        setCategoryInputs(prev => {
                          const copy = [...prev];
                          copy[idx] = { ...copy[idx], limit_dollars: val };
                          return copy;
                        });
                      }}
                      placeholder="0.00"
                    />
                  </div>
                </div>
              ))}
            </div>
          </div>

          <div className="p-3 bg-stone-100 rounded-lg text-xs flex justify-between items-center">
            <span className="font-semibold text-stone-700">Total Computed Budget:</span>
            <span className="font-mono font-bold text-stone-900">
              {formatMoney(
                categoryInputs.reduce((sum, ci) => sum + Math.round(parseFloat(ci.limit_dollars || '0') * 100), 0),
                currency
              )}
            </span>
          </div>

          <div className="flex justify-end gap-2 pt-2">
            <Button variant="outline" type="button" onClick={() => setIsModalOpen(false)}>
              Cancel
            </Button>
            <Button variant="primary" type="submit" isLoading={isSaving}>
              Save Budget Limits
            </Button>
          </div>
        </form>
      </Modal>
    </div>
  );
};

export default BudgetsPage;
