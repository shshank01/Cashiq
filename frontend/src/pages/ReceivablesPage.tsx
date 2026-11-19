import React, { useState, useEffect } from 'react';
import { useWorkspace } from '../contexts/WorkspaceContext';
import { receivablesApi } from '../api/payables';
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
import { ArrowDownLeft, Plus, Clock, AlertTriangle } from 'lucide-react';

export function ReceivablesPage() {
  const { currentWorkspace, currency: currencyFromContext, isLoading: wsLoading, formatConverted } = useWorkspace();
  const [receivables, setReceivables] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [summary, setSummary] = useState({ total_minor: 0, upcoming_minor: 0, overdue_minor: 0, count: 0 });
  const [isAddModalOpen, setIsAddModalOpen] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [form, setForm] = useState({
    client: '',
    description: '',
    amount: '',
    due_date: new Date().toISOString().split('T')[0],
  });

  const loadReceivables = async () => {
    if (!currentWorkspace) return;
    setLoading(true);
    setError(null);
    try {
      const data = await receivablesApi.list(currentWorkspace.id);
      setReceivables(data.receivables || []);
      if (data.summary) {
        setSummary(data.summary);
      }
    } catch (err: any) {
      setError(err.message || 'Failed to load receivables');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (currentWorkspace) {
      loadReceivables();
    } else if (!wsLoading) {
      setLoading(false);
    }
  }, [currentWorkspace, wsLoading]);

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!currentWorkspace || !form.client || !form.amount) return;
    setIsSubmitting(true);
    try {
      const amount_minor = Math.round(parseFloat(form.amount) * 100);
      await receivablesApi.create(currentWorkspace.id, {
        client: form.client,
        description: form.description,
        amount_minor,
        currency: currentWorkspace.currency || 'USD',
        due_date: new Date(form.due_date).toISOString(),
      });
      setIsAddModalOpen(false);
      setForm({ client: '', description: '', amount: '', due_date: new Date().toISOString().split('T')[0] });
      await loadReceivables();
    } catch (err: any) {
      alert(err.message || 'Failed to create invoice');
    } finally {
      setIsSubmitting(false);
    }
  };

  if (loading || wsLoading) return <LoadingSpinner />;
  if (error) return <ErrorState message={error} onRetry={loadReceivables} />;

  const currency = currencyFromContext || currentWorkspace?.currency || 'USD';

  const columns: Column[] = [
    {
      key: 'client',
      header: 'Client / Debtor',
      render: (r: any) => (
        <div>
          <span className="font-medium text-stone-900">{r.client}</span>
          {r.description && <p className="text-xs text-stone-500">{r.description}</p>}
        </div>
      ),
    },
    {
      key: 'due_date',
      header: 'Expected Payment Date',
      render: (r: any) => (
        <span className="text-stone-700 text-sm">
          {new Date(r.due_date).toLocaleDateString()}
        </span>
      ),
    },
    {
      key: 'amount',
      header: 'Amount Expected',
      render: (r: any) => (
        <span className="font-semibold text-stone-900">
          {formatConverted(r.amount_minor, r.currency)}
        </span>
      ),
    },
    {
      key: 'status',
      header: 'Status',
      render: (r: any) => <StatusBadge status={r.status} />,
    },
  ];

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-stone-900 font-serif">Accounts Receivable</h1>
          <p className="text-sm text-stone-500 mt-1">
            Track money the business expects to receive, customer billings, and overdue invoices.
          </p>
        </div>
        <Button onClick={() => setIsAddModalOpen(true)} className="flex items-center gap-2">
          <Plus className="w-4 h-4" />
          Add Receivable
        </Button>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <Card className="p-5">
          <div className="flex items-center justify-between">
            <h3 className="text-xs font-semibold text-stone-500 uppercase tracking-wider">Total Expected</h3>
            <Clock className="w-4 h-4 text-stone-400" />
          </div>
          <p className="mt-2 text-2xl font-bold text-stone-900">
            {formatConverted(summary.total_minor)}
          </p>
        </Card>
        <Card className="p-5">
          <div className="flex items-center justify-between">
            <h3 className="text-xs font-semibold text-stone-500 uppercase tracking-wider">Upcoming Inflows</h3>
            <ArrowDownLeft className="w-4 h-4 text-stone-400" />
          </div>
          <p className="mt-2 text-2xl font-bold text-teal-700">
            {formatConverted(summary.upcoming_minor)}
          </p>
        </Card>
        <Card className="p-5">
          <div className="flex items-center justify-between">
            <h3 className="text-xs font-semibold text-stone-500 uppercase tracking-wider">Past Due Invoices</h3>
            <AlertTriangle className="w-4 h-4 text-rose-500" />
          </div>
          <p className="mt-2 text-2xl font-bold text-rose-600">
            {formatConverted(summary.overdue_minor)}
          </p>
        </Card>
      </div>

      <Card>
        {receivables.length === 0 ? (
          <EmptyState
            icon={ArrowDownLeft}
            title="No Receivables"
            description="You have no outstanding client invoices or expected payments logged."
            actionLabel="Add Receivable"
            onAction={() => setIsAddModalOpen(true)}
          />
        ) : (
          <Table columns={columns} data={receivables} />
        )}
      </Card>

      <Modal
        isOpen={isAddModalOpen}
        onClose={() => setIsAddModalOpen(false)}
        title="Add Accounts Receivable Invoice"
      >
        <form onSubmit={handleCreate} className="space-y-4">
          <Input
            label="Client / Customer Name *"
            placeholder="e.g. Acme Corp, Enterprise Partner"
            value={form.client}
            onChange={(e) => setForm({ ...form, client: e.target.value })}
            required
          />
          <Input
            label="Description"
            placeholder="e.g. Enterprise License Q4 Inflow"
            value={form.description}
            onChange={(e) => setForm({ ...form, description: e.target.value })}
          />
          <Input
            label="Amount Expected (in dollars) *"
            type="number"
            step="0.01"
            placeholder="0.00"
            value={form.amount}
            onChange={(e) => setForm({ ...form, amount: e.target.value })}
            required
          />
          <Input
            label="Payment Due Date *"
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
              Save Receivable
            </Button>
          </div>
        </form>
      </Modal>
    </div>
  );
}

export default ReceivablesPage;
