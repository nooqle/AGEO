'use client';

import { useEffect, useRef, useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { useCanvasStore } from '@/stores/canvasStore';
import { CanvasContentType } from '@/types/canvas';
import { isConfidenceCanvasReport, isSiteConfidenceCanvasReport } from '@/adapters/exportArtifacts';
import { cn } from '@/lib/cn';
import { getPlatformDisplayName, normalizePublicPlatformId } from '@/config/platformLabel';
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
  RiRobot2Line,
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
  if (isSiteConfidenceCanvasReport(content)) {
    return { icon: RiRobot2Line, label: '官网' };
  }
  if (isConfidenceCanvasReport(content)) {
    return { icon: RiShieldCheckLine, label: '置信' };
  }
  if (content.category === 'baseline' || content.category === 'panorama') {
    return { icon: RiFileChartLine, label: '全景' };
  }
  return { icon: RiPieChartLine, label: '分析' };
}

function formatCompactDuplicateSuffix(createdAt: Date | string | undefined): string {
  if (!createdAt) {
    return '';
  }
  const parsed = createdAt instanceof Date ? createdAt : new Date(createdAt);
  if (Number.isNaN(parsed.getTime())) {
    return '';
  }
  const hours = `${parsed.getHours()}`.padStart(2, '0');
  const minutes = `${parsed.getMinutes()}`.padStart(2, '0');
  return `${hours}:${minutes}`;
}

function normalizeArtifactTitle(title: string): string {
  return title
    .replace(/\s+/g, ' ')
    .replace(/^[^|｜]+[|｜]\s*/, '')
    .replace(/（[^）]*最新[^）]*）/g, '')
    .trim();
}

function extractPlatformToken(title: string): string | null {
  const normalizedTitle = normalizeArtifactTitle(title);
  const match = normalizedTitle.match(/deepseek|kimi|doubao|yuanbao|hunyuan|豆包|元宝|深度求索|腾讯元宝/i);
  if (!match) {
    return null;
  }
  const token = match[0];
  if (/豆包/.test(token)) {
    return '豆包';
  }
  if (/元宝|腾讯元宝/.test(token)) {
    return '元宝';
  }
  if (/deepseek|深度求索/i.test(token)) {
    return 'DeepSeek';
  }
  if (/kimi/i.test(token)) {
    return 'Kimi';
  }
  const normalized = normalizePublicPlatformId(token);
  return getPlatformDisplayName(normalized || token);
}

function getCompactArtifactCopy(content: CanvasContent): { primary: string; secondary: string } {
  const meta = getReportMeta(content);
  const normalizedTitle = normalizeArtifactTitle(content.title || '');
  const platformToken = extractPlatformToken(normalizedTitle);

  if (content.type === 'report' && isSiteConfidenceCanvasReport(content)) {
    return { primary: '官网', secondary: '报告' };
  }

  if (platformToken) {
    return {
      primary: platformToken,
      secondary:
        content.type === 'dataTable'
          ? '数据'
          : content.type === 'fetchResults'
            ? '抓取'
            : meta.label,
    };
  }

  if (normalizedTitle.includes('问题')) {
    return { primary: '问题', secondary: '列表' };
  }
  if (normalizedTitle.includes('资料')) {
    return { primary: '资料', secondary: '表' };
  }
  if (normalizedTitle.includes('抓取')) {
    return { primary: '抓取', secondary: '结果' };
  }
  if (content.type === 'dataTable') {
    return { primary: '数据', secondary: '表格' };
  }
  if (content.type === 'questionList') {
    return { primary: '问题', secondary: '列表' };
  }
  if (content.type === 'fetchResults') {
    return { primary: '抓取', secondary: '结果' };
  }
  if (content.type === 'workflow') {
    return { primary: '品牌', secondary: '档案' };
  }
  return { primary: meta.label, secondary: '' };
}

interface ArtifactNavProps {
  compact?: boolean;
}

export function ArtifactNav({ compact = false }: ArtifactNavProps) {
  const { contents, activeContentIndex, setActiveContentById, openCanvas } = useCanvasStore();
  const prevCountRef = useRef(contents.length);
  const [glowIds, setGlowIds] = useState<Set<string>>(new Set());
  const titleCounts = contents.reduce((acc, content) => {
    const next = acc.get(content.title) ?? 0;
    acc.set(content.title, next + 1);
    return acc;
  }, new Map<string, number>());

  useEffect(() => {
    if (prevCountRef.current === 0) {
      prevCountRef.current = contents.length;
      return;
    }

    if (contents.length > prevCountRef.current) {
      const newIds = contents.slice(prevCountRef.current).map(c => c.id);
      prevCountRef.current = contents.length;
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
      <div className="flex flex-col items-center gap-2 px-1 py-1">
        {contents.map((content, index) => {
          const meta = getReportMeta(content);
          const Icon = meta.icon;
          const isActive = index === activeContentIndex;
          const hasGlow = glowIds.has(content.id);
          const compactCopy = getCompactArtifactCopy(content);
          const hasDuplicateTitle = (titleCounts.get(content.title) ?? 0) > 1;
          const duplicateSuffix = hasDuplicateTitle
            ? formatCompactDuplicateSuffix(content.createdAt)
            : '';
          const secondaryText = duplicateSuffix || compactCopy.secondary;

          return (
            <button
              key={content.id}
              type="button"
              onClick={() => handleClick(content.id)}
              className={cn(
                'relative w-full min-h-[58px] px-0.5 py-1.5 flex flex-col items-center justify-center rounded-xl cursor-pointer transition-colors'
              )}
              style={{
                backgroundColor: isActive ? 'var(--bg-tertiary)' : undefined,
                border: isActive
                  ? '1px solid var(--color-primary)'
                  : hasGlow
                    ? '1px solid var(--border-hover)'
                    : '1px solid transparent',
              }}
              title={content.title}
            >
              <Icon
                className="w-5 h-5"
                style={{ color: isActive ? 'var(--color-primary)' : 'var(--text-secondary)' }}
              />
              <span
                className="mt-0.5 text-[10px] leading-none font-medium"
                style={{ color: isActive ? 'var(--text-primary)' : 'var(--text-secondary)' }}
              >
                {compactCopy.primary}
              </span>
              {secondaryText && (
                <span
                  className="mt-0.5 text-[9px] leading-none"
                  style={{ color: 'var(--text-tertiary)' }}
                >
                  {secondaryText}
                </span>
              )}
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
            const isSiteConfidenceReport =
              content.type === 'report' && isSiteConfidenceCanvasReport(content);

            return (
              <motion.button
                key={content.id}
                type="button"
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
                    {isSiteConfidenceReport ? '官网 AI 友好度' : content.title}
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
