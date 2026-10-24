import React from 'react';

export interface Column<T = any> {
  key?: string;
  accessor?: string;
  header: string;
  render?: (item: T) => React.ReactNode;
}

export interface TableProps<T = any> extends React.TableHTMLAttributes<HTMLTableElement> {
  data?: T[];
  columns?: Column<T>[];
  onRowClick?: (item: T) => void;
  keyExtractor?: (item: T) => string | number;
  children?: React.ReactNode;
  className?: string;
}

export function Table<T = any>({
  data,
  columns,
  onRowClick,
  keyExtractor = (item: any) => item.id || Math.random(),
  children,
  className = '',
  ...props
}: TableProps<T>) {
  if (children) {
    return (
      <div className="overflow-x-auto w-full rounded-lg border border-stone-200">
        <table className={`w-full text-left border-collapse text-sm text-stone-600 ${className}`} {...props}>
          {children}
        </table>
      </div>
    );
  }

  const colList = columns || [];
  const dataList = data || [];

  return (
    <div className="overflow-x-auto w-full rounded-lg border border-stone-200">
      <table className={`w-full text-left border-collapse ${className}`} {...props}>
        <thead>
          <tr className="border-b border-stone-200 bg-stone-50">
            {colList.map((col, idx) => {
              const k = col.key || col.accessor || String(idx);
              return (
                <th 
                  key={k} 
                  className="px-4 py-3 text-xs font-semibold text-stone-500 uppercase tracking-wider"
                >
                  {col.header}
                </th>
              );
            })}
          </tr>
        </thead>
        <tbody className="divide-y divide-stone-100 bg-white">
          {dataList.length === 0 ? (
            <tr>
              <td colSpan={colList.length || 1} className="px-4 py-8 text-center text-stone-500 text-sm">
                No data available
              </td>
            </tr>
          ) : (
            dataList.map((item) => (
              <tr 
                key={keyExtractor(item)} 
                onClick={() => onRowClick?.(item)}
                className={`group ${onRowClick ? 'cursor-pointer hover:bg-stone-50/80 transition-colors' : ''}`}
              >
                {colList.map((col, idx) => {
                  const k = col.key || col.accessor || String(idx);
                  return (
                    <td key={k} className="px-4 py-3.5 text-sm text-stone-700">
                      {col.render ? col.render(item) : (item as any)[col.key || col.accessor || '']}
                    </td>
                  );
                })}
              </tr>
            ))
          )}
        </tbody>
      </table>
    </div>
  );
}

export default Table;
