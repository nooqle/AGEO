'use client';

import { useState, useMemo, useCallback, useEffect } from 'react';
import type { FetchResultsCanvasContent, FetchResultItem, FetchPlatformResult, FetchCitation } from '@/types/canvas';

// ---------------------------------------------------------------------------
// Types & constants
// ---------------------------------------------------------------------------

interface FetchResultsContentProps {
  content: FetchResultsCanvasContent;
}

const PLATFORM_CONFIG: Record<string, { label: string; color: string; dotColor: string }> = {
  doubao:    { label: '豆包',     color: 'var(--color-accent-cyan)',   dotColor: '#06B6D4' },
  hunyuan:   { label: '混元',     color: 'var(--color-accent-purple)', dotColor: '#A855F7' },
  kimi:      { label: 'Kimi',    color: 'var(--color-secondary)',     dotColor: '#10B981' },
  deepseek:  { label: 'DeepSeek',color: 'var(--color-primary)',       dotColor: '#6366F1' },
};

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
        borderTop: '1px solid var(--border-default)',
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
              border: '1px solid var(--border-default)',
              textDecoration: 'none',
              transition: 'border-color var(--transition-fast)',
            }}
            onMouseEnter={(e) => {
              (e.currentTarget as HTMLAnchorElement).style.borderColor = 'var(--border-hover)';
            }}
            onMouseLeave={(e) => {
              (e.currentTarget as HTMLAnchorElement).style.borderColor = 'var(--border-default)';
            }}
          >
            {/* Citation index badge */}
            <span
              style={{
                flexShrink: 0,
                width: '1.125rem',
                height: '1.125rem',
                borderRadius: '50%',
                backgroundColor: cite.is_official ? 'rgba(16,185,129,0.15)' : 'rgba(99,102,241,0.15)',
                color: cite.is_official ? 'var(--status-success)' : 'var(--color-primary-light)',
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
  if (!pr.success) {
    return (
      <div
        style={{
          padding: '1rem',
          borderRadius: 'var(--radius-md)',
          backgroundColor: 'rgba(239,68,68,0.06)',
          border: '1px solid rgba(239,68,68,0.2)',
        }}
      >
        <p
          style={{
            margin: 0,
            fontSize: '0.8125rem',
            color: 'var(--status-error)',
          }}
        >
          {pr.error || '抓取失败'}
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
              border: '1px solid var(--border-default)',
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
              border: '1px solid var(--border-default)',
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
}

function QuestionSection({ item, index, platforms, defaultExpanded = true }: QuestionSectionProps) {
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

  const [activeTab, setActiveTab] = useState<string>(availablePlatforms[0] ?? '');
  const [isExpanded, setIsExpanded] = useState(defaultExpanded);

  // 当可用平台列表变化且当前选中平台不再可用时，重置到第一个平台
  useEffect(() => {
    if (availablePlatforms.length > 0 && !availablePlatforms.includes(activeTab)) {
      setActiveTab(availablePlatforms[0]);
    }
  }, [availablePlatforms, activeTab]);

  const toggleExpand = useCallback(() => setIsExpanded((v) => !v), []);

  const activePlatformResult = activeTab ? resultsByPlatform[activeTab] : undefined;

  // Success count for this question
  const successCount = item.platform_results?.filter((pr) => pr.success).length ?? 0;
  const totalCount = item.platform_results?.length ?? 0;

  return (
    <div
      style={{
        border: '1px solid var(--border-default)',
        borderRadius: 'var(--radius-lg)',
        overflow: 'hidden',
        backgroundColor: 'var(--bg-secondary)',
      }}
    >
      {/* Question header — click to collapse/expand */}
      <button
        onClick={toggleExpand}
        style={{
          width: '100%',
          display: 'flex',
          alignItems: 'flex-start',
          gap: '0.75rem',
          padding: '0.875rem 1rem',
          background: 'none',
          border: 'none',
          cursor: 'pointer',
          textAlign: 'left',
          transition: 'background-color var(--transition-fast)',
        }}
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
          style={{
            flexShrink: 0,
            width: '1.375rem',
            height: '1.375rem',
            borderRadius: '50%',
            backgroundColor: 'var(--bg-elevated)',
            border: '1px solid var(--border-default)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            fontSize: '0.6875rem',
            fontWeight: 600,
            color: 'var(--text-secondary)',
            marginTop: '0.0625rem',
          }}
        >
          {index + 1}
        </span>

        {/* Question text */}
        <span
          style={{
            flex: 1,
            fontSize: '0.875rem',
            fontWeight: 500,
            color: 'var(--text-primary)',
            lineHeight: '1.45',
          }}
        >
          {item.question_text || item.question_id}
        </span>

        {/* Right side: success badge + chevron */}
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '0.5rem',
            flexShrink: 0,
          }}
        >
          <span
            style={{
              fontSize: '0.6875rem',
              color: successCount === totalCount ? 'var(--status-success)' : 'var(--status-warning)',
              backgroundColor:
                successCount === totalCount
                  ? 'rgba(16,185,129,0.1)'
                  : 'rgba(245,158,11,0.1)',
              padding: '0.125rem 0.5rem',
              borderRadius: 'var(--radius-full)',
              border: `1px solid ${successCount === totalCount ? 'rgba(16,185,129,0.25)' : 'rgba(245,158,11,0.25)'}`,
              whiteSpace: 'nowrap',
            }}
          >
            {successCount}/{totalCount} 平台
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
        <div id={`question-body-${item.question_id}`} style={{ borderTop: '1px solid var(--border-default)' }}>
          {/* Platform tab bar */}
          {availablePlatforms.length > 1 && (
            <div
              role="tablist"
              aria-label="平台选择"
              style={{
                display: 'flex',
                gap: '0',
                padding: '0.5rem 1rem 0',
                borderBottom: '1px solid var(--border-default)',
                backgroundColor: 'var(--bg-tertiary)',
                overflowX: 'auto',
              }}
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
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: '0.375rem',
                      padding: '0.375rem 0.75rem',
                      background: 'none',
                      border: 'none',
                      borderBottom: isActive
                        ? `2px solid ${dotColor}`
                        : '2px solid transparent',
                      cursor: 'pointer',
                      fontSize: '0.8125rem',
                      fontWeight: isActive ? 600 : 400,
                      color: isActive ? 'var(--text-primary)' : 'var(--text-muted)',
                      whiteSpace: 'nowrap',
                      transition: 'color var(--transition-fast)',
                      marginBottom: '-1px',
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
                        backgroundColor: pr?.success ? dotColor : 'var(--status-error)',
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
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '0.375rem',
                padding: '0.5rem 1rem',
                borderBottom: '1px solid var(--border-default)',
                backgroundColor: 'var(--bg-tertiary)',
              }}
            >
              <span
                style={{
                  width: '6px',
                  height: '6px',
                  borderRadius: '50%',
                  backgroundColor: resultsByPlatform[availablePlatforms[0]]?.success
                    ? getPlatformDotColor(availablePlatforms[0])
                    : 'var(--status-error)',
                }}
              />
              <span
                style={{
                  fontSize: '0.8125rem',
                  fontWeight: 600,
                  color: 'var(--text-secondary)',
                }}
              >
                {getPlatformLabel(availablePlatforms[0])}
              </span>
            </div>
          )}

          {/* Answer pane */}
          <div
            role="tabpanel"
            aria-labelledby={`tab-${item.question_id}-${activeTab}`}
            style={{ padding: '1rem' }}
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
}

function StatsPanel({ fetchResults, platforms }: StatsPanelProps) {
  const [open, setOpen] = useState(false);

  const stats = useMemo(() => {
    let total = 0;
    let success = 0;
    const platformStats: Record<string, { total: number; success: number }> = {};

    fetchResults.forEach((item) => {
      item.platform_results?.forEach((pr) => {
        total++;
        if (pr.success) success++;
        const p = pr.platform || 'unknown';
        if (!platformStats[p]) platformStats[p] = { total: 0, success: 0 };
        platformStats[p].total++;
        if (pr.success) platformStats[p].success++;
      });
    });

    return {
      total,
      success,
      failed: total - success,
      successRate: total > 0 ? Math.round((success / total) * 100) : 0,
      platformStats,
    };
  }, [fetchResults]);

  return (
    <div
      style={{
        border: '1px solid var(--border-default)',
        borderRadius: 'var(--radius-lg)',
        overflow: 'hidden',
        backgroundColor: 'var(--bg-secondary)',
      }}
    >
      {/* Toggle header */}
      <button
        onClick={() => setOpen((v) => !v)}
        style={{
          width: '100%',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          padding: '0.75rem 1rem',
          background: 'none',
          border: 'none',
          cursor: 'pointer',
          transition: 'background-color var(--transition-fast)',
        }}
        onMouseEnter={(e) => {
          (e.currentTarget as HTMLButtonElement).style.backgroundColor = 'var(--bg-tertiary)';
        }}
        onMouseLeave={(e) => {
          (e.currentTarget as HTMLButtonElement).style.backgroundColor = 'transparent';
        }}
        aria-expanded={open}
        aria-controls="stats-panel-body"
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.625rem' }}>
          <span style={{ fontSize: '0.875rem', fontWeight: 500, color: 'var(--text-secondary)' }}>
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
              border: '1px solid var(--border-default)',
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
          style={{
            borderTop: '1px solid var(--border-default)',
            padding: '1rem',
            display: 'flex',
            flexDirection: 'column',
            gap: '1rem',
          }}
        >
          {/* Overview metrics */}
          <div
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(4, 1fr)',
              gap: '0.5rem',
            }}
          >
            {[
              { label: '总抓取', value: stats.total, color: 'var(--status-info)' },
              { label: '成功', value: stats.success, color: 'var(--status-success)' },
              { label: '失败', value: stats.failed, color: 'var(--status-error)' },
              { label: '成功率', value: `${stats.successRate}%`, color: 'var(--text-primary)' },
            ].map(({ label, value, color }) => (
              <div
                key={label}
                style={{
                  padding: '0.625rem 0.75rem',
                  borderRadius: 'var(--radius-md)',
                  backgroundColor: 'var(--bg-tertiary)',
                  border: '1px solid var(--border-default)',
                  textAlign: 'center',
                }}
              >
                <div style={{ fontSize: '1.25rem', fontWeight: 700, color }}>
                  {value}
                </div>
                <div style={{ fontSize: '0.6875rem', color: 'var(--text-muted)', marginTop: '0.125rem' }}>
                  {label}
                </div>
              </div>
            ))}
          </div>

          {/* Per-platform breakdown */}
          {platforms.length > 0 && (
            <div>
              <p
                style={{
                  margin: '0 0 0.5rem',
                  fontSize: '0.75rem',
                  fontWeight: 500,
                  color: 'var(--text-muted)',
                  textTransform: 'uppercase',
                  letterSpacing: '0.05em',
                }}
              >
                平台分布
              </p>
              <div
                style={{
                  display: 'grid',
                  gridTemplateColumns: 'repeat(auto-fill, minmax(120px, 1fr))',
                  gap: '0.5rem',
                }}
              >
                {platforms.map((platform) => {
                  const ps = stats.platformStats[platform];
                  if (!ps) return null;
                  const rate = Math.round((ps.success / ps.total) * 100);
                  const dotColor = getPlatformDotColor(platform);

                  return (
                    <div
                      key={platform}
                      style={{
                        padding: '0.625rem 0.75rem',
                        borderRadius: 'var(--radius-md)',
                        backgroundColor: 'var(--bg-elevated)',
                        border: '1px solid var(--border-default)',
                      }}
                    >
                      <div
                        style={{
                          display: 'flex',
                          alignItems: 'center',
                          gap: '0.375rem',
                          marginBottom: '0.375rem',
                        }}
                      >
                        <span
                          style={{
                            width: '6px',
                            height: '6px',
                            borderRadius: '50%',
                            backgroundColor: dotColor,
                            flexShrink: 0,
                          }}
                        />
                        <span
                          style={{
                            fontSize: '0.8125rem',
                            fontWeight: 500,
                            color: 'var(--text-primary)',
                          }}
                        >
                          {getPlatformLabel(platform)}
                        </span>
                      </div>
                      <div style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>
                        {ps.success}/{ps.total} 成功
                      </div>
                      <div style={{ fontSize: '0.6875rem', color: 'var(--text-muted)' }}>
                        {rate}% 成功率
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

export function FetchResultsContent({ content }: FetchResultsContentProps) {
  const { fetchResults } = content.data;

  // All unique platforms in a stable display order
  const platforms = useMemo<string[]>(() => {
    const ORDER = ['doubao', 'hunyuan', 'kimi', 'deepseek'];
    const seen = new Set<string>();
    fetchResults?.forEach((item) => {
      item.platform_results?.forEach((pr) => {
        if (pr.platform) seen.add(pr.platform);
      });
    });
    // Return known platforms in preferred order first, then any unknowns
    const ordered = ORDER.filter((p) => seen.has(p));
    seen.forEach((p) => {
      if (!ordered.includes(p)) ordered.push(p);
    });
    return ordered;
  }, [fetchResults]);

  // Empty state
  if (!fetchResults || fetchResults.length === 0) {
    return (
      <div
        style={{
          padding: '3rem 1.5rem',
          textAlign: 'center',
          color: 'var(--text-muted)',
        }}
      >
        <p style={{ margin: 0, fontSize: '0.875rem' }}>暂无抓取结果</p>
      </div>
    );
  }

  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        height: '100%',
      }}
    >
      {/* Scrollable content area */}
      <div
        style={{
          flex: 1,
          overflowY: 'auto',
          padding: '1.25rem',
          display: 'flex',
          flexDirection: 'column',
          gap: '0.75rem',
        }}
      >
        {/* Page header */}
        <div style={{ marginBottom: '0.25rem' }}>
          <h2
            style={{
              margin: '0 0 0.25rem',
              fontSize: '1rem',
              fontWeight: 600,
              color: 'var(--text-primary)',
            }}
          >
            答案抓取结果
          </h2>
          <p style={{ margin: 0, fontSize: '0.8125rem', color: 'var(--text-muted)' }}>
            共 {fetchResults.length} 个问题，覆盖 {platforms.length} 个平台
          </p>
        </div>

        {/* Collapsible stats — secondary, placed before main content */}
        <StatsPanel fetchResults={fetchResults} platforms={platforms} />

        {/* Divider */}
        <div
          style={{
            borderBottom: '1px solid var(--border-default)',
          }}
        />

        {/* One section per question */}
        {fetchResults.map((item, idx) => (
          <QuestionSection
            key={item.question_id || idx}
            item={item}
            index={idx}
            platforms={platforms}
            defaultExpanded={true}
          />
        ))}
      </div>
    </div>
  );
}
