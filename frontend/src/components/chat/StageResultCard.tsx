'use client';

import { useState } from 'react';
import { cn } from '@/lib/cn';
import type { StageResult, PlatformStatusData } from '@/types/snapshot';
import type { QualityLevel } from '@/types/task';
import {
  RiBuilding2Line,
  RiUserLine,
  RiQuestionLine,
  RiGlobalLine,
  RiBarChartBoxLine,
  RiArrowDownSLine,
  RiArrowUpSLine,
  RiCheckLine,
  RiCloseLine,
  RiLoader4Line,
  RiTimeLine,
  RiShieldCheckLine,
  RiAlertLine,
  RiHistoryLine,
} from '@remixicon/react';

interface StageResultCardProps {
  result: StageResult;
  isLatest?: boolean;
  /** Whether this card was replayed from cache on reconnection */
  isReplay?: boolean;
  className?: string;
}

const STAGE_ICONS: Record<string, typeof RiBuilding2Line> = {
  brand_profile: RiBuilding2Line,
  personas: RiUserLine,
  questions: RiQuestionLine,
  platform_status: RiGlobalLine,
  metrics_preview: RiBarChartBoxLine,
};

const STAGE_COLORS: Record<string, string> = {
  brand_profile: '#6366F1',
  personas: '#8B5CF6',
  questions: '#3B82F6',
  platform_status: '#F59E0B',
  metrics_preview: '#22C55E',
};

function PlatformStatusIcon({ status }: { status: PlatformStatusData['status'] }) {
  switch (status) {
    case 'success':
      return <RiCheckLine className="w-3.5 h-3.5 text-[#22C55E]" />;
    case 'failed':
      return <RiCloseLine className="w-3.5 h-3.5 text-[#EF4444]" />;
    case 'fetching':
      return <RiLoader4Line className="w-3.5 h-3.5 text-[#F59E0B] animate-spin" />;
    case 'waiting':
      return <RiTimeLine className="w-3.5 h-3.5 text-[--text-disabled]" />;
    default:
      return <RiTimeLine className="w-3.5 h-3.5 text-[--text-disabled]" />;
  }
}

const KEY_LABELS: Record<string, string> = {
  brand_name: '品牌',
  industry: '行业',
  competitors: '竞品',
  products: '产品',
  description: '描述',
  domain: '领域',
  market_position: '市场定位',
  target_audience: '目标受众',
};

function BrandProfileContent({ data }: { data: Record<string, unknown> }) {
  const entries = Object.entries(data).filter(
    ([key]) => !key.startsWith('_') && typeof data[key] !== 'object'
  );
  return (
    <div className="space-y-1">
      {entries.slice(0, 5).map(([key, value]) => (
        <div key={key} className="flex items-center gap-2 text-xs">
          <span className="text-[--text-tertiary] min-w-[64px]">{KEY_LABELS[key] || key}:</span>
          <span className="text-[--text-primary] truncate">{String(value)}</span>
        </div>
      ))}
    </div>
  );
}

function PersonasContent({ data }: { data: Record<string, unknown> }) {
  const personas = Array.isArray(data.personas) ? data.personas
    : Array.isArray(data.persona_names) ? data.persona_names : [];
  const count = typeof data.count === 'number' ? data.count
    : typeof data.persona_count === 'number' ? data.persona_count : personas.length;
  return (
    <div className="space-y-1.5">
      <div className="text-xs text-[--text-secondary]">
        已生成 <span className="text-[--text-primary] font-medium">{count}</span> 个用户画像
      </div>
      {personas.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {(personas as Array<Record<string, unknown>>).slice(0, 4).map((p, i) => (
            <span
              key={i}
              className="text-[10px] px-2 py-0.5 rounded-full bg-[--bg-tertiary] text-[--text-secondary] border border-[--border-default]"
            >
              {String(p.name || p.label || `P${i + 1}`)}
            </span>
          ))}
          {personas.length > 4 && (
            <span className="text-[10px] px-2 py-0.5 text-[--text-tertiary]">
              +{personas.length - 4}
            </span>
          )}
        </div>
      )}
    </div>
  );
}

function QuestionsContent({ data }: { data: Record<string, unknown> }) {
  const count = typeof data.count === 'number' ? data.count
    : typeof data.question_count === 'number' ? data.question_count : 0;
  const categories = Array.isArray(data.categories) ? data.categories as string[] : [];
  const examples = Array.isArray(data.examples) ? data.examples as string[]
    : Array.isArray(data.sample_questions) ? data.sample_questions as string[] : [];
  return (
    <div className="space-y-1.5">
      <div className="text-xs text-[--text-secondary]">
        已生成 <span className="text-[--text-primary] font-medium">{count}</span> 个模拟问题
      </div>
      {categories.length > 0 && (
        <div className="flex flex-wrap gap-1">
          {categories.slice(0, 5).map((cat, i) => (
            <span
              key={i}
              className="text-[10px] px-1.5 py-0.5 rounded bg-[--bg-tertiary] text-[--text-secondary]"
            >
              {cat}
            </span>
          ))}
        </div>
      )}
      {examples.length > 0 && (
        <div className="text-[10px] text-[--text-tertiary] italic truncate">
          例: &quot;{examples[0]}&quot;
        </div>
      )}
    </div>
  );
}

function PlatformStatusContent({ data }: { data: Record<string, unknown> }) {
  const platforms = Array.isArray(data.platforms) ? data.platforms as PlatformStatusData[] : [];
  const completedCount = typeof data.completedCount === 'number'
    ? data.completedCount
    : platforms.filter((p) => p.status === 'success' || p.status === 'failed').length;
  const totalCount = platforms.length || 4;

  return (
    <div className="space-y-1.5">
      <div className="text-xs text-[--text-secondary]">
        平台抓取进度: <span className="text-[--text-primary] font-medium">{completedCount}/{totalCount}</span>
      </div>
      <div className="grid grid-cols-2 gap-1.5">
        {platforms.map((p, i) => (
          <div
            key={i}
            className={cn(
              'flex items-center gap-1.5 px-2 py-1 rounded text-xs',
              'bg-[--bg-tertiary] border border-[--border-default]',
              p.status === 'success' && 'border-[#22C55E]/30',
              p.status === 'failed' && 'border-[#EF4444]/30',
              p.status === 'fetching' && 'border-[#F59E0B]/30',
            )}
          >
            <PlatformStatusIcon status={p.status} />
            <span className={cn(
              'truncate capitalize',
              p.status === 'success' && 'text-[--text-secondary]',
              p.status === 'failed' && 'text-[#EF4444]',
              p.status === 'fetching' && 'text-[#F59E0B]',
              p.status === 'waiting' && 'text-[--text-disabled]',
            )}>
              {p.platform}
            </span>
            {p.mentionCount !== undefined && p.status === 'success' && (
              <span className="ml-auto text-[10px] text-[#22C55E]">
                {p.mentionCount}
              </span>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

function MetricsPreviewContent({ data }: { data: Record<string, unknown> }) {
  const bwvs = typeof data.bwvs_index === 'number' ? data.bwvs_index : null;
  const scoreBand = typeof data.score_band === 'string' ? data.score_band : null;
  return (
    <div className="flex items-center gap-4">
      {bwvs !== null && (
        <div className="text-center">
          <div className={cn(
            'text-2xl font-bold',
            bwvs >= 70 ? 'text-[#22C55E]' :
            bwvs >= 40 ? 'text-[#F59E0B]' : 'text-[#EF4444]'
          )}>
            {bwvs.toFixed(1)}
          </div>
          <div className="text-[10px] text-[--text-tertiary] mt-0.5">BWVS</div>
        </div>
      )}
      {scoreBand && (
        <div className="text-xs text-[--text-secondary]">{scoreBand}</div>
      )}
    </div>
  );
}

/** Quality indicator tooltip messages */
const QUALITY_CONFIG: Record<QualityLevel, { icon: typeof RiShieldCheckLine; color: string; tooltip: string } | null> = {
  high: null, // No icon shown for high quality
  good: {
    icon: RiShieldCheckLine,
    color: 'var(--success)',
    tooltip: '数据已验证并增强',
  },
  adequate: {
    icon: RiShieldCheckLine,
    color: 'var(--warning)',
    tooltip: '经过质量检查后数据已验证',
  },
  partial: {
    icon: RiAlertLine,
    color: 'var(--warning)',
    tooltip: '部分数据字段可能不完整',
  },
};

function QualityIndicator({ level }: { level: QualityLevel }) {
  const config = QUALITY_CONFIG[level];
  if (!config) return null;

  const Icon = config.icon;

  return (
    <span
      className="relative group cursor-help"
      tabIndex={0}
      aria-label={config.tooltip}
    >
      <Icon className="w-3 h-3" style={{ color: config.color }} />
      {/* Tooltip */}
      <span
        className="absolute bottom-full left-1/2 -translate-x-1/2 mb-1.5 px-2.5 py-1.5 rounded-md text-[11px] whitespace-nowrap opacity-0 group-hover:opacity-100 group-focus:opacity-100 transition-opacity duration-200 pointer-events-none z-10"
        style={{
          background: 'var(--bg-elevated)',
          border: '1px solid var(--border-hover)',
          color: 'var(--text-secondary)',
          boxShadow: '0 4px 12px rgba(0,0,0,0.3)',
        }}
      >
        {config.tooltip}
      </span>
    </span>
  );
}

export function StageResultCard({ result, isLatest, isReplay, className }: StageResultCardProps) {
  const [isExpanded, setIsExpanded] = useState(false);
  const Icon = STAGE_ICONS[result.resultType] || RiBarChartBoxLine;
  const accentColor = STAGE_COLORS[result.resultType] || '#6366F1';

  const needsExpansion = result.resultType !== 'metrics_preview';

  // Cycle 3: Quality level from data metadata
  const qualityLevel = (result.data as Record<string, unknown>)._qualityLevel as QualityLevel | undefined;

  // Cycle 3: Status from data (supports 'verifying' state for A1 retry)
  const stageStatus = (result.data as Record<string, unknown>)._status as string | undefined;
  const isVerifying = stageStatus === 'verifying';

  const renderContent = () => {
    // Cycle 3: Show shimmer placeholder when verifying
    if (isVerifying) {
      return (
        <div className="space-y-2" aria-hidden="true">
          <div className="h-2.5 w-4/5 rounded animate-shimmer" />
          <div className="h-2.5 w-3/5 rounded animate-shimmer" />
          <div className="text-[11px] italic mt-1" style={{ color: 'var(--text-muted)' }}>
            正在验证数据质量...
          </div>
        </div>
      );
    }

    switch (result.resultType) {
      case 'brand_profile':
        return <BrandProfileContent data={result.data} />;
      case 'personas':
        return <PersonasContent data={result.data} />;
      case 'questions':
        return <QuestionsContent data={result.data} />;
      case 'platform_status':
        return <PlatformStatusContent data={result.data} />;
      case 'metrics_preview':
        return <MetricsPreviewContent data={result.data} />;
      default:
        return null;
    }
  };

  // Status badge rendering
  const renderStatusBadge = () => {
    if (isVerifying) {
      return (
        <span
          className="text-[10px] font-medium px-1.5 py-0.5 rounded-full whitespace-nowrap"
          style={{ backgroundColor: 'rgba(99,102,241,0.1)', color: 'var(--brand-primary)' }}
        >
          验证中
        </span>
      );
    }
    return (
      <span
        className="text-[10px] font-medium px-1.5 py-0.5 rounded-full whitespace-nowrap"
        style={{ backgroundColor: '#22C55E', color: '#FFFFFF' }}
      >
        已完成
      </span>
    );
  };

  return (
    <div
      role="status"
      aria-live="polite"
      aria-label={`${result.stageName} ${isVerifying ? '正在验证数据质量' : '结果'}`}
      className={cn(
        'rounded-[10px] border-l-2 overflow-hidden transition-all duration-200',
        isLatest ? 'animate-slide-up' : 'animate-fade-to-muted',
        className,
      )}
      style={{
        backgroundColor: 'var(--bg-secondary)',
        borderLeftColor: accentColor,
        boxShadow: '0 1px 3px rgba(0,0,0,0.2)',
      }}
    >
      {/* Header */}
      <button
        onClick={() => needsExpansion && setIsExpanded(!isExpanded)}
        className={cn(
          'w-full flex items-center gap-2 px-3 py-2',
          needsExpansion && 'cursor-pointer hover:bg-[--bg-tertiary]',
          !needsExpansion && 'cursor-default',
        )}
      >
        <Icon className="w-4 h-4 flex-shrink-0" style={{ color: accentColor }} />
        <span className="text-xs font-medium text-[--text-primary] flex-1 text-left">
          {result.stageName}
        </span>

        {/* Cycle 3: Replay icon (decorative) */}
        {isReplay && (
          <RiHistoryLine
            className="w-3 h-3 flex-shrink-0"
            style={{ color: 'var(--text-disabled)' }}
            aria-hidden="true"
          />
        )}

        {/* Cycle 3: Quality indicator */}
        {qualityLevel && !isVerifying && (
          <QualityIndicator level={qualityLevel} />
        )}

        {renderStatusBadge()}

        {needsExpansion && (
          isExpanded
            ? <RiArrowUpSLine className="w-3.5 h-3.5 text-[--text-tertiary]" />
            : <RiArrowDownSLine className="w-3.5 h-3.5 text-[--text-tertiary]" />
        )}
      </button>

      {/* Content */}
      <div
        className={cn(
          'grid transition-[grid-template-rows] duration-300 ease-in-out',
          !needsExpansion && 'grid-rows-[1fr]',
          needsExpansion && isExpanded ? 'grid-rows-[1fr]' : needsExpansion ? 'grid-rows-[0fr]' : '',
        )}
      >
        <div className={cn(
          'overflow-hidden px-3',
          (!needsExpansion || isExpanded) && 'pb-2',
          needsExpansion && isExpanded && 'max-h-[140px] overflow-y-auto',
        )}>
          {renderContent()}
        </div>
      </div>
    </div>
  );
}

export default StageResultCard;
