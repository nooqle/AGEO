'use client';

import { useState, type FormEvent } from 'react';
import { RiAddLine, RiSendPlane2Line } from '@remixicon/react';
import { motion } from 'framer-motion';
import { BrandAvatar } from './BrandAvatar';

interface HeroSectionProps {
  totalBrands: number;
  selectedBrandName?: string;
  selectedBrandDomain?: string;
  analysisLabel?: string;
  monitoringStatusLabel?: string;
  hasMonitoringContext?: boolean;
  isLoading: boolean;
  onNewAnalysis: () => void;
  onCommandSubmit?: (value: string) => void;
  isCommandSubmitting?: boolean;
}

export function HeroSection({
  totalBrands,
  selectedBrandName,
  selectedBrandDomain,
  analysisLabel = '全景分析',
  monitoringStatusLabel = '待监测',
  hasMonitoringContext = false,
  isLoading,
  onNewAnalysis,
  onCommandSubmit,
  isCommandSubmitting = false,
}: HeroSectionProps) {
  const [commandInput, setCommandInput] = useState('');

  if (isLoading) return null;

  if (totalBrands === 0) {
    return (
      <motion.section
        className="dashboard-shell rounded-[18px] px-7 py-8"
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.32 }}
      >
        <div className="max-w-3xl">
          <div className="text-[11px] font-medium tracking-[0.18em] text-[var(--text-tertiary)]">
            品牌分析首页
          </div>
          <h1 className="mt-3 text-[clamp(1.65rem,2.3vw,2.2rem)] font-semibold leading-[1.12] text-[var(--text-primary)]">
            先建立品牌，再通过 AI 对话完成基础信息和问题集。
          </h1>
          <p className="mt-4 text-[14px] leading-8 text-[var(--text-secondary)]">
            确认后，Dashboard 会展示周期趋势、平台表现和最新报告。
          </p>
          <button
            type="button"
            onClick={onNewAnalysis}
            className="mt-5 inline-flex min-h-10 items-center gap-2 rounded-[12px] bg-[var(--brand-primary)] px-4 text-[14px] font-medium text-[var(--brand-contrast)] transition-opacity hover:opacity-90"
          >
            <RiAddLine className="h-4 w-4" />
            新建品牌
          </button>
        </div>
      </motion.section>
    );
  }

  const brandName = selectedBrandName || '当前品牌';
  const helperText = hasMonitoringContext
    ? `${analysisLabel}已有上下文，可直接提问或继续调整问题集。`
    : `${analysisLabel}尚未开始，需先通过 AI 对话完成问题集确认。`;

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    onCommandSubmit?.(commandInput.trim());
  };

  return (
    <motion.section
      className="dashboard-shell relative overflow-hidden rounded-[18px] px-6 py-6"
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.28 }}
    >
      <span
        className="absolute right-5 top-5 rounded-full border px-3 py-1.5 text-[12px] font-semibold"
        style={{
          background: 'var(--status-warning-bg)',
          borderColor: 'color-mix(in srgb, var(--status-warning) 24%, var(--border-subtle) 76%)',
          color: 'var(--status-warning)',
        }}
      >
        {monitoringStatusLabel}
      </span>

      <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_minmax(420px,560px)] xl:items-end">
        <div className="grid min-w-0 grid-cols-[52px_minmax(0,1fr)] items-center gap-4 pr-0 sm:pr-24">
          <BrandAvatar name={brandName} domain={selectedBrandDomain} size={52} className="flex-shrink-0" />
          <div className="min-w-0">
            <div className="text-[11px] font-medium tracking-[0.14em] text-[var(--text-tertiary)]">
              当前品牌
            </div>
            <h1 className="mt-1 break-words text-[26px] font-semibold leading-tight text-[var(--text-primary)] sm:text-[30px]">
              {brandName}
            </h1>
            <p className="mt-1 text-[13px] leading-6 text-[var(--text-secondary)]">
              {selectedBrandDomain ? `${selectedBrandDomain} · ` : ''}
              {helperText}
            </p>
          </div>
        </div>

        <form className="grid gap-3 sm:grid-cols-[minmax(0,1fr)_auto]" onSubmit={handleSubmit}>
          <input
            value={commandInput}
            onChange={(event) => setCommandInput(event.target.value)}
            placeholder="输入您的问题..."
            className="min-h-12 min-w-0 rounded-[13px] border bg-[var(--bg-secondary)] px-4 text-[14px] text-[var(--text-primary)] outline-none transition-colors focus:border-[var(--brand-primary)]"
            style={{ borderColor: 'var(--border-subtle)' }}
          />
          <button
            type="submit"
            disabled={isCommandSubmitting}
            className="inline-flex min-h-12 items-center justify-center gap-2 rounded-[13px] bg-[var(--brand-primary)] px-5 text-[14px] font-semibold text-[var(--brand-contrast)] transition-opacity hover:opacity-90 disabled:cursor-wait disabled:opacity-70"
          >
            {isCommandSubmitting ? (
              <span className="h-4 w-4 animate-spin rounded-full border-2 border-current border-t-transparent" />
            ) : (
              <RiSendPlane2Line className="h-4 w-4" />
            )}
            AI 对话
          </button>
        </form>
      </div>
    </motion.section>
  );
}
