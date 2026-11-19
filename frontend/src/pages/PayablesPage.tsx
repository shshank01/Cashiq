import React, { useState, useEffect } from 'react';
import { useWorkspace } from '../contexts/WorkspaceContext';
import { payablesApi } from '../api/payables';
import { formatMoney } from '../utils/format';
import { Button } from '../components/ui/Button';
import { Card } from '../components/ui/Card';
import { Input } from '../components/ui/Input';
import { Modal } from '../components/ui/Modal';
import { LoadingSpinner } from '../components/ui/LoadingSpinner';
import { ErrorState } from '../components/ui/ErrorState';
import { EmptyState } from '../components/ui/EmptyState';
import { Table, Column } from '../components/ui/Table';
import { StatusBadge } from '../components/ui/StatusBadge';
import { ArrowUpRight, Plus, Check, Clock, AlertTriangle } from 'lucide-react';

export function PayablesPage() {
  const { currentWorkspace, currency: currencyFromContext, isLoading: wsLoading, formatConverted } = useWorkspace();
  const [payables, setPayables] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [summary, setSummary] = useState({ total_minor: 0, upcoming_minor: 0, overdue_minor: 0, count: 0 });
  const [isAddModalOpen, setIsAddModalOpen] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [form, setForm] = useState({
    vendor: '',
    description: '',
    amount: '',
    due_date: new Date().toISOString().split('T')[0],
  });

  const loadPayables = async () => {
    if (!currentWorkspace) return;
    setLoading(true);
    setError(null);
    try {
      const data = await payablesApi.list(currentWorkspace.id);
      setPayables(data.payables || []);
      if (data.summary) {
        setSummary(data.summary);
      }
    } catch (err: any) {
      setError(err.message || 'Failed to load payables');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (currentWorkspace) {
      loadPayables();
    } else if (!wsLoading) {
      setLoading(false);
    }
  }, [currentWorkspace, wsLoading]);

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!currentWorkspace || !form.vendor || !form.amount) return;
    setIsSubmitting(true);
    try {
      const amount_minor = Math.round(parseFloat(form.amount) * 100);
      await payablesApi.create(currentWorkspace.id, {
        vendor: form.vendor,
        description: form.description,
        amount_minor,
        currency: currentWorkspace.currency || 'USD',
        due_date: new Date(form.due_date).toISOString(),
      });
      setIsAddModalOpen(false);
      setForm({ vendor: '', description: '', amount: '', due_date: new Date().toISOString().split('T')[0] });
      await loadPayables();
    } catch (err: any) {
      alert(err.message || 'Failed to create bill');
    } finally {
      setIsSubmitting(false);
    }
  };

  if (loading || wsLoading) return <LoadingSpinner />;
  if (error) return <ErrorState message={error} onRetry={loadPayables} />;

  const currency = currencyFromContext || currentWorkspace?.currency || 'USD';

  const columns: Column[] = [
    {
      key: 'vendor',
      header: 'Vendor / Payee',
      render: (p: any) => (
        <div>
          <span className="font-medium text-stone-900">{p.vendor}</span>
          {p.description && <p className="text-xs text-stone-500">{p.description}</p>}
        </div>
      ),
    },
    {
      key: 'due_date',
      header: 'Due Date',
      render: (p: any) => (
        <span className="text-stone-700 text-sm">
          {new Date(p.due_date).toLocaleDateString()}
        </span>
      ),
    },
    {
      key: 'amount',
      header: 'Amount',
      render: (p: any) => (
        <span className="font-semibold text-stone-900">
          {formatConverted(p.amount_minor, p.currency)}
        </span>
      ),
    },
    {
      key: 'status',
      header: 'Status',
      render: (p: any) => <StatusBadge status={p.status} />,
    },
  ];

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-stone-900 font-serif">Accounts Payable</h1>
          <p className="text-sm text-stone-500 mt-1">
            Track money the business needs to pay, upcoming obligations, and overdue vendor invoices.
          </p>
        </div>
        <Button onClick={() => setIsAddModalOpen(true)} className="flex items-center gap-2">
          <Plus className="w-4 h-4" />
          Add Payable
        </Button>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <Card className="p-5">
          <div className="flex items-center justify-between">
            <h3 className="text-xs font-semibold text-stone-500 uppercase tracking-wider">Total Outstanding</h3>
            <Clock className="w-4 h-4 text-stone-400" />
          </div>
          <p className="mt-2 text-2xl font-bold text-stone-900">
            {formatConverted(summary.total_minor)}
          </p>
        </Card>
        <Card className="p-5">
          <div className="flex items-center justify-between">
            <h3 className="text-xs font-semibold text-stone-500 uppercase tracking-wider">Upcoming Bills</h3>
            <ArrowUpRight className="w-4 h-4 text-stone-400" />
          </div>
          <p className="mt-2 text-2xl font-bold text-teal-700">
            {formatConverted(summary.upcoming_minor)}
          </p>
        </Card>
        <Card className="p-5">
          <div className="flex items-center justify-between">
            <h3 className="text-xs font-semibold text-stone-500 uppercase tracking-wider">Overdue</h3>
            <AlertTriangle className="w-4 h-4 text-rose-500" />
          </div>
          <p className="mt-2 text-2xl font-bold text-rose-600">
            {formatConverted(summary.overdue_minor)}
          </p>
        </Card>
      </div>

      <Card>
        {payables.length === 0 ? (
          <EmptyState
            icon={ArrowUpRight}
            title="No Payables Logged"
            description="You have no outstanding vendor invoices or accounts payable."
            actionLabel="Add Payable"
            onAction={() => setIsAddModalOpen(true)}
          />
        ) : (
          <Table columns={columns} data={payables} />
        )}
      </Card>

      <Modal
        isOpen={isAddModalOpen}
        onClose={() => setIsAddModalOpen(false)}
        title="Add Accounts Payable Bill"
      >
        <form onSubmit={handleCreate} className="space-y-4">
          <Input
            label="Vendor / Payee Name *"
            placeholder="e.g. AWS, WeWork, Law Firm"
            value={form.vendor}
            onChange={(e) => setForm({ ...form, vendor: e.target.value })}
            required
          />
          <Input
            label="Description"
            placeholder="e.g. Cloud Compute March Statement"
            value={form.description}
            onChange={(e) => setForm({ ...form, description: e.target.value })}
          />
          <Input
            label="Amount (in dollars) *"
            type="number"
            step="0.01"
            placeholder="0.00"
            value={form.amount}
            onChange={(e) => setForm({ ...form, amount: e.target.value })}
            required
          />
          <Input
            label="Due Date *"
            type="date"
            value={form.due_date}
            onChange={(e) => setForm({ ...form, due_date: e.target.value })}
            required
          />
          <div className="flex justify-end gap-3 pt-3 border-t border-stone-100">
            <Button variant="outline" type="button" onClick={() => setIsAddModalOpen(false)}>
              Cancel
            </Button>
            <Button variant="primary" type="submit" isLoading={isSubmitting}>
              Save Payable
            </Button>
          </div>
        </form>
      </Modal>
    </div>
  );
}

export default PayablesPage;
