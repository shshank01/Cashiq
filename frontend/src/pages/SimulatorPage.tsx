import React, { useState, useEffect } from 'react';
import { useWorkspace } from '../contexts/WorkspaceContext';
import { simulatorApi } from '../api/simulator';
import { SimulationResponse, SavedScenario } from '../types';
import { formatMoney } from '../utils/format';
import Card from '../components/ui/Card';
import Button from '../components/ui/Button';
import Input from '../components/ui/Input';
import LoadingSpinner from '../components/ui/LoadingSpinner';
import ErrorState from '../components/ui/ErrorState';
import Modal from '../components/ui/Modal';
import { 
  Sliders, 
  TrendingUp, 
  TrendingDown, 
  AlertTriangle, 
  CheckCircle2, 
  ShieldAlert, 
  Save, 
  Trash2, 
  RotateCcw,
  Clock,
  Sparkles,
  Pencil
} from 'lucide-react';
import {
  ResponsiveContainer,
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  BarChart,
  Bar
} from 'recharts';

interface EditableValueBadgeProps {
  value: number;
  min: number;
  max: number;
  unit: '%' | 'days';
  colorClass?: string;
  onChange: (val: number) => void;
  ariaLabel?: string;
}

const parseNumericValue = (
  raw: string,
  fallback: number,
  min: number,
  max: number,
  unit: '%' | 'days'
): number => {
  const trimmed = raw.trim();
  if (!trimmed) return fallback;

  if (trimmed.toLowerCase() === 'on time' || trimmed.toLowerCase() === 'ontime') {
    return 0;
  }

  const cleaned = trimmed.replace(/\s+/g, '');
  const match = cleaned.match(/^([+-]?\d+(?:\.\d+)?)/);
  if (!match) {
    const fallbackMatch = cleaned.match(/([+-]?\d+(?:\.\d+)?)/);
    if (!fallbackMatch) return fallback;
    const num = parseFloat(fallbackMatch[1]);
    if (isNaN(num)) return fallback;
    const finalVal = unit === 'days' ? Math.round(num) : Math.round(num * 10) / 10;
    return Math.min(max, Math.max(min, finalVal));
  }

  const num = parseFloat(match[1]);
  if (isNaN(num)) return fallback;

  const finalVal = unit === 'days' ? Math.round(num) : Math.round(num * 10) / 10;
  return Math.min(max, Math.max(min, finalVal));
};

const formatDisplay = (val: number, unit: '%' | 'days'): string => {
  if (unit === '%') {
    return val > 0 ? `+${val}%` : `${val}%`;
  }
  return val === 0 ? 'On Time' : `+${val} days`;
};

const formatEditInit = (val: number, unit: '%' | 'days'): string => {
  if (unit === '%') {
    return val > 0 ? `+${val}%` : `${val}%`;
  }
  return val === 0 ? '0' : `+${val} days`;
};

const EditableValueBadge: React.FC<EditableValueBadgeProps> = ({
  value,
  min,
  max,
  unit,
  colorClass,
  onChange,
  ariaLabel
}) => {
  const [isEditing, setIsEditing] = useState(false);
  const [inputText, setInputText] = useState('');
  const inputRef = React.useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (isEditing && inputRef.current) {
      inputRef.current.focus();
      inputRef.current.select();
    }
  }, [isEditing]);

  const handleStartEdit = () => {
    setInputText(formatEditInit(value, unit));
    setIsEditing(true);
  };

  const handleCommit = () => {
    const parsed = parseNumericValue(inputText, value, min, max, unit);
    onChange(parsed);
    setIsEditing(false);
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter') {
      e.preventDefault();
      handleCommit();
    } else if (e.key === 'Escape') {
      e.preventDefault();
      setIsEditing(false);
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      const current = parseNumericValue(inputText, value, min, max, unit);
      const next = Math.min(max, current + 1);
      setInputText(formatEditInit(next, unit));
      onChange(next);
    } else if (e.key === 'ArrowDown') {
      e.preventDefault();
      const current = parseNumericValue(inputText, value, min, max, unit);
      const next = Math.max(min, current - 1);
      setInputText(formatEditInit(next, unit));
      onChange(next);
    }
  };

  if (isEditing) {
    return (
      <div className="flex items-center">
        <input
          ref={inputRef}
          type="text"
          value={inputText}
          onChange={(e) => setInputText(e.target.value)}
          onBlur={handleCommit}
          onKeyDown={handleKeyDown}
          aria-label={ariaLabel || 'Exact parameter value'}
          className="w-20 px-1.5 py-0.5 text-xs font-mono font-semibold text-right border border-teal-600 rounded bg-white shadow-sm focus:outline-none focus:ring-1 focus:ring-teal-600 text-stone-900"
          placeholder={unit === '%' ? '+0%' : '0 days'}
        />
      </div>
    );
  }

  return (
    <div
      role="button"
      tabIndex={0}
      onClick={handleStartEdit}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          handleStartEdit();
        }
      }}
      title="Click to type an exact number (e.g. +7%, +13%, +22 days)"
      aria-label={ariaLabel || 'Click to type an exact number'}
      className={`group font-mono font-semibold cursor-pointer px-1.5 py-0.5 rounded border border-dashed border-transparent hover:border-stone-300 hover:bg-stone-50 transition-all flex items-center gap-1 select-none ${colorClass || 'text-stone-800'}`}
    >
      <span>{formatDisplay(value, unit)}</span>
      <Pencil className="w-2.5 h-2.5 opacity-0 group-hover:opacity-60 text-stone-400 transition-opacity" />
    </div>
  );
};

export const SimulatorPage: React.FC = () => {
  const { currentWorkspace, currency: contextCurrency } = useWorkspace();
  const currency = contextCurrency || 'USD';

  // Simulation controls
  const [revenueChangePct, setRevenueChangePct] = useState<number>(-10);
  const [expenseChangePct, setExpenseChangePct] = useState<number>(5);
  const [delayedDays, setDelayedDays] = useState<number>(15);
  const [horizonMonths, setHorizonMonths] = useState<number>(6);

  // Results & state
  const [simulation, setSimulation] = useState<SimulationResponse | null>(null);
  const [savedScenarios, setSavedScenarios] = useState<SavedScenario[]>([]);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [isSimulating, setIsSimulating] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  // Save Modal
  const [isSaveModalOpen, setIsSaveModalOpen] = useState<boolean>(false);
  const [scenarioName, setScenarioName] = useState<string>('');
  const [scenarioDesc, setScenarioDesc] = useState<string>('');
  const [isSaving, setIsSaving] = useState<boolean>(false);

  const fetchSimulation = async () => {
    if (!currentWorkspace) return;
    setIsSimulating(true);
    setError(null);
    try {
      const res = await simulatorApi.run(currentWorkspace.id, {
        revenue_change_pct: revenueChangePct,
        expense_change_pct: expenseChangePct,
        delayed_receivables_days: delayedDays,
        months: horizonMonths,
      });
      setSimulation(res);
    } catch (err: any) {
      setError(err.response?.data?.detail || err.message || 'Failed to compute financial simulation.');
    } finally {
      setIsSimulating(false);
      setIsLoading(false);
    }
  };

  const fetchSavedScenarios = async () => {
    if (!currentWorkspace) return;
    try {
      const list = await simulatorApi.listScenarios(currentWorkspace.id);
      setSavedScenarios(list);
    } catch (err) {
      console.error('Failed to load saved scenarios', err);
    }
  };

  useEffect(() => {
    fetchSimulation();
    fetchSavedScenarios();
  }, [currentWorkspace]);

  const handleApplySliders = () => {
    fetchSimulation();
  };

  const handleReset = () => {
    setRevenueChangePct(0);
    setExpenseChangePct(0);
    setDelayedDays(0);
    setHorizonMonths(6);
  };

  const handleSaveScenario = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!currentWorkspace || !simulation || !scenarioName.trim()) return;
    setIsSaving(true);
    try {
      await simulatorApi.saveScenario(currentWorkspace.id, {
        name: scenarioName.trim(),
        description: scenarioDesc.trim() || undefined,
        parameters: simulation.inputs,
        results: simulation.scenarios,
      });
      setIsSaveModalOpen(false);
      setScenarioName('');
      setScenarioDesc('');
      fetchSavedScenarios();
    } catch (err: any) {
      alert('Failed to save scenario: ' + (err.message || 'Unknown error'));
    } finally {
      setIsSaving(false);
    }
  };

  const handleDeleteScenario = async (scenarioId: string) => {
    if (!currentWorkspace || !window.confirm('Delete this saved scenario?')) return;
    try {
      await simulatorApi.deleteScenario(currentWorkspace.id, scenarioId);
      fetchSavedScenarios();
    } catch (err: any) {
      alert('Failed to delete scenario: ' + err.message);
    }
  };

  const handleLoadScenario = (s: SavedScenario) => {
    if (s.parameters) {
      setRevenueChangePct(s.parameters.revenue_change_pct ?? 0);
      setExpenseChangePct(s.parameters.expense_change_pct ?? 0);
      setDelayedDays(s.parameters.delayed_receivables_days ?? 0);
      setHorizonMonths(s.parameters.months ?? 6);
      fetchSimulation();
    }
  };

  if (isLoading) return <LoadingSpinner />;
  if (error && !simulation) return <ErrorState message={error} onRetry={fetchSimulation} />;

  const scenarios = simulation?.scenarios;
  const baseline = scenarios?.baseline;
  const expected = scenarios?.expected_case;
  const best = scenarios?.best_case;
  const worst = scenarios?.worst_case;

  return (
    <div className="space-y-6">
      {/* Page Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-serif font-bold text-stone-900 tracking-tight flex items-center gap-2">
            <Sliders className="w-6 h-6 text-teal-700" />
            What-If Financial Simulator
          </h1>
          <p className="text-xs text-stone-500 mt-1">
            Simulate revenue shifts, expense fluctuations, and payment delays to stress-test your cash runway.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" size="sm" onClick={handleReset} className="flex items-center gap-1.5">
            <RotateCcw className="w-3.5 h-3.5" />
            Reset Defaults
          </Button>
          <Button variant="primary" size="sm" onClick={() => setIsSaveModalOpen(true)} className="flex items-center gap-1.5">
            <Save className="w-3.5 h-3.5" />
            Save Scenario
          </Button>
        </div>
      </div>

      {/* Simulator Interactive Control Panel */}
      <Card className="p-6 bg-white border-stone-200 shadow-sm">
        <h2 className="text-sm font-semibold text-stone-800 uppercase tracking-wider mb-4 flex items-center gap-2">
          <Sparkles className="w-4 h-4 text-teal-600" />
          Simulation Parameters
        </h2>

        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
          {/* Revenue Change Slider */}
          <div className="space-y-2">
            <div className="flex justify-between items-center text-xs">
              <span className="font-medium text-stone-700">Revenue Adjustment</span>
              <EditableValueBadge
                value={revenueChangePct}
                min={-50}
                max={50}
                unit="%"
                colorClass={revenueChangePct >= 0 ? 'text-teal-700' : 'text-rose-600'}
                onChange={setRevenueChangePct}
                ariaLabel="Revenue Adjustment Percentage"
              />
            </div>
            <input
              type="range"
              min="-50"
              max="50"
              step="1"
              value={revenueChangePct}
              onChange={(e) => setRevenueChangePct(Number(e.target.value))}
              className="w-full accent-teal-600 cursor-pointer"
            />
            <div className="flex justify-between text-[10px] text-stone-400 font-mono">
              <span>-50%</span>
              <span>0%</span>
              <span>+50%</span>
            </div>
            <p className="text-[11px] text-stone-400">Simulate market contractions or pipeline growth</p>
          </div>

          {/* Expense Change Slider */}
          <div className="space-y-2">
            <div className="flex justify-between items-center text-xs">
              <span className="font-medium text-stone-700">Expense Adjustment</span>
              <EditableValueBadge
                value={expenseChangePct}
                min={-50}
                max={50}
                unit="%"
                colorClass={expenseChangePct <= 0 ? 'text-teal-700' : 'text-rose-600'}
                onChange={setExpenseChangePct}
                ariaLabel="Expense Adjustment Percentage"
              />
            </div>
            <input
              type="range"
              min="-50"
              max="50"
              step="1"
              value={expenseChangePct}
              onChange={(e) => setExpenseChangePct(Number(e.target.value))}
              className="w-full accent-teal-600 cursor-pointer"
            />
            <div className="flex justify-between text-[10px] text-stone-400 font-mono">
              <span>-50%</span>
              <span>0%</span>
              <span>+50%</span>
            </div>
            <p className="text-[11px] text-stone-400">Simulate hiring, cloud spikes, or budget cuts</p>
          </div>

          {/* Delayed Payments Slider */}
          <div className="space-y-2">
            <div className="flex justify-between items-center text-xs">
              <span className="font-medium text-stone-700">Receivables Delay</span>
              <EditableValueBadge
                value={delayedDays}
                min={0}
                max={60}
                unit="days"
                colorClass="text-stone-800"
                onChange={setDelayedDays}
                ariaLabel="Receivables Delay in Days"
              />
            </div>
            <input
              type="range"
              min="0"
              max="60"
              step="1"
              value={delayedDays}
              onChange={(e) => setDelayedDays(Number(e.target.value))}
              className="w-full accent-teal-600 cursor-pointer"
            />
            <div className="flex justify-between text-[10px] text-stone-400 font-mono">
              <span>On Time</span>
              <span>+30d</span>
              <span>+60d</span>
            </div>
            <p className="text-[11px] text-stone-400">Simulate client invoice collection delays</p>
          </div>

          {/* Forecast Horizon */}
          <div className="space-y-2">
            <div className="flex justify-between text-xs">
              <span className="font-medium text-stone-700">Projection Horizon</span>
              <span className="font-mono font-semibold text-stone-800">{horizonMonths} Months</span>
            </div>
            <div className="grid grid-cols-3 gap-2">
              {[3, 6, 12].map((m) => (
                <button
                  key={m}
                  onClick={() => setHorizonMonths(m)}
                  className={`py-1.5 text-xs rounded-lg font-medium border transition-colors ${
                    horizonMonths === m
                      ? 'bg-teal-700 text-white border-teal-700 shadow-sm'
                      : 'bg-stone-50 text-stone-600 border-stone-200 hover:bg-stone-100'
                  }`}
                >
                  {m}M
                </button>
              ))}
            </div>
            <Button
              onClick={handleApplySliders}
              isLoading={isSimulating}
              className="w-full mt-2"
              size="sm"
            >
              Run Simulation
            </Button>
          </div>
        </div>
      </Card>

      {/* Scenario KPI Comparison Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        {/* Baseline Card */}
        <Card className="p-4 border-l-4 border-l-stone-400 bg-white shadow-sm">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold text-stone-500 uppercase tracking-wider">Baseline Trend</span>
            <Clock className="w-4 h-4 text-stone-400" />
          </div>
          <div className="mt-2">
            <p className="text-2xl font-serif font-bold text-stone-900">
              {baseline?.runway_months && baseline.runway_months >= 99 ? 'Sustainable' : `${baseline?.runway_months ?? 0} mo`}
            </p>
            <p className="text-xs text-stone-500 mt-1">
              Ending Cash: <span className="font-mono font-semibold text-stone-800">{formatMoney(baseline?.ending_cash_minor ?? 0, currency)}</span>
            </p>
            <p className="text-[11px] text-stone-400 mt-0.5">Current operational cadence</p>
          </div>
        </Card>

        {/* Expected Case Card */}
        <Card className="p-4 border-l-4 border-l-teal-600 bg-white shadow-sm">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold text-teal-800 uppercase tracking-wider">Expected Scenario</span>
            <Sliders className="w-4 h-4 text-teal-600" />
          </div>
          <div className="mt-2">
            <p className="text-2xl font-serif font-bold text-teal-900">
              {expected?.runway_months && expected.runway_months >= 99 ? 'Sustainable' : `${expected?.runway_months ?? 0} mo`}
            </p>
            <p className="text-xs text-stone-500 mt-1">
              Ending Cash: <span className="font-mono font-semibold text-stone-800">{formatMoney(expected?.ending_cash_minor ?? 0, currency)}</span>
            </p>
            <p className="text-[11px] text-teal-700 mt-0.5">
              Rev: {revenueChangePct}% | Exp: {expenseChangePct}% | Delay: +{delayedDays}d
            </p>
          </div>
        </Card>

        {/* Best Case Card */}
        <Card className="p-4 border-l-4 border-l-emerald-600 bg-white shadow-sm">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold text-emerald-800 uppercase tracking-wider">Best-Case (Optimistic)</span>
            <CheckCircle2 className="w-4 h-4 text-emerald-600" />
          </div>
          <div className="mt-2">
            <p className="text-2xl font-serif font-bold text-emerald-900">
              {best?.runway_months && best.runway_months >= 99 ? 'Sustainable' : `${best?.runway_months ?? 0} mo`}
            </p>
            <p className="text-xs text-stone-500 mt-1">
              Ending Cash: <span className="font-mono font-semibold text-emerald-800">{formatMoney(best?.ending_cash_minor ?? 0, currency)}</span>
            </p>
            <p className="text-[11px] text-stone-400 mt-0.5">Prompt payments & expense discipline</p>
          </div>
        </Card>

        {/* Worst Case Card */}
        <Card className="p-4 border-l-4 border-l-rose-500 bg-white shadow-sm">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold text-rose-800 uppercase tracking-wider">Worst-Case (Stress Test)</span>
            <ShieldAlert className="w-4 h-4 text-rose-500" />
          </div>
          <div className="mt-2">
            <p className="text-2xl font-serif font-bold text-rose-900">
              {worst?.runway_months && worst.runway_months >= 99 ? 'Sustainable' : `${worst?.runway_months ?? 0} mo`}
            </p>
            <p className="text-xs text-stone-500 mt-1">
              Ending Cash: <span className="font-mono font-semibold text-rose-700">{formatMoney(worst?.ending_cash_minor ?? 0, currency)}</span>
            </p>
            <p className="text-[11px] text-stone-400 mt-0.5">Prolonged delays & unforeseen costs</p>
          </div>
        </Card>
      </div>

      {/* Trajectory Comparison Chart */}
      <Card className="p-6 bg-white border-stone-200 shadow-sm">
        <div className="flex items-center justify-between mb-4">
          <div>
            <h3 className="text-sm font-semibold text-stone-800">Projected Cash Balance Comparison</h3>
            <p className="text-xs text-stone-500">Side-by-side cash trajectory across all 4 financial models</p>
          </div>
        </div>
        <div className="h-80 w-full">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={simulation?.comparison_chart || []} margin={{ top: 10, right: 30, left: 20, bottom: 5 }}>
              <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#E7E5E4" />
              <XAxis dataKey="month_label" tick={{ fontSize: 11, fill: '#78716C' }} />
              <YAxis
                tick={{ fontSize: 11, fill: '#78716C' }}
                tickFormatter={(v) => `$${(v / 100000).toFixed(0)}k`}
              />
              <Tooltip
                formatter={(val: number) => [formatMoney(val, currency), 'Cash Balance']}
                labelStyle={{ fontWeight: 600, color: '#1C1917' }}
                contentStyle={{ backgroundColor: '#FFFFFF', borderColor: '#E7E5E4', borderRadius: '8px' }}
              />
              <Legend wrapperStyle={{ fontSize: 12 }} />
              <Line type="monotone" dataKey="best_cash_minor" name="Best Case" stroke="#059669" strokeWidth={2} dot={{ r: 3 }} />
              <Line type="monotone" dataKey="expected_cash_minor" name="Expected (Simulated)" stroke="#0F766E" strokeWidth={3} dot={{ r: 4 }} />
              <Line type="monotone" dataKey="baseline_cash_minor" name="Baseline (Current)" stroke="#78716C" strokeWidth={2} strokeDasharray="5 5" />
              <Line type="monotone" dataKey="worst_cash_minor" name="Worst Case (Stress)" stroke="#E11D48" strokeWidth={2} dot={{ r: 3 }} />
            </LineChart>
          </ResponsiveContainer>
        </div>
      </Card>

      {/* Monthly Net Cash Flow Breakdown Chart */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <Card className="p-6 bg-white border-stone-200 shadow-sm lg:col-span-2">
          <h3 className="text-sm font-semibold text-stone-800 mb-1">Expected Monthly Net Cash Flow</h3>
          <p className="text-xs text-stone-500 mb-4">Monthly cash surplus / deficit under simulated conditions</p>
          <div className="h-64 w-full">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={simulation?.comparison_chart || []}>
                <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#E7E5E4" />
                <XAxis dataKey="month_label" tick={{ fontSize: 11, fill: '#78716C' }} />
                <YAxis
                  tick={{ fontSize: 11, fill: '#78716C' }}
                  tickFormatter={(v) => `$${(v / 100000).toFixed(0)}k`}
                />
                <Tooltip
                  formatter={(val: number) => [formatMoney(val, currency), 'Net Flow']}
                  contentStyle={{ backgroundColor: '#FFFFFF', borderColor: '#E7E5E4', borderRadius: '8px' }}
                />
                <Legend wrapperStyle={{ fontSize: 12 }} />
                <Bar dataKey="expected_net_flow_minor" name="Simulated Net Flow" fill="#0F766E" radius={[4, 4, 0, 0]} />
                <Bar dataKey="baseline_net_flow_minor" name="Baseline Net Flow" fill="#D6D3D1" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </Card>

        {/* Saved Scenarios List */}
        <Card className="p-6 bg-white border-stone-200 shadow-sm flex flex-col justify-between">
          <div>
            <h3 className="text-sm font-semibold text-stone-800 mb-1 flex items-center justify-between">
              <span>Saved Scenarios</span>
              <span className="text-xs font-normal text-stone-500 font-mono">{savedScenarios.length} saved</span>
            </h3>
            <p className="text-xs text-stone-500 mb-4">Restore or compare previously saved simulations</p>

            {savedScenarios.length === 0 ? (
              <div className="text-center py-8 text-stone-400 text-xs">
                No saved scenarios yet. Use "Save Scenario" above to record your forecasts.
              </div>
            ) : (
              <div className="space-y-3 max-h-60 overflow-y-auto pr-1">
                {savedScenarios.map((s) => (
                  <div
                    key={s.id}
                    className="p-3 bg-stone-50 border border-stone-200 rounded-lg flex items-center justify-between hover:bg-stone-100/80 transition-colors cursor-pointer"
                    onClick={() => handleLoadScenario(s)}
                  >
                    <div className="min-w-0 flex-1">
                      <p className="text-xs font-semibold text-stone-900 truncate">{s.name}</p>
                      <p className="text-[11px] text-stone-500 mt-0.5">
                        Rev: {s.parameters?.revenue_change_pct ?? 0}% | Exp: {s.parameters?.expense_change_pct ?? 0}%
                      </p>
                    </div>
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        handleDeleteScenario(s.id);
                      }}
                      className="p-1 text-stone-400 hover:text-rose-600 transition-colors ml-2"
                      title="Delete scenario"
                    >
                      <Trash2 className="w-3.5 h-3.5" />
                    </button>
                  </div>
                ))}
              </div>
            )}
          </div>
          <p className="text-[11px] text-stone-400 mt-4 border-t border-stone-100 pt-3">
            💡 Pro Tip: Run stress tests before quarterly budget reviews to determine safe hiring buffers.
          </p>
        </Card>
      </div>

      {/* Save Scenario Modal */}
      <Modal isOpen={isSaveModalOpen} onClose={() => setIsSaveModalOpen(false)} title="Save What-If Scenario">
        <form onSubmit={handleSaveScenario} className="space-y-4">
          <div>
            <label className="block text-xs font-semibold text-stone-700 mb-1">Scenario Name *</label>
            <Input
              required
              placeholder="e.g. Q3 Hiring Expansion (+15% spend, -10% rev)"
              value={scenarioName}
              onChange={(e) => setScenarioName(e.target.value)}
            />
          </div>
          <div>
            <label className="block text-xs font-semibold text-stone-700 mb-1">Description / Assumptions</label>
            <textarea
              rows={3}
              placeholder="Notes on headcount changes, expected enterprise deals, or delayed invoicing..."
              value={scenarioDesc}
              onChange={(e) => setScenarioDesc(e.target.value)}
              className="w-full text-xs p-2.5 border border-stone-300 rounded-lg focus:outline-none focus:ring-1 focus:ring-teal-600"
            />
          </div>
          <div className="p-3 bg-stone-50 rounded-lg border border-stone-200 text-xs space-y-1">
            <p className="font-semibold text-stone-800">Parameters to Save:</p>
            <p className="text-stone-600">• Revenue Change: {revenueChangePct}%</p>
            <p className="text-stone-600">• Expense Change: {expenseChangePct}%</p>
            <p className="text-stone-600">• Delayed Receivables: {delayedDays} days</p>
            <p className="text-stone-600">• Horizon: {horizonMonths} Months</p>
          </div>
          <div className="flex justify-end gap-2 pt-2">
            <Button variant="outline" type="button" onClick={() => setIsSaveModalOpen(false)}>
              Cancel
            </Button>
            <Button variant="primary" type="submit" isLoading={isSaving}>
              Save Scenario
            </Button>
          </div>
        </form>
      </Modal>
    </div>
  );
};

export default SimulatorPage;
