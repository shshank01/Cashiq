import React, { useEffect, useState, useRef } from 'react';
import { useWorkspace } from '../contexts/WorkspaceContext';
import { transactionsApi } from '../api/transactions';
import { documentsApi } from '../api/documents';
import { formatMoney } from '../utils/format';
import { Transaction, MLStatusResponse } from '../types';
import Table, { Column } from '../components/ui/Table';
import Button from '../components/ui/Button';
import Input from '../components/ui/Input';
import Select from '../components/ui/Select';
import Modal from '../components/ui/Modal';
import LoadingSpinner from '../components/ui/LoadingSpinner';
import ErrorState from '../components/ui/ErrorState';
import Pagination from '../components/ui/Pagination';
import StatusBadge from '../components/ui/StatusBadge';
import Badge from '../components/ui/Badge';
import Card from '../components/ui/Card';
import { 
  Plus, 
  Search, 
  Edit2, 
  Trash2, 
  Check, 
  AlertTriangle, 
  Upload, 
  FileText, 
  FileSpreadsheet, 
  FileCheck, 
  ArrowUpDown, 
  Filter, 
  CheckCircle2, 
  X,
  Brain,
  Activity,
  RefreshCw,
  Info,
  ShieldAlert,
  Sparkles
} from 'lucide-react';

const STANDARD_CATEGORIES = [
  "Software & Cloud Services",
  "Payroll & Wages",
  "Rent & Facilities",
  "Marketing & Advertising",
  "Professional & Legal",
  "Meals & Entertainment",
  "Office Supplies & Equipment",
  "Travel & Transportation",
  "Utilities & Telecom",
  "Taxes & Compliance",
  "Insurance",
  "Banking & Fees",
  "Equipment & Hardware",
  "Shipping & Logistics",
  "Inventory & Raw Materials",
  "Groceries & Ingredients",
  "Medical Supplies & Equipment",
  "Construction & Site Materials",
  "Personal & Household",
  "Client Revenue",
  "Loans & Financing",
  "Miscellaneous"
];

const ALERT_TYPE_LABELS: Record<string, { label: string; badgeClass: string }> = {
  operational_relevance: {
    label: 'Operational Relevance',
    badgeClass: 'bg-amber-50 text-amber-800 border-amber-300 hover:bg-amber-100',
  },
  merchant_category_mismatch: {
    label: 'Category Mismatch',
    badgeClass: 'bg-indigo-50 text-indigo-800 border-indigo-300 hover:bg-indigo-100',
  },
  amount_anomaly: {
    label: 'Unusual Amount',
    badgeClass: 'bg-rose-50 text-rose-700 border-rose-200 hover:bg-rose-100',
  },
  merchant_behavior: {
    label: 'Merchant Spike',
    badgeClass: 'bg-rose-50 text-rose-700 border-rose-200 hover:bg-rose-100',
  },
  frequency_timing: {
    label: 'Frequency Alert',
    badgeClass: 'bg-orange-50 text-orange-800 border-orange-300 hover:bg-orange-100',
  },
  multivariate: {
    label: 'Unusual Pattern',
    badgeClass: 'bg-rose-50 text-rose-700 border-rose-200 hover:bg-rose-100',
  },
};

export const TransactionsPage: React.FC = () => {
  const { currentWorkspace, currency: contextCurrency, formatConverted } = useWorkspace();
  const [transactions, setTransactions] = useState<Transaction[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  
  // Filters and pagination
  const [search, setSearch] = useState('');
  const [typeFilter, setTypeFilter] = useState('');
  const [categoryFilter, setCategoryFilter] = useState('');
  const [anomalySeverityFilter, setAnomalySeverityFilter] = useState('');
  const [sortBy, setSortBy] = useState('date');
  const [sortOrder, setSortOrder] = useState('desc');
  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);

  // Add / Edit Modal
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [editingTransaction, setEditingTransaction] = useState<Transaction | null>(null);
  const [form, setForm] = useState({
    description: '',
    merchant: '',
    amount: '',
    type: 'expense',
    category_name: '',
    date: new Date().toISOString().split('T')[0],
    notes: '',
  });

  // Category Confirmation Modal
  const [confirmCatModalOpen, setConfirmCatModalOpen] = useState(false);
  const [targetTx, setTargetTx] = useState<Transaction | null>(null);
  const [newCategoryName, setNewCategoryName] = useState('');

  // Anomaly Review & Adaptive Learning Modal
  const [anomalyModalOpen, setAnomalyModalOpen] = useState(false);
  const [selectedAnomalyTx, setSelectedAnomalyTx] = useState<Transaction | null>(null);
  const [anomalyFeedbackNote, setAnomalyFeedbackNote] = useState('');
  const [anomalyFeedbackCategory, setAnomalyFeedbackCategory] = useState('');
  const [isSubmittingFeedback, setIsSubmittingFeedback] = useState(false);

  // ML Status Modal
  const [mlStatusModalOpen, setMlStatusModalOpen] = useState(false);
  const [mlStatus, setMlStatus] = useState<MLStatusResponse | null>(null);
  const [isLoadingMLStatus, setIsLoadingMLStatus] = useState(false);
  const [isRetraining, setIsRetraining] = useState(false);
  const [isScanning, setIsScanning] = useState(false);

  // Document Import Modal
  const [isImportModalOpen, setIsImportModalOpen] = useState(false);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [isUploading, setIsUploading] = useState(false);
  const [importResult, setImportResult] = useState<{
    document_id: string;
    filename: string;
    file_type?: string;
    review_required_count?: number;
    validation_failed_count?: number;
    cache_hit?: boolean;
    processing_ms?: number;
    extraction_metadata?: any;
    drafts: any[];
  } | null>(null);
  const [selectedDraftIndices, setSelectedDraftIndices] = useState<number[]>([]);
  const [isConfirmingDrafts, setIsConfirmingDrafts] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const fetchTransactions = async () => {
    if (!currentWorkspace) return;
    setIsLoading(true);
    setError(null);
    try {
      const response = await transactionsApi.list(currentWorkspace.id, {
        page,
        per_page: 15,
        search: search || undefined,
        type: typeFilter || undefined,
        category: categoryFilter || undefined,
        sort_by: sortBy,
        sort_order: sortOrder,
      });
      setTransactions(response.transactions || (response as any).data || []);
      setTotalPages(response.total_pages || 1);
    } catch (err: any) {
      setError(err.message || 'Failed to load transactions');
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    fetchTransactions();
  }, [currentWorkspace, page, search, typeFilter, categoryFilter, sortBy, sortOrder]);

  const handleOpenAddModal = () => {
    setEditingTransaction(null);
    setForm({
      description: '',
      merchant: '',
      amount: '',
      type: 'expense',
      category_name: '',
      date: new Date().toISOString().split('T')[0],
      notes: '',
    });
    setIsModalOpen(true);
  };

  const handleOpenEditModal = (tx: Transaction) => {
    setEditingTransaction(tx);
    setForm({
      description: tx.description || '',
      merchant: tx.merchant || '',
      amount: (tx.amount_minor / 100).toFixed(2),
      type: tx.type || 'expense',
      category_name: tx.category_name || '',
      date: tx.date ? new Date(tx.date).toISOString().split('T')[0] : '',
      notes: tx.notes || '',
    });
    setIsModalOpen(true);
  };

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!currentWorkspace || !form.amount) return;
    try {
      const amount_minor = Math.round(parseFloat(form.amount) * 100);
      if (editingTransaction) {
        await transactionsApi.update(currentWorkspace.id, editingTransaction.id, {
          description: form.description,
          merchant: form.merchant,
          amount_minor,
          type: form.type,
          category_name: form.category_name,
          date: new Date(form.date).toISOString(),
          notes: form.notes,
        });
      } else {
        await transactionsApi.create(currentWorkspace.id, {
          description: form.description,
          merchant: form.merchant,
          amount_minor,
          type: form.type,
          category_name: form.category_name,
          date: new Date(form.date).toISOString(),
          currency: currentWorkspace.currency || 'USD',
          source: 'manual',
          notes: form.notes,
        });
      }
      setIsModalOpen(false);
      fetchTransactions();
    } catch (err: any) {
      alert('Error saving transaction: ' + (err.message || 'Failed'));
    }
  };

  const handleDelete = async (txId: string) => {
    if (!currentWorkspace) return;
    if (!window.confirm('Are you sure you want to delete this transaction from the verified ledger?')) return;
    try {
      await transactionsApi.delete(currentWorkspace.id, txId);
      fetchTransactions();
    } catch (err: any) {
      alert('Failed to delete transaction: ' + (err.message || 'Failed'));
    }
  };

  const handleOpenConfirmCatModal = (tx: Transaction) => {
    setTargetTx(tx);
    setNewCategoryName(tx.category_name || 'Miscellaneous');
    setConfirmCatModalOpen(true);
  };

  const handleSaveCategoryConfirmation = async () => {
    if (!currentWorkspace || !targetTx) return;
    try {
      await transactionsApi.confirmCategory(currentWorkspace.id, targetTx.id, newCategoryName);
      setConfirmCatModalOpen(false);
      fetchTransactions();
    } catch (err: any) {
      alert('Failed to update verified category: ' + err.message);
    }
  };

  // Anomaly Review & Feedback Handlers
  const handleOpenAnomalyModal = (tx: Transaction) => {
    setSelectedAnomalyTx(tx);
    setAnomalyFeedbackCategory(tx.category_name || 'Miscellaneous');
    setAnomalyFeedbackNote('');
    setAnomalyModalOpen(true);
  };

  const handleSubmitAnomalyFeedback = async (feedback: 'legitimate' | 'incorrect_category' | 'genuine_anomaly' | 'suspicious') => {
    if (!currentWorkspace || !selectedAnomalyTx) return;
    setIsSubmittingFeedback(true);
    try {
      await transactionsApi.submitAnomalyFeedback(
        currentWorkspace.id,
        selectedAnomalyTx.id,
        feedback,
        anomalyFeedbackNote || undefined,
        feedback === 'incorrect_category' || anomalyFeedbackCategory !== selectedAnomalyTx.category_name
          ? (anomalyFeedbackCategory || undefined)
          : undefined
      );
      setAnomalyModalOpen(false);
      setSelectedAnomalyTx(null);
      fetchTransactions();
    } catch (err: any) {
      alert('Error recording anomaly feedback: ' + (err.message || 'Failed'));
    } finally {
      setIsSubmittingFeedback(false);
    }
  };

  const handleFetchMLStatus = async () => {
    if (!currentWorkspace) return;
    setIsLoadingMLStatus(true);
    try {
      const data = await transactionsApi.getMLStatus(currentWorkspace.id);
      setMlStatus(data);
      setMlStatusModalOpen(true);
    } catch (err: any) {
      alert('Failed to fetch ML system status: ' + (err.message || 'Error'));
    } finally {
      setIsLoadingMLStatus(false);
    }
  };

  const handleTriggerRetrain = async () => {
    if (!currentWorkspace) return;
    setIsRetraining(true);
    try {
      const res = await transactionsApi.triggerRetraining(currentWorkspace.id);
      alert(`Model retraining completed! Active version: ${res.model_version || 'Updated'}`);
      handleFetchMLStatus();
      fetchTransactions();
    } catch (err: any) {
      alert('Retraining failed: ' + (err.message || 'Error'));
    } finally {
      setIsRetraining(false);
    }
  };

  const handleScanAnomalies = async () => {
    if (!currentWorkspace) return;
    setIsScanning(true);
    try {
      const res = await transactionsApi.scanAnomalies(currentWorkspace.id);
      alert(`Scanned ${res.total_scanned} transactions. Identified ${res.flagged_anomalies} anomalies.`);
      setMlStatusModalOpen(false);
      fetchTransactions();
    } catch (err: any) {
      alert('Scan failed: ' + (err.message || 'Error'));
    } finally {
      setIsScanning(false);
    }
  };

  // Document Ingestion Upload Handler
  const handleUploadDocument = async () => {
    if (!currentWorkspace || !selectedFile) return;
    setIsUploading(true);
    try {
      const res = await documentsApi.upload(currentWorkspace.id, selectedFile);
      const drafts = res.draft_transactions || [];
      setImportResult({
        document_id: res.document_id,
        filename: res.filename,
        file_type: res.file_type,
        review_required_count: res.review_required_count,
        validation_failed_count: res.validation_failed_count,
        cache_hit: res.cache_hit,
        processing_ms: res.processing_ms,
        extraction_metadata: res.extraction_metadata,
        drafts: drafts
      });
      setSelectedDraftIndices(drafts.map((_: any, idx: number) => idx));
    } catch (err: any) {
      alert('Document parsing failed: ' + (err.message || 'Error'));
    } finally {
      setIsUploading(false);
    }
  };

  // Confirm extracted drafts
  const handleConfirmSelectedDrafts = async () => {
    if (!currentWorkspace || !importResult) return;
    setIsConfirmingDrafts(true);
    try {
      const selectedDrafts = importResult.drafts.filter((_, idx) => selectedDraftIndices.includes(idx));
      await documentsApi.confirm(currentWorkspace.id, importResult.document_id, selectedDrafts);
      setIsImportModalOpen(false);
      setImportResult(null);
      setSelectedFile(null);
      fetchTransactions();
    } catch (err: any) {
      alert('Failed to confirm drafts: ' + (err.message || 'Error'));
    } finally {
      setIsConfirmingDrafts(false);
    }
  };

  const currency = contextCurrency || currentWorkspace?.currency || 'USD';

  const columns: Column[] = [
    {
      key: 'date',
      header: 'Date',
      render: (tx: Transaction) => (
        <span className="text-stone-700 text-xs font-mono">
          {new Date(tx.date).toLocaleDateString()}
        </span>
      ),
    },
    {
      key: 'description',
      header: 'Description & Merchant',
      render: (tx: Transaction) => (
        <div>
          <div className="flex items-center gap-1.5 flex-wrap">
            <span className="font-medium text-stone-900 text-xs sm:text-sm">{tx.description}</span>
            {tx.anomaly_feedback_status === 'legitimate' && (
              <button
                type="button"
                onClick={() => handleOpenAnomalyModal(tx)}
                title={tx.anomaly_reason || 'Verified legitimate by user. Baseline adapted.'}
                className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-semibold bg-emerald-50 text-emerald-700 border border-emerald-200 hover:bg-emerald-100 transition-colors cursor-pointer"
              >
                <CheckCircle2 className="w-3 h-3 text-emerald-600" />
                Verified Legitimate
              </button>
            )}
            {(tx.anomaly_feedback_status === 'suspicious' || tx.anomaly_feedback_status === 'genuine_anomaly') && (
              <button
                type="button"
                onClick={() => handleOpenAnomalyModal(tx)}
                title={tx.anomaly_reason || 'Confirmed genuine anomaly by user.'}
                className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-semibold bg-rose-100 text-rose-800 border border-rose-300 hover:bg-rose-200 transition-colors cursor-pointer"
              >
                <AlertTriangle className="w-3 h-3 text-rose-600" />
                Genuine Anomaly
              </button>
            )}
            {tx.is_anomaly && !['legitimate', 'suspicious', 'genuine_anomaly'].includes(tx.anomaly_feedback_status || '') && (() => {
              const alertKey = tx.anomaly_alert_type || tx.anomaly_explanation_details?.alert_type || 'multivariate';
              const meta = ALERT_TYPE_LABELS[alertKey] || ALERT_TYPE_LABELS.multivariate;
              return (
                <button
                  type="button"
                  onClick={() => handleOpenAnomalyModal(tx)}
                  title={tx.anomaly_reason || 'Click to review structured anomaly explanation & feedback'}
                  className={`inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-semibold border transition-colors cursor-pointer ${meta.badgeClass}`}
                >
                  <AlertTriangle className="w-3 h-3" />
                  <span>{meta.label}{tx.anomaly_severity ? ` (${tx.anomaly_severity})` : ''}</span>
                </button>
              );
            })()}
          </div>
          {tx.merchant && <p className="text-[11px] text-stone-500 font-sans mt-0.5">{tx.merchant}</p>}
        </div>
      ),
    },
    {
      key: 'category',
      header: 'Category & ML Confidence',
      render: (tx: Transaction) => (
        <div className="flex items-center gap-2">
          <Badge variant="default" className="text-xs">
            {tx.category_name || 'Miscellaneous'}
          </Badge>
          {tx.confidence !== null && tx.confidence !== undefined && (
            <span className="text-[11px] font-mono text-stone-400">
              {Math.round(tx.confidence * 100)}%
            </span>
          )}
          {(tx as any).review_required ? (
            <Button
              variant="outline"
              size="sm"
              onClick={() => handleOpenConfirmCatModal(tx)}
              className="py-0.5 px-2 text-[10px] text-teal-700 hover:bg-teal-50"
            >
              <Check className="w-3 h-3 mr-1" /> Confirm / Edit
            </Button>
          ) : (
            <button
              onClick={() => handleOpenConfirmCatModal(tx)}
              className="text-[10px] text-stone-400 hover:text-stone-700 underline"
            >
              change
            </button>
          )}
        </div>
      ),
    },
    {
      key: 'type',
      header: 'Type',
      render: (tx: Transaction) => (
        <StatusBadge status={tx.type === 'income' ? 'paid' : 'draft'}>
          {tx.type}
        </StatusBadge>
      ),
    },
    {
      key: 'amount',
      header: 'Amount',
      render: (tx: Transaction) => {
        const isExp = tx.type === 'expense';
        return (
          <span className={`font-semibold font-mono text-xs sm:text-sm ${isExp ? 'text-rose-600' : 'text-teal-700'}`}>
            {isExp ? '-' : '+'}
            {formatConverted(tx.amount_minor, tx.currency)}
          </span>
        );
      },
    },
    {
      key: 'actions',
      header: '',
      render: (tx: Transaction) => (
        <div className="flex items-center justify-end gap-1">
          <Button variant="ghost" size="sm" onClick={() => handleOpenEditModal(tx)} title="Edit transaction">
            <Edit2 className="w-3.5 h-3.5 text-stone-500" />
          </Button>
          <Button variant="ghost" size="sm" onClick={() => handleDelete(tx.id)} title="Delete transaction">
            <Trash2 className="w-3.5 h-3.5 text-rose-500 hover:text-rose-700" />
          </Button>
        </div>
      ),
    },
  ];

  return (
    <div className="space-y-6">
      {/* Top Header & Action Buttons */}
      <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4 border-b border-stone-200 pb-5">
        <div>
          <h1 className="text-2xl sm:text-3xl font-serif font-bold tracking-tight text-stone-900">
            Transactions Ledger
          </h1>
          <p className="text-xs sm:text-sm text-stone-500 mt-1">
            Standard chart of accounts, integer minor-unit balance storage, and TF-IDF supervised categorization.
          </p>
        </div>
        <div className="flex items-center gap-2.5">
          <Button 
            variant="outline" 
            onClick={handleFetchMLStatus}
            className="flex items-center gap-1.5 text-stone-700 hover:text-stone-900 border-stone-300"
            title="Inspect active ML models, anomaly contamination, drift detection and retraining status"
          >
            <Brain className="w-4 h-4 text-indigo-600" />
            ML Intelligence
          </Button>
          <Button 
            variant="outline" 
            onClick={() => { setImportResult(null); setIsImportModalOpen(true); }}
            className="flex items-center gap-1.5"
          >
            <Upload className="w-4 h-4 text-teal-700" />
            Import Statement / Receipt
          </Button>
          <Button onClick={handleOpenAddModal} className="flex items-center gap-1.5">
            <Plus className="w-4 h-4" />
            Add Transaction
          </Button>
        </div>
      </div>

      {/* Filters Toolbar */}
      <div className="bg-white p-4 rounded-xl border border-stone-200 shadow-xs space-y-3">
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-3">
          {/* Search Input */}
          <div className="relative">
            <Search className="w-4 h-4 text-stone-400 absolute left-3 top-3 pointer-events-none" />
            <Input
              type="text"
              placeholder="Search description, merchant, notes..."
              value={search}
              onChange={(e) => { setSearch(e.target.value); setPage(1); }}
              className="pl-9 w-full text-xs"
            />
          </div>

          {/* Type Filter */}
          <Select
            value={typeFilter}
            onChange={(e) => { setTypeFilter(e.target.value); setPage(1); }}
            options={[
              { value: '', label: 'All Types (In & Out)' },
              { value: 'income', label: 'Income Only' },
              { value: 'expense', label: 'Expenses Only' },
            ]}
          />

          {/* Category Filter */}
          <Select
            value={categoryFilter}
            onChange={(e) => { setCategoryFilter(e.target.value); setPage(1); }}
            options={[
              { value: '', label: 'All Categories' },
              ...STANDARD_CATEGORIES.map(c => ({ value: c, label: c }))
            ]}
          />

          {/* Anomaly Severity Filter */}
          <Select
            value={anomalySeverityFilter}
            onChange={(e) => { setAnomalySeverityFilter(e.target.value); setPage(1); }}
            options={[
              { value: '', label: 'All Severity & Normal' },
              { value: 'anomalies', label: 'All Flagged Anomalies' },
              { value: 'high', label: 'High / Critical Severity' },
              { value: 'medium', label: 'Medium Severity' },
              { value: 'low', label: 'Low Severity' },
            ]}
          />

          {/* Sort By */}
          <Select
            value={`${sortBy}:${sortOrder}`}
            onChange={(e) => {
              const [sb, so] = e.target.value.split(':');
              setSortBy(sb);
              setSortOrder(so);
              setPage(1);
            }}
            options={[
              { value: 'date:desc', label: 'Sort: Newest Date First' },
              { value: 'date:asc', label: 'Sort: Oldest Date First' },
              { value: 'amount:desc', label: 'Sort: Highest Amount First' },
              { value: 'amount:asc', label: 'Sort: Lowest Amount First' },
            ]}
          />
        </div>
      </div>

      {/* Transactions Data Table */}
      {error ? (
        <ErrorState message={error} onRetry={fetchTransactions} />
      ) : isLoading ? (
        <LoadingSpinner />
      ) : (
        <Card>
          <Table
            columns={columns}
            data={transactions.filter((tx) => {
              if (anomalySeverityFilter === 'anomalies') return tx.is_anomaly;
              if (anomalySeverityFilter === 'high') return tx.is_anomaly && (tx.anomaly_severity === 'critical' || tx.anomaly_severity === 'high');
              if (anomalySeverityFilter === 'medium') return tx.is_anomaly && tx.anomaly_severity === 'medium';
              if (anomalySeverityFilter === 'low') return tx.is_anomaly && tx.anomaly_severity === 'low';
              return true;
            })}
          />
          {totalPages > 1 && (
            <div className="p-4 border-t border-stone-100">
              <Pagination
                currentPage={page}
                totalPages={totalPages}
                onPageChange={setPage}
              />
            </div>
          )}
        </Card>
      )}

      {/* Add / Edit Transaction Modal */}
      <Modal
        isOpen={isModalOpen}
        onClose={() => setIsModalOpen(false)}
        title={editingTransaction ? 'Edit Ledger Transaction' : 'Record New Transaction'}
      >
        <form onSubmit={handleSave} className="space-y-4">
          <Input
            label="Transaction Description *"
            placeholder="e.g. AWS Cloud Compute monthly"
            value={form.description}
            onChange={(e) => setForm({ ...form, description: e.target.value })}
            required
          />
          <div className="grid grid-cols-2 gap-3">
            <Input
              label="Merchant / Counterparty"
              placeholder="e.g. Amazon Web Services"
              value={form.merchant}
              onChange={(e) => setForm({ ...form, merchant: e.target.value })}
            />
            <Select
              label="Type *"
              value={form.type}
              onChange={(e) => setForm({ ...form, type: e.target.value })}
              options={[
                { value: 'expense', label: 'Expense (Outflow)' },
                { value: 'income', label: 'Income (Inflow)' },
              ]}
            />
          </div>
          <div className="grid grid-cols-2 gap-3">
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
              label="Transaction Date *"
              type="date"
              value={form.date}
              onChange={(e) => setForm({ ...form, date: e.target.value })}
              required
            />
          </div>
          <div>
            <label className="block text-xs font-semibold text-stone-700 mb-1">
              Category (or leave empty for TF-IDF ML prediction)
            </label>
            <select
              value={form.category_name}
              onChange={(e) => setForm({ ...form, category_name: e.target.value })}
              className="w-full px-3 py-2 bg-stone-50 border border-stone-200 rounded-lg text-sm text-stone-800 focus:outline-none focus:ring-1 focus:ring-teal-600"
            >
              <option value="">-- Let ML Predict Category --</option>
              {STANDARD_CATEGORIES.map(c => (
                <option key={c} value={c}>{c}</option>
              ))}
            </select>
          </div>
          <Input
            label="Accounting Notes"
            placeholder="Optional internal reconciliation notes..."
            value={form.notes}
            onChange={(e) => setForm({ ...form, notes: e.target.value })}
          />
          <div className="flex justify-end gap-3 pt-3 border-t border-stone-100">
            <Button variant="outline" type="button" onClick={() => setIsModalOpen(false)}>
              Cancel
            </Button>
            <Button variant="primary" type="submit">
              {editingTransaction ? 'Save Changes' : 'Record Transaction'}
            </Button>
          </div>
        </form>
      </Modal>

      {/* Confirm / Change Category Modal (Section 6 Verified User Feedback) */}
      <Modal
        isOpen={confirmCatModalOpen}
        onClose={() => setConfirmCatModalOpen(false)}
        title="Verify & Correct Transaction Category"
      >
        <div className="space-y-4">
          <p className="text-xs text-stone-600">
            When you verify or correct a category, CashIQ stores the label for supervised model retraining without disrupting live transactions.
          </p>
          {targetTx && (
            <div className="p-3 bg-stone-50 rounded-lg border border-stone-200 text-xs">
              <p className="font-semibold text-stone-900">{targetTx.description}</p>
              <p className="text-stone-500 mt-1">Merchant: {targetTx.merchant || 'None'} • Amount: {formatConverted(targetTx.amount_minor, targetTx.currency)}</p>
            </div>
          )}
          <div>
            <label className="block text-xs font-semibold text-stone-700 mb-1">Correct / Verified Category</label>
            <select
              value={newCategoryName}
              onChange={(e) => setNewCategoryName(e.target.value)}
              className="w-full px-3 py-2 bg-white border border-stone-200 rounded-lg text-sm text-stone-800 focus:outline-none focus:ring-1 focus:ring-teal-600"
            >
              {STANDARD_CATEGORIES.map(c => (
                <option key={c} value={c}>{c}</option>
              ))}
            </select>
          </div>
          <div className="flex justify-end gap-2 pt-3 border-t border-stone-100">
            <Button variant="outline" onClick={() => setConfirmCatModalOpen(false)}>
              Cancel
            </Button>
            <Button variant="primary" onClick={handleSaveCategoryConfirmation}>
              Store Verified Label
            </Button>
          </div>
        </div>
      </Modal>

      {/* Statement / Receipt Ingestion Modal (Section 7) */}
      <Modal
        isOpen={isImportModalOpen}
        onClose={() => setIsImportModalOpen(false)}
        title="Import Financial Documents (CSV, PDF, or Receipt OCR)"
      >
        <div className="space-y-4 max-w-2xl">
          {!importResult ? (
            <div className="space-y-4">
              <p className="text-xs text-stone-600 leading-relaxed">
                Upload bank statements in <strong>CSV</strong> or <strong>PDF</strong>, or receipt images (JPG/PNG).
                Draft transactions will be parsed, categorized via ML, and queued for your human review before writing to the ledger.
              </p>

              {/* Upload Dropzone */}
              <div 
                onClick={() => fileInputRef.current?.click()}
                className="p-8 border-2 border-dashed border-stone-300 hover:border-teal-600 rounded-xl bg-stone-50 hover:bg-teal-50/20 cursor-pointer text-center transition-colors"
              >
                <input 
                  type="file" 
                  ref={fileInputRef} 
                  className="hidden" 
                  accept=".csv,.pdf,image/png,image/jpeg,image/jpg"
                  onChange={(e) => setSelectedFile(e.target.files?.[0] || null)}
                />
                <Upload className="w-8 h-8 text-stone-400 mx-auto mb-2" />
                <p className="text-xs font-semibold text-stone-800">
                  {selectedFile ? selectedFile.name : 'Click to browse statement or receipt file'}
                </p>
                <p className="text-[11px] text-stone-400 mt-1">
                  Supported: CSV, PDF bank statements, PNG/JPG receipt photos
                </p>
              </div>

              <div className="flex justify-end gap-2 pt-2 border-t border-stone-100">
                <Button variant="outline" onClick={() => setIsImportModalOpen(false)}>
                  Cancel
                </Button>
                <Button 
                  variant="primary" 
                  disabled={!selectedFile || isUploading} 
                  isLoading={isUploading}
                  onClick={handleUploadDocument}
                >
                  Parse & Extract Drafts
                </Button>
              </div>
            </div>
          ) : (
            <div className="space-y-4">
              <div className="flex items-center justify-between gap-2">
                <div>
                  <h4 className="text-xs font-semibold text-stone-900">
                    Extracted Draft Transactions ({importResult.drafts.length} found)
                  </h4>
                  <p className="text-[11px] text-stone-500">
                    {importResult.extraction_metadata?.engine ? `Engine: ${importResult.extraction_metadata.engine}` : 'Parsed'}
                    {importResult.processing_ms ? ` • ${importResult.processing_ms}ms` : ''}
                    {importResult.cache_hit ? ' • Cached' : ''}
                    {(importResult.review_required_count || 0) > 0 ? ` • ${importResult.review_required_count} need review` : ''}
                  </p>
                </div>
                <Button 
                  variant="ghost" 
                  size="sm" 
                  onClick={() => setImportResult(null)}
                  className="text-xs text-stone-500"
                >
                  Upload another file
                </Button>
              </div>

              {/* Drafts List */}
              <div className="max-h-72 overflow-y-auto border border-stone-200 rounded-lg divide-y divide-stone-100">
                {importResult.drafts.map((draft, idx) => {
                  const isChecked = selectedDraftIndices.includes(idx);
                  const valStatus = draft.validation?.reconciliation_status;
                  const isInvalid = draft.validation && draft.validation.is_valid === false;
                  return (
                    <div key={idx} className={`p-3 flex items-start gap-3 text-xs ${isInvalid ? 'bg-rose-50/40' : 'bg-white hover:bg-stone-50'}`}>
                      <input 
                        type="checkbox"
                        checked={isChecked}
                        onChange={(e) => {
                          if (e.target.checked) {
                            setSelectedDraftIndices([...selectedDraftIndices, idx]);
                          } else {
                            setSelectedDraftIndices(selectedDraftIndices.filter(i => i !== idx));
                          }
                        }}
                        className="mt-0.5 rounded text-teal-600 focus:ring-teal-500"
                      />
                      <div className="min-w-0 flex-1 space-y-1">
                        <div className="flex items-center justify-between gap-2">
                          <span className="font-semibold text-stone-800 truncate">{draft.description}</span>
                          <span className="font-mono font-bold text-stone-900 shrink-0">{formatConverted(draft.amount_minor, (draft as any).currency || 'USD')}</span>
                        </div>
                        <div className="flex flex-wrap items-center gap-1.5 text-[11px] text-stone-500">
                          <span>{draft.date ? draft.date.split('T')[0] : 'Date missing'}</span>
                          <span>•</span>
                          <span className="text-teal-700 font-medium">{draft.category_name}</span>
                          {draft.extraction_confidence !== undefined && (
                            <span className={`px-1.5 py-0.2 rounded text-[10px] font-mono ${draft.extraction_confidence >= 0.85 ? 'bg-emerald-50 text-emerald-700' : 'bg-amber-50 text-amber-800'}`}>
                              {Math.round(draft.extraction_confidence * 100)}% extract conf
                            </span>
                          )}
                          {(valStatus === 'exact_match' || valStatus === 'reconciled_within_rounding') && (
                            <span className="px-1.5 py-0.2 rounded text-[10px] bg-emerald-50 text-emerald-700 border border-emerald-200">
                              Total reconciled
                            </span>
                          )}
                          {draft.tax_minor ? (
                            <span className="text-stone-500">Tax: {formatConverted(draft.tax_minor, draft.currency || 'USD')}</span>
                          ) : null}
                          {draft.invoice_no && (
                            <span className="font-mono text-stone-400">#{draft.invoice_no}</span>
                          )}
                        </div>
                        {draft.review_reasons && draft.review_reasons.length > 0 && (
                          <div className="text-[10px] text-amber-800 bg-amber-50 border border-amber-200 rounded px-2 py-1">
                            Review required: {draft.review_reasons.join(' ')}
                          </div>
                        )}
                      </div>
                    </div>
                  );
                })}
              </div>

              <div className="flex items-center justify-between pt-3 border-t border-stone-100">
                <span className="text-xs text-stone-500">
                  {selectedDraftIndices.length} of {importResult.drafts.length} selected
                </span>
                <div className="flex gap-2">
                  <Button variant="outline" onClick={() => setIsImportModalOpen(false)}>
                    Cancel
                  </Button>
                  <Button 
                    variant="primary" 
                    disabled={selectedDraftIndices.length === 0 || isConfirmingDrafts}
                    isLoading={isConfirmingDrafts}
                    onClick={handleConfirmSelectedDrafts}
                  >
                    Confirm & Save to Ledger ({selectedDraftIndices.length})
                  </Button>
                </div>
              </div>
            </div>
          )}
        </div>
      </Modal>

      {/* Anomaly Review & Adaptive Learning Modal */}
      <Modal
        isOpen={anomalyModalOpen && !!selectedAnomalyTx}
        onClose={() => { setAnomalyModalOpen(false); setSelectedAnomalyTx(null); }}
        title="Context-Aware Anomaly Review & Adaptive Learning"
      >
        {selectedAnomalyTx && (() => {
          let explanationDetails: any = selectedAnomalyTx.anomaly_explanation_details || null;
          if (!explanationDetails) {
            try {
              if (selectedAnomalyTx.anomaly_explanation) {
                explanationDetails = JSON.parse(selectedAnomalyTx.anomaly_explanation);
              }
            } catch (e) {
              explanationDetails = null;
            }
          }

          const scorePercent = Math.round((selectedAnomalyTx.anomaly_score || 0) * 100);
          const confPercent = explanationDetails?.confidence !== undefined
            ? Math.round(explanationDetails.confidence * 100)
            : null;
          const severity = selectedAnomalyTx.anomaly_severity || 'medium';
          const alertType = explanationDetails?.alert_type || selectedAnomalyTx.anomaly_alert_type || 'multivariate';
          const alertMeta = ALERT_TYPE_LABELS[alertType] || ALERT_TYPE_LABELS.multivariate;
          const isLegitimate = selectedAnomalyTx.anomaly_feedback_status === 'legitimate';
          const isGenuineAnomaly = selectedAnomalyTx.anomaly_feedback_status === 'suspicious' || selectedAnomalyTx.anomaly_feedback_status === 'genuine_anomaly';
          const bizCtx = explanationDetails?.business_context;
          const contributingFactors: any[] = explanationDetails?.contributing_factors || [];

          return (
            <div className="space-y-4 text-xs">
              {/* Header Banner */}
              <div className={`p-3.5 rounded-lg border flex items-start gap-3 ${
                isLegitimate
                  ? 'bg-emerald-50 border-emerald-200 text-emerald-900'
                  : isGenuineAnomaly
                  ? 'bg-rose-50 border-rose-300 text-rose-900'
                  : alertType === 'operational_relevance'
                  ? 'bg-amber-50 border-amber-200 text-amber-950'
                  : alertType === 'merchant_category_mismatch'
                  ? 'bg-indigo-50 border-indigo-200 text-indigo-950'
                  : severity === 'critical'
                  ? 'bg-rose-50 border-rose-200 text-rose-900'
                  : 'bg-stone-50 border-stone-200 text-stone-900'
              }`}>
                {isLegitimate ? (
                  <CheckCircle2 className="w-5 h-5 text-emerald-600 shrink-0 mt-0.5" />
                ) : (
                  <ShieldAlert className="w-5 h-5 text-rose-600 shrink-0 mt-0.5" />
                )}
                <div className="space-y-1 flex-1 min-w-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="font-semibold text-sm">
                      {isLegitimate
                        ? 'Verified Legitimate Expenditure'
                        : isGenuineAnomaly
                        ? 'Confirmed Genuine Anomaly'
                        : alertMeta.label}
                    </span>
                    <span className={`px-2 py-0.5 rounded-full text-[10px] font-bold uppercase tracking-wider ${
                      severity === 'critical'
                        ? 'bg-rose-200 text-rose-900'
                        : severity === 'high'
                        ? 'bg-orange-200 text-orange-900'
                        : 'bg-amber-200 text-amber-900'
                    }`}>
                      {scorePercent}% Score • {severity}
                    </span>
                    {confPercent !== null && (
                      <span className="px-2 py-0.5 rounded-full text-[10px] font-semibold bg-white/80 text-stone-700 border border-stone-200">
                        {confPercent}% Confidence
                      </span>
                    )}
                  </div>
                  <p className="text-xs leading-relaxed opacity-90">
                    {selectedAnomalyTx.anomaly_reason || 'Flagged by CashIQ business-context-aware anomaly detector.'}
                  </p>
                </div>
              </div>

              {/* Transaction Summary */}
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-2.5 p-3 bg-stone-50 rounded-lg border border-stone-200 text-[11px]">
                <div>
                  <span className="text-stone-400 block">Amount</span>
                  <span className="font-mono font-bold text-stone-900 text-xs">
                    {formatConverted(selectedAnomalyTx.amount_minor, selectedAnomalyTx.currency)}
                  </span>
                </div>
                <div>
                  <span className="text-stone-400 block">Category</span>
                  <span className="font-medium text-stone-800">{selectedAnomalyTx.category_name}</span>
                </div>
                <div>
                  <span className="text-stone-400 block">Merchant</span>
                  <span className="font-medium text-stone-800">{selectedAnomalyTx.merchant || 'None specified'}</span>
                </div>
                <div>
                  <span className="text-stone-400 block">Date</span>
                  <span className="font-mono text-stone-700">{new Date(selectedAnomalyTx.date).toLocaleDateString()}</span>
                </div>
              </div>

              {/* Business Operational Context */}
              {bizCtx && (
                <div className="p-3 bg-stone-50/70 rounded-lg border border-stone-200 flex flex-wrap items-center justify-between gap-2 text-[11px]">
                  <div>
                    <span className="text-stone-500 block">Business Context</span>
                    <span className="font-semibold text-stone-800">
                      {bizCtx.profile_configured
                        ? `${bizCtx.business_type || 'Business'} • ${bizCtx.industry || 'General'}${bizCtx.operating_model ? ` (${bizCtx.operating_model})` : ''}`
                        : 'Business profile not configured'}
                    </span>
                  </div>
                  <div className="flex items-center gap-1.5">
                    <span className={`px-2 py-0.5 rounded-full font-semibold uppercase text-[10px] border ${
                      bizCtx.category_relevance_status === 'expected'
                        ? 'bg-emerald-50 text-emerald-700 border-emerald-200'
                        : bizCtx.category_relevance_status === 'unrelated'
                        ? 'bg-rose-50 text-rose-700 border-rose-200'
                        : bizCtx.category_relevance_status === 'unusual'
                        ? 'bg-amber-50 text-amber-800 border-amber-200'
                        : 'bg-stone-100 text-stone-600 border-stone-200'
                    }`}>
                      Category Relevance: {bizCtx.category_relevance_status || 'unknown'}
                    </span>
                    {bizCtx.personalized && (
                      <span className="px-1.5 py-0.5 rounded bg-teal-50 text-teal-700 border border-teal-200 text-[10px]">
                        Personalized
                      </span>
                    )}
                  </div>
                </div>
              )}

              {/* Structured Contributing Factors Breakdown */}
              {contributingFactors.length > 0 ? (
                <div className="space-y-2 border border-stone-200 rounded-lg p-3 bg-white">
                  <h4 className="text-xs font-semibold text-stone-900 flex items-center gap-1.5">
                    <Sparkles className="w-3.5 h-3.5 text-indigo-600" />
                    Contributing Risk & Context Factors
                  </h4>
                  <div className="space-y-2">
                    {contributingFactors.map((f: any) => (
                      <div key={f.factor} className={`p-2.5 rounded-md border text-[11px] ${f.triggered ? 'bg-amber-50/40 border-amber-200' : 'bg-stone-50 border-stone-200'}`}>
                        <div className="flex items-center justify-between gap-2 mb-1">
                          <span className="font-semibold text-stone-900 flex items-center gap-1.5">
                            <span>{f.label}</span>
                            {f.triggered && (
                              <span className="px-1.5 py-0.2 rounded text-[9px] font-bold uppercase bg-rose-100 text-rose-700">
                                Triggered
                              </span>
                            )}
                          </span>
                          <span className="font-mono text-stone-600">
                            {Math.round((f.score || 0) * 100)}% impact • {Math.round((f.confidence || 0) * 100)}% conf
                          </span>
                        </div>
                        <div className="w-full h-1.5 bg-stone-200 rounded-full overflow-hidden mb-1.5">
                          <div
                            className={`h-full rounded-full ${f.triggered ? 'bg-rose-500' : 'bg-teal-500'}`}
                            style={{ width: `${Math.min(100, Math.round((f.score || 0) * 100))}%` }}
                          />
                        </div>
                        <p className="text-stone-600 leading-relaxed">{f.detail}</p>
                      </div>
                    ))}
                  </div>
                </div>
              ) : explanationDetails && (
                <div className="space-y-2 border border-stone-200 rounded-lg p-3 bg-white">
                  <h4 className="text-xs font-semibold text-stone-900 flex items-center gap-1.5">
                    <Sparkles className="w-3.5 h-3.5 text-indigo-600" />
                    Statistical Feature Summary
                  </h4>
                  <div className="grid grid-cols-2 gap-2 text-[11px]">
                    <div className="p-2 bg-stone-50 rounded">
                      <span className="text-stone-500 block">Category Median</span>
                      <span className="font-mono font-medium text-stone-900">
                        {explanationDetails.category_median_minor || explanationDetails.category_mean_minor
                          ? formatConverted(explanationDetails.category_median_minor || explanationDetails.category_mean_minor, selectedAnomalyTx.currency)
                          : 'Cold-start benchmark'}
                      </span>
                    </div>
                    <div className="p-2 bg-stone-50 rounded">
                      <span className="text-stone-500 block">Category Spend Multiple</span>
                      <span className="font-mono font-medium text-stone-900">
                        {explanationDetails.category_multiple ? `${explanationDetails.category_multiple}× normal` : 'N/A'}
                      </span>
                    </div>
                  </div>
                </div>
              )}

              {/* Adaptive Feedback Submission Form */}
              <div className="space-y-3 pt-2 border-t border-stone-200">
                <div>
                  <h4 className="font-semibold text-stone-900 text-xs mb-1">
                    Adaptive Learning Feedback
                  </h4>
                  <p className="text-stone-500 text-[11px] mb-2">
                    Your decision adapts future baselines and merchant-category classifications without disabling detection of new risk patterns.
                  </p>
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5 mb-2">
                    <div>
                      <label className="block text-[11px] font-medium text-stone-700 mb-1">
                        Correct Category (if misclassified)
                      </label>
                      <select
                        value={anomalyFeedbackCategory}
                        onChange={(e) => setAnomalyFeedbackCategory(e.target.value)}
                        className="w-full text-xs p-2 rounded-md border border-stone-300 bg-white focus:outline-none focus:ring-2 focus:ring-teal-500"
                      >
                        {STANDARD_CATEGORIES.map(c => (
                          <option key={c} value={c}>{c}</option>
                        ))}
                      </select>
                    </div>
                    <div>
                      <label className="block text-[11px] font-medium text-stone-700 mb-1">
                        Reviewer Notes (optional)
                      </label>
                      <input
                        type="text"
                        value={anomalyFeedbackNote}
                        onChange={(e) => setAnomalyFeedbackNote(e.target.value)}
                        placeholder="e.g., Authorized cafeteria supply, vendor recategorization..."
                        className="w-full text-xs p-2 rounded-md border border-stone-300 focus:outline-none focus:ring-2 focus:ring-teal-500"
                      />
                    </div>
                  </div>
                </div>

                <div className="flex flex-wrap items-center justify-between gap-2 pt-2">
                  <Button
                    variant="outline"
                    onClick={() => { setAnomalyModalOpen(false); setSelectedAnomalyTx(null); }}
                    className="text-stone-600"
                  >
                    Close
                  </Button>
                  <div className="flex flex-wrap gap-2">
                    <Button
                      variant="outline"
                      className="border-rose-300 text-rose-700 hover:bg-rose-50 flex items-center gap-1.5"
                      disabled={isSubmittingFeedback}
                      isLoading={isSubmittingFeedback}
                      onClick={() => handleSubmitAnomalyFeedback('genuine_anomaly')}
                    >
                      <AlertTriangle className="w-3.5 h-3.5 text-rose-600" />
                      Genuine Anomaly
                    </Button>
                    <Button
                      variant="outline"
                      className="border-indigo-300 text-indigo-700 hover:bg-indigo-50 flex items-center gap-1.5"
                      disabled={isSubmittingFeedback}
                      isLoading={isSubmittingFeedback}
                      onClick={() => handleSubmitAnomalyFeedback('incorrect_category')}
                    >
                      <RefreshCw className="w-3.5 h-3.5 text-indigo-600" />
                      Incorrect Category
                    </Button>
                    <Button
                      variant="primary"
                      className="bg-emerald-600 hover:bg-emerald-700 text-white flex items-center gap-1.5"
                      disabled={isSubmittingFeedback}
                      isLoading={isSubmittingFeedback}
                      onClick={() => handleSubmitAnomalyFeedback('legitimate')}
                    >
                      <CheckCircle2 className="w-3.5 h-3.5" />
                      Legitimate (Adapt)
                    </Button>
                  </div>
                </div>
              </div>
            </div>
          );
        })()}
      </Modal>

      {/* ML System Status Modal */}
      <Modal
        isOpen={mlStatusModalOpen}
        onClose={() => setMlStatusModalOpen(false)}
        title="CashIQ Machine Learning Architecture & Health"
      >
        <div className="space-y-4 text-xs">
          {isLoadingMLStatus && (
            <div className="py-8 flex justify-center">
              <LoadingSpinner size="md" />
            </div>
          )}

          {mlStatus && (
            <>
              {/* Architecture Badges */}
              <div className="space-y-2">
                <h4 className="font-semibold text-stone-900 text-xs">Active ML Models & Serving</h4>
                <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
                  <div className="p-2.5 bg-indigo-50/60 rounded-lg border border-indigo-100">
                    <span className="text-[10px] uppercase font-bold text-indigo-700 block">1. Categorizer</span>
                    <span className="font-mono text-stone-900 font-semibold text-xs truncate block">
                      {mlStatus.active_model_versions?.categorizer || 'v1.2.0'}
                    </span>
                    <span className="text-[10px] text-stone-500 block mt-0.5">TF-IDF + Logistic Regression</span>
                  </div>
                  <div className="p-2.5 bg-teal-50/60 rounded-lg border border-teal-100">
                    <span className="text-[10px] uppercase font-bold text-teal-700 block">2. Anomaly Detector</span>
                    <span className="font-mono text-stone-900 font-semibold text-xs truncate block">
                      {mlStatus.active_model_versions?.anomaly_detector || 'v2.0.0'}
                    </span>
                    <span className="text-[10px] text-stone-500 block mt-0.5">Context Multivariate IsoForest</span>
                  </div>
                  <div className="p-2.5 bg-amber-50/60 rounded-lg border border-amber-100">
                    <span className="text-[10px] uppercase font-bold text-amber-700 block">3. Forecaster</span>
                    <span className="font-mono text-stone-900 font-semibold text-xs truncate block">
                      {mlStatus.active_model_versions?.forecaster || 'v1.0.0'}
                    </span>
                    <span className="text-[10px] text-stone-500 block mt-0.5">Exponential Smoothing & Cold Start</span>
                  </div>
                </div>
              </div>

              {/* Health and Drift Stats */}
              <div className="space-y-2 border-t border-stone-200 pt-3">
                <h4 className="font-semibold text-stone-900 text-xs">System Health & Behavioral Drift</h4>
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-[11px]">
                  <div className="p-2 bg-stone-50 rounded border border-stone-200">
                    <span className="text-stone-500 block">Transactions</span>
                    <span className="font-mono font-bold text-stone-900 text-sm">
                      {mlStatus.health?.total_transactions || 0}
                    </span>
                  </div>
                  <div className="p-2 bg-stone-50 rounded border border-stone-200">
                    <span className="text-stone-500 block">Contamination Rate</span>
                    <span className="font-mono font-bold text-stone-900 text-sm">
                      {Math.round((mlStatus.health?.anomaly_rate || 0) * 100)}%
                    </span>
                  </div>
                  <div className="p-2 bg-stone-50 rounded border border-stone-200">
                    <span className="text-stone-500 block">Verified Feedback</span>
                    <span className="font-mono font-bold text-emerald-700 text-sm">
                      {mlStatus.health?.verified_feedback_count || 0}
                    </span>
                  </div>
                  <div className="p-2 bg-stone-50 rounded border border-stone-200">
                    <span className="text-stone-500 block">Drift Status</span>
                    <span className={`font-semibold text-sm ${mlStatus.health?.drift_detected ? 'text-amber-600' : 'text-teal-700'}`}>
                      {mlStatus.health?.drift_detected ? 'Shift Detected' : 'Stable'}
                    </span>
                  </div>
                </div>
              </div>

              {/* Retrain & Scan Trigger Actions */}
              <div className="flex flex-col sm:flex-row items-center justify-between gap-3 pt-3 border-t border-stone-200">
                <div className="text-[11px] text-stone-500">
                  Orchestrator Version: <span className="font-mono">{mlStatus.orchestrator_version}</span>
                </div>
                <div className="flex gap-2">
                  <Button
                    variant="outline"
                    size="sm"
                    disabled={isScanning}
                    isLoading={isScanning}
                    onClick={handleScanAnomalies}
                    className="flex items-center gap-1.5"
                  >
                    <Activity className="w-3.5 h-3.5 text-stone-600" />
                    Scan Anomalies
                  </Button>
                  <Button
                    variant="primary"
                    size="sm"
                    disabled={isRetraining}
                    isLoading={isRetraining}
                    onClick={handleTriggerRetrain}
                    className="flex items-center gap-1.5"
                  >
                    <RefreshCw className="w-3.5 h-3.5" />
                    Retrain Baselines
                  </Button>
                </div>
              </div>
            </>
          )}
        </div>
      </Modal>
    </div>
  );
};

export default TransactionsPage;
