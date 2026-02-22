'use client';

import { useState } from 'react';
import type { DataTableCanvasContent, TableColumn, TableRow } from '@/types/canvas';
import { RiArrowDownSLine, RiArrowUpSLine } from '@remixicon/react';
import { cn } from '@/lib/cn';

interface DataTableContentProps {
  content: DataTableCanvasContent;
}

type SortDirection = 'asc' | 'desc' | null;

export function DataTableContent({ content }: DataTableContentProps) {
  const data = content.data;
  const columns: TableColumn[] = data.columns ?? [];
  const rows: TableRow[] = data.rows ?? [];

  const [sortColumn, setSortColumn] = useState<string | null>(null);
  const [sortDirection, setSortDirection] = useState<SortDirection>(null);

  const handleSort = (columnKey: string) => {
    if (sortColumn === columnKey) {
      setSortDirection(sortDirection === 'asc' ? 'desc' : sortDirection === 'desc' ? null : 'asc');
      if (sortDirection === 'desc') {
        setSortColumn(null);
      }
    } else {
      setSortColumn(columnKey);
      setSortDirection('asc');
    }
  };

  const toComparable = (value: unknown) => {
    if (value === null || value === undefined) return '';
    if (typeof value === 'number' || typeof value === 'string') return value;
    return String(value);
  };

  const sortedRows = [...rows].sort((a, b) => {
    if (!sortColumn || !sortDirection) return 0;
    const aVal = toComparable(a[sortColumn]);
    const bVal = toComparable(b[sortColumn]);
    if (aVal < bVal) return sortDirection === 'asc' ? -1 : 1;
    if (aVal > bVal) return sortDirection === 'asc' ? 1 : -1;
    return 0;
  });

  return (
    <div className="p-4">
      {/* 表格描述 */}
      {data.description && (
        <p className="text-sm text-gray-600 mb-4">{data.description}</p>
      )}

      {/* 表格 */}
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b">
              {columns.map((col) => (
                <th
                  key={col.key}
                  className={cn(
                    'px-4 py-3 text-left font-medium text-gray-700',
                    col.sortable && 'cursor-pointer hover:bg-gray-50'
                  )}
                  onClick={() => col.sortable && handleSort(col.key)}
                >
                  <div className="flex items-center gap-1">
                    {col.label}
                    {col.sortable && sortColumn === col.key && (
                      sortDirection === 'asc' ? (
                        <RiArrowUpSLine className="w-4 h-4" />
                      ) : (
                        <RiArrowDownSLine className="w-4 h-4" />
                      )
                    )}
                  </div>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {sortedRows.map((row, index) => (
              <tr key={index} className="border-b hover:bg-gray-50">
                {columns.map((col) => (
                  <td key={col.key} className="px-4 py-3 text-gray-900">
                    {col.format ? col.format(row[col.key], row) as React.ReactNode : (row[col.key] as React.ReactNode)}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* 分页信息 */}
      <div className="mt-4 text-sm text-gray-500">
        共 {rows.length} 条数据
      </div>
    </div>
  );
}
