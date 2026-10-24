import React, { useEffect, useState, useMemo } from 'react';
import { useWorkspace } from '../contexts/WorkspaceContext';
import { recurringApi } from '../api/recurring';
import { formatMoney } from '../utils/format';
import { 
  RefreshCw, Repeat, Calendar, Plus, Trash2, CheckCircle2, 
  AlertCircle, AlertTriangle, X, Play, Pause, Search, Sparkles, ArrowDownRight, ArrowUpRight
} from 'lucide-react';
import { Button } from '../components/ui/Button';
import { Table, Column } from '../components/ui/Table';
import { Badge } from '../components/ui/Badge';
import { Card } from '../components/ui/Card';
import { Modal } from '../components/ui/Modal';
import { Input } from '../components/ui/Input';
import { LoadingSpinner } from '../components/ui/LoadingSpinner';
import { ErrorState } from '../components/ui/ErrorState';
import { EmptyState } from '../components/ui/EmptyState';
import { RecurringPayment } from '../types';

interface BannerState {
  type: 'success' | 'warning' | 'info';
  message: string;
  timestamp: string;
}

export function RecurringPage() {
  const { currentWorkspace, currency, isLoading: wsLoading, formatConverted } = useWorkspace();
  const [recurring, setRecurring] = useState<RecurringPayment[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [isDetecting, setIsDetecting] = useState(false);
  const [isSeeding, setIsSeeding] = useState(false);
  const [activeTab, setActiveTab] = useState<'all' | 'expense' | 'income'>('all');
  const [searchQuery, setSearchQuery] = useState('');
  const [banner, setBanner] = useState<BannerState | null>(null);

  // Manual Add Modal State
  const [isAddModalOpen, setIsAddModalOpen] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [form, setForm] = useState({
    merchant: '',
    description: '',
    amount: '',
    frequency: 'monthly',
    type: 'expense',
    category_name: 'Software & Cloud Services',
    next_date: new Date(Date.now() + 30 * 24 * 60 * 60 * 1000).toISOString().split('T')[0],
  });

  const fetchRecurring = async () => {
    if (!currentWorkspace) return;
    setIsLoading(true);
    setError(null);
    try {
      const data = await recurringApi.list(currentWorkspace.id);
      setRecurring(data.recurring_payments || (Array.isArray(data) ? data : []));
    } catch (err: any) {
      setError(err.message || 'Failed to fetch recurring transactions');
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    if (currentWorkspace) {
      fetchRecurring();
    } else if (!wsLoading) {
      setIsLoading(false);
    }
  }, [currentWorkspace, wsLoading]);

  const handleDetect = async () => {
    if (!currentWorkspace) return;
    setIsDetecting(true);
    try {
      const res = await recurringApi.detect(currentWorkspace.id);
      const items = res.recurring_payments || (Array.isArray(res) ? res : []);
      setRecurring(items);

      const txAnalyzed = res.transactions_analyzed ?? 0;
      const detectedCount = res.detected_count ?? items.length;

      const timeStr = new Date().toLocaleTimeString();

      if (txAnalyzed === 0) {
        setBanner({
          type: 'warning',
          message: 'Workspace currently has 0 transactions. Pattern detection requires transaction history to evaluate frequency and amount variance. Click "Load Demo Transactions" to test detection immediately.',
          timestamp: timeStr,
        });
      } else if (detectedCount === 0) {
        setBanner({
          type: 'info',
          message: `Analyzed ${txAnalyzed} transactions, but found no recurring patterns meeting the confidence threshold (requires ≥2 repeat charges from the same vendor spaced 5+ days apart).`,
          timestamp: timeStr,
        });
      } else {
        setBanner({
          type: 'success',
          message: `Pattern detection successful! Analyzed ${txAnalyzed} transactions and registered ${detectedCount} recurring obligations with upcoming expected debit schedules.`,
          timestamp: timeStr,
        });
      }
    } catch (err: any) {
      setBanner({
        type: 'warning',
        message: 'Detection notice: ' + (err.message || 'Failed to execute pattern analysis.'),
        timestamp: new Date().toLocaleTimeString(),
      });
    } finally {
      setIsDetecting(false);
    }
  };

  const handleSeedDemo = async () => {
    if (!currentWorkspace) return;
    setIsSeeding(true);
    try {
      const res = await recurringApi.seedDemo(currentWorkspace.id);
      const items = res.recurring_payments || [];
      setRecurring(items);
      setBanner({
        type: 'success',
        message: 'Successfully generated sample recurring obligations (AWS, Gusto Payroll, WeWork, GitHub, Stripe Retainer) and historical transactions.',
        timestamp: new Date().toLocaleTimeString(),
      });
    } catch (err: any) {
      alert('Failed to seed demo data: ' + (err.message || 'Unknown error'));
    } finally {
      setIsSeeding(false);
    }
  };

  const handleToggleStatus = async (item: RecurringPayment) => {
    if (!currentWorkspace) return;
    try {
      const res = await recurringApi.toggleStatus(currentWorkspace.id, item.id);
      setRecurring(res.recurring_payments || []);
    } catch (err: any) {
      alert('Failed to update status: ' + (err.message || 'Error'));
    }
  };

  const handleDelete = async (item: RecurringPayment) => {
    if (!currentWorkspace) return;
    if (!confirm(`Are you sure you want to delete recurring rule for "${item.merchant}"?`)) return;
    try {
      const res = await recurringApi.delete(currentWorkspace.id, item.id);
      setRecurring(res.recurring_payments || []);
    } catch (err: any) {
      alert('Failed to delete recurring rule: ' + (err.message || 'Error'));
    }
  };

  const handleCreateRecurring = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!currentWorkspace || !form.merchant || !form.amount) return;

    setIsSubmitting(true);
    try {
      const amount_minor = Math.round(parseFloat(form.amount) * 100);
      const res = await recurringApi.create(currentWorkspace.id, {
        merchant: form.merchant,
        description: form.description,
        amount_minor,
        frequency: form.frequency,
        type: form.type,
        category_name: form.category_name,
        next_date: form.next_date,
        currency: currency,
      });

      setRecurring(res.recurring_payments || []);
      setIsAddModalOpen(false);
      setForm({
        merchant: '',
        description: '',
        amount: '',
        frequency: 'monthly',
        type: 'expense',
        category_name: 'Software & Cloud Services',
        next_date: new Date(Date.now() + 30 * 24 * 60 * 60 * 1000).toISOString().split('T')[0],
      });
      setBanner({
        type: 'success',
        message: `Successfully added recurring obligation for "${form.merchant}".`,
        timestamp: new Date().toLocaleTimeString(),
      });
    } catch (err: any) {
      alert('Failed to create recurring payment: ' + (err.message || 'Error'));
    } finally {
      setIsSubmitting(false);
    }
  };

  // KPI Calculations
  const stats = useMemo(() => {
    let monthlyExpenses = 0;
    let monthlyIncome = 0;
    let activeCount = 0;

    for (const r of recurring) {
      if (r.status === 'paused') continue;
      activeCount++;

      // Normalize amount to monthly equivalent
      let multiplier = 1;
      if (r.frequency === 'weekly') multiplier = 52 / 12;
      else if (r.frequency === 'bi-weekly') multiplier = 26 / 12;
      else if (r.frequency === 'quarterly') multiplier = 1 / 3;
      else if (r.frequency === 'yearly') multiplier = 1 / 12;

      const monthlyVal = (r.amount_minor || 0) * multiplier;
      if (r.type === 'income') {
        monthlyIncome += monthlyVal;
      } else {
        monthlyExpenses += monthlyVal;
      }
    }

    return {
      monthlyExpenses: Math.round(monthlyExpenses),
      monthlyIncome: Math.round(monthlyIncome),
      netMonthly: Math.round(monthlyIncome - monthlyExpenses),
      activeCount,
      totalCount: recurring.length,
    };
  }, [recurring]);

  // Filtered List
  const filteredList = useMemo(() => {
    return recurring.filter((item) => {
      if (activeTab === 'expense' && item.type !== 'expense') return false;
      if (activeTab === 'income' && item.type !== 'income') return false;
      if (searchQuery.trim()) {
        const q = searchQuery.toLowerCase();
        const m = (item.merchant || '').toLowerCase();
        const d = (item.description || '').toLowerCase();
        const c = (item.category_name || '').toLowerCase();
        if (!m.includes(q) && !d.includes(q) && !c.includes(q)) return false;
      }
      return true;
    });
  }, [recurring, activeTab, searchQuery]);

  if (isLoading || wsLoading) return <LoadingSpinner />;
  if (error) return <ErrorState message={error} onRetry={fetchRecurring} />;

  const columns: Column[] = [
    {
      key: 'merchant',
      header: 'Vendor / Description',
      render: (item: any) => (
        <div>
          <div className="flex items-center gap-2">
            <span className="font-semibold text-stone-900">{item.merchant}</span>
            {item.category_name && (
              <span className="text-[11px] px-1.5 py-0.5 bg-stone-100 text-stone-600 rounded">
                {item.category_name}
              </span>
            )}
          </div>
          {item.description && <p className="text-xs text-stone-500 mt-0.5">{item.description}</p>}
        </div>
      ),
    },
    {
      key: 'type',
      header: 'Flow Type',
      render: (item: any) => (
        <span className={`inline-flex items-center gap-1 text-xs font-medium px-2 py-0.5 rounded-full ${
          item.type === 'income' ? 'bg-teal-50 text-teal-700 border border-teal-200' : 'bg-stone-100 text-stone-700'
        }`}>
          {item.type === 'income' ? <ArrowUpRight className="w-3 h-3 text-teal-600" /> : <ArrowDownRight className="w-3 h-3 text-rose-500" />}
          <span className="capitalize">{item.type || 'expense'}</span>
        </span>
      ),
    },
    {
      key: 'amount',
      header: 'Typical Amount',
      render: (item: any) => (
        <span className={`font-semibold font-mono text-sm ${item.type === 'income' ? 'text-teal-700' : 'text-stone-900'}`}>
          {item.type === 'income' ? '+' : ''}{formatConverted(item.amount_minor, item.currency)}
        </span>
      ),
    },
    {
      key: 'frequency',
      header: 'Cadence',
      render: (item: any) => (
        <span className="capitalize text-stone-700 text-xs px-2 py-1 bg-stone-50 border border-stone-200 rounded font-medium">
          {item.frequency}
        </span>
      ),
    },
    {
      key: 'next_date',
      header: 'Next Expected Charge',
      render: (item: any) => (
        <div className="flex items-center gap-1.5 text-stone-600 text-sm">
          <Calendar className="w-3.5 h-3.5 text-stone-400" />
          <span>{item.next_date ? new Date(item.next_date).toLocaleDateString() : 'N/A'}</span>
        </div>
      ),
    },
    {
      key: 'status',
      header: 'Status',
      render: (item: any) => (
        <span className={`inline-flex items-center gap-1 text-xs px-2 py-0.5 rounded-full font-medium ${
          item.status === 'paused' ? 'bg-amber-50 text-amber-700 border border-amber-200' : 'bg-emerald-50 text-emerald-700 border border-emerald-200'
        }`}>
          <span className={`w-1.5 h-1.5 rounded-full ${item.status === 'paused' ? 'bg-amber-500' : 'bg-emerald-500'}`} />
          <span className="capitalize">{item.status || 'active'}</span>
        </span>
      ),
    },
    {
      key: 'confidence',
      header: 'Confidence',
      render: (item: any) => {
        const pct = Math.round((item.confidence || 0.95) * 100);
        return (
          <Badge variant={pct >= 90 ? 'success' : 'info'}>
            {pct}% match
          </Badge>
        );
      },
    },
    {
      key: 'actions',
      header: '',
      render: (item: any) => (
        <div className="flex items-center justify-end gap-1.5">
          <button
            type="button"
            onClick={() => handleToggleStatus(item)}
            className="p-1.5 text-stone-400 hover:text-stone-700 hover:bg-stone-100 rounded transition-colors"
            title={item.status === 'paused' ? 'Resume recurring schedule' : 'Pause recurring schedule'}
          >
            {item.status === 'paused' ? <Play className="w-3.5 h-3.5 text-teal-600" /> : <Pause className="w-3.5 h-3.5" />}
          </button>
          <button
            type="button"
            onClick={() => handleDelete(item)}
            className="p-1.5 text-stone-400 hover:text-rose-600 hover:bg-rose-50 rounded transition-colors"
            title="Delete recurring rule"
          >
            <Trash2 className="w-3.5 h-3.5" />
          </button>
        </div>
      ),
    },
  ];

  return (
    <div className="space-y-6">
      {/* Header and Actions */}
      <div className="flex flex-col sm:flex-row sm:justify-between sm:items-center gap-4">
        <div>
          <h1 className="text-2xl font-bold text-stone-900 font-serif">Recurring Obligations</h1>
          <p className="text-sm text-stone-500 mt-1">
            Statistical pattern-based detection of subscription software, payroll cycles, and lease schedules.
          </p>
        </div>
        <div className="flex items-center gap-2.5 flex-wrap">
          {recurring.length === 0 && (
            <Button
              onClick={handleSeedDemo}
              disabled={isSeeding || isDetecting}
              variant="outline"
              className="flex items-center gap-1.5 text-stone-700 text-xs sm:text-sm"
            >
              <Sparkles className="w-4 h-4 text-teal-600" />
              <span>{isSeeding ? 'Generating Sample Data...' : 'Load Demo Obligations'}</span>
            </Button>
          )}

          <Button
            onClick={() => setIsAddModalOpen(true)}
            variant="outline"
            className="flex items-center gap-1.5 text-xs sm:text-sm"
          >
            <Plus className="w-4 h-4 text-stone-600" />
            <span>Add Recurring</span>
          </Button>

          <Button
            onClick={handleDetect}
            disabled={isDetecting || isSeeding}
            variant="primary"
            className="flex items-center gap-2 text-xs sm:text-sm shadow-xs"
          >
            <RefreshCw className={`h-4 w-4 ${isDetecting ? 'animate-spin' : ''}`} />
            <span>{isDetecting ? 'Analyzing Intervals...' : 'Detect Recurring'}</span>
          </Button>
        </div>
      </div>

      {/* Detection Status Banner */}
      {banner && (
        <div className={`p-4 rounded-lg border flex items-start justify-between gap-3 transition-all ${
          banner.type === 'success'
            ? 'bg-teal-50/70 border-teal-200 text-teal-900'
            : banner.type === 'warning'
            ? 'bg-amber-50/80 border-amber-200 text-amber-900'
            : 'bg-stone-50 border-stone-200 text-stone-800'
        }`}>
          <div className="flex items-start gap-3">
            {banner.type === 'success' && <CheckCircle2 className="w-5 h-5 text-teal-600 shrink-0 mt-0.5" />}
            {banner.type === 'warning' && <AlertTriangle className="w-5 h-5 text-amber-600 shrink-0 mt-0.5" />}
            {banner.type === 'info' && <AlertCircle className="w-5 h-5 text-stone-500 shrink-0 mt-0.5" />}
            <div>
              <p className="text-sm font-medium leading-relaxed">{banner.message}</p>
              <p className="text-[11px] opacity-70 mt-1">Processed at {banner.timestamp}</p>
            </div>
          </div>
          <button
            type="button"
            onClick={() => setBanner(null)}
            className="p-1 hover:bg-black/5 rounded transition-colors text-stone-500 hover:text-stone-800"
          >
            <X className="w-4 h-4" />
          </button>
        </div>
      )}

      {/* Top Metric Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <Card className="p-5">
          <p className="text-xs font-semibold text-stone-500 uppercase tracking-wider">Monthly Recurring Spend</p>
          <p className="mt-2 text-2xl font-bold font-mono text-stone-900">
            {formatConverted(stats.monthlyExpenses)}
          </p>
          <span className="text-[11px] text-stone-400 mt-1 block">Normalized monthly burn rate</span>
        </Card>

        <Card className="p-5">
          <p className="text-xs font-semibold text-stone-500 uppercase tracking-wider">Monthly Recurring Revenue</p>
          <p className="mt-2 text-2xl font-bold font-mono text-teal-700">
            {formatConverted(stats.monthlyIncome)}
          </p>
          <span className="text-[11px] text-stone-400 mt-1 block">Predictable MRR retainer inflow</span>
        </Card>

        <Card className="p-5">
          <p className="text-xs font-semibold text-stone-500 uppercase tracking-wider">Net Monthly Run Rate</p>
          <p className={`mt-2 text-2xl font-bold font-mono ${stats.netMonthly >= 0 ? 'text-teal-700' : 'text-rose-600'}`}>
            {stats.netMonthly >= 0 ? '+' : ''}{formatConverted(stats.netMonthly)}
          </p>
          <span className="text-[11px] text-stone-400 mt-1 block">Recurring net cash trajectory</span>
        </Card>

        <Card className="p-5">
          <p className="text-xs font-semibold text-stone-500 uppercase tracking-wider">Tracked Obligations</p>
          <div className="mt-2 flex items-baseline gap-2">
            <span className="text-2xl font-bold font-mono text-stone-900">{stats.activeCount}</span>
            <span className="text-xs text-stone-500">active ({stats.totalCount} total)</span>
          </div>
          <span className="text-[11px] text-stone-400 mt-1 block">SaaS, payroll, leases & clients</span>
        </Card>
      </div>

      {/* Search and Filters Bar */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        {/* Flow Tabs */}
        <div className="flex items-center gap-1 bg-stone-100 p-1 rounded-lg border border-stone-200">
          <button
            type="button"
            onClick={() => setActiveTab('all')}
            className={`px-3 py-1.5 text-xs font-medium rounded-md transition-all ${
              activeTab === 'all' ? 'bg-white text-stone-900 font-semibold shadow-xs' : 'text-stone-600 hover:text-stone-900'
            }`}
          >
            All Obligations ({recurring.length})
          </button>
          <button
            type="button"
            onClick={() => setActiveTab('expense')}
            className={`px-3 py-1.5 text-xs font-medium rounded-md transition-all ${
              activeTab === 'expense' ? 'bg-white text-stone-900 font-semibold shadow-xs' : 'text-stone-600 hover:text-stone-900'
            }`}
          >
            Expenses ({recurring.filter(r => r.type !== 'income').length})
          </button>
          <button
            type="button"
            onClick={() => setActiveTab('income')}
            className={`px-3 py-1.5 text-xs font-medium rounded-md transition-all ${
              activeTab === 'income' ? 'bg-white text-stone-900 font-semibold shadow-xs' : 'text-stone-600 hover:text-stone-900'
            }`}
          >
            Income ({recurring.filter(r => r.type === 'income').length})
          </button>
        </div>

        {/* Search Input */}
        <div className="relative w-full sm:w-64">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-stone-400" />
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Filter merchant or category..."
            className="w-full pl-9 pr-3 py-1.5 bg-white border border-stone-200 rounded-lg text-xs md:text-sm focus:outline-none focus:ring-1 focus:ring-teal-600 focus:border-teal-600"
          />
        </div>
      </div>

      {/* Main Table / Empty State Card */}
      <Card>
        {recurring.length === 0 ? (
          <div className="py-12 px-6 text-center">
            <div className="w-12 h-12 bg-stone-100 rounded-full flex items-center justify-center mx-auto mb-4 text-stone-500">
              <Repeat className="w-6 h-6 text-teal-700" />
            </div>
            <h3 className="text-base font-semibold text-stone-900 font-serif">No Recurring Transactions Detected</h3>
            <p className="text-sm text-stone-500 max-w-md mx-auto mt-1 mb-6">
              Run automatic interval pattern detection across your transaction history, load pre-configured demo obligations, or add recurring schedules manually.
            </p>
            <div className="flex flex-wrap items-center justify-center gap-3">
              <Button onClick={handleDetect} disabled={isDetecting} variant="primary" className="flex items-center gap-2">
                <RefreshCw className={`h-4 w-4 ${isDetecting ? 'animate-spin' : ''}`} />
                <span>{isDetecting ? 'Analyzing...' : 'Detect Recurring Now'}</span>
              </Button>
              <Button onClick={handleSeedDemo} disabled={isSeeding} variant="outline" className="flex items-center gap-2">
                <Sparkles className="w-4 h-4 text-teal-600" />
                <span>{isSeeding ? 'Loading...' : 'Load Demo Obligations'}</span>
              </Button>
              <Button onClick={() => setIsAddModalOpen(true)} variant="outline" className="flex items-center gap-1.5">
                <Plus className="w-4 h-4" />
                <span>Add Manually</span>
              </Button>
            </div>
          </div>
        ) : filteredList.length === 0 ? (
          <div className="py-12 text-center text-stone-500 text-sm">
            No recurring items matching your filter "{searchQuery}".
          </div>
        ) : (
          <Table columns={columns} data={filteredList} />
        )}
      </Card>

      {/* Manual Add Modal */}
      <Modal
        isOpen={isAddModalOpen}
        onClose={() => setIsAddModalOpen(false)}
        title="Create Recurring Obligation Schedule"
      >
        <form onSubmit={handleCreateRecurring} className="space-y-4">
          <Input
            label="Vendor / Counterparty Name"
            value={form.merchant}
            onChange={(e) => setForm({ ...form, merchant: e.target.value })}
            placeholder="e.g. Google Cloud, Slack, Office Lease"
            required
          />

          <Input
            label="Description / Purpose (Optional)"
            value={form.description}
            onChange={(e) => setForm({ ...form, description: e.target.value })}
            placeholder="e.g. Team Workspace Subscription"
          />

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-sm font-medium text-stone-700 mb-1.5">
                Payment Type
              </label>
              <select
                value={form.type}
                onChange={(e) => setForm({ ...form, type: e.target.value })}
                className="w-full p-2 border border-stone-300 rounded-md text-sm focus:outline-none focus:ring-1 focus:ring-teal-600"
              >
                <option value="expense">Expense (Outflow)</option>
                <option value="income">Income (Inflow)</option>
              </select>
            </div>

            <Input
              label={`Amount (${currency})`}
              type="number"
              step="0.01"
              value={form.amount}
              onChange={(e) => setForm({ ...form, amount: e.target.value })}
              placeholder="e.g. 150.00"
              required
            />
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-sm font-medium text-stone-700 mb-1.5">
                Cadence / Frequency
              </label>
              <select
                value={form.frequency}
                onChange={(e) => setForm({ ...form, frequency: e.target.value })}
                className="w-full p-2 border border-stone-300 rounded-md text-sm focus:outline-none focus:ring-1 focus:ring-teal-600"
              >
                <option value="weekly">Weekly</option>
                <option value="bi-weekly">Bi-Weekly</option>
                <option value="monthly">Monthly</option>
                <option value="quarterly">Quarterly</option>
                <option value="yearly">Yearly</option>
              </select>
            </div>

            <Input
              label="Next Expected Date"
              type="date"
              value={form.next_date}
              onChange={(e) => setForm({ ...form, next_date: e.target.value })}
              required
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-stone-700 mb-1.5">
              Category
            </label>
            <select
              value={form.category_name}
              onChange={(e) => setForm({ ...form, category_name: e.target.value })}
              className="w-full p-2 border border-stone-300 rounded-md text-sm focus:outline-none focus:ring-1 focus:ring-teal-600"
            >
              <option value="Software & Cloud Services">Software & Cloud Services</option>
              <option value="Payroll & Wages">Payroll & Wages</option>
              <option value="Rent & Facilities">Rent & Facilities</option>
              <option value="Marketing & Advertising">Marketing & Advertising</option>
              <option value="Professional & Legal">Professional & Legal</option>
              <option value="Client Revenue">Client Revenue</option>
              <option value="Miscellaneous">Miscellaneous</option>
            </select>
          </div>

          <div className="pt-3 flex justify-end gap-2 border-t border-stone-100">
            <Button type="button" variant="outline" onClick={() => setIsAddModalOpen(false)}>
              Cancel
            </Button>
            <Button type="submit" variant="primary" disabled={isSubmitting}>
              {isSubmitting ? 'Saving...' : 'Save Recurring Rule'}
            </Button>
          </div>
        </form>
      </Modal>
    </div>
  );
}

export default RecurringPage;
