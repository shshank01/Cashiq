import React from 'react';
import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer
} from 'recharts';
import { formatMoney } from '../../utils/format';

export interface CashFlowData {
  date: string;
  amount?: number; // in cents
  net_minor?: number;
  income_minor?: number;
  expenses_minor?: number;
}

export interface CashFlowChartProps {
  data: CashFlowData[];
  currency?: string;
}

export function CashFlowChart({ data, currency = 'USD' }: CashFlowChartProps) {
  const chartData = (data || []).map((d) => ({
    date: d.date,
    amount: d.net_minor !== undefined ? d.net_minor : (d.amount || 0),
  }));

  return (
    <div className="w-full h-[300px]">
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart
          data={chartData}
          margin={{ top: 10, right: 30, left: 0, bottom: 0 }}
        >
          <defs>
            <linearGradient id="colorAmount" x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%" stopColor="#0d9488" stopOpacity={0.8}/>
              <stop offset="95%" stopColor="#0d9488" stopOpacity={0.05}/>
            </linearGradient>
          </defs>
          <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#e7e5e4" />
          <XAxis 
            dataKey="date" 
            axisLine={false}
            tickLine={false}
            tick={{ fill: '#78716c', fontSize: 12 }}
            dy={10}
          />
          <YAxis 
            axisLine={false}
            tickLine={false}
            tick={{ fill: '#78716c', fontSize: 12 }}
            tickFormatter={(value) => formatMoney(value, currency)}
            width={85}
          />
          <Tooltip 
            formatter={(value: number) => [formatMoney(value, currency), 'Net Cash Flow']}
            labelStyle={{ color: '#1c1917', fontWeight: 600, marginBottom: '4px' }}
            contentStyle={{ borderRadius: '6px', border: '1px solid #e7e5e4', boxShadow: '0 2px 4px rgba(0,0,0,0.05)' }}
          />
          <Area 
            type="monotone" 
            dataKey="amount" 
            stroke="#0d9488" 
            strokeWidth={2}
            fillOpacity={1} 
            fill="url(#colorAmount)" 
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}

export default CashFlowChart;
