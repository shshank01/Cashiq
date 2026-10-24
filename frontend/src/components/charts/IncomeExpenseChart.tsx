import React from 'react';
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer
} from 'recharts';
import { formatMoney } from '../../utils/format';

export interface IncomeExpenseData {
  period?: string;
  month?: string;
  income?: number; // in cents
  income_minor?: number;
  expense?: number; // in cents
  expenses_minor?: number;
}

export interface IncomeExpenseChartProps {
  data: IncomeExpenseData[];
  currency?: string;
}

export function IncomeExpenseChart({ data, currency = 'USD' }: IncomeExpenseChartProps) {
  const chartData = (data || []).map((d) => ({
    period: d.period || d.month || '',
    income: d.income_minor !== undefined ? d.income_minor : (d.income || 0),
    expense: d.expenses_minor !== undefined ? d.expenses_minor : (d.expense || 0),
  }));

  return (
    <div className="w-full h-[300px]">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart
          data={chartData}
          margin={{ top: 20, right: 30, left: 10, bottom: 5 }}
        >
          <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#e7e5e4" />
          <XAxis 
            dataKey="period" 
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
            formatter={(value: number, name: string) => [
              formatMoney(value, currency), 
              name === 'income' ? 'Income' : 'Expenses'
            ]}
            labelStyle={{ color: '#1c1917', fontWeight: 600, marginBottom: '4px' }}
            contentStyle={{ borderRadius: '6px', border: '1px solid #e7e5e4', boxShadow: '0 2px 4px rgba(0,0,0,0.05)' }}
            cursor={{ fill: '#f5f5f4' }}
          />
          <Legend 
            wrapperStyle={{ paddingTop: '15px' }}
            iconType="circle"
          />
          <Bar dataKey="income" fill="#0d9488" radius={[4, 4, 0, 0]} maxBarSize={36} name="Income" />
          <Bar dataKey="expense" fill="#e11d48" radius={[4, 4, 0, 0]} maxBarSize={36} name="Expenses" />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

export default IncomeExpenseChart;
