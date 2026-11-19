import React, { useState, useEffect } from 'react';
import { useWorkspace } from '../contexts/WorkspaceContext';
import { forecastApi } from '../api/forecast';
import { formatMoney } from '../utils/format';
import { Button } from '../components/ui/Button';
import { Card } from '../components/ui/Card';
import { LoadingSpinner } from '../components/ui/LoadingSpinner';
import { ErrorState } from '../components/ui/ErrorState';
import { EmptyState } from '../components/ui/EmptyState';
import { StatusBadge } from '../components/ui/StatusBadge';
import { ForecastChart } from '../components/charts/ForecastChart';
import { TrendingUp, RefreshCw, BarChart2 } from 'lucide-react';

export function ForecastPage() {
  const { currentWorkspace, currency: currencyFromContext, isLoading: wsLoading, formatConverted, fxRate, convertWithFx } = useWorkspace();
  const [forecast, setForecast] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [generating, setGenerating] = useState(false);

  const loadForecast = async () => {
    if (!currentWorkspace) return;
    setLoading(true);
    setError(null);
    try {
      const data = await forecastApi.get(currentWorkspace.id);
      setForecast(data);
    } catch (err: any) {
      if (err.response?.status === 404) {
        setForecast(null);
      } else {
        setError(err.message || 'Failed to load forecast');
      }
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (currentWorkspace) {
      loadForecast();
    } else if (!wsLoading) {
      setLoading(false);
    }
  }, [currentWorkspace, wsLoading]);

  const generateForecast = async () => {
    if (!currentWorkspace) return;
    setGenerating(true);
    setError(null);
    try {
      const data = await forecastApi.generate(currentWorkspace.id);
      setForecast(data);
    } catch (err: any) {
      setError(err.message || 'Failed to generate forecast');
    } finally {
      setGenerating(false);
    }
  };

  if (loading || wsLoading) return <LoadingSpinner />;
  if (error) return <ErrorState message={error} onRetry={loadForecast} />;

  const currency = currencyFromContext || 'USD';
  const rawDaily = forecast?.daily_forecast || forecast?.daily_forecasts || [];
  const summary = forecast?.summary || {};
  const metrics = forecast?.metrics || {};
  const modelInfo = forecast?.model_info || {};

  const chartMultiplier = (convertWithFx && currency.toUpperCase() === 'INR')
    ? fxRate
    : 1;

  const dailyData = rawDaily.map((d: any) => ({
    ...d,
    cash_position_minor: Math.round((d.cash_position_minor !== undefined ? d.cash_position_minor : (d.predicted_minor || 0)) * chartMultiplier),
    predicted_minor: Math.round((d.predicted_minor || 0) * chartMultiplier),
    lower_minor: Math.round((d.lower_minor || 0) * chartMultiplier),
    upper_minor: Math.round((d.upper_minor || 0) * chartMultiplier),
    income_minor: Math.round((d.income_minor || 0) * chartMultiplier),
    expenses_minor: Math.round((d.expenses_minor || 0) * chartMultiplier),
  }));

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-3">
            <h1 className="text-2xl font-bold text-stone-900 font-serif">Cash Flow Forecast</h1>
            {forecast?.forecast_type && (
              <StatusBadge status={forecast.forecast_type}>
                {forecast.forecast_type.toUpperCase()} MODEL
              </StatusBadge>
            )}
          </div>
          <p className="text-sm text-stone-500 mt-1">
            Time-ordered statistical forecasting with confidence bounds & cold-start support.
          </p>
        </div>
        <Button onClick={generateForecast} disabled={generating} className="flex items-center gap-2">
          <RefreshCw className={`w-4 h-4 ${generating ? 'animate-spin' : ''}`} />
          {generating ? 'Recomputing...' : 'Generate Forecast'}
        </Button>
      </div>

      {!forecast || dailyData.length === 0 ? (
        <EmptyState
          icon={TrendingUp}
          title="No Forecast Available"
          description="Generate a forecast to predict future cash flows using Exponential Smoothing & moving averages."
          actionLabel="Generate Now"
          onAction={generateForecast}
        />
      ) : (
        <>
          <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
            <Card className="p-5">
              <h3 className="text-xs font-semibold text-stone-500 uppercase tracking-wider">Current Cash</h3>
              <p className="mt-2 text-2xl font-bold text-stone-900">
                {formatConverted(forecast.current_balance || summary.current_cash_minor || 0)}
              </p>
            </Card>
            <Card className="p-5">
              <h3 className="text-xs font-semibold text-stone-500 uppercase tracking-wider">Projected 30-Day Ending</h3>
              <p className="mt-2 text-2xl font-bold text-teal-700">
                {formatConverted(forecast.projected_balance_30d || summary.end_cash_position_minor || 0)}
              </p>
            </Card>
            <Card className="p-5">
              <h3 className="text-xs font-semibold text-stone-500 uppercase tracking-wider">Lowest Expected Point</h3>
              <p className="mt-2 text-2xl font-bold text-rose-600">
                {formatConverted(forecast.lowest_balance_30d || summary.lowest_cash_position_minor || 0)}
              </p>
            </Card>
            <Card className="p-5">
              <h3 className="text-xs font-semibold text-stone-500 uppercase tracking-wider">Forecast Accuracy (MAE)</h3>
              <p className="mt-2 text-2xl font-bold text-stone-700">
                {metrics.mae ? formatConverted(Math.round(metrics.mae * 100)) : 'Validating'}
              </p>
              {metrics.rmse && (
                <span className="text-xs text-stone-400">RMSE: {formatConverted(Math.round(metrics.rmse * 100))}</span>
              )}
            </Card>
          </div>

          <Card className="p-6" title="Cash Position Trajectory & Uncertainty Envelope">
            <div className="h-[360px] mt-2">
              <ForecastChart data={dailyData} currency={currency} />
            </div>
            {modelInfo.description && (
              <p className="text-xs text-stone-500 mt-4 border-t border-stone-100 pt-3">
                <strong>Model Details:</strong> {modelInfo.description} (Method: {modelInfo.method})
              </p>
            )}
          </Card>
        </>
      )}
    </div>
  );
}

export default ForecastPage;
