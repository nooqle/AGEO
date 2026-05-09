'use client';

import { useMemo } from 'react';
import {
  RiCheckLine,
  RiCloseLine,
  RiLoader4Line,
  RiTimeLine,
} from '@remixicon/react';
import {
  getUserFacingStageLabel,
  sanitizeUserFacingErrorMessage,
} from '@/lib/workflowStageLabels';
import type { RunHistoryEntry, RunStatus } from '@/types/monitoring';

// =========================================================================
// Status display config
// =========================================================================

const STATUS_CONFIG: Record<
  RunStatus,
  { label: string; color: string; Icon: typeof RiCheckLine }
> = {
  completed: { label: '成功', color: 'var(--success)', Icon: RiCheckLine },
  failed: { label: '失败', color: 'var(--error)', Icon: RiCloseLine },
  running: { label: '运行中', color: 'var(--warning)', Icon: RiLoader4Line },
  pending: { label: '等待中', color: 'var(--text-muted)', Icon: RiTimeLine },
};

// =========================================================================
// Component
// =========================================================================

interface RunHistoryTableProps {
  entries: RunHistoryEntry[];
  isLoading?: boolean;
}

export function RunHistoryTable({ entries, isLoading }: RunHistoryTableProps) {
  const sortedEntries = useMemo(
    () =>
      [...entries].sort((a, b) => {
        const dateA = a.created_at ? new Date(a.created_at).getTime() : 0;
        const dateB = b.created_at ? new Date(b.created_at).getTime() : 0;
        return dateB - dateA;
      }),
    [entries]
  );

  const formatDate = (dateStr: string | null) => {
    if (!dateStr) return '--';
    const date = new Date(dateStr);
    return date.toLocaleDateString('zh-CN', {
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  };

  if (isLoading) {
    return (
      <div
        className="rounded-xl p-6"
        style={{
          background: 'var(--bg-tertiary)',
          border: '1px solid var(--border-subtle)',
        }}
      >
        <div className="space-y-3">
          {Array.from({ length: 3 }).map((_, i) => (
            <div
              key={i}
              className="h-10 rounded-lg animate-shimmer"
            />
          ))}
        </div>
      </div>
    );
  }

  if (entries.length === 0) {
    return (
      <div
        className="rounded-xl p-8 text-center"
        style={{
          background: 'var(--bg-tertiary)',
          border: '1px solid var(--border-subtle)',
        }}
      >
        <p className="text-sm" style={{ color: 'var(--text-tertiary)' }}>
          暂无执行记录
        </p>
      </div>
    );
  }

  return (
    <div
      className="rounded-xl overflow-hidden"
      style={{
        background: 'var(--bg-tertiary)',
        border: '1px solid var(--border-subtle)',
      }}
    >
      {/* Header */}
      <div className="px-4 py-3">
        <h3 className="text-sm font-medium" style={{ color: 'var(--text-primary)' }}>
          执行历史
        </h3>
      </div>

      {/* Table */}
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr style={{ borderTop: '1px solid var(--border-subtle)' }}>
              <th
                className="text-left px-4 py-2 text-xs font-medium"
                style={{ color: 'var(--text-tertiary)' }}
              >
                执行时间
              </th>
              <th
                className="text-left px-4 py-2 text-xs font-medium"
                style={{ color: 'var(--text-tertiary)' }}
              >
                状态
              </th>
              <th
                className="text-left px-4 py-2 text-xs font-medium"
                style={{ color: 'var(--text-tertiary)' }}
              >
                进度
              </th>
              <th
                className="text-right px-4 py-2 text-xs font-medium"
                style={{ color: 'var(--text-tertiary)' }}
              >
                完成时间
              </th>
            </tr>
          </thead>
          <tbody>
            {sortedEntries.map((entry) => {
              const statusConf = STATUS_CONFIG[entry.status];
              const StatusIcon = statusConf.Icon;
              const stageLabel = getUserFacingStageLabel(entry.current_stage);
              const errorMessage = sanitizeUserFacingErrorMessage(
                entry.error_message,
                '本次执行没有生成可用于展示的结果。'
              );

              return (
                <tr
                  key={entry.id}
                  className="transition-colors"
                  style={{ borderTop: '1px solid var(--border-subtle)' }}
                  onMouseEnter={(e) => {
                    e.currentTarget.style.backgroundColor = 'var(--bg-elevated)';
                  }}
                  onMouseLeave={(e) => {
                    e.currentTarget.style.backgroundColor = 'transparent';
                  }}
                >
                  {/* Execution time */}
                  <td className="px-4 py-2.5">
                    <span className="text-xs" style={{ color: 'var(--text-secondary)' }}>
                      {formatDate(entry.created_at)}
                    </span>
                  </td>

                  {/* Status */}
                  <td className="px-4 py-2.5">
                    <span
                      className="inline-flex items-center gap-1 text-xs font-medium"
                      style={{ color: statusConf.color }}
                    >
                      <StatusIcon
                        className={`w-3.5 h-3.5 ${entry.status === 'running' ? 'animate-spin' : ''}`}
                      />
                      {statusConf.label}
                    </span>
                    {errorMessage && entry.status === 'failed' && (
                      <p
                        className="text-[11px] mt-0.5 truncate max-w-[200px]"
                        style={{ color: 'var(--text-muted)' }}
                        title={errorMessage}
                      >
                        {errorMessage}
                      </p>
                    )}
                  </td>

                  {/* Progress / Stage */}
                  <td className="px-4 py-2.5">
                    <span
                      className="text-xs"
                      style={{ color: 'var(--text-secondary)' }}
                    >
                      {entry.progress != null ? `${Math.round(entry.progress * 100)}%` : '--'}
                    </span>
                    {stageLabel && (
                      <p
                        className="text-[11px] mt-0.5 truncate max-w-[160px]"
                        style={{ color: 'var(--text-muted)' }}
                      >
                        {stageLabel}
                      </p>
                    )}
                  </td>

                  {/* Completed time */}
                  <td className="px-4 py-2.5 text-right">
                    <span className="text-xs" style={{ color: 'var(--text-muted)' }}>
                      {formatDate(entry.completed_at)}
                    </span>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
