import React, { useState, useEffect } from 'react';
import { useWorkspace } from '../contexts/WorkspaceContext';
import { insightsApi } from '../api/insights';
import { Button } from '../components/ui/Button';
import { Card } from '../components/ui/Card';
import { LoadingSpinner } from '../components/ui/LoadingSpinner';
import { ErrorState } from '../components/ui/ErrorState';
import { EmptyState } from '../components/ui/EmptyState';
import { StatusBadge } from '../components/ui/StatusBadge';
import { Lightbulb, RefreshCw, TrendingDown, TrendingUp, AlertTriangle, AlertCircle, Info } from 'lucide-react';

export function InsightsPage() {
  const { currentWorkspace, isLoading: wsLoading } = useWorkspace();
  const [insights, setInsights] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [generating, setGenerating] = useState(false);

  const loadInsights = async () => {
    if (!currentWorkspace) return;
    setLoading(true);
    setError(null);
    try {
      const data = await insightsApi.list(currentWorkspace.id);
      setInsights(data.insights || (Array.isArray(data) ? data : []));
    } catch (err: any) {
      setError(err.message || 'Failed to load insights');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (currentWorkspace) {
      loadInsights();
    } else if (!wsLoading) {
      setLoading(false);
    }
  }, [currentWorkspace, wsLoading]);

  const generateInsights = async () => {
    if (!currentWorkspace) return;
    setGenerating(true);
    setError(null);
    try {
      const res = await insightsApi.generate(currentWorkspace.id);
      setInsights(res.insights || (Array.isArray(res) ? res : []));
    } catch (err: any) {
      setError(err.message || 'Failed to generate insights');
    } finally {
      setGenerating(false);
    }
  };

  const getSeverityBadge = (severity: string) => {
    switch ((severity || '').toLowerCase()) {
      case 'critical':
        return <StatusBadge status="failed">Critical</StatusBadge>;
      case 'warning':
        return <StatusBadge status="pending">Warning</StatusBadge>;
      default:
        return <StatusBadge status="active">Informational</StatusBadge>;
    }
  };

  const getIcon = (type: string, severity: string) => {
    if (severity === 'critical') return <AlertCircle className="w-5 h-5 text-rose-600" />;
    if (severity === 'warning') return <AlertTriangle className="w-5 h-5 text-amber-500" />;
    if (type.includes('positive') || type.includes('growth')) return <TrendingUp className="w-5 h-5 text-teal-600" />;
    if (type.includes('surge') || type.includes('increase')) return <TrendingDown className="w-5 h-5 text-rose-500" />;
    return <Lightbulb className="w-5 h-5 text-teal-600" />;
  };

  if (loading) return <LoadingSpinner />;
  if (error) return <ErrorState message={error} onRetry={loadInsights} />;

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-stone-900 font-serif">Financial Insights</h1>
          <p className="text-sm text-stone-500 mt-1">
            Automated intelligence derived from verified historical transactions, recurring patterns, and burn rates.
          </p>
        </div>
        <Button onClick={generateInsights} disabled={generating} className="flex items-center gap-2">
          <RefreshCw className={`w-4 h-4 ${generating ? 'animate-spin' : ''}`} />
          {generating ? 'Synthesizing...' : 'Refresh Insights'}
        </Button>
      </div>

      {insights.length === 0 ? (
        <EmptyState
          icon={Lightbulb}
          title="No Insights Available"
          description="Click Refresh Insights to scan recent transaction data for expense surges, runway risks, and obligations."
          actionLabel="Generate Insights"
          onAction={generateInsights}
        />
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {insights.map((insight) => (
            <Card key={insight.id} className="p-5 border-l-4 border-l-teal-600">
              <div className="flex items-start gap-3.5">
                <div className="p-2.5 bg-stone-50 rounded-lg shrink-0">
                  {getIcon(insight.type, insight.severity)}
                </div>
                <div className="flex-1">
                  <div className="flex items-center justify-between gap-2 mb-1.5">
                    <h3 className="text-sm font-semibold text-stone-900">{insight.title}</h3>
                    {getSeverityBadge(insight.severity)}
                  </div>
                  <p className="text-xs text-stone-600 leading-relaxed">{insight.description}</p>
                  {insight.created_at && (
                    <p className="text-[11px] text-stone-400 mt-3">
                      Detected {new Date(insight.created_at).toLocaleDateString()}
                    </p>
                  )}
                </div>
              </div>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}

export default InsightsPage;
