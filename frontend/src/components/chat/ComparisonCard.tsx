'use client';

import { RiArrowLeftRightLine, RiArrowUpSLine, RiArrowDownSLine } from '@remixicon/react';
import { cn } from '@/lib/cn';

export interface ComparisonDimension {
  label: string;
  previous: number;
  current: number;
  delta: number;
  deltaPercent?: number;
  direction: 'up' | 'down' | 'stable';
}

interface ComparisonCardProps {
  /** e.g., "Feb 17 vs Feb 21" */
  dateRange: string;
  /** BWVS or main score comparison */
  mainScore?: {
    label: string;
    previous: number;
    current: number;
    delta: number;
    deltaPercent?: number;
  };
  dimensions: ComparisonDimension[];
  /** Free-form analysis text */
  analysis?: string;
  className?: string;
}

export function ComparisonCard({
  dateRange,
  mainScore,
  dimensions,
  analysis,
  className,
}: ComparisonCardProps) {
  return (
    <div
      role="article"
      aria-label={`分析对比: ${dateRange}`}
      className={cn(
        'rounded-[10px] my-1.5 animate-slide-up',
        className
      )}
      style={{
        background: 'var(--bg-elevated)',
        borderLeft: '2px solid var(--phase-plan, #3B82F6)',
        boxShadow: '0 1px 3px rgba(0,0,0,0.2)',
        padding: '16px 20px',
      }}
    >
      {/* Header */}
      <div className="flex items-center gap-2 mb-3">
        <RiArrowLeftRightLine className="w-4 h-4 flex-shrink-0" style={{ color: 'var(--phase-plan)' }} />
        <span className="text-[13px] font-semibold" style={{ color: 'var(--text-primary)' }}>
          分析对比
        </span>
        <span className="text-xs" style={{ color: 'var(--text-secondary)' }}>
          {dateRange}
        </span>
      </div>

      {/* Main score comparison */}
      {mainScore && (
        <div className="flex items-center justify-center gap-3 py-3 mb-3">
          {/* Previous */}
          <div className="text-center">
            <div className="text-xl font-semibold" style={{ color: 'var(--text-tertiary)' }}>
              {mainScore.previous.toFixed(1)}
            </div>
            <div className="text-[10px] mt-0.5" style={{ color: 'var(--text-disabled)' }}>
              上次
            </div>
          </div>
          {/* Arrow */}
          <span className="text-sm" style={{ color: 'var(--text-disabled)' }}>
            &rarr;
          </span>
          {/* Current */}
          <div className="text-center">
            <div
              className="text-2xl font-bold"
              style={{
                color:
                  mainScore.current >= 70
                    ? 'var(--success)'
                    : mainScore.current >= 40
                    ? 'var(--warning)'
                    : 'var(--error)',
              }}
            >
              {mainScore.current.toFixed(1)}
            </div>
            <div className="text-[10px] mt-0.5" style={{ color: 'var(--text-disabled)' }}>
              本次
            </div>
          </div>
          {/* Delta badge */}
          <DeltaBadge
            delta={mainScore.delta}
            deltaPercent={mainScore.deltaPercent}
          />
        </div>
      )}

      {/* Empty state */}
      {dimensions.length === 0 && !mainScore && (
        <div className="py-6 text-center" style={{ color: 'var(--text-tertiary)' }}>
          <RiArrowLeftRightLine className="w-8 h-8 mx-auto mb-2 opacity-40" />
          <p className="text-xs">需要至少两次分析才能进行对比</p>
          <p className="text-[11px] mt-1" style={{ color: 'var(--text-disabled)' }}>完成下一次分析后，对比数据将自动显示</p>
        </div>
      )}

      {/* Dimensions table */}
      {dimensions.length > 0 && (
        <div
          className="rounded-lg overflow-hidden mt-3"
          style={{
            background: 'var(--bg-primary)',
            border: '1px solid var(--border-subtle)',
          }}
        >
          {/* Table header */}
          <div
            role="table"
            aria-label="维度变化"
          >
            <div
              role="row"
              className="grid grid-cols-4 gap-2 px-3 py-2 text-[11px] font-semibold uppercase tracking-wider"
              style={{
                background: 'var(--bg-tertiary)',
                color: 'var(--text-primary)',
              }}
            >
              <div role="columnheader">维度</div>
              <div role="columnheader" className="text-right">上次</div>
              <div role="columnheader" className="text-right">本次</div>
              <div role="columnheader" className="text-right">变化</div>
            </div>
            {/* Table rows */}
            {dimensions.map((dim, i) => (
              <div
                key={i}
                role="row"
                className="grid grid-cols-4 gap-2 px-3 py-2 text-xs"
                style={{
                  borderTop: '1px solid var(--border-subtle)',
                  color: 'var(--text-secondary)',
                }}
              >
                <div role="cell">{dim.label}</div>
                <div role="cell" className="text-right">
                  {typeof dim.previous === 'number' ? dim.previous.toFixed(1) : '-'}
                </div>
                <div role="cell" className="text-right font-medium" style={{ color: 'var(--text-primary)' }}>
                  {typeof dim.current === 'number' ? dim.current.toFixed(1) : '-'}
                </div>
                <div role="cell" className="text-right">
                  <DeltaInline
                    delta={dim.delta}
                    direction={dim.direction}
                  />
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Analysis text */}
      {analysis && (
        <div
          className="mt-3 pt-3 text-xs leading-relaxed prose-chat"
          style={{
            borderTop: '1px solid var(--border-subtle)',
            color: 'var(--text-secondary)',
          }}
        >
          {analysis}
        </div>
      )}
    </div>
  );
}

function DeltaBadge({ delta, deltaPercent }: { delta: number; deltaPercent?: number }) {
  if (delta === 0) {
    return (
      <span className="text-xs px-2 py-0.5 rounded" style={{ color: 'var(--text-muted)' }}>
        无变化
      </span>
    );
  }
  const isPositive = delta > 0;
  const color = isPositive ? 'var(--success)' : 'var(--error)';
  return (
    <span className="text-xs font-medium px-2 py-0.5 rounded" style={{ color }}>
      {isPositive ? '+' : ''}{delta.toFixed(1)}
      {deltaPercent !== undefined && (
        <span className="ml-0.5 opacity-70">
          ({isPositive ? '+' : ''}{deltaPercent.toFixed(1)}%)
        </span>
      )}
    </span>
  );
}

function DeltaInline({ delta, direction }: { delta: number; direction: 'up' | 'down' | 'stable' }) {
  if (direction === 'stable' || delta === 0) {
    return <span style={{ color: 'var(--text-muted)' }}>~</span>;
  }

  const isUp = direction === 'up';
  const color = isUp ? 'var(--success)' : 'var(--error)';
  const Icon = isUp ? RiArrowUpSLine : RiArrowDownSLine;

  return (
    <span className="inline-flex items-center gap-0.5" style={{ color }}>
      <Icon className="w-3 h-3" />
      {isUp ? '+' : ''}{delta.toFixed(1)}
    </span>
  );
}

export default ComparisonCard;
