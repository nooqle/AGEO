'use client';

import { useState, useCallback, useMemo } from 'react';
import {
  RiPlayLine,
  RiPauseLine,
  RiSettings4Line,
  RiDeleteBinLine,
  RiTimeLine,
  RiCalendarCheckLine,
} from '@remixicon/react';
import type {
  MonitoringSchedule,
  ScheduleFrequency,
  ScheduleStatus,
  UpdateScheduleInput,
} from '@/types/monitoring';
import { FREQUENCY_LABELS } from '@/types/monitoring';

// =========================================================================
// Status indicator configuration
// =========================================================================

const STATUS_CONFIG: Record<ScheduleStatus, { color: string; label: string; animation: string }> = {
  active: { color: 'var(--success)', label: '运行中', animation: 'schedule-status-active' },
  paused: { color: 'var(--warning)', label: '已暂停', animation: '' },
  error: { color: 'var(--error)', label: '异常', animation: '' },
  completed: { color: 'var(--text-muted)', label: '已完成', animation: '' },
};

const FREQUENCY_OPTIONS: { value: ScheduleFrequency; label: string }[] = [
  { value: 'daily', label: '每天' },
  { value: 'weekly', label: '每周' },
  { value: 'biweekly', label: '每两周' },
  { value: 'monthly', label: '每月' },
];

const HOUR_OPTIONS = Array.from({ length: 24 }, (_, i) => ({
  value: i,
  label: `${i.toString().padStart(2, '0')}:00`,
}));

// =========================================================================
// Component
// =========================================================================

interface ScheduleStatusCardProps {
  schedule: MonitoringSchedule;
  onPause: (scheduleId: string) => void;
  onResume: (scheduleId: string) => void;
  onUpdate: (scheduleId: string, data: UpdateScheduleInput) => void;
  onDelete: (scheduleId: string) => void;
}

export function ScheduleStatusCard({
  schedule,
  onPause,
  onResume,
  onUpdate,
  onDelete,
}: ScheduleStatusCardProps) {
  const [isEditing, setIsEditing] = useState(false);
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);
  const [editForm, setEditForm] = useState<UpdateScheduleInput>({
    frequency: schedule.frequency,
    preferred_hour: schedule.preferred_hour,
    alert_threshold_bwvs: schedule.alert_threshold_bwvs,
  });

  const statusConfig = STATUS_CONFIG[schedule.status];

  const formatNextRun = useMemo(() => {
    if (!schedule.next_run_at) return '未安排';
    const date = new Date(schedule.next_run_at);
    const now = new Date();
    const diffMs = date.getTime() - now.getTime();
    const diffHours = Math.floor(diffMs / 3_600_000);
    const diffDays = Math.floor(diffMs / 86_400_000);

    if (diffMs < 0) return '即将执行';
    if (diffHours < 1) return '1小时内';
    if (diffHours < 24) return `${diffHours}小时后`;
    if (diffDays < 7) return `${diffDays}天后`;
    return date.toLocaleDateString('zh-CN', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
  }, [schedule.next_run_at]);

  const handleTogglePause = useCallback(() => {
    if (schedule.status === 'active') {
      onPause(schedule.id);
    } else if (schedule.status === 'paused' || schedule.status === 'error') {
      onResume(schedule.id);
    }
  }, [schedule, onPause, onResume]);

  const handleSaveEdit = useCallback(() => {
    onUpdate(schedule.id, editForm);
    setIsEditing(false);
  }, [schedule.id, editForm, onUpdate]);

  const handleCancelEdit = useCallback(() => {
    setEditForm({
      frequency: schedule.frequency,
      preferred_hour: schedule.preferred_hour,
      alert_threshold_bwvs: schedule.alert_threshold_bwvs,
    });
    setIsEditing(false);
    setShowDeleteConfirm(false);
  }, [schedule]);

  const handleConfirmDelete = useCallback(() => {
    onDelete(schedule.id);
    setShowDeleteConfirm(false);
  }, [schedule.id, onDelete]);

  return (
    <div
      role="status"
      aria-label={`监测状态: ${statusConfig.label}，频率: ${FREQUENCY_LABELS[schedule.frequency]}${schedule.next_run_at ? `，下次执行: ${formatNextRun}` : ''}`}
      className="rounded-xl p-5"
      style={{
        background: 'var(--bg-tertiary)',
        border: '1px solid var(--border-default)',
      }}
    >
      {/* Main status row */}
      <div className="flex items-center justify-between flex-wrap gap-4">
        <div className="flex items-center gap-4">
          {/* Status light */}
          <div className="flex items-center gap-2.5">
            <div
              className={`w-3 h-3 rounded-full ${statusConfig.animation}`}
              style={{ backgroundColor: statusConfig.color }}
            />
            <span
              className="text-sm font-semibold"
              style={{ color: 'var(--text-primary)' }}
            >
              {statusConfig.label}
            </span>
          </div>

          {/* Frequency */}
          <div className="flex items-center gap-1.5">
            <RiCalendarCheckLine className="w-4 h-4" style={{ color: 'var(--text-tertiary)' }} />
            <span className="text-sm" style={{ color: 'var(--text-secondary)' }}>
              {FREQUENCY_LABELS[schedule.frequency]}
            </span>
          </div>

          {/* Next run */}
          {schedule.next_run_at && (
            <div className="flex items-center gap-1.5">
              <RiTimeLine className="w-4 h-4" style={{ color: 'var(--text-tertiary)' }} />
              <span className="text-sm" style={{ color: 'var(--text-secondary)' }}>
                下次执行: {formatNextRun}
              </span>
            </div>
          )}

          {/* Run count */}
          <span className="text-xs" style={{ color: 'var(--text-muted)' }}>
            已执行 {schedule.total_runs} 次
          </span>
        </div>

        {/* Action buttons */}
        <div className="flex items-center gap-2">
          {(schedule.status === 'active' || schedule.status === 'paused' || schedule.status === 'error') && (
            <button
              onClick={handleTogglePause}
              className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-lg transition-colors"
              style={{
                backgroundColor: 'var(--bg-elevated)',
                color: 'var(--text-secondary)',
                border: '1px solid var(--border-default)',
              }}
              onMouseEnter={(e) => {
                e.currentTarget.style.borderColor = 'var(--border-hover)';
                e.currentTarget.style.color = 'var(--text-primary)';
              }}
              onMouseLeave={(e) => {
                e.currentTarget.style.borderColor = 'var(--border-default)';
                e.currentTarget.style.color = 'var(--text-secondary)';
              }}
            >
              {schedule.status === 'active' ? (
                <>
                  <RiPauseLine className="w-3.5 h-3.5" />
                  暂停监测
                </>
              ) : (
                <>
                  <RiPlayLine className="w-3.5 h-3.5" />
                  恢复监测
                </>
              )}
            </button>
          )}
          <button
            onClick={() => isEditing ? handleCancelEdit() : setIsEditing(true)}
            className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-lg transition-colors"
            style={{
              backgroundColor: 'var(--bg-elevated)',
              color: 'var(--text-secondary)',
              border: '1px solid var(--border-default)',
            }}
            onMouseEnter={(e) => {
              e.currentTarget.style.borderColor = 'var(--border-hover)';
              e.currentTarget.style.color = 'var(--text-primary)';
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.borderColor = 'var(--border-default)';
              e.currentTarget.style.color = 'var(--text-secondary)';
            }}
          >
            <RiSettings4Line className="w-3.5 h-3.5" />
            编辑设置
          </button>
        </div>
      </div>

      {/* Consecutive failures warning */}
      {schedule.consecutive_failures > 0 && (
        <div
          className="mt-3 px-3 py-2 rounded-lg text-xs"
          style={{
            backgroundColor: 'rgba(239, 68, 68, 0.1)',
            color: 'var(--error)',
            border: '1px solid rgba(239, 68, 68, 0.2)',
          }}
        >
          连续失败 {schedule.consecutive_failures} 次
          {schedule.status === 'error' && ' — 监测已自动暂停，请检查配置后恢复'}
        </div>
      )}

      {/* Edit panel (inline expand) */}
      {isEditing && (
        <div
          className="mt-4 pt-4 animate-fade-in"
          style={{ borderTop: '1px solid var(--border-default)' }}
        >
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
            {/* Frequency selector (pill) */}
            <div>
              <label className="text-xs font-medium mb-2 block" style={{ color: 'var(--text-tertiary)' }}>
                执行频率
              </label>
              <div
                className="flex gap-1 rounded-lg p-1"
                style={{ background: 'var(--bg-elevated)' }}
              >
                {FREQUENCY_OPTIONS.map((opt) => (
                  <button
                    key={opt.value}
                    onClick={() => setEditForm((f) => ({ ...f, frequency: opt.value }))}
                    className="flex-1 px-2 py-1 text-xs font-medium rounded-md transition-colors"
                    style={{
                      background:
                        editForm.frequency === opt.value ? 'var(--bg-primary)' : 'transparent',
                      color:
                        editForm.frequency === opt.value
                          ? 'var(--text-primary)'
                          : 'var(--text-tertiary)',
                    }}
                  >
                    {opt.label}
                  </button>
                ))}
              </div>
            </div>

            {/* Time selector */}
            <div>
              <label className="text-xs font-medium mb-2 block" style={{ color: 'var(--text-tertiary)' }}>
                执行时间
              </label>
              <select
                value={editForm.preferred_hour ?? schedule.preferred_hour}
                onChange={(e) =>
                  setEditForm((f) => ({ ...f, preferred_hour: Number(e.target.value) }))
                }
                className="w-full px-3 py-1.5 text-sm rounded-lg"
                style={{
                  backgroundColor: 'var(--bg-elevated)',
                  color: 'var(--text-primary)',
                  border: '1px solid var(--border-default)',
                }}
              >
                {HOUR_OPTIONS.map((opt) => (
                  <option key={opt.value} value={opt.value}>
                    {opt.label}
                  </option>
                ))}
              </select>
            </div>

            {/* Alert threshold */}
            <div>
              <label className="text-xs font-medium mb-2 block" style={{ color: 'var(--text-tertiary)' }}>
                告警阈值 (BWVS 变化点数)
              </label>
              <input
                type="number"
                min={1}
                max={100}
                step={1}
                value={editForm.alert_threshold_bwvs ?? schedule.alert_threshold_bwvs}
                onChange={(e) =>
                  setEditForm((f) => ({ ...f, alert_threshold_bwvs: Number(e.target.value) }))
                }
                className="w-full px-3 py-1.5 text-sm rounded-lg"
                style={{
                  backgroundColor: 'var(--bg-elevated)',
                  color: 'var(--text-primary)',
                  border: '1px solid var(--border-default)',
                }}
              />
            </div>
          </div>

          {/* Edit actions */}
          <div className="flex items-center justify-between mt-4">
            <button
              onClick={() => setShowDeleteConfirm(true)}
              className="flex items-center gap-1.5 text-xs transition-colors"
              style={{ color: 'var(--error)' }}
              onMouseEnter={(e) => {
                e.currentTarget.style.opacity = '0.8';
              }}
              onMouseLeave={(e) => {
                e.currentTarget.style.opacity = '1';
              }}
            >
              <RiDeleteBinLine className="w-3.5 h-3.5" />
              删除监测计划
            </button>

            <div className="flex items-center gap-2">
              <button
                onClick={handleCancelEdit}
                className="px-3 py-1.5 text-xs font-medium rounded-lg transition-colors"
                style={{
                  color: 'var(--text-tertiary)',
                  border: '1px solid var(--border-default)',
                }}
              >
                取消
              </button>
              <button
                onClick={handleSaveEdit}
                className="px-4 py-1.5 text-xs font-medium rounded-lg transition-colors"
                style={{
                  backgroundColor: 'var(--brand-primary)',
                  color: '#FFFFFF',
                }}
                onMouseEnter={(e) => {
                  e.currentTarget.style.backgroundColor = 'var(--brand-hover)';
                }}
                onMouseLeave={(e) => {
                  e.currentTarget.style.backgroundColor = 'var(--brand-primary)';
                }}
              >
                保存
              </button>
            </div>
          </div>

          {/* Delete confirmation */}
          {showDeleteConfirm && (
            <div
              className="mt-3 px-3 py-2.5 rounded-lg text-xs animate-fade-in"
              style={{
                backgroundColor: 'rgba(239, 68, 68, 0.1)',
                border: '1px solid rgba(239, 68, 68, 0.2)',
              }}
            >
              <p className="mb-2" style={{ color: 'var(--error)' }}>
                确定要删除该监测计划吗？此操作不可恢复。
              </p>
              <div className="flex gap-2">
                <button
                  onClick={handleConfirmDelete}
                  className="px-3 py-1 text-xs font-medium rounded-md"
                  style={{
                    backgroundColor: 'var(--error)',
                    color: '#FFFFFF',
                  }}
                >
                  确认删除
                </button>
                <button
                  onClick={() => setShowDeleteConfirm(false)}
                  className="px-3 py-1 text-xs font-medium rounded-md"
                  style={{
                    color: 'var(--text-tertiary)',
                    border: '1px solid var(--border-default)',
                  }}
                >
                  取消
                </button>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
