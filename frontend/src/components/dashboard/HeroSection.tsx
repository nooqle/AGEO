'use client';

import { RiAddLine, RiFileChartLine, RiLineChartLine } from '@remixicon/react';
import { motion } from 'framer-motion';

interface HeroSectionProps {
  totalSessions: number;
  totalBrands: number;
  lastActiveBrand?: string;
  isLoading: boolean;
  onNewAnalysis: () => void;
}

const STEPS = [
  {
    icon: RiAddLine,
    title: '创建品牌',
    desc: '录入品牌与竞品信息，形成分析对象。',
  },
  {
    icon: RiFileChartLine,
    title: '进入分析',
    desc: '通过对话发起采集，生成结构化判断。',
  },
  {
    icon: RiLineChartLine,
    title: '查看结果',
    desc: '在首页看最近一轮摘要，再打开完整报告。',
  },
];

const containerVariants = {
  hidden: {},
  show: {
    transition: { staggerChildren: 0.08 },
  },
};

const itemVariants = {
  hidden: { opacity: 0, y: 12 },
  show: { opacity: 1, y: 0, transition: { duration: 0.28 } },
};

export function HeroSection({ totalSessions, totalBrands, lastActiveBrand, isLoading, onNewAnalysis }: HeroSectionProps) {
  if (isLoading) return null;

  const isEmpty = totalBrands === 0;

  if (isEmpty) {
    return (
      <motion.section
        className="dashboard-shell overflow-hidden rounded-[30px] px-7 py-8 lg:px-8 lg:py-9"
        style={{
          position: 'relative',
        }}
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.32 }}
      >
        <div className="grid gap-8 xl:grid-cols-[1.02fr_0.98fr] xl:items-end">
          <div className="space-y-4">
            <div className="text-[11px] font-medium tracking-[0.18em]" style={{ color: 'var(--text-tertiary)' }}>
              品牌分析首页
            </div>
            <h1
              className="max-w-3xl text-[clamp(1.65rem,2.3vw,2.2rem)] font-semibold leading-[1.08]"
              style={{ color: 'var(--text-primary)', letterSpacing: '-0.03em' }}
            >
              用首页判断层快速看清品牌是否被提到、内容是否进入答案，以及整体战况。
            </h1>
            <p className="max-w-2xl text-[14px] leading-8" style={{ color: 'var(--text-secondary)' }}>
              创建品牌并完成首次分析后，可直接查看最近一轮报告的关键指标、引用来源和关联问题。
            </p>
            <div className="flex flex-wrap items-center gap-3 pt-1">
              <button
                className="rounded-full px-5 py-2.5 text-sm font-medium transition-opacity hover:opacity-90"
                style={{
                  background: 'var(--brand-primary)',
                  color: 'var(--brand-contrast)',
                  boxShadow: 'var(--shadow-sm)',
                }}
                onClick={onNewAnalysis}
              >
                新建品牌
              </button>
              <div className="text-[12px]" style={{ color: 'var(--text-tertiary)' }}>
                创建后即可进入对话分析并生成首页判断。
              </div>
            </div>
          </div>

          <motion.div
            className="grid gap-3 md:grid-cols-3 xl:grid-cols-1"
            variants={containerVariants}
            initial="hidden"
            animate="show"
          >
            {STEPS.map((step) => (
              <motion.div
                key={step.title}
                className="rounded-[20px] border px-4 py-4"
                style={{
                  background: 'color-mix(in srgb, var(--bg-elevated) 96%, #eef1ee 4%)',
                  borderColor: 'var(--border-subtle)',
                }}
                variants={itemVariants}
              >
                <div className="flex items-start gap-3">
                  <div
                    className="mt-0.5 flex h-9 w-9 flex-shrink-0 items-center justify-center rounded-xl"
                    style={{ background: 'var(--bg-secondary)' }}
                  >
                    <step.icon className="h-4 w-4" style={{ color: 'var(--color-primary)' }} />
                  </div>
                  <div>
                    <div className="text-[14px] font-semibold" style={{ color: 'var(--text-primary)' }}>
                      {step.title}
                    </div>
                    <div className="mt-1 text-[12px] leading-6" style={{ color: 'var(--text-tertiary)' }}>
                      {step.desc}
                    </div>
                  </div>
                </div>
              </motion.div>
            ))}
          </motion.div>
        </div>
      </motion.section>
    );
  }

  return (
    <motion.section
      className="dashboard-shell overflow-hidden rounded-[24px] px-5 py-3"
      style={{
        position: 'relative',
      }}
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.28 }}
    >
      <div className="flex flex-col gap-2 xl:flex-row xl:items-center xl:justify-between">
        <div className="max-w-3xl">
          <div className="text-[10px] font-medium tracking-[0.16em]" style={{ color: 'var(--text-tertiary)' }}>
            概览
          </div>
          <div className="mt-1 text-[clamp(0.94rem,1.02vw,1.08rem)] font-semibold tracking-[-0.03em]" style={{ color: 'var(--text-primary)' }}>
            当前已管理 {totalBrands} 个品牌，累计完成 {totalSessions} 次分析
          </div>
          <div className="mt-2 flex flex-wrap gap-2">
            <span
              className="rounded-full border px-2.5 py-0.5 text-[11px] font-medium"
              style={{
                background: 'color-mix(in srgb, var(--bg-elevated) 96%, #eef1ee 4%)',
                borderColor: 'color-mix(in srgb, var(--border-subtle) 88%, #87988f 12%)',
                color: 'var(--text-secondary)',
              }}
            >
              {totalBrands} 个品牌
            </span>
            <span
              className="rounded-full border px-2.5 py-0.5 text-[11px] font-medium"
              style={{
                background: 'color-mix(in srgb, var(--bg-elevated) 96%, #e9f1ed 4%)',
                borderColor: 'color-mix(in srgb, var(--border-subtle) 82%, var(--color-primary) 18%)',
                color: 'var(--text-secondary)',
              }}
            >
              {totalSessions} 次分析
            </span>
            {lastActiveBrand ? (
              <span
                className="rounded-full border px-2.5 py-0.5 text-[11px] font-medium"
                style={{
                  background: 'color-mix(in srgb, var(--bg-elevated) 94%, #eef6f4 6%)',
                  borderColor: 'color-mix(in srgb, var(--border-subtle) 84%, #7ca89a 16%)',
                  color: 'var(--text-secondary)',
                }}
              >
                最近活跃：{lastActiveBrand}
              </span>
            ) : null}
          </div>
        </div>
        {lastActiveBrand ? (
          <div className="rounded-full border px-3 py-1 text-[11px] font-medium" style={{ borderColor: 'var(--border-subtle)', color: 'var(--text-secondary)', background: 'color-mix(in srgb, var(--bg-elevated) 96%, #e9f1ed 4%)' }}>
            当前查看：{lastActiveBrand}
          </div>
        ) : null}
      </div>
    </motion.section>
  );
}
