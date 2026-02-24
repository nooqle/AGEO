'use client';

import { RiSearchEyeLine } from '@remixicon/react';
import { cn } from '@/lib/cn';
import { MarkdownContent } from './Message/MarkdownContent';

interface FocusCardProps {
  title: string;
  /** Structured key-value pairs for metrics display */
  stats?: { label: string; value: string | number }[];
  /** Markdown/plain-text analysis body */
  content: string;
  className?: string;
}

export function FocusCard({ title, stats, content, className }: FocusCardProps) {
  return (
    <div
      role="article"
      aria-label={`聚焦分析: ${title}`}
      className={cn(
        'rounded-[10px] my-1.5 animate-slide-up',
        className
      )}
      style={{
        background: 'var(--bg-secondary)',
        borderLeft: '2px solid var(--info, #3B82F6)',
        boxShadow: '0 1px 3px rgba(0,0,0,0.2)',
        padding: '14px 18px',
      }}
    >
      {/* Header */}
      <div className="flex items-center gap-2 mb-2.5">
        <RiSearchEyeLine className="w-4 h-4 flex-shrink-0" style={{ color: 'var(--info)' }} />
        <h4 className="text-[13px] font-semibold" style={{ color: 'var(--text-primary)' }}>
          {title}
        </h4>
      </div>

      {/* Stats row */}
      {stats && stats.length > 0 && (
        <div className="flex flex-wrap gap-x-4 gap-y-1 mb-3">
          {stats.map((stat, i) => (
            <div key={i} className="text-xs min-w-[80px]" style={{ color: 'var(--text-secondary)' }}>
              <div className="flex items-center gap-1.5">
                <span>{stat.label}</span>
                <span className="font-semibold" style={{ color: 'var(--text-primary)' }}>
                  {typeof stat.value === 'number' ? stat.value.toFixed(1) : stat.value}
                </span>
              </div>
              {typeof stat.value === 'number' && (
                <div className="mt-0.5 h-[3px] rounded-full w-16" style={{ background: 'var(--border-default)' }}>
                  <div
                    className="h-full rounded-full transition-all duration-500"
                    style={{
                      width: `${Math.min(Math.max(Number(stat.value), 0), 100)}%`,
                      background: Number(stat.value) >= 60 ? 'var(--success)' : Number(stat.value) >= 30 ? 'var(--warning)' : 'var(--error)',
                    }}
                  />
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      {/* Body content — full Markdown rendering via MarkdownContent */}
      <div className="focus-card-body text-xs leading-relaxed [&_.markdown-content_p]:text-xs [&_.markdown-content_p]:leading-relaxed [&_.markdown-content_li]:text-xs [&_.markdown-content_h3]:text-xs [&_.markdown-content_h3]:font-semibold [&_.markdown-content_h2]:text-[13px]">
        <MarkdownContent content={content} />
      </div>
    </div>
  );
}

export default FocusCard;
