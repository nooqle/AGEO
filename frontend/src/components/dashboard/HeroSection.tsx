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
            先建立品牌，再通过智能对话完成基础信息和问题集。
          </h1>
          <p className="mt-4 text-[14px] leading-8 text-[var(--text-secondary)]">
            确认后，看板会展示周期趋势、平台表现和最新报告。
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
    ? `${analysisLabel}已有样本。需要解释、修正或补充时，在这里提交反馈。`
    : `${analysisLabel}尚未形成可用样本。可以提交补充事实、修正意见或证据追问。`;

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    onCommandSubmit?.(commandInput.trim());
  };

  return (
    <motion.section
      className="relative overflow-hidden rounded-[14px] border bg-[var(--bg-elevated)] px-4 py-4"
      style={{ borderColor: 'var(--border-subtle)' }}
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.28 }}
    >
      <span
        className="absolute right-4 top-4 rounded-lg border px-2.5 py-1 text-[11px] font-medium"
        style={{
          background: 'var(--status-warning-bg)',
          borderColor: 'color-mix(in srgb, var(--status-warning) 24%, var(--border-subtle) 76%)',
          color: 'var(--status-warning)',
        }}
      >
        {monitoringStatusLabel}
      </span>

      <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(380px,520px)] lg:items-end">
        <div className="grid min-w-0 grid-cols-[40px_minmax(0,1fr)] items-center gap-3 pr-20 sm:pr-24">
          <BrandAvatar name={brandName} domain={selectedBrandDomain} size={40} className="flex-shrink-0" />
          <div className="min-w-0">
            <div className="text-[11px] font-medium tracking-[0.12em] text-[var(--text-tertiary)]">
              事实修正
            </div>
            <h2 className="mt-1 break-words text-[17px] font-semibold leading-tight text-[var(--text-primary)]">
              补充事实与证据
            </h2>
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
            placeholder="补充事实、修正判断或追问证据..."
            className="min-h-11 min-w-0 rounded-lg border bg-[var(--bg-secondary)] px-3 text-[13px] text-[var(--text-primary)] outline-none transition-colors focus:border-[var(--brand-primary)]"
            style={{ borderColor: 'var(--border-subtle)' }}
          />
          <button
            type="submit"
            disabled={isCommandSubmitting}
            className="inline-flex min-h-11 items-center justify-center gap-2 rounded-lg bg-[var(--brand-primary)] px-4 text-[13px] font-semibold text-[var(--brand-contrast)] transition-opacity hover:opacity-90 disabled:cursor-wait disabled:opacity-70"
          >
            {isCommandSubmitting ? (
              <span className="h-4 w-4 animate-spin rounded-full border-2 border-current border-t-transparent" />
            ) : (
              <RiSendPlane2Line className="h-4 w-4" />
            )}
            提交反馈
          </button>
        </form>
      </div>
    </motion.section>
  );
}
