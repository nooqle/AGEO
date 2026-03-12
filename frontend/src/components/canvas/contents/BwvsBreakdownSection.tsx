'use client';

import { cn } from '@/lib/cn';
import type { BwvsBreakdown } from '@/types/dashboard';

/** Dimension definition for a single composite visibility axis */
interface BwvsDimension {
  key: string;
  label: string;
  weight: number;
  score: number;
  competitorScore?: number | null;
}

/** Optional competitor average breakdown */
export interface CompetitorBreakdown {
  total: number;
  mention_score: number;
  sentiment_score: number;
  coverage_score: number;
  citation_score: number;
}

interface BwvsBreakdownSectionProps {
  breakdown: BwvsBreakdown;
  overallScore: number;
  scoreBand?: string;
  competitor?: CompetitorBreakdown | null;
}

/**
 * Legacy support section for old report payloads.
 * It keeps the internal composite score readable without making it the main narrative.
 */
export function BwvsBreakdownSection({
  breakdown,
  overallScore,
  scoreBand,
  competitor,
}: BwvsBreakdownSectionProps) {
  const dimensions: BwvsDimension[] = [
    {
      key: 'mention',
      label: '提及率',
      weight: breakdown.weights.mention,
      score: breakdown.mention_score,
      competitorScore: competitor?.mention_score,
    },
    {
      key: 'sentiment',
      label: '情感倾向',
      weight: breakdown.weights.sentiment,
      score: breakdown.sentiment_score,
      competitorScore: competitor?.sentiment_score,
    },
    {
      key: 'coverage',
      label: '平台覆盖',
      weight: breakdown.weights.coverage,
      score: breakdown.coverage_score,
      competitorScore: competitor?.coverage_score,
    },
    {
      key: 'citation',
      label: '引用质量',
      weight: breakdown.weights.citation,
      score: breakdown.citation_score,
      competitorScore: competitor?.citation_score,
    },
  ];

  const hasCompetitor = competitor != null;
  const formulaText = `提及率 ${breakdown.weights.mention}% · 情感倾向 ${breakdown.weights.sentiment}% · 平台覆盖 ${breakdown.weights.coverage}% · 引用质量 ${breakdown.weights.citation}%`;

  return (
    <div
      className="rounded-xl p-5"
      style={{
        background: 'var(--bg-elevated, #2D2D2D)',
        border: '1px solid var(--border-subtle)',
      }}
    >
      <h4
        className="mb-1 text-[15px] font-semibold"
        style={{ color: 'var(--text-primary, #E5E5E5)' }}
      >
        可见度维度拆解
      </h4>
      <p
        className="mb-4 text-[13px]"
        style={{ color: 'var(--text-muted, #6B6B6B)' }}
      >
        该拆解仅用于解释内部评分维度，不作为对客户的主结论。
      </p>

      <div
        className="mb-4 flex items-center gap-4 border-b border-[var(--border-subtle)] pb-4"
      >
        <div className="text-center">
          <div
            className={cn(
              'text-4xl font-bold',
              overallScore >= 70
                ? 'text-emerald-400'
                : overallScore >= 40
                  ? 'text-amber-400'
                  : 'text-red-400'
            )}
          >
            {overallScore.toFixed(1)}
          </div>
          <div
            className="mt-1 text-[13px]"
            style={{ color: 'var(--text-secondary, #A3A3A3)' }}
          >
            {scoreBand || '内部参考'}
          </div>
        </div>

        {hasCompetitor && competitor && (
          <>
            <div
              className="text-xs"
              style={{ color: 'var(--text-muted, #6B6B6B)' }}
            >
              vs
            </div>
            <div className="text-center">
              <div
                className={cn(
                  'text-2xl font-bold',
                  competitor.total >= 70
                    ? 'text-emerald-400'
                    : competitor.total >= 40
                      ? 'text-amber-400'
                      : 'text-red-400'
                )}
                style={{ opacity: 0.7 }}
              >
                {competitor.total.toFixed(1)}
              </div>
              <div
                className="mt-1 text-[13px]"
                style={{ color: 'var(--text-tertiary, #8A8A8A)' }}
              >
                竞品参考
              </div>
            </div>
          </>
        )}
      </div>

      {hasCompetitor && (
        <div className="mb-3 flex items-center gap-4">
          <div className="flex items-center gap-1.5">
            <div
              className="h-2 w-3 rounded-sm"
              style={{ background: 'var(--info, #3B82F6)' }}
            />
            <span
              className="text-[11px]"
              style={{ color: 'var(--text-tertiary, #8A8A8A)' }}
            >
              我的品牌
            </span>
          </div>
          <div className="flex items-center gap-1.5">
            <div
              className="h-2 w-3 rounded-sm"
              style={{ background: 'var(--text-tertiary, #8A8A8A)', opacity: 0.5 }}
            />
            <span
              className="text-[11px]"
              style={{ color: 'var(--text-tertiary, #8A8A8A)' }}
            >
              竞品均值
            </span>
          </div>
        </div>
      )}

      <div className="space-y-3">
        {dimensions.map((dim) => (
          <DimensionBar key={dim.key} dimension={dim} hasCompetitor={hasCompetitor} />
        ))}
      </div>

      {breakdown.citation_note && (
        <p
          className="ml-0 mt-3 text-xs"
          style={{ color: 'var(--text-muted, #6B6B6B)' }}
        >
          * {breakdown.citation_note}
        </p>
      )}

      <div
        className="mt-4 border-t border-[var(--border-subtle)] pt-3"
        style={{
          fontFamily: 'monospace',
          fontSize: '11px',
          color: 'var(--text-disabled, #525252)',
        }}
      >
        {formulaText}
      </div>
    </div>
  );
}

function DimensionBar({
  dimension,
  hasCompetitor,
}: {
  dimension: BwvsDimension;
  hasCompetitor: boolean;
}) {
  const { label, weight, score, competitorScore } = dimension;
  const barColor = getScoreColor(score);
  const competitorBarColor = competitorScore != null ? getScoreColor(competitorScore) : undefined;

  return (
    <div>
      <div className="mb-1 flex items-center justify-between">
        <span
          className="text-[13px] font-medium"
          style={{ color: 'var(--text-primary, #E5E5E5)', width: '80px' }}
        >
          {label}
        </span>
        <span
          className="text-[11px]"
          style={{ color: 'var(--text-muted, #6B6B6B)' }}
        >
          权重 {weight}%
        </span>
      </div>

      <div className="flex items-center gap-3">
        <div className="flex-1 space-y-1">
          <div
            className="w-full overflow-hidden rounded-full"
            style={{
              height: hasCompetitor ? '8px' : '10px',
              background: 'var(--bg-tertiary, #262626)',
            }}
          >
            <div
              className="h-full rounded-full"
              style={{
                width: `${Math.min(100, score)}%`,
                backgroundColor: barColor,
                transition: 'width 500ms ease-out',
              }}
            />
          </div>

          {hasCompetitor && competitorScore != null && competitorBarColor && (
            <div
              className="w-full overflow-hidden rounded-full"
              style={{
                height: '6px',
                background: 'var(--bg-tertiary, #262626)',
              }}
            >
              <div
                className="h-full rounded-full"
                style={{
                  width: `${Math.min(100, competitorScore)}%`,
                  backgroundColor: competitorBarColor,
                  opacity: 0.45,
                  transition: 'width 500ms ease-out',
                }}
              />
            </div>
          )}
        </div>

        <div className="w-24 flex-shrink-0 text-right">
          <span
            className="text-[13px] font-semibold"
            style={{ color: 'var(--text-primary, #E5E5E5)' }}
          >
            {score.toFixed(1)}
          </span>
          {hasCompetitor && competitorScore != null && (
            <span
              className="ml-1 text-[11px]"
              style={{ color: 'var(--text-tertiary, #8A8A8A)' }}
            >
              vs {competitorScore.toFixed(1)}
            </span>
          )}
        </div>
      </div>
    </div>
  );
}

function getScoreColor(score: number): string {
  if (score >= 60) return 'var(--success, #22C55E)';
  if (score >= 30) return 'var(--warning, #F59E0B)';
  return 'var(--error, #EF4444)';
}

export default BwvsBreakdownSection;
