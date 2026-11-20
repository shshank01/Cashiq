import React, { useState, useEffect } from 'react';
import { useWorkspace } from '../contexts/WorkspaceContext';
import { reconciliationApi } from '../api/reconciliation';
import { ReconciliationSessionData, ReconciliationItemData } from '../types';
import { formatMoney } from '../utils/format';
import Card from '../components/ui/Card';
import Button from '../components/ui/Button';
import LoadingSpinner from '../components/ui/LoadingSpinner';
import ErrorState from '../components/ui/ErrorState';
import { 
  FileCheck2, 
  UploadCloud, 
  CheckCircle2, 
  AlertTriangle, 
  FileText, 
  Download, 
  RefreshCw, 
  PlusCircle, 
  Clock, 
  ShieldCheck,
  Search,
  Filter
} from 'lucide-react';

export const ReconciliationPage: React.FC = () => {
  const { currentWorkspace, currency: contextCurrency } = useWorkspace();
  const currency = contextCurrency || 'USD';

  const [sessions, setSessions] = useState<any[]>([]);
  const [activeSession, setActiveSession] = useState<ReconciliationSessionData | null>(null);
  const [selectedSessionId, setSelectedSessionId] = useState<string>('');
  
  const [activeTab, setActiveTab] = useState<'all' | 'matched' | 'review' | 'unmatched_bank'>('all');
  const [searchTerm, setSearchTerm] = useState<string>('');

  const [isUploading, setIsUploading] = useState<boolean>(false);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  const [selectedUnmatchedIds, setSelectedUnmatchedIds] = useState<string[]>([]);
  const [isImporting, setIsImporting] = useState<boolean>(false);

  const fetchSessions = async () => {
    if (!currentWorkspace) return;
    setIsLoading(true);
    setError(null);
    try {
      const list = await reconciliationApi.listSessions(currentWorkspace.id);
      setSessions(list);
      if (list.length > 0) {
        const firstId = list[0].id;
        setSelectedSessionId(firstId);
        const sess = await reconciliationApi.getSession(currentWorkspace.id, firstId);
        setActiveSession(sess);
      }
    } catch (err: any) {
      setError(err.response?.data?.detail || err.message || 'Failed to load reconciliation sessions.');
    } finally {
      setIsLoading(false);
    }
  };

  const handleSelectSession = async (sessionId: string) => {
    if (!currentWorkspace) return;
    setSelectedSessionId(sessionId);
    setIsLoading(true);
    try {
      const sess = await reconciliationApi.getSession(currentWorkspace.id, sessionId);
      setActiveSession(sess);
      setSelectedUnmatchedIds([]);
    } catch (err: any) {
      setError(err.message || 'Failed to load session details.');
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    fetchSessions();
  }, [currentWorkspace]);

  const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file || !currentWorkspace) return;

    setIsUploading(true);
    setError(null);
    try {
      const res = await reconciliationApi.upload(currentWorkspace.id, file);
      await fetchSessions();
      if (res.session_id) {
        await handleSelectSession(res.session_id);
      }
    } catch (err: any) {
      setError(err.response?.data?.detail || err.message || 'Failed to reconcile bank statement.');
    } finally {
      setIsUploading(false);
      e.target.value = '';
    }
  };

  const handleApproveMatch = async (itemId: string) => {
    if (!currentWorkspace || !activeSession) return;
    try {
      await reconciliationApi.approveMatch(currentWorkspace.id, activeSession.id, itemId);
      setActiveSession(prev => {
        if (!prev) return null;
        return {
          ...prev,
          items: prev.items.map(it => it.id === itemId ? { ...it, status: 'approved' } : it)
        };
      });
    } catch (err: any) {
      alert('Failed to approve match: ' + err.message);
    }
  };

  const handleImportUnmatched = async () => {
    if (!currentWorkspace || !activeSession || selectedUnmatchedIds.length === 0) return;
    setIsImporting(true);
    try {
      const res = await reconciliationApi.importUnmatched(currentWorkspace.id, activeSession.id, selectedUnmatchedIds);
      alert(res.message);
      // Reload session
      const updated = await reconciliationApi.getSession(currentWorkspace.id, activeSession.id);
      setActiveSession(updated);
      setSelectedUnmatchedIds([]);
    } catch (err: any) {
      alert('Failed to import to ledger: ' + err.message);
    } finally {
      setIsImporting(false);
    }
  };

  const handleExportCSV = async () => {
    if (!currentWorkspace || !activeSession) return;
    try {
      const blob = await reconciliationApi.exportReport(currentWorkspace.id, activeSession.id);
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `reconciliation_report_${activeSession.id.slice(0, 8)}.csv`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
    } catch (err: any) {
      alert('Failed to export CSV report: ' + err.message);
    }
  };

  if (isLoading && !activeSession) return <LoadingSpinner />;

  // Filter items
  const filteredItems = (activeSession?.items || []).filter((it) => {
    if (activeTab === 'matched' && it.match_type !== 'exact' && it.match_type !== 'probable') return false;
    if (activeTab === 'review' && it.match_type !== 'difference' && it.match_type !== 'duplicate') return false;
    if (activeTab === 'unmatched_bank' && it.match_type !== 'unmatched_bank') return false;

    if (searchTerm) {
      const term = searchTerm.toLowerCase();
      return (
        it.description.toLowerCase().includes(term) ||
        (it.reference && it.reference.toLowerCase().includes(term))
      );
    }
    return true;
  });

  const unmatchedBankItems = (activeSession?.items || []).filter(it => it.match_type === 'unmatched_bank');

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-serif font-bold text-stone-900 tracking-tight flex items-center gap-2">
            <FileCheck2 className="w-6 h-6 text-teal-700" />
            Bank Statement Reconciliation
          </h1>
          <p className="text-xs text-stone-500 mt-1">
            Automatically match statement lines with internal transactions, detect discrepancies, and import missing records.
          </p>
        </div>

        <div className="flex items-center gap-2">
          {activeSession && (
            <Button variant="outline" size="sm" onClick={handleExportCSV} className="flex items-center gap-1.5">
              <Download className="w-3.5 h-3.5" />
              Export Report
            </Button>
          )}

          <label className="cursor-pointer">
            <input
              type="file"
              accept=".csv"
              onChange={handleFileUpload}
              className="hidden"
              disabled={isUploading}
            />
            <span className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold rounded-lg text-white bg-teal-700 hover:bg-teal-800 shadow-sm transition-colors">
              <UploadCloud className="w-4 h-4" />
              {isUploading ? 'Reconciling Statement...' : 'Upload Statement CSV'}
            </span>
          </label>
        </div>
      </div>

      {/* Reconciliation Summary Cards */}
      {activeSession ? (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-5 gap-4">
          <Card className="p-4 bg-white border-stone-200 shadow-sm">
            <span className="text-xs font-semibold text-stone-500 uppercase tracking-wider">Reconciled Rate</span>
            <p className="text-2xl font-serif font-bold text-teal-800 mt-1 font-mono">
              {activeSession.summary?.match_rate_pct ?? 0}%
            </p>
            <p className="text-[11px] text-stone-400 mt-0.5">
              {activeSession.matched_count} of {activeSession.total_statement_rows} matched
            </p>
          </Card>

          <Card className="p-4 bg-white border-stone-200 shadow-sm">
            <span className="text-xs font-semibold text-stone-500 uppercase tracking-wider">Exact Matches</span>
            <p className="text-2xl font-serif font-bold text-emerald-700 mt-1 font-mono">
              {activeSession.summary?.exact_matches ?? 0}
            </p>
            <p className="text-[11px] text-stone-400 mt-0.5">Identical amount & posting date</p>
          </Card>

          <Card className="p-4 bg-white border-stone-200 shadow-sm">
            <span className="text-xs font-semibold text-stone-500 uppercase tracking-wider">Probable Matches</span>
            <p className="text-2xl font-serif font-bold text-teal-700 mt-1 font-mono">
              {activeSession.summary?.probable_matches ?? 0}
            </p>
            <p className="text-[11px] text-stone-400 mt-0.5">Date shift within ±3 days</p>
          </Card>

          <Card className="p-4 bg-white border-stone-200 shadow-sm">
            <span className="text-xs font-semibold text-stone-500 uppercase tracking-wider">Discrepancies</span>
            <p className={`text-2xl font-serif font-bold mt-1 font-mono ${(activeSession.summary?.difference_matches ?? 0) > 0 ? 'text-amber-600' : 'text-stone-900'}`}>
              {activeSession.summary?.difference_matches ?? 0}
            </p>
            <p className="text-[11px] text-stone-400 mt-0.5">Amount or fee differences</p>
          </Card>

          <Card className="p-4 bg-white border-stone-200 shadow-sm">
            <span className="text-xs font-semibold text-stone-500 uppercase tracking-wider">Missing in Ledger</span>
            <p className={`text-2xl font-serif font-bold mt-1 font-mono ${activeSession.unmatched_bank_count > 0 ? 'text-rose-600' : 'text-emerald-700'}`}>
              {activeSession.unmatched_bank_count}
            </p>
            <p className="text-[11px] text-stone-400 mt-0.5">Unrecorded bank entries</p>
          </Card>
        </div>
      ) : (
        <Card className="p-8 text-center bg-white border-stone-200 shadow-sm">
          <UploadCloud className="w-10 h-10 text-stone-300 mx-auto mb-2" />
          <h3 className="text-sm font-semibold text-stone-800">No Bank Statement Reconciled</h3>
          <p className="text-xs text-stone-500 max-w-sm mx-auto mt-1 mb-4">
            Upload your bank statement CSV file (with Date, Description, Amount/Debit/Credit columns) to begin automated ledger matching.
          </p>
        </Card>
      )}

      {/* Main Reconciliation Table */}
      {activeSession && (
        <Card className="bg-white border-stone-200 shadow-sm overflow-hidden">
          {/* Controls Bar */}
          <div className="p-4 border-b border-stone-200 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 bg-stone-50/50">
            {/* Tabs */}
            <div className="flex space-x-2">
              {[
                { id: 'all', label: `All (${activeSession.items.length})` },
                { id: 'matched', label: `Matched (${(activeSession.summary?.exact_matches || 0) + (activeSession.summary?.probable_matches || 0)})` },
                { id: 'review', label: `Review Needed (${activeSession.summary?.difference_matches || 0})` },
                { id: 'unmatched_bank', label: `Unmatched in Bank (${activeSession.unmatched_bank_count})` },
              ].map((tab) => (
                <button
                  key={tab.id}
                  onClick={() => setActiveTab(tab.id as any)}
                  className={`px-3 py-1.5 text-xs font-semibold rounded-lg transition-colors ${
                    activeTab === tab.id
                      ? 'bg-white text-teal-800 shadow-sm border border-stone-200'
                      : 'text-stone-600 hover:text-stone-900 hover:bg-stone-100'
                  }`}
                >
                  {tab.label}
                </button>
              ))}
            </div>

            {/* Search & Actions */}
            <div className="flex items-center gap-2">
              <div className="relative">
                <Search className="w-3.5 h-3.5 text-stone-400 absolute left-2.5 top-2.5" />
                <input
                  type="text"
                  placeholder="Filter transactions..."
                  value={searchTerm}
                  onChange={(e) => setSearchTerm(e.target.value)}
                  className="text-xs pl-8 pr-3 py-1.5 bg-white border border-stone-200 rounded-lg focus:outline-none focus:ring-1 focus:ring-teal-600"
                />
              </div>

              {activeTab === 'unmatched_bank' && unmatchedBankItems.length > 0 && (
                <Button
                  size="sm"
                  variant="primary"
                  onClick={handleImportUnmatched}
                  disabled={selectedUnmatchedIds.length === 0 || isImporting}
                  className="flex items-center gap-1.5 text-xs"
                >
                  <PlusCircle className="w-3.5 h-3.5" />
                  Import Selected ({selectedUnmatchedIds.length})
                </Button>
              )}
            </div>
          </div>

          {/* Table */}
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead className="bg-stone-50 border-b border-stone-200 text-stone-600 uppercase tracking-wider font-semibold">
                <tr>
                  {activeTab === 'unmatched_bank' && (
                    <th className="py-2.5 px-3 w-10">
                      <input
                        type="checkbox"
                        checked={selectedUnmatchedIds.length === unmatchedBankItems.length && unmatchedBankItems.length > 0}
                        onChange={(e) => {
                          if (e.target.checked) {
                            setSelectedUnmatchedIds(unmatchedBankItems.map(i => i.id));
                          } else {
                            setSelectedUnmatchedIds([]);
                          }
                        }}
                        className="rounded accent-teal-600 cursor-pointer"
                      />
                    </th>
                  )}
                  <th className="py-2.5 px-4">Statement Date</th>
                  <th className="py-2.5 px-4">Description / Payee</th>
                  <th className="py-2.5 px-4 text-right">Amount</th>
                  <th className="py-2.5 px-4">Match Status</th>
                  <th className="py-2.5 px-4">Discrepancy / Details</th>
                  <th className="py-2.5 px-4 text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-stone-100">
                {filteredItems.length === 0 ? (
                  <tr>
                    <td colSpan={7} className="py-8 text-center text-stone-400">
                      No statement items match the active filter.
                    </td>
                  </tr>
                ) : (
                  filteredItems.map((it) => {
                    const isDebit = it.amount_minor < 0;
                    const isSelected = selectedUnmatchedIds.includes(it.id);
                    return (
                      <tr key={it.id} className="hover:bg-stone-50/70 transition-colors">
                        {activeTab === 'unmatched_bank' && (
                          <td className="py-3 px-3">
                            <input
                              type="checkbox"
                              checked={isSelected}
                              onChange={(e) => {
                                if (e.target.checked) {
                                  setSelectedUnmatchedIds(prev => [...prev, it.id]);
                                } else {
                                  setSelectedUnmatchedIds(prev => prev.filter(id => id !== it.id));
                                }
                              }}
                              className="rounded accent-teal-600 cursor-pointer"
                            />
                          </td>
                        )}
                        <td className="py-3 px-4 font-mono text-stone-600 whitespace-nowrap">{it.date}</td>
                        <td className="py-3 px-4">
                          <p className="font-medium text-stone-900 truncate max-w-xs">{it.description}</p>
                          {it.reference && <p className="text-[10px] text-stone-400 font-mono">Ref: {it.reference}</p>}
                        </td>
                        <td className={`py-3 px-4 text-right font-mono font-semibold whitespace-nowrap ${isDebit ? 'text-stone-900' : 'text-emerald-700'}`}>
                          {isDebit ? '-' : '+'}{formatMoney(Math.abs(it.amount_minor), currency)}
                        </td>
                        <td className="py-3 px-4 whitespace-nowrap">
                          <span
                            className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-semibold uppercase ${
                              it.match_type === 'exact'
                                ? 'bg-emerald-100 text-emerald-800'
                                : it.match_type === 'probable'
                                ? 'bg-teal-100 text-teal-800'
                                : it.match_type === 'difference'
                                ? 'bg-amber-100 text-amber-800'
                                : 'bg-rose-100 text-rose-800'
                            }`}
                          >
                            {it.match_type.replace('_', ' ')}
                          </span>
                        </td>
                        <td className="py-3 px-4 text-stone-500 text-[11px]">
                          {it.discrepancy_details?.reason || (it.match_type === 'exact' ? 'Exact ledger match confirmed' : '—')}
                        </td>
                        <td className="py-3 px-4 text-right whitespace-nowrap">
                          {it.status === 'approved' ? (
                            <span className="inline-flex items-center gap-1 text-[11px] text-emerald-700 font-medium">
                              <CheckCircle2 className="w-3.5 h-3.5" /> Reconciled
                            </span>
                          ) : it.match_type === 'probable' || it.match_type === 'difference' ? (
                            <Button
                              size="sm"
                              variant="outline"
                              onClick={() => handleApproveMatch(it.id)}
                              className="text-[11px] py-1 px-2 h-auto"
                            >
                              Approve Match
                            </Button>
                          ) : it.match_type === 'unmatched_bank' ? (
                            <span className="text-[11px] text-stone-400">Select to import</span>
                          ) : (
                            <span className="text-[11px] text-stone-400">—</span>
                          )}
                        </td>
                      </tr>
                    );
                  })
                )}
              </tbody>
            </table>
          </div>
        </Card>
      )}
    </div>
  );
};

export default ReconciliationPage;
