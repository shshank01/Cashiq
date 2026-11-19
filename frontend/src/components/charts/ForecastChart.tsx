import React from 'react';
import {
  ComposedChart,
  Line,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer
} from 'recharts';
import { formatMoney } from '../../utils/format';

export interface ForecastData {
  date: string;
  actual?: number; // in cents
  forecast?: number; // in cents
  predicted_minor?: number;
  income_minor?: number;
  expenses_minor?: number;
  net_minor?: number;
  cash_position_minor?: number;
  lower_minor?: number;
  upper_minor?: number;
}

export interface ForecastChartProps {
  data: ForecastData[];
  currency?: string;
}

export function ForecastChart({ data, currency = 'USD' }: ForecastChartProps) {
  // Normalize data for chart display if using cash_position_minor or predicted_minor
  const formattedData = (data || []).map((d) => ({
    date: d.date,
    forecast: d.cash_position_minor ?? d.predicted_minor ?? d.forecast,
    actual: d.actual,
    lower: d.lower_minor,
    upper: d.upper_minor,
  }));

  return (
    <div className="w-full h-[320px]">
      <ResponsiveContainer width="100%" height="100%">
        <ComposedChart
          data={formattedData}
          margin={{ top: 10, right: 30, left: 0, bottom: 0 }}
        >
          <defs>
            <linearGradient id="colorForecast" x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%" stopColor="#0d9488" stopOpacity={0.25}/>
              <stop offset="95%" stopColor="#0d9488" stopOpacity={0}/>
            </linearGradient>
          </defs>
          <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#e7e5e4" />
          <XAxis 
            dataKey="date" 
            axisLine={false}
            tickLine={false}
            tick={{ fill: '#78716c', fontSize: 11 }}
            dy={10}
            tickFormatter={(val: string) => {
              try {
                if (!val) return '';
                const parts = val.split('-');
                if (parts.length === 3) return `${parseInt(parts[1], 10)}/${parseInt(parts[2], 10)}`;
                return val;
              } catch {
                return val;
              }
            }}
          />
          <YAxis 
            axisLine={false}
            tickLine={false}
            tick={{ fill: '#78716c', fontSize: 11 }}
            tickFormatter={(value) => formatMoney(value, currency)}
            width={95}
          />
          <Tooltip 
            formatter={(value: any, name: any) => [
              formatMoney(Number(value) || 0, currency), 
              name ? (String(name).charAt(0).toUpperCase() + String(name).slice(1)) : ''
            ]}
            labelStyle={{ color: '#1c1917', fontWeight: 600, marginBottom: '4px' }}
            contentStyle={{ borderRadius: '6px', border: '1px solid #e7e5e4', boxShadow: '0 2px 4px rgba(0,0,0,0.05)' }}
          />
          <Legend 
            wrapperStyle={{ paddingTop: '15px' }}
            iconType="circle"
          />
          <Area 
            type="monotone" 
            dataKey="forecast" 
            stroke="#0d9488" 
            strokeDasharray="4 4"
            strokeWidth={2}
            fillOpacity={1} 
            fill="url(#colorForecast)" 
            name="Projected Balance"
          />
          {formattedData.some((d) => d.actual !== undefined) && (
            <Line 
              type="monotone" 
              dataKey="actual" 
              stroke="#1c1917" 
              strokeWidth={2}
              dot={{ r: 3, fill: '#1c1917' }}
              activeDot={{ r: 5 }}
              name="Historical Cash"
              connectNulls
            />
          )}
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
}

export default ForecastChart;
