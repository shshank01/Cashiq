import React, { useState, useEffect } from 'react';
import { useWorkspace } from '../contexts/WorkspaceContext';
import { reportsApi } from '../api/reports';
import { formatMoney } from '../utils/format';
import { Select } from '../components/ui/Select';
import { Card } from '../components/ui/Card';
import { Table, Column } from '../components/ui/Table';
import { LoadingSpinner } from '../components/ui/LoadingSpinner';
import { ErrorState } from '../components/ui/ErrorState';
import { IncomeExpenseChart } from '../components/charts/IncomeExpenseChart';
import { CategoryPieChart } from '../components/charts/CategoryPieChart';
import { FileText, TrendingUp, TrendingDown, DollarSign } from 'lucide-react';

export function ReportsPage() {
  const { currentWorkspace, currency: currencyFromContext, formatConverted, fxRate, convertWithFx } = useWorkspace();
  const [activeTab, setActiveTab] = useState<'income-expense' | 'category' | 'cash-flow'>('income-expense');
  const [period, setPeriod] = useState('90');
  
  const [data, setData] = useState<any>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchReport = async () => {
    if (!currentWorkspace) return;
    setIsLoading(true);
    setError(null);
    try {
      let reportData;
      if (activeTab === 'income-expense') {
        reportData = await reportsApi.getIncomeExpense(currentWorkspace.id, { period });
      } else if (activeTab === 'category') {
        reportData = await reportsApi.getCategorySpend(currentWorkspace.id, { period });
      } else {
        reportData = await reportsApi.getCashFlow(currentWorkspace.id, { period });
      }
      setData(reportData);
    } catch (err: any) {
      setError(err.message || 'Failed to fetch report data');
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    fetchReport();
  }, [currentWorkspace, activeTab, period]);

  if (!currentWorkspace) return null;

  const currency = currencyFromContext || currentWorkspace.currency || 'USD';

  const tabs = [
    { id: 'income-expense', name: 'Income vs Expense' },
    { id: 'category', name: 'Category Spend Breakdown' },
    { id: 'cash-flow', name: 'Statement of Cash Flows' },
  ] as const;

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row sm:justify-between sm:items-center gap-4">
        <div>
          <h1 className="text-2xl font-bold text-stone-900 font-serif">Financial Reports</h1>
          <p className="text-sm text-stone-500 mt-1">
            Accounting-grade financial reporting computed directly from ledger records.
          </p>
        </div>
        <div className="w-56">
          <Select
            value={period}
            onChange={(e) => setPeriod(e.target.value)}
            options={[
              { value: '30', label: 'Last 30 Days' },
              { value: '90', label: 'Last 90 Days (Quarter)' },
              { value: '180', label: 'Last 180 Days (Half Year)' },
              { value: '365', label: 'Last 365 Days (Annual)' },
            ]}
          />
        </div>
      </div>

      <div className="border-b border-stone-200">
        <nav className="-mb-px flex space-x-6">
          {tabs.map((tab) => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id as any)}
              className={`
                whitespace-nowrap pb-3 px-1 border-b-2 font-medium text-sm transition-colors cursor-pointer
                ${activeTab === tab.id
                  ? 'border-teal-600 text-teal-700'
                  : 'border-transparent text-stone-500 hover:text-stone-700 hover:border-stone-300'
                }
              `}
            >
              {tab.name}
            </button>
          ))}
        </nav>
      </div>

      <div className="min-h-[400px]">
        {isLoading ? (
          <div className="flex justify-center items-center h-64">
            <LoadingSpinner />
          </div>
        ) : error ? (
          <ErrorState message={error} onRetry={fetchReport} />
        ) : !data ? (
          <div className="text-center text-stone-500 py-12">No data available for this period.</div>
        ) : (
          <div className="space-y-6">
            {activeTab === 'income-expense' && (
              <>
                <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                  <Card className="p-5">
                    <span className="text-xs font-semibold text-stone-500 uppercase tracking-wider">Total Income</span>
                    <p className="text-2xl font-bold text-teal-700 mt-2">
                      {formatConverted(data.total_income_minor || 0)}
                    </p>
                  </Card>
                  <Card className="p-5">
                    <span className="text-xs font-semibold text-stone-500 uppercase tracking-wider">Total Expenses</span>
                    <p className="text-2xl font-bold text-rose-600 mt-2">
                      {formatConverted(data.total_expenses_minor || 0)}
                    </p>
                  </Card>
                  <Card className="p-5">
                    <span className="text-xs font-semibold text-stone-500 uppercase tracking-wider">Net Operating Income</span>
                    <p className={`text-2xl font-bold mt-2 ${data.net_income_minor >= 0 ? 'text-teal-700' : 'text-rose-600'}`}>
                      {formatConverted(data.net_income_minor || 0)}
                    </p>
                    <span className="text-xs text-stone-400">Margin: {data.net_profit_margin_pct || 0}%</span>
                  </Card>
                </div>

                <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                  <Card className="p-5" title="Revenue By Category">
                    <Table
                      data={data.revenue_breakdown || []}
                      columns={[
                        { key: 'category', header: 'Category' },
                        { key: 'amount', header: 'Amount', render: (r: any) => formatConverted(r.amount_minor) },
                        { key: 'percentage', header: 'Share', render: (r: any) => `${r.percentage}%` },
                      ]}
                    />
                  </Card>

                  <Card className="p-5" title="Expense By Category">
                    <Table
                      data={data.expense_breakdown || []}
                      columns={[
                        { key: 'category', header: 'Category' },
                        { key: 'amount', header: 'Amount', render: (r: any) => formatConverted(r.amount_minor) },
                        { key: 'percentage', header: 'Share', render: (r: any) => `${r.percentage}%` },
                      ]}
                    />
                  </Card>
                </div>
              </>
            )}

            {activeTab === 'category' && (
              <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
                <Card className="p-5 lg:col-span-5" title="Spending Distribution">
                  <CategoryPieChart 
                    data={(data.categories || []).map((c: any) => ({
                      ...c,
                      amount_minor: Math.round((c.amount_minor || 0) * ((convertWithFx && currency.toUpperCase() === 'INR') ? fxRate : 1)),
                    }))} 
                    currency={currency} 
                  />
                </Card>
                <Card className="p-5 lg:col-span-7" title="Detailed Category Breakdown">
                  <Table
                    data={data.categories || []}
                    columns={[
                      { key: 'category', header: 'Expense Category' },
                      { key: 'count', header: 'Transactions', render: (r: any) => r.transaction_count },
                      { key: 'amount', header: 'Total Spend', render: (r: any) => formatConverted(r.amount_minor) },
                      { key: 'share', header: '% Total', render: (r: any) => `${r.percentage}%` },
                    ]}
                  />
                </Card>
              </div>
            )}

            {activeTab === 'cash-flow' && (
              <Card className="p-6">
                <div className="max-w-2xl mx-auto space-y-4">
                  <h3 className="text-lg font-bold text-stone-900 border-b border-stone-200 pb-3">
                    Statement of Cash Flows ({data.period?.start_date} to {data.period?.end_date})
                  </h3>

                  <div className="space-y-3 text-sm">
                    <div className="flex justify-between py-2 border-b border-stone-100 font-semibold text-stone-700">
                      <span>Beginning Cash Balance</span>
                      <span>{formatConverted(data.beginning_cash_minor)}</span>
                    </div>

                    <div className="pl-3 space-y-1.5 text-stone-600">
                      <div className="flex justify-between">
                        <span>Operating Inflows (Revenue Receipts)</span>
                        <span className="text-teal-700 font-medium">+{formatConverted(data.operating_cash_inflows_minor)}</span>
                      </div>
                      <div className="flex justify-between">
                        <span>Operating Outflows (Supplier & Staff Expenses)</span>
                        <span className="text-rose-600 font-medium">-{formatConverted(data.operating_cash_outflows_minor)}</span>
                      </div>
                      <div className="flex justify-between pt-1 border-t border-dashed border-stone-200 font-semibold text-stone-800">
                        <span>Net Cash from Operating Activities</span>
                        <span>{formatConverted(data.net_operating_cash_flow_minor)}</span>
                      </div>
                    </div>

                    <div className="flex justify-between py-2 border-t border-stone-100 text-stone-600">
                      <span>Financing & Capital Activities</span>
                      <span>{formatConverted(data.investing_financing_cash_flow_minor || 0)}</span>
                    </div>

                    <div className="flex justify-between py-3 border-t-2 border-stone-800 text-base font-bold text-stone-900">
                      <span>Ending Cash Balance</span>
                      <span className="text-teal-700">{formatConverted(data.ending_cash_minor)}</span>
                    </div>
                  </div>
                </div>
              </Card>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

export default ReportsPage;
