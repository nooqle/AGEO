'use client';

import { useEffect, useRef, useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { useCanvasStore } from '@/stores/canvasStore';
import { CanvasContentType } from '@/types/canvas';
import { isConfidenceCanvasReport } from '@/adapters/exportArtifacts';
import { cn } from '@/lib/cn';
import {
  RiFileChartLine,
  RiBarChartBoxLine,
  RiBuilding2Line,
  RiChromeLine,
  RiQuestionLine,
  RiSearchLine,
  RiFileTextLine,
  RiTableLine,
  RiGitBranchLine,
  RiPieChartLine,
  RiShieldCheckLine,
} from '@remixicon/react';
import type { CanvasContent } from '@/types/canvas';

const TYPE_ICONS: Record<CanvasContentType, typeof RiFileChartLine> = {
  report: RiFileChartLine,
  chart: RiBarChartBoxLine,
  workflow: RiBuilding2Line,
  questionList: RiQuestionLine,
  fetchResults: RiSearchLine,
  dataTable: RiTableLine,
  pipeline: RiGitBranchLine,
  browser: RiChromeLine,
};

const TYPE_LABELS: Record<CanvasContentType, string> = {
  report: '报告',
  chart: '图表',
  workflow: '档案',
  questionList: '问题',
  fetchResults: '抓取',
  dataTable: '数据',
  pipeline: '画像',
  browser: '浏览器',
};

/** Report subtypes: baseline vs scenario get different icon & label */
function getReportMeta(content: CanvasContent) {
  if (content.type !== 'report') {
    return { icon: TYPE_ICONS[content.type] || RiFileTextLine, label: TYPE_LABELS[content.type] || '' };
  }
  if (isConfidenceCanvasReport(content)) {
    return { icon: RiShieldCheckLine, label: '置信' };
  }
  if (content.category === 'baseline' || content.category === 'panorama') {
    return { icon: RiFileChartLine, label: '全景' };
  }
  return { icon: RiPieChartLine, label: '分析' };
}

interface ArtifactNavProps {
  compact?: boolean;
}

export function ArtifactNav({ compact = false }: ArtifactNavProps) {
  const { contents, activeContentIndex, setActiveContentById, openCanvas } = useCanvasStore();
  const prevCountRef = useRef(contents.length);
  const [glowIds, setGlowIds] = useState<Set<string>>(new Set());

  useEffect(() => {
    if (contents.length > prevCountRef.current) {
      const newIds = contents.slice(prevCountRef.current).map(c => c.id);
      setGlowIds(prev => {
        const next = new Set(prev);
        newIds.forEach(id => next.add(id));
        return next;
      });
      const timer = setTimeout(() => {
        setGlowIds(prev => {
          const next = new Set(prev);
          newIds.forEach(id => next.delete(id));
          return next;
        });
      }, 1500);
      return () => clearTimeout(timer);
    }
    prevCountRef.current = contents.length;
  }, [contents]);

  if (contents.length === 0) return null;

  const handleClick = (id: string) => {
    setActiveContentById(id);
    openCanvas();
  };

  // Compact mode: vertical icon-only strip
  if (compact) {
    return (
      <div className="flex flex-col items-center gap-2 px-1.5">
        {contents.map((content, index) => {
          const meta = getReportMeta(content);
          const Icon = meta.icon;
          const isActive = index === activeContentIndex;
          const hasGlow = glowIds.has(content.id);

          return (
            <button
              key={content.id}
              onClick={() => handleClick(content.id)}
              className={cn(
                'relative w-10 h-10 flex flex-col items-center justify-center rounded-lg cursor-pointer transition-colors',
                hasGlow && 'glow-border'
              )}
              style={{
                backgroundColor: isActive ? 'var(--bg-tertiary)' : undefined,
                border: isActive ? '1px solid var(--border-hover)' : '1px solid transparent',
              }}
              title={content.title}
            >
              <Icon
                className="w-5 h-5"
                style={{ color: isActive ? 'var(--color-primary)' : 'var(--text-secondary)' }}
              />
              <span
                className="text-[12px] mt-0.5 leading-none"
                style={{ color: isActive ? 'var(--text-primary)' : 'var(--text-secondary)' }}
              >
                {meta.label}
              </span>
              {content.hasNewVersion && !isActive && (
                <span
                  className="absolute top-0.5 right-0.5 w-2 h-2 rounded-full"
                  style={{ backgroundColor: 'var(--error)' }}
                />
              )}
            </button>
          );
        })}
      </div>
    );
  }

  // Full mode (legacy sidebar bottom)
  return (
    <div style={{ borderTop: '1px solid var(--border-subtle)' }}>
      <div className="px-3 py-2">
        <span
          className="text-xs font-medium uppercase tracking-wider"
          style={{ color: 'var(--text-tertiary)' }}
        >
          交付物
        </span>
      </div>
      <motion.div className="py-1">
        <AnimatePresence mode="popLayout">
          {contents.map((content, index) => {
            const meta = getReportMeta(content);
            const Icon = meta.icon;
            const isActive = index === activeContentIndex;
            const hasGlow = glowIds.has(content.id);

            return (
              <motion.button
                key={content.id}
                layout
                exit={{ opacity: 0, x: -10 }}
                onClick={() => handleClick(content.id)}
                className={cn(
                  'w-full flex items-center gap-2.5 mx-2 px-2 py-2 rounded-lg transition-all text-left',
                  hasGlow && 'glow-border'
                )}
                style={{
                  width: 'calc(100% - 16px)',
                  backgroundColor: isActive ? 'var(--bg-tertiary)' : undefined,
                  border: isActive ? '1px solid var(--border-hover)' : hasGlow ? undefined : '1px solid transparent',
                }}
                title={content.title}
              >
                <Icon
                  className="w-5 h-5 flex-shrink-0"
                  style={{ color: isActive ? 'var(--color-primary)' : 'var(--text-secondary)' }}
                />
                <div className="flex-1 min-w-0">
                  <p
                    className="text-xs truncate"
                    style={{ color: isActive ? 'var(--text-primary)' : 'var(--text-secondary)' }}
                  >
                    {content.title}
                  </p>
                  <p
                    className="text-xs truncate"
                    style={{ color: 'var(--text-secondary)' }}
                  >
                    {meta.label}
                  </p>
                </div>
              </motion.button>
            );
          })}
        </AnimatePresence>
      </motion.div>
    </div>
  );
}
