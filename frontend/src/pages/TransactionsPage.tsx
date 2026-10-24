import React, { useEffect, useState, useRef } from 'react';
import { useWorkspace } from '../contexts/WorkspaceContext';
import { transactionsApi } from '../api/transactions';
import { documentsApi } from '../api/documents';
import { formatMoney } from '../utils/format';
import { Transaction } from '../types';
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
  X
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
  "Client Revenue",
  "Loans & Financing",
  "Miscellaneous"
];

export const TransactionsPage: React.FC = () => {
  const { currentWorkspace, currency: contextCurrency, formatConverted } = useWorkspace();
  const [transactions, setTransactions] = useState<Transaction[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  
  // Filters and pagination
  const [search, setSearch] = useState('');
  const [typeFilter, setTypeFilter] = useState('');
  const [categoryFilter, setCategoryFilter] = useState('');
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

  // Document Import Modal
  const [isImportModalOpen, setIsImportModalOpen] = useState(false);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [isUploading, setIsUploading] = useState(false);
  const [importResult, setImportResult] = useState<{
    document_id: string;
    filename: string;
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
            {tx.is_anomaly && (
              <span
                title={tx.anomaly_reason || 'Anomalous spending pattern'}
                className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-semibold bg-rose-50 text-rose-700 border border-rose-200"
              >
                <AlertTriangle className="w-3 h-3 text-rose-500" />
                Unusual
              </span>
            )}
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
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
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
          <Table columns={columns} data={transactions} />
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
              <div className="flex items-center justify-between">
                <div>
                  <h4 className="text-xs font-semibold text-stone-900">
                    Extracted Draft Transactions ({importResult.drafts.length} found)
                  </h4>
                  <p className="text-[11px] text-stone-500">
                    Review and confirm before adding to financial ledger.
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
                  return (
                    <div key={idx} className="p-3 flex items-center gap-3 bg-white hover:bg-stone-50 text-xs">
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
                        className="rounded text-teal-600 focus:ring-teal-500"
                      />
                      <div className="min-w-0 flex-1">
                        <div className="flex items-center justify-between">
                          <span className="font-semibold text-stone-800 truncate">{draft.description}</span>
                          <span className="font-mono font-bold text-stone-900">{formatConverted(draft.amount_minor, (draft as any).currency || 'USD')}</span>
                        </div>
                        <div className="flex items-center gap-2 mt-1 text-[11px] text-stone-500">
                          <span>{draft.date.split('T')[0]}</span>
                          <span>•</span>
                          <span className="text-teal-700 font-medium">{draft.category_name}</span>
                          {draft.confidence && (
                            <span className="text-stone-400">({Math.round(draft.confidence * 100)}% conf)</span>
                          )}
                        </div>
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
    </div>
  );
};

export default TransactionsPage;
