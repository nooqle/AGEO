'use client';

import { RiAddLine, RiRobot2Line, RiLineChartLine } from '@remixicon/react';
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
    desc: '添加要分析的品牌信息',
  },
  {
    icon: RiRobot2Line,
    title: 'AI 分析',
    desc: '多维度智能分析品牌表现',
  },
  {
    icon: RiLineChartLine,
    title: '获取洞察',
    desc: '查看数据报告与优化建议',
  },
];

const containerVariants = {
  hidden: {},
  show: {
    transition: { staggerChildren: 0.1 },
  },
};

const itemVariants = {
  hidden: { opacity: 0, y: 16 },
  show: { opacity: 1, y: 0, transition: { duration: 0.35 } },
};

export function HeroSection({ totalSessions, totalBrands, lastActiveBrand, isLoading, onNewAnalysis }: HeroSectionProps) {

  if (isLoading) return null;

  const isEmpty = totalBrands === 0;
  const isReturningUser = totalBrands === 0 && totalSessions > 0;

  if (isEmpty) {
    return (
      <motion.div
        className="relative text-center py-12 lg:py-16 rounded-2xl overflow-hidden"
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ duration: 0.4 }}
      >
        {/* Subtle radial gradient background */}
        <div
          className="absolute inset-0 pointer-events-none"
          style={{
            background: 'radial-gradient(ellipse at center, rgba(99,102,241,0.12) 0%, transparent 70%)',
          }}
        />

        <div className="relative z-10">
          <h1 className="gradient-text text-3xl lg:text-4xl font-bold mb-3">
            {isReturningUser ? '品牌列表为空' : 'Specta AI 品牌洞察平台'}
          </h1>
          <p className="text-base mb-8" style={{ color: 'var(--text-secondary)' }}>
            {isReturningUser
              ? '您之前的分析记录仍然保留。添加品牌即可开始新的分析。'
              : '智能分析品牌在 AI 搜索引擎中的可见度，发现优化机会'}
          </p>

          <button
            className="btn-primary px-6 py-3 text-base cursor-pointer"
            onClick={onNewAnalysis}
          >
            新建品牌
          </button>

          <motion.div
            className="grid grid-cols-1 md:grid-cols-3 gap-4 mt-8 max-w-2xl mx-auto"
            variants={containerVariants}
            initial="hidden"
            animate="show"
          >
            {STEPS.map((step) => (
              <motion.div
                key={step.title}
                className="card-modern p-6 text-center"
                variants={itemVariants}
              >
                <div
                  className="w-10 h-10 rounded-xl flex items-center justify-center mx-auto mb-3"
                  style={{ background: 'var(--bg-tertiary)' }}
                >
                  <step.icon className="w-5 h-5" style={{ color: 'var(--color-primary)' }} />
                </div>
                <div className="text-sm font-medium mb-1" style={{ color: 'var(--text-primary)' }}>
                  {step.title}
                </div>
                <div className="text-xs" style={{ color: 'var(--text-tertiary)' }}>
                  {step.desc}
                </div>
              </motion.div>
            ))}
          </motion.div>
        </div>
      </motion.div>
    );
  }

  // Has data: compact summary bar
  return (
    <motion.div
      className="flex items-center justify-between py-3"
      style={{ borderBottom: '1px solid var(--border-subtle)' }}
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      transition={{ duration: 0.3 }}
    >
      <span className="text-sm" style={{ color: 'var(--text-secondary)' }}>
        共 {totalBrands} 个品牌 · {totalSessions} 次分析
        {lastActiveBrand && ` · 最近活跃: ${lastActiveBrand}`}
      </span>
    </motion.div>
  );
}
