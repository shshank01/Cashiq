import React from 'react';
import {
  PieChart,
  Pie,
  Cell,
  Tooltip,
  Legend,
  ResponsiveContainer
} from 'recharts';
import { formatMoney } from '../../utils/format';

export interface CategoryData {
  name?: string;
  category?: string;
  value?: number; // in cents
  amount_minor?: number;
  percentage?: number;
  color?: string;
}

export interface CategoryPieChartProps {
  data: CategoryData[];
  currency?: string;
}

const DEFAULT_COLORS = ['#0d9488', '#0284c7', '#f59e0b', '#e11d48', '#8b5cf6', '#64748b', '#14b8a6', '#f97316'];

export function CategoryPieChart({ data, currency = 'USD' }: CategoryPieChartProps) {
  const chartData = (data || [])
    .map((d) => ({
      name: d.name || d.category || 'Other',
      value: d.amount_minor !== undefined ? d.amount_minor : (d.value || 0),
      color: d.color,
    }))
    .filter((d) => d.value > 0);

  if (!chartData || chartData.length === 0) {
    return (
      <div className="w-full h-[320px] flex items-center justify-center text-xs text-stone-400">
        No expense category data available.
      </div>
    );
  }

  return (
    <div className="w-full h-[340px]">
      <ResponsiveContainer width="100%" height="100%">
        <PieChart margin={{ top: 10, right: 10, bottom: 10, left: 10 }}>
          <Pie
            data={chartData}
            cx="50%"
            cy="42%"
            innerRadius={55}
            outerRadius={80}
            paddingAngle={3}
            dataKey="value"
          >
            {chartData.map((entry, index) => (
              <Cell 
                key={`cell-${index}`} 
                fill={entry.color || DEFAULT_COLORS[index % DEFAULT_COLORS.length]} 
                stroke="#ffffff"
                strokeWidth={2}
              />
            ))}
          </Pie>
          <Tooltip 
            formatter={(value: number, name: string) => [
              formatMoney(value, currency), 
              name
            ]}
            contentStyle={{ 
              borderRadius: '8px', 
              border: '1px solid #e7e5e4', 
              boxShadow: '0 4px 6px -1px rgba(0, 0, 0, 0.08)',
              fontSize: '12px',
              padding: '8px 12px'
            }}
          />
          <Legend 
            layout="horizontal" 
            verticalAlign="bottom" 
            align="center"
            iconType="circle"
            iconSize={8}
            wrapperStyle={{ 
              paddingTop: '12px',
              fontSize: '11px',
              lineHeight: '20px'
            }}
            formatter={(value: string) => (
              <span className="text-xs text-stone-600 font-medium px-1">
                {value}
              </span>
            )}
          />
        </PieChart>
      </ResponsiveContainer>
    </div>
  );
}

export default CategoryPieChart;
