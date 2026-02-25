'use client';

import { cn } from '@/lib/cn';
import type { BwvsBreakdown } from '@/types/dashboard';

/** Dimension definition for a single BWVS scoring axis */
interface BwvsDimension {
  key: string;
  label: string;
  weight: number;  // percentage, e.g. 40
  score: number;   // 0-100
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
 * BwvsBreakdownSection renders the four BWVS v2 dimensions as horizontal bars
 * with optional competitor comparison using grouped (side-by-side) bars.
 *
 * Placement: inside ReportContent "overview" tab, below the Score Card.
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

  // Build formula display string
  const formulaText = `BWVS = ${breakdown.mention_score.toFixed(1)}x${(breakdown.weights.mention / 100).toFixed(2)} + ${breakdown.sentiment_score.toFixed(1)}x${(breakdown.weights.sentiment / 100).toFixed(2)} + ${breakdown.coverage_score.toFixed(1)}x${(breakdown.weights.coverage / 100).toFixed(2)} + ${breakdown.citation_score.toFixed(1)}x${(breakdown.weights.citation / 100).toFixed(2)} = ${overallScore.toFixed(1)}`;

  return (
    <div
      className="p-5 rounded-xl"
      style={{
        background: 'var(--bg-secondary, #1A1A1A)',
        border: '1px solid var(--border-default, #262626)',
      }}
    >
      {/* Section title */}
      <h4
        className="text-[15px] font-semibold mb-1"
        style={{ color: 'var(--text-primary, #E5E5E5)' }}
      >
        BWVS 指数构成
      </h4>
      <p
        className="text-[13px] mb-4"
        style={{ color: 'var(--text-muted, #6B6B6B)' }}
      >
        {breakdown.formula}
      </p>

      {/* Overall score header */}
      <div
        className="flex items-center gap-4 pb-4 mb-4"
        style={{ borderBottom: '1px solid var(--border-default, #262626)' }}
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
            className="text-[13px] mt-1"
            style={{ color: 'var(--text-secondary, #A3A3A3)' }}
          >
            {scoreBand || (overallScore >= 70 ? '优秀' : overallScore >= 40 ? '良好' : '需改进')}
          </div>
        </div>

        {hasCompetitor && (
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
                className="text-[13px] mt-1"
                style={{ color: 'var(--text-tertiary, #8A8A8A)' }}
              >
                竞品均值
              </div>
            </div>
          </>
        )}
      </div>

      {/* Legend for competitor mode */}
      {hasCompetitor && (
        <div className="flex items-center gap-4 mb-3">
          <div className="flex items-center gap-1.5">
            <div
              className="w-3 h-2 rounded-sm"
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
              className="w-3 h-2 rounded-sm"
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

      {/* Dimension bars */}
      <div className="space-y-3">
        {dimensions.map((dim) => (
          <DimensionBar
            key={dim.key}
            dimension={dim}
            hasCompetitor={hasCompetitor}
          />
        ))}
      </div>

      {/* Citation note */}
      {breakdown.citation_note && (
        <p
          className="text-xs mt-3 ml-0"
          style={{ color: 'var(--text-muted, #6B6B6B)' }}
        >
          * {breakdown.citation_note}
        </p>
      )}

      {/* Formula row */}
      <div
        className="mt-4 pt-3"
        style={{
          borderTop: '1px solid var(--border-default, #262626)',
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

/** Single dimension horizontal bar (with optional competitor side-by-side) */
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
      {/* Label row */}
      <div className="flex items-center justify-between mb-1">
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

      {/* Bar(s) + score value */}
      <div className="flex items-center gap-3">
        <div className="flex-1 space-y-1">
          {/* Brand bar */}
          <div
            className="w-full rounded-full overflow-hidden"
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

          {/* Competitor bar (grouped, side-by-side) */}
          {hasCompetitor && competitorScore != null && (
            <div
              className="w-full rounded-full overflow-hidden"
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

        {/* Score values */}
        <div className="w-24 text-right flex-shrink-0">
          <span
            className="text-[13px] font-semibold"
            style={{ color: 'var(--text-primary, #E5E5E5)' }}
          >
            {score.toFixed(1)}
          </span>
          {hasCompetitor && competitorScore != null && (
            <span
              className="text-[11px] ml-1"
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

/**
 * Returns the CSS color for a score value:
 * >= 60: success green
 * 30-59: warning amber
 * < 30: error red
 */
function getScoreColor(score: number): string {
  if (score >= 60) return 'var(--success, #22C55E)';
  if (score >= 30) return 'var(--warning, #F59E0B)';
  return 'var(--error, #EF4444)';
}

export default BwvsBreakdownSection;
