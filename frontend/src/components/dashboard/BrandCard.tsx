'use client';

import { useMemo, useState, type KeyboardEvent } from 'react';
import { motion } from 'framer-motion';
import { RiAddLine, RiCalendar2Line, RiChat1Line } from '@remixicon/react';
import type { Entity } from '@/types/entity';
import { BrandAvatar } from './BrandAvatar';
import { useTheme } from '@/hooks/useTheme';

interface BrandCardProps {
  entity: Entity;
  isSelected?: boolean;
  onClick?: () => void;
  onAnalyze?: () => void;
  onMonitor?: () => void;
  isAnalyzeLoading?: boolean;
  isMonitorLoading?: boolean;
}

interface AddBrandCardProps {
  onClick: () => void;
}

function cleanCardText(value: string | null | undefined, fallback: string): string {
  const text = (value || '').trim();
  if (!text || /\?{2,}/.test(text)) return fallback;
  return text;
}

export function BrandCard({ entity, isSelected, onClick, onAnalyze, onMonitor, isAnalyzeLoading = false, isMonitorLoading = false }: BrandCardProps) {
  const { theme } = useTheme();
  const [renderedAt] = useState(() => Date.now());
  const displayName = cleanCardText(entity.name, '未命名品牌');
  const industryLabel = cleanCardText(entity.industry, '未设置行业');
  const lastAnalyzedLabel = useMemo(() => {
    if (!entity.lastAnalyzed) return '尚未分析';
    const diff = renderedAt - new Date(entity.lastAnalyzed).getTime();
    const days = Math.floor(diff / 86400000);
    if (days === 0) return '今天分析';
    if (days === 1) return '昨天分析';
    if (days < 7) return `${days} 天前分析`;
    return new Date(entity.lastAnalyzed).toLocaleDateString('zh-CN', { month: 'short', day: 'numeric' }) + ' 分析';
  }, [entity.lastAnalyzed, renderedAt]);

  const isDark = theme === 'dark';
  const handleCardKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    if (!onClick) return;
    if (event.key === 'Enter' || event.key === ' ') {
      event.preventDefault();
      onClick();
    }
  };

  return (
    <motion.div
      className="w-full min-w-0 rounded-[22px] border px-3.5 py-3 text-left transition-all duration-200"
      style={{
        background: isDark
          ? (isSelected
              ? 'linear-gradient(180deg, color-mix(in srgb, var(--bg-elevated) 86%, var(--brand-primary) 14%), color-mix(in srgb, var(--bg-secondary) 94%, #181510 6%))'
              : 'linear-gradient(180deg, color-mix(in srgb, var(--bg-elevated) 92%, #1c211c 8%), color-mix(in srgb, var(--bg-secondary) 96%, #17130f 4%))')
          : (isSelected
              ? 'linear-gradient(180deg, color-mix(in srgb, var(--bg-elevated) 93%, #e6f0ec 7%), color-mix(in srgb, var(--bg-secondary) 98%, #dfe8e4 2%))'
              : 'linear-gradient(180deg, color-mix(in srgb, var(--bg-elevated) 98%, #eef1ee 2%), var(--bg-secondary))'),
        borderColor: isDark
          ? (isSelected ? 'color-mix(in srgb, var(--brand-primary) 38%, var(--border-subtle) 62%)' : 'rgba(255,255,255,0.08)')
          : (isSelected ? 'color-mix(in srgb, var(--brand-primary) 30%, var(--border-subtle) 70%)' : 'color-mix(in srgb, var(--border-subtle) 92%, #c9d0c9 8%)'),
        boxShadow: isDark
          ? (isSelected ? '0 20px 44px rgba(8,12,24,0.34)' : '0 12px 28px rgba(8,12,24,0.22)')
          : (isSelected ? '0 18px 36px rgba(24, 30, 28, 0.07)' : '0 10px 24px rgba(24, 30, 28, 0.035)'),
      }}
      whileHover={{ y: -2 }}
      transition={{ duration: 0.18 }}
    >
      <div className="flex min-h-[132px] flex-col">
        <div
          role="button"
          tabIndex={0}
          aria-pressed={isSelected}
          aria-label={`${displayName} ${isSelected ? '当前查看' : '切换查看'}`}
          className="min-w-0 rounded-[16px] outline-none transition-shadow focus-visible:ring-2 focus-visible:ring-[var(--color-primary)]/40"
          onClick={onClick}
          onKeyDown={handleCardKeyDown}
        >
          <div className="flex items-start justify-between gap-3">
            <BrandAvatar name={displayName} domain={entity.domain} size={42} />
            <span
              className="rounded-full border px-2.5 py-1 text-[10px]"
              style={{ borderColor: 'var(--border-subtle)', color: 'var(--text-tertiary)' }}
            >
              {lastAnalyzedLabel}
            </span>
          </div>

          <div className="mt-2.5 min-w-0">
            <div className="flex items-center gap-2">
              <div className="truncate text-[14px] font-semibold" style={{ color: 'var(--text-primary)' }}>
                {displayName}
              </div>
              <span
                className="inline-flex flex-shrink-0 rounded-full border px-2 py-0.5 text-[10px]"
                style={{ borderColor: 'var(--border-subtle)', color: 'var(--text-tertiary)' }}
              >
                {entity.visibilityScope === 'organization' ? '组织空间' : '个人空间'}
              </span>
            </div>
            {entity.domain && (
              <div className="mt-0.5 truncate text-[11px]" style={{ color: 'var(--text-tertiary)' }}>
                {entity.domain}
              </div>
            )}
          </div>

          <div className="mt-2.5 flex items-center justify-between gap-3">
            <div className="text-[11px]" style={{ color: 'var(--text-secondary)' }}>
              {industryLabel}
            </div>
            <div className="text-[11px]" style={{ color: isSelected ? 'var(--color-primary)' : 'var(--text-tertiary)' }}>
              {isSelected ? '当前查看中' : '点击切换'}
            </div>
          </div>
        </div>

        <div className="mt-2.5 border-t pt-2" style={{ borderColor: 'var(--border-subtle)' }}>
          <div className="grid grid-cols-2 gap-2">
            <button
              type="button"
              disabled={isAnalyzeLoading || isMonitorLoading}
              aria-busy={isAnalyzeLoading}
              className="flex min-h-8 items-center justify-center gap-1.5 rounded-[12px] px-3 py-1.5 text-[11px] font-medium transition-colors disabled:cursor-wait disabled:opacity-70"
              style={{
                background: isDark
                  ? (isSelected
                      ? 'color-mix(in srgb, var(--brand-primary) 22%, var(--bg-elevated) 78%)'
                      : 'color-mix(in srgb, var(--brand-primary) 14%, var(--bg-elevated) 86%)')
                  : (isSelected
                      ? 'color-mix(in srgb, var(--color-primary) 10%, var(--bg-elevated) 90%)'
                      : 'color-mix(in srgb, var(--color-primary) 6%, var(--bg-elevated) 94%)'),
                color: isDark
                  ? 'var(--brand-text)'
                  : 'color-mix(in srgb, var(--color-primary) 62%, var(--text-primary) 38%)',
                border: isDark
                  ? '1px solid color-mix(in srgb, var(--brand-primary) 34%, var(--border-subtle) 66%)'
                  : '1px solid color-mix(in srgb, var(--color-primary) 16%, var(--border-subtle) 84%)',
                boxShadow: isDark ? 'inset 0 1px 0 rgba(255,255,255,0.04)' : 'none',
              }}
              onClick={(event) => {
                event.stopPropagation();
                onAnalyze?.();
              }}
            >
              {isAnalyzeLoading ? <span className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-current border-t-transparent" /> : <RiChat1Line className="h-3.5 w-3.5" />}
              {isAnalyzeLoading ? '进入中' : '进入分析'}
            </button>
            <button
              type="button"
              disabled={isAnalyzeLoading || isMonitorLoading}
              aria-busy={isMonitorLoading}
              className="flex min-h-8 items-center justify-center gap-1.5 rounded-[12px] px-3 py-1.5 text-[11px] font-medium transition-colors disabled:cursor-wait disabled:opacity-70"
              style={{
                background: isDark
                  ? 'linear-gradient(180deg, rgba(255,255,255,0.06), rgba(255,255,255,0.025))'
                  : 'color-mix(in srgb, var(--bg-secondary) 72%, var(--bg-tertiary) 28%)',
                color: isDark
                  ? 'rgba(255,255,255,0.90)'
                  : 'color-mix(in srgb, var(--text-primary) 74%, var(--text-secondary) 26%)',
                border: isDark
                  ? '1px solid rgba(255,255,255,0.12)'
                  : '1px solid color-mix(in srgb, var(--border-subtle) 84%, #b8c1b9 16%)',
                boxShadow: isDark ? 'inset 0 1px 0 rgba(255,255,255,0.03)' : 'none',
              }}
              onClick={(event) => {
                event.stopPropagation();
                onMonitor?.();
              }}
            >
              {isMonitorLoading ? <span className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-current border-t-transparent" /> : <RiCalendar2Line className="h-3.5 w-3.5" />}
              {isMonitorLoading ? '跳转中' : '设置监测'}
            </button>
          </div>
        </div>
      </div>
    </motion.div>
  );
}

export function AddBrandCard({ onClick }: AddBrandCardProps) {
  const { theme } = useTheme();
  const isDark = theme === 'dark';

  return (
    <motion.button
      type="button"
      className="flex h-[164px] w-full min-w-0 flex-col items-start justify-between rounded-[22px] border border-dashed px-3.5 py-3 text-left transition-all duration-200"
      style={{
        background: isDark
          ? 'linear-gradient(180deg, rgba(255,255,255,0.045), rgba(255,255,255,0.018))'
          : 'linear-gradient(180deg, color-mix(in srgb, var(--bg-elevated) 96%, #eef1ee 4%), color-mix(in srgb, var(--bg-secondary) 99%, #e7e9e5 1%))',
        borderColor: isDark
          ? 'rgba(255,255,255,0.10)'
          : 'color-mix(in srgb, var(--border-subtle) 90%, #c6cec6 10%)',
      }}
      onClick={onClick}
      whileHover={{ y: -2 }}
      transition={{ duration: 0.18 }}
    >
      <div
        className="flex h-10 w-10 items-center justify-center rounded-2xl"
        style={{ background: 'var(--bg-secondary)' }}
      >
        <RiAddLine className="h-5 w-5" style={{ color: 'var(--text-secondary)' }} />
      </div>
      <div>
        <div className="text-[13px] font-semibold" style={{ color: 'var(--text-primary)' }}>
          新建品牌
        </div>
        <div className="mt-1 text-[11px] leading-5" style={{ color: 'var(--text-tertiary)' }}>
          添加品牌并开始分析。
        </div>
      </div>
    </motion.button>
  );
}
