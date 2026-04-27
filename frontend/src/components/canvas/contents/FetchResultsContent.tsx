'use client';

import { useState, useMemo, useCallback } from 'react';
import { buildFetchExportViewModel } from '@/adapters/exportArtifacts';
import type {
  FetchResultsCanvasContent,
  FetchResultItem,
  FetchPlatformResult,
  FetchCitation,
  FetchPlatformStatusProjection,
  FetchPlatformStatusSummary,
  FetchPlatformStatusValue,
  FetchTimingSummary,
} from '@/types/canvas';
import { ReportHero, ReportMetricCard, ReportPage, ReportSection } from './ReportScaffold';

// ---------------------------------------------------------------------------
// Types & constants
// ---------------------------------------------------------------------------

interface FetchResultsContentProps {
  content: FetchResultsCanvasContent;
  printMode?: boolean;
}

const PLATFORM_CONFIG: Record<string, { label: string; color: string; dotColor: string }> = {
  doubao:    { label: '豆包',     color: 'var(--evidence-source)',    dotColor: '#4F6F88' },
  yuanbao:   { label: '元宝',     color: 'var(--evidence-secondary)', dotColor: '#7B6A4C' },
  kimi:      { label: 'Kimi',    color: 'var(--success)',            dotColor: '#3F8F62' },
  deepseek:  { label: 'DeepSeek',color: 'var(--brand-primary)',      dotColor: '#1F7A6B' },
};

const PLATFORM_ORDER = ['doubao', 'yuanbao', 'kimi', 'deepseek'] as const;

function normalizeFetchStatus(value: string | undefined): FetchPlatformStatusValue {
  const normalized = value?.trim().toLowerCase();
  if (normalized === 'success') return 'success';
  if (normalized === 'skipped') return 'skipped';
  if (normalized === 'running') return 'running';
  if (normalized === 'pending') return 'pending';
  if (normalized === 'takeover_required') return 'takeover_required';
  return 'failed';
}

function getStatusBadge(status: FetchPlatformStatusValue): {
  label: string;
  color: string;
  backgroundColor: string;
  borderColor: string;
} {
  if (status === 'success') {
    return {
      label: '成功',
      color: 'var(--status-success)',
      backgroundColor: 'rgba(16,185,129,0.10)',
      borderColor: 'rgba(16,185,129,0.22)',
    };
  }
  if (status === 'skipped') {
    return {
      label: '已跳过',
      color: 'var(--text-muted)',
      backgroundColor: 'var(--bg-elevated)',
      borderColor: 'var(--border-subtle)',
    };
  }
  if (status === 'running') {
    return {
      label: '进行中',
      color: 'var(--status-info)',
      backgroundColor: 'rgba(59,130,246,0.10)',
      borderColor: 'rgba(59,130,246,0.22)',
    };
  }
  if (status === 'pending' || status === 'takeover_required') {
    return {
      label: status === 'takeover_required' ? '待接管' : '待处理',
      color: 'var(--status-warning)',
      backgroundColor: 'rgba(245,158,11,0.10)',
      borderColor: 'rgba(245,158,11,0.22)',
    };
  }
  return {
    label: '失败',
    color: 'var(--status-error)',
    backgroundColor: 'rgba(239,68,68,0.06)',
    borderColor: 'rgba(239,68,68,0.20)',
  };
}

function getPlatformLabel(platform: string): string {
  return PLATFORM_CONFIG[platform]?.label ?? platform;
}

function getPlatformDotColor(platform: string): string {
  return PLATFORM_CONFIG[platform]?.dotColor ?? 'var(--text-muted)';
}

// ---------------------------------------------------------------------------
// Utility: extract hostname for citation display
// ---------------------------------------------------------------------------

function extractHostname(url: string): string {
  try {
    return new URL(url).hostname.replace(/^www\./, '');
  } catch {
    return url;
  }
}

// ---------------------------------------------------------------------------
// Utility: sanitise href to prevent XSS via javascript: / data: protocols
// ---------------------------------------------------------------------------

function getSafeUrl(url: string): string {
  if (!url) return '#';
  try {
    const parsed = new URL(url);
    if (parsed.protocol !== 'https:' && parsed.protocol !== 'http:') {
      return '#';
    }
    return url;
  } catch {
    return '#';
  }
}

// ---------------------------------------------------------------------------
// Sub-component: Citation list
// ---------------------------------------------------------------------------

interface CitationListProps {
  citations: FetchCitation[];
}

function CitationList({ citations }: CitationListProps) {
  if (!citations || citations.length === 0) return null;

  return (
    <div
      style={{
        marginTop: '0.75rem',
        paddingTop: '0.75rem',
        borderTop: '1px solid var(--border-subtle)',
      }}
    >
      <p
        style={{
          fontSize: '0.6875rem',
          fontWeight: 500,
          textTransform: 'uppercase',
          letterSpacing: '0.06em',
          color: 'var(--text-muted)',
          marginBottom: '0.5rem',
        }}
      >
        引用来源 ({citations.length})
      </p>
      <div style={{ display: 'flex', flexDirection: 'column', gap: '0.375rem' }}>
        {citations.map((cite) => (
          <a
            key={cite.index}
            href={getSafeUrl(cite.url)}
            target="_blank"
            rel="noopener noreferrer"
            style={{
              display: 'flex',
              alignItems: 'flex-start',
              gap: '0.5rem',
              padding: '0.375rem 0.5rem',
              borderRadius: 'var(--radius-sm)',
              backgroundColor: 'var(--bg-elevated)',
              border: '1px solid var(--border-subtle)',
              textDecoration: 'none',
              transition: 'border-color var(--transition-fast)',
            }}
            onMouseEnter={(e) => {
              (e.currentTarget as HTMLAnchorElement).style.borderColor = 'var(--border-hover)';
            }}
            onMouseLeave={(e) => {
              (e.currentTarget as HTMLAnchorElement).style.borderColor = 'var(--border-subtle)';
            }}
          >
            {/* Citation index badge */}
            <span
              style={{
                flexShrink: 0,
                width: '1.125rem',
                height: '1.125rem',
                borderRadius: '50%',
                backgroundColor: cite.is_official ? 'var(--status-success-bg)' : 'var(--status-info-bg)',
                color: cite.is_official ? 'var(--status-success)' : 'var(--status-info)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                fontSize: '0.625rem',
                fontWeight: 700,
                lineHeight: 1,
              }}
            >
              {cite.index}
            </span>

            <div style={{ flex: 1, minWidth: 0 }}>
              {/* Title */}
              <p
                style={{
                  margin: 0,
                  fontSize: '0.75rem',
                  color: 'var(--text-primary)',
                  lineHeight: '1.25',
                }}
              >
                {cite.title}
              </p>
              {/* Domain */}
              <p
                style={{
                  margin: '0.125rem 0 0',
                  fontSize: '0.6875rem',
                  color: 'var(--text-muted)',
                  lineHeight: '1.2',
                }}
              >
                {cite.site_name
                  ? `${cite.site_name} · ${extractHostname(cite.url)}`
                  : extractHostname(cite.url)}
                {cite.is_official && (
                  <span
                    style={{
                      marginLeft: '0.375rem',
                      fontSize: '0.625rem',
                      color: 'var(--status-success)',
                      fontWeight: 600,
                    }}
                  >
                    官网
                  </span>
                )}
              </p>
            </div>
          </a>
        ))}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Sub-component: Single platform answer pane
// ---------------------------------------------------------------------------

interface PlatformPaneProps {
  platformResult: FetchPlatformResult;
}

function PlatformPane({ platformResult: pr }: PlatformPaneProps) {
  const status = normalizeFetchStatus(pr.status ?? (pr.success ? 'success' : 'failed'));
  const badge = getStatusBadge(status);

  if (status !== 'success') {
    return (
      <div
        style={{
          padding: '1rem',
          borderRadius: 'var(--radius-md)',
          backgroundColor: badge.backgroundColor,
          border: `1px solid ${badge.borderColor}`,
        }}
      >
        <p
          style={{
            margin: 0,
            fontSize: '0.8125rem',
            color: badge.color,
          }}
        >
          {status === 'skipped'
            ? '该平台已跳过'
            : status === 'running'
              ? '该平台仍在抓取中'
              : status === 'pending'
                ? '该平台尚未开始处理'
                : status === 'takeover_required'
                  ? '该平台等待人工接管'
                  : pr.error || '抓取失败'}
        </p>
        {pr.duration !== undefined && (
          <p
            style={{
              margin: '0.375rem 0 0',
              fontSize: '0.6875rem',
              color: 'var(--text-muted)',
            }}
          >
            耗时 {pr.duration.toFixed(1)}s
          </p>
        )}
      </div>
    );
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '0' }}>
      {/* Answer metadata row */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: '0.75rem',
          marginBottom: '0.625rem',
          flexWrap: 'wrap',
        }}
      >
        {pr.answer?.word_count !== undefined && (
          <span
            style={{
              fontSize: '0.6875rem',
              color: 'var(--text-muted)',
              backgroundColor: 'var(--bg-elevated)',
              padding: '0.125rem 0.5rem',
              borderRadius: 'var(--radius-full)',
              border: '1px solid var(--border-subtle)',
            }}
          >
            {pr.answer.word_count} 词
          </span>
        )}
        {pr.answer?.has_brand_mention === true && (
          <span
            style={{
              fontSize: '0.6875rem',
              color: 'var(--status-success)',
              backgroundColor: 'rgba(16,185,129,0.1)',
              padding: '0.125rem 0.5rem',
              borderRadius: 'var(--radius-full)',
              border: '1px solid rgba(16,185,129,0.25)',
            }}
          >
            提及品牌
          </span>
        )}
        {pr.answer?.has_brand_mention === false && (
          <span
            style={{
              fontSize: '0.6875rem',
              color: 'var(--text-muted)',
              backgroundColor: 'var(--bg-elevated)',
              padding: '0.125rem 0.5rem',
              borderRadius: 'var(--radius-full)',
              border: '1px solid var(--border-subtle)',
            }}
          >
            未提及品牌
          </span>
        )}
        {pr.fetch_method && (
          <span
            style={{
              fontSize: '0.6875rem',
              color: 'var(--text-muted)',
            }}
          >
            via {pr.fetch_method}
          </span>
        )}
        {pr.duration !== undefined && (
          <span
            style={{
              fontSize: '0.6875rem',
              color: 'var(--text-muted)',
              marginLeft: 'auto',
            }}
          >
            {pr.duration.toFixed(1)}s
          </span>
        )}
      </div>

      {/* Full answer text — no line-clamp */}
      {pr.answer?.content ? (
        <p
          style={{
            margin: 0,
            fontSize: '0.8125rem',
            lineHeight: '1.65',
            color: 'var(--text-secondary)',
            whiteSpace: 'pre-wrap',
            wordBreak: 'break-word',
          }}
        >
          {pr.answer.content}
        </p>
      ) : (
        <p
          style={{
            margin: 0,
            fontSize: '0.8125rem',
            color: 'var(--text-muted)',
            fontStyle: 'italic',
          }}
        >
          暂无回答内容
        </p>
      )}

      {/* Citations */}
      {pr.citations && pr.citations.length > 0 && (
        <CitationList citations={pr.citations} />
      )}

      {/*
        TODO(future): answer accuracy annotation
        Placeholder for future "答案正确性标注" feature:
        - field: `answer_accuracy?: 'correct' | 'partial' | 'incorrect' | 'unverified'`
        - This will allow analysts to annotate whether the AI answer is factually correct
        - Planned as part of P2 multi-department view enhancement
      */}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Sub-component: Single question section
// ---------------------------------------------------------------------------

interface QuestionSectionProps {
  item: FetchResultItem;
  index: number;
  platforms: string[];
  defaultExpanded?: boolean;
  printMode?: boolean;
}

function QuestionSection({ item, index, platforms, defaultExpanded = true, printMode = false }: QuestionSectionProps) {
  // Build a lookup for platform results present in this question
  const resultsByPlatform = useMemo<Record<string, FetchPlatformResult>>(() => {
    const map: Record<string, FetchPlatformResult> = {};
    item.platform_results?.forEach((pr) => {
      if (pr.platform) map[pr.platform] = pr;
    });
    return map;
  }, [item.platform_results]);

  // Available platforms for this question (in display order)
  const availablePlatforms = useMemo(
    () => platforms.filter((p) => resultsByPlatform[p] !== undefined),
    [platforms, resultsByPlatform]
  );

  const [selectedTab, setActiveTab] = useState<string>('');
  const [isExpanded, setIsExpanded] = useState(defaultExpanded);

  // 当前选中的平台：优先使用用户选择的，若不在可用列表则回退到第一个
  const activeTab = availablePlatforms.includes(selectedTab) ? selectedTab : (availablePlatforms[0] ?? '');

  const toggleExpand = useCallback(() => setIsExpanded((v) => !v), []);

  const activePlatformResult = activeTab ? resultsByPlatform[activeTab] : undefined;

  // Success count for this question
  const successCount =
    item.platform_results?.filter((pr) => normalizeFetchStatus(pr.status ?? (pr.success ? 'success' : 'failed')) === 'success').length ?? 0;
  const skippedCount =
    item.platform_results?.filter((pr) => normalizeFetchStatus(pr.status ?? (pr.success ? 'success' : 'failed')) === 'skipped').length ?? 0;
  const totalCount = item.platform_results?.length ?? 0;

  if (printMode) {
    return (
      <div className="overflow-hidden rounded-[22px] border border-[var(--border-subtle)] bg-[var(--bg-elevated)]">
        <div className="flex items-start gap-3 px-5 py-4">
          <span className="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full border border-[var(--border-subtle)] bg-[var(--bg-secondary)] text-[11px] font-semibold text-[var(--text-secondary)]">
            {index + 1}
          </span>
          <div className="min-w-0 flex-1">
            <div className="text-[16px] font-semibold leading-7 text-[var(--text-primary)]">{item.question_text || item.question_id}</div>
            <div className="mt-2 flex flex-wrap items-center gap-2">
              <span
                className="whitespace-nowrap rounded-full border px-2.5 py-1 text-[11px] font-semibold"
                style={{
                  color: successCount === totalCount ? 'var(--status-success)' : 'var(--status-warning)',
                  backgroundColor:
                    successCount === totalCount
                      ? 'rgba(16,185,129,0.10)'
                      : 'rgba(245,158,11,0.10)',
                  borderColor:
                    successCount === totalCount ? 'rgba(16,185,129,0.22)' : 'rgba(245,158,11,0.22)',
                }}
              >
                {successCount}/{totalCount} 平台{skippedCount > 0 ? ` · ${skippedCount} 已跳过` : ''}
              </span>
            </div>
          </div>
        </div>

        <div className="border-t border-[var(--border-subtle)] px-5 py-5">
          <div className="space-y-5">
            {availablePlatforms.map((platform) => {
              const result = resultsByPlatform[platform];
              if (!result) {
                return null;
              }

              return (
                <section key={`${item.question_id}-${platform}`} className="rounded-[18px] border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-4 py-4">
                  <div className="flex items-center gap-2 border-b border-[var(--border-subtle)] pb-3">
                    <span
                      style={{
                        width: '6px',
                        height: '6px',
                        borderRadius: '50%',
                        backgroundColor:
                          normalizeFetchStatus(result.status ?? (result.success ? 'success' : 'failed')) === 'success'
                            ? getPlatformDotColor(platform)
                            : 'var(--status-error)',
                        flexShrink: 0,
                      }}
                    />
                    <span className="text-[13px] font-semibold text-[var(--text-secondary)]">
                      {getPlatformLabel(platform)}
                    </span>
                  </div>
                  <div className="pt-4">
                    <PlatformPane platformResult={result} />
                  </div>
                </section>
              );
            })}
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="overflow-hidden rounded-[22px] border border-[var(--border-subtle)] bg-[var(--bg-elevated)]">
      {/* Question header — click to collapse/expand */}
      <button
        onClick={toggleExpand}
        className="flex w-full items-start gap-3 bg-transparent px-5 py-4 text-left transition-colors duration-150"
        onMouseEnter={(e) => {
          (e.currentTarget as HTMLButtonElement).style.backgroundColor = 'var(--bg-tertiary)';
        }}
        onMouseLeave={(e) => {
          (e.currentTarget as HTMLButtonElement).style.backgroundColor = 'transparent';
        }}
        aria-expanded={isExpanded}
        aria-controls={`question-body-${item.question_id}`}
      >
        {/* Index badge */}
        <span
          className="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full border border-[var(--border-subtle)] bg-[var(--bg-secondary)] text-[11px] font-semibold text-[var(--text-secondary)]"
        >
          {index + 1}
        </span>

        {/* Question text */}
        <span
          className="flex-1 text-[16px] font-semibold leading-7 text-[var(--text-primary)]"
        >
          {item.question_text || item.question_id}
        </span>

        {/* Right side: success badge + chevron */}
        <div className="flex shrink-0 items-center gap-2">
          <span
            className="whitespace-nowrap rounded-full border px-2.5 py-1 text-[11px] font-semibold"
            style={{
              color: successCount === totalCount ? 'var(--status-success)' : 'var(--status-warning)',
              backgroundColor:
                successCount === totalCount
                  ? 'rgba(16,185,129,0.10)'
                  : 'rgba(245,158,11,0.10)',
              borderColor:
                successCount === totalCount ? 'rgba(16,185,129,0.22)' : 'rgba(245,158,11,0.22)',
            }}
          >
            {successCount}/{totalCount} 平台{skippedCount > 0 ? ` · ${skippedCount} 已跳过` : ''}
          </span>
          {/* Chevron icon via SVG to avoid adding deps */}
          <svg
            width="14"
            height="14"
            viewBox="0 0 14 14"
            fill="none"
            style={{
              color: 'var(--text-muted)',
              transform: isExpanded ? 'rotate(180deg)' : 'rotate(0deg)',
              transition: 'transform var(--transition-base)',
              flexShrink: 0,
            }}
          >
            <path
              d="M3.5 5.25L7 8.75L10.5 5.25"
              stroke="currentColor"
              strokeWidth="1.5"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          </svg>
        </div>
      </button>

      {/* Expanded content */}
      {isExpanded && (
        <div id={`question-body-${item.question_id}`} className="border-t border-[var(--border-subtle)]">
          {/* Platform tab bar */}
          {availablePlatforms.length > 1 && (
            <div
              role="tablist"
              aria-label="平台选择"
              className="flex overflow-x-auto border-b border-[var(--border-subtle)] bg-[var(--bg-tertiary)] px-5 pt-3"
              onKeyDown={(e) => {
                const currentIdx = availablePlatforms.indexOf(activeTab);
                if (e.key === 'ArrowRight') {
                  e.preventDefault();
                  const next = availablePlatforms[(currentIdx + 1) % availablePlatforms.length];
                  setActiveTab(next);
                } else if (e.key === 'ArrowLeft') {
                  e.preventDefault();
                  const prev = availablePlatforms[(currentIdx - 1 + availablePlatforms.length) % availablePlatforms.length];
                  setActiveTab(prev);
                }
              }}
            >
              {availablePlatforms.map((platform) => {
                const pr = resultsByPlatform[platform];
                const isActive = activeTab === platform;
                const dotColor = getPlatformDotColor(platform);

                return (
                  <button
                    key={platform}
                    id={`tab-${item.question_id}-${platform}`}
                    onClick={() => setActiveTab(platform)}
                    className="mb-[-1px] flex items-center gap-1.5 border-b-2 bg-transparent px-3 py-2 text-[13px] whitespace-nowrap transition-colors duration-150"
                    style={{
                      borderBottomColor: isActive ? dotColor : 'transparent',
                      color: isActive ? 'var(--text-primary)' : 'var(--text-muted)',
                      fontWeight: isActive ? 600 : 500,
                    }}
                    aria-selected={isActive}
                    role="tab"
                  >
                    {/* Status dot */}
                    <span
                      style={{
                        width: '6px',
                        height: '6px',
                        borderRadius: '50%',
                        backgroundColor:
                          normalizeFetchStatus(pr?.status ?? (pr?.success ? 'success' : 'failed')) === 'success'
                            ? dotColor
                            : 'var(--status-error)',
                        flexShrink: 0,
                      }}
                    />
                    {getPlatformLabel(platform)}
                  </button>
                );
              })}
            </div>
          )}

          {/* Single platform — show label inline without tabs */}
          {availablePlatforms.length === 1 && (
            <div
              className="flex items-center gap-1.5 border-b border-[var(--border-subtle)] bg-[var(--bg-tertiary)] px-5 py-3"
            >
              <span
                style={{
                  width: '6px',
                  height: '6px',
                  borderRadius: '50%',
                  backgroundColor:
                    normalizeFetchStatus(
                      resultsByPlatform[availablePlatforms[0]]?.status ??
                        (resultsByPlatform[availablePlatforms[0]]?.success ? 'success' : 'failed')
                    ) === 'success'
                      ? getPlatformDotColor(availablePlatforms[0])
                      : 'var(--status-error)',
                }}
              />
              <span
                className="text-[13px] font-semibold text-[var(--text-secondary)]"
              >
                {getPlatformLabel(availablePlatforms[0])}
              </span>
            </div>
          )}

          {/* Answer pane */}
          <div
            role="tabpanel"
            aria-labelledby={`tab-${item.question_id}-${activeTab}`}
            className="px-5 py-5"
          >
            {activePlatformResult ? (
              <PlatformPane platformResult={activePlatformResult} />
            ) : (
              <p
                style={{
                  margin: 0,
                  fontSize: '0.8125rem',
                  color: 'var(--text-muted)',
                  fontStyle: 'italic',
                }}
              >
                该平台暂无数据
              </p>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Sub-component: Collapsible stats panel
// ---------------------------------------------------------------------------

interface StatsPanelProps {
  fetchResults: FetchResultItem[];
  platforms: string[];
  successCount: number;
  failedCount: number;
  skippedCount: number;
  platformStatus?: FetchPlatformStatusProjection;
  timingSummary?: FetchTimingSummary;
  printMode?: boolean;
}

function StatsPanel({
  fetchResults,
  platforms,
  successCount,
  failedCount,
  skippedCount,
  platformStatus,
  timingSummary,
  printMode = false,
}: StatsPanelProps) {
  const [open, setOpen] = useState(false);

  const stats = useMemo(() => {
    let total = 0;
    const platformStats: Record<string, { total: number; success: number; skipped: number; status?: FetchPlatformStatusValue; totalMs?: number }> = {};

    fetchResults.forEach((item) => {
      item.platform_results?.forEach((pr) => {
        total++;
        const p = pr.platform || 'unknown';
        if (!platformStats[p]) {
          platformStats[p] = { total: 0, success: 0, skipped: 0 };
        }
        platformStats[p].total++;
        const status = normalizeFetchStatus(pr.status ?? (pr.success ? 'success' : 'failed'));
        if (status === 'success') platformStats[p].success++;
        if (status === 'skipped') platformStats[p].skipped++;
      });
    });

    platformStatus?.platforms?.forEach((summary) => {
      const platform = summary.platform;
      const existing = platformStats[platform] || { total: 0, success: 0, skipped: 0 };
      platformStats[platform] = {
        ...existing,
        total: summary.questions_total ?? existing.total,
        success: summary.questions_completed ?? existing.success,
        status: normalizeFetchStatus(summary.status),
        totalMs: typeof summary.timing?.total_ms === 'number' ? summary.timing.total_ms : existing.totalMs,
      };
    });

    Object.entries(timingSummary?.platforms || {}).forEach(([platform, timing]) => {
      const existing = platformStats[platform] || { total: 0, success: 0, skipped: 0 };
      platformStats[platform] = {
        ...existing,
        totalMs: typeof timing.total_ms === 'number' ? timing.total_ms : existing.totalMs,
      };
    });

    return {
      total,
      success: successCount,
      failed: failedCount,
      skipped: skippedCount,
      successRate: total > 0 ? Math.round((successCount / total) * 100) : 0,
      platformStats,
    };
  }, [failedCount, fetchResults, platformStatus?.platforms, skippedCount, successCount, timingSummary?.platforms]);

  if (printMode) {
    return (
      <div className="overflow-hidden rounded-[22px] border border-[var(--border-subtle)] bg-[var(--bg-secondary)]">
        <div className="flex items-center justify-between px-5 py-4">
          <div className="flex items-center gap-2.5">
            <span className="text-[15px] font-semibold text-[var(--text-secondary)]">数据统计</span>
            <span
              style={{
                fontSize: '0.6875rem',
                color: 'var(--status-success)',
                backgroundColor: 'rgba(16,185,129,0.1)',
                padding: '0.125rem 0.5rem',
                borderRadius: 'var(--radius-full)',
                border: '1px solid rgba(16,185,129,0.2)',
              }}
            >
              {stats.successRate}% 成功率
            </span>
            <span
              style={{
                fontSize: '0.6875rem',
                color: 'var(--text-muted)',
                backgroundColor: 'var(--bg-elevated)',
                padding: '0.125rem 0.5rem',
                borderRadius: 'var(--radius-full)',
                border: '1px solid var(--border-subtle)',
              }}
            >
              {stats.total} 次抓取
            </span>
          </div>
        </div>

        <div className="flex flex-col gap-4 border-t border-[var(--border-subtle)] px-5 py-5">
          <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
            {[
              { label: '总抓取', value: stats.total, color: 'var(--status-info)' },
              { label: '成功', value: stats.success, color: 'var(--status-success)' },
              { label: '已跳过', value: stats.skipped, color: 'var(--text-muted)' },
              { label: '失败', value: stats.failed, color: 'var(--status-error)' },
            ].map(({ label, value, color }) => (
              <div key={label}>
                <ReportMetricCard
                  label={label}
                  value={<span style={{ color }}>{value}</span>}
                  accent="rgba(148,163,184,0.06)"
                />
              </div>
            ))}
          </div>

          {platforms.length > 0 ? (
            <div>
              <p className="mb-2 text-[12px] font-medium tracking-[0.12em] text-[var(--text-tertiary)]">
                平台分布
              </p>
              <div className="grid gap-2 sm:grid-cols-2 xl:grid-cols-4">
                {platforms.map((platform) => {
                  const ps = stats.platformStats[platform];
                  if (!ps) return null;
                  const rate = Math.round((ps.success / ps.total) * 100);
                  const dotColor = getPlatformDotColor(platform);

                  return (
                    <div
                      key={platform}
                      className="rounded-[18px] border border-[var(--border-subtle)] bg-[var(--bg-elevated)] px-4 py-3"
                    >
                      <div className="mb-1.5 flex items-center gap-1.5">
                        <span
                          style={{
                            width: '6px',
                            height: '6px',
                            borderRadius: '50%',
                            backgroundColor: dotColor,
                            flexShrink: 0,
                          }}
                        />
                        <span className="text-[14px] font-semibold text-[var(--text-primary)]">
                          {getPlatformLabel(platform)}
                        </span>
                      </div>
                      <div className="text-[13px] text-[var(--text-secondary)]">
                        {ps.success}/{ps.total} 成功
                      </div>
                      <div className="text-[12px] text-[var(--text-tertiary)]">
                        {ps.skipped > 0 ? `已跳过 ${ps.skipped} · ` : ''}{rate}% 成功率
                        {typeof ps.totalMs === 'number' ? ` · ${(ps.totalMs / 1000).toFixed(1)}s` : ''}
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          ) : null}
        </div>
      </div>
    );
  }

  return (
    <div className="overflow-hidden rounded-[22px] border border-[var(--border-subtle)] bg-[var(--bg-secondary)]">
      {/* Toggle header */}
      <button
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center justify-between bg-transparent px-5 py-4 transition-colors duration-150"
        onMouseEnter={(e) => {
          (e.currentTarget as HTMLButtonElement).style.backgroundColor = 'var(--bg-tertiary)';
        }}
        onMouseLeave={(e) => {
          (e.currentTarget as HTMLButtonElement).style.backgroundColor = 'transparent';
        }}
        aria-expanded={open}
        aria-controls="stats-panel-body"
      >
        <div className="flex items-center gap-2.5">
          <span className="text-[15px] font-semibold text-[var(--text-secondary)]">
            数据统计
          </span>
          {/* Quick summary chips */}
          <span
            style={{
              fontSize: '0.6875rem',
              color: 'var(--status-success)',
              backgroundColor: 'rgba(16,185,129,0.1)',
              padding: '0.125rem 0.5rem',
              borderRadius: 'var(--radius-full)',
              border: '1px solid rgba(16,185,129,0.2)',
            }}
          >
            {stats.successRate}% 成功率
          </span>
          <span
            style={{
              fontSize: '0.6875rem',
              color: 'var(--text-muted)',
              backgroundColor: 'var(--bg-elevated)',
              padding: '0.125rem 0.5rem',
              borderRadius: 'var(--radius-full)',
              border: '1px solid var(--border-subtle)',
            }}
          >
            {stats.total} 次抓取
          </span>
        </div>
        <svg
          width="14"
          height="14"
          viewBox="0 0 14 14"
          fill="none"
          style={{
            color: 'var(--text-muted)',
            transform: open ? 'rotate(180deg)' : 'rotate(0deg)',
            transition: 'transform var(--transition-base)',
          }}
        >
          <path
            d="M3.5 5.25L7 8.75L10.5 5.25"
            stroke="currentColor"
            strokeWidth="1.5"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </svg>
      </button>

      {/* Stats detail */}
      {open && (
        <div
          id="stats-panel-body"
          className="flex flex-col gap-4 border-t border-[var(--border-subtle)] px-5 py-5"
        >
          {/* Overview metrics */}
          <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
            {[
              { label: '总抓取', value: stats.total, color: 'var(--status-info)' },
              { label: '成功', value: stats.success, color: 'var(--status-success)' },
              { label: '已跳过', value: stats.skipped, color: 'var(--text-muted)' },
              { label: '失败', value: stats.failed, color: 'var(--status-error)' },
            ].map(({ label, value, color }) => (
              <div key={label}>
                <ReportMetricCard
                  label={label}
                  value={<span style={{ color }}>{value}</span>}
                  accent="rgba(148,163,184,0.06)"
                />
              </div>
            ))}
          </div>

          {/* Per-platform breakdown */}
          {platforms.length > 0 && (
            <div>
              <p className="mb-2 text-[12px] font-medium tracking-[0.12em] text-[var(--text-tertiary)]">
                平台分布
              </p>
              <div className="grid gap-2 sm:grid-cols-2 xl:grid-cols-4">
                {platforms.map((platform) => {
                  const ps = stats.platformStats[platform];
                  if (!ps) return null;
                  const rate = Math.round((ps.success / ps.total) * 100);
                  const dotColor = getPlatformDotColor(platform);

                  return (
                    <div
                      key={platform}
                      className="rounded-[18px] border border-[var(--border-subtle)] bg-[var(--bg-elevated)] px-4 py-3"
                    >
                      <div className="mb-1.5 flex items-center gap-1.5">
                        <span
                          style={{
                            width: '6px',
                            height: '6px',
                            borderRadius: '50%',
                            backgroundColor: dotColor,
                            flexShrink: 0,
                          }}
                        />
                        <span className="text-[14px] font-semibold text-[var(--text-primary)]">
                          {getPlatformLabel(platform)}
                        </span>
                      </div>
                      <div className="text-[13px] text-[var(--text-secondary)]">
                        {ps.success}/{ps.total} 成功
                      </div>
                      <div className="text-[12px] text-[var(--text-tertiary)]">
                        {ps.skipped > 0 ? `已跳过 ${ps.skipped} · ` : ''}{rate}% 成功率
                        {typeof ps.totalMs === 'number' ? ` · ${(ps.totalMs / 1000).toFixed(1)}s` : ''}
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export function FetchResultsContent({ content, printMode = false }: FetchResultsContentProps) {
  const view = useMemo(() => buildFetchExportViewModel(content), [content]);
  const fetchResults = view.items;

  // All unique platforms in a stable display order
  const platforms = useMemo<string[]>(() => {
    const seen = new Set<string>();
    view.platformStatus?.platforms?.forEach((summary) => {
      seen.add(summary.platform);
    });
    Object.keys(view.platformStatus?.platform_statuses || {}).forEach((platform) => {
      seen.add(platform);
    });
    fetchResults?.forEach((item) => {
      item.platform_results?.forEach((pr) => {
        if (pr.platform) seen.add(pr.platform);
      });
    });
    // Return known platforms in preferred order first, then any unknowns
    const ordered: string[] = [...PLATFORM_ORDER.filter((p) => seen.has(p))];
    seen.forEach((p) => {
      if (!ordered.includes(p)) {
        ordered.push(p);
      }
    });
    return ordered;
  }, [fetchResults, view.platformStatus?.platform_statuses, view.platformStatus?.platforms]);

  // Empty state
  if (!fetchResults || fetchResults.length === 0) {
    return (
      <ReportPage>
        <ReportSection eyebrow="抓取结果">
          <div className="py-10 text-center text-[14px] text-[var(--text-tertiary)]">暂无抓取结果</div>
        </ReportSection>
      </ReportPage>
    );
  }

  return (
    <ReportPage>
      <ReportHero
        eyebrow="抓取结果"
        title={content.title || view.title || 'AI答案抓取结果'}
        meta={
          <>
            <span>共 {fetchResults.length} 个问题</span>
            <span>覆盖 {platforms.length} 个平台</span>
            {typeof view.timingSummary?.total_ms === 'number' && (
              <span>总耗时 {(view.timingSummary.total_ms / 1000).toFixed(1)}s</span>
            )}
          </>
        }
      />

      <ReportSection eyebrow="抓取概览">
        <StatsPanel
          fetchResults={fetchResults}
          platforms={platforms}
          successCount={view.successCount}
          failedCount={view.failedCount}
          skippedCount={view.skippedCount}
          platformStatus={view.platformStatus}
          timingSummary={view.timingSummary}
          printMode={printMode}
        />
      </ReportSection>

      <ReportSection eyebrow="逐题查看" title="按问题查看各平台回答">
        <div className="space-y-4">
          {fetchResults.map((item, idx) => (
            <QuestionSection
              key={item.question_id || idx}
              item={item}
              index={idx}
              platforms={platforms}
              defaultExpanded={true}
              printMode={printMode}
            />
          ))}
        </div>
      </ReportSection>
    </ReportPage>
  );
}

