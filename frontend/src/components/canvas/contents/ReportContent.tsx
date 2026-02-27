'use client';

import { useState } from 'react';
import { cn } from '@/lib/cn';
import type { ReportCanvasContent, CitationAnalysis, KeywordAnalysis } from '@/types/canvas';
import type { BwvsBreakdown } from '@/types/dashboard';
import { BwvsBreakdownSection } from './BwvsBreakdownSection';
import type { CompetitorBreakdown } from './BwvsBreakdownSection';
import { WordCloudSection } from './WordCloudSection';
import { PLATFORM_NAMES, PLATFORM_COLORS } from '@/config/platforms';

interface ReportContentProps {
  content: ReportCanvasContent;
}

type TabId = 'overview' | 'industry' | 'platforms' | 'competitors' | 'citations' | 'semantics' | 'recommendations' | 'risks';

const TABS: { id: TabId; label: string }[] = [
  { id: 'overview', label: '总览' },
  { id: 'industry', label: '行业洞察' },
  { id: 'platforms', label: '平台分析' },
  { id: 'competitors', label: '竞品对比' },
  { id: 'citations', label: '信息源分析' },
  { id: 'semantics', label: '语义词云' },
  { id: 'recommendations', label: '优化建议' },
  { id: 'risks', label: '风险提示' },
];

function formatMetricValue(value: unknown): string {
  if (value === null || value === undefined) return '--';
  if (typeof value === 'string' || typeof value === 'number' || typeof value === 'boolean') {
    return String(value);
  }
  if (typeof value === 'object' && 'value' in (value as Record<string, unknown>)) {
    return formatMetricValue((value as Record<string, unknown>).value);
  }
  if (Array.isArray(value)) {
    return value.map(formatMetricValue).join(', ');
  }
  try {
    return JSON.stringify(value);
  } catch {
    return '--';
  }
}

export function ReportContent({ content }: ReportContentProps) {
  const data = content.data;
  const [activeTab, setActiveTab] = useState<TabId>('overview');

  // Extended data from A5 artifact
  const ext = data as Record<string, unknown>;
  const keyFindings = Array.isArray(ext.key_findings) ? ext.key_findings as string[] : [];
  // Structured strength/weakness items (new format) or plain strings (legacy)
  interface StrengthItem { title: string; scenario?: string; platforms?: string[]; evidence?: string; eeat_factor?: string }
  interface WeaknessItem { title: string; scenario?: string; platforms?: string[]; evidence?: string; improvement_hint?: string }
  const strengths: (string | StrengthItem)[] = Array.isArray(ext.strengths) ? ext.strengths : [];
  const weaknesses: (string | WeaknessItem)[] = Array.isArray(ext.weaknesses) ? ext.weaknesses : [];

  // Actionable recommendations from core prompt (richer than supplementary)
  const actionableRecs = Array.isArray(ext.actionable_recommendations)
    ? ext.actionable_recommendations as Array<Record<string, unknown>>
    : [];
  const opportunities = Array.isArray(ext.opportunities) ? ext.opportunities as string[] : [];
  const threats = Array.isArray(ext.threats) ? ext.threats as string[] : [];
  const actionPlan = (ext.action_plan || {}) as Record<string, string[]>;
  const platformBreakdown = (ext.platform_breakdown || {}) as Record<string, Record<string, number>>;
  const sentimentDist = (ext.sentiment_distribution || {}) as Record<string, number>;

  // Industry insights (new in Cycle 2) — nested under ext.industry_insights
  const industryInsights = (ext.industry_insights && typeof ext.industry_insights === 'object')
    ? ext.industry_insights as Record<string, unknown> : null;
  const industryBackground = industryInsights && typeof industryInsights.background === 'string'
    ? industryInsights.background as string : null;
  const industryTrends = industryInsights && Array.isArray(industryInsights.trends)
    ? industryInsights.trends as unknown[] : [];
  const industryOpportunities = industryInsights && Array.isArray(industryInsights.opportunities)
    ? industryInsights.opportunities as unknown[] : [];

  // Platform analysis details (new in Cycle 2)
  const platformAnalysis = Array.isArray(ext.platform_analysis)
    ? ext.platform_analysis as Array<Record<string, unknown>>
    : [];

  // Competitor comparison matrix (new in Cycle 2) — nested under ext.competitor_deep_analysis
  const competitorDeep = (ext.competitor_deep_analysis && typeof ext.competitor_deep_analysis === 'object')
    ? ext.competitor_deep_analysis as Record<string, unknown> : null;
  const competitorMatrix = competitorDeep && Array.isArray(competitorDeep.comparison_matrix)
    ? competitorDeep.comparison_matrix as Array<Record<string, unknown>> : [];
  const competitorOverview = competitorDeep && typeof competitorDeep.overview === 'string'
    ? competitorDeep.overview as string : null;
  const differentiationStrategy = competitorDeep && typeof competitorDeep.differentiation_strategy === 'string'
    ? competitorDeep.differentiation_strategy as string : null;

  // Risk items (new in Cycle 2) — field name: risk_alerts
  const risks = Array.isArray(ext.risk_alerts)
    ? ext.risk_alerts as Array<Record<string, unknown>>
    : [];

  // Delta vs previous snapshot (new in Cycle 2)
  const deltaPrev = (ext.delta_vs_previous && typeof ext.delta_vs_previous === 'object')
    ? ext.delta_vs_previous as Record<string, { value: number; direction: 'up' | 'down' | 'stable' }>
    : null;

  // BWVS v2 breakdown data
  const bwvsBreakdown = (ext.bwvs_breakdown && typeof ext.bwvs_breakdown === 'object')
    ? ext.bwvs_breakdown as unknown as BwvsBreakdown
    : null;

  // Competitor breakdown (if available)
  const competitorBreakdown = (() => {
    if (!ext.competitor_bwvs || typeof ext.competitor_bwvs !== 'object') return null;
    const comp = ext.competitor_bwvs as Record<string, unknown>;
    if (typeof comp.total !== 'number') return null;
    return comp as unknown as CompetitorBreakdown;
  })();

  // Degradation note (if A5 used fallback report)
  const degradationNote = typeof ext._degradation_note === 'string' ? ext._degradation_note : null;

  // Citation analysis data (new Tab)
  const citationAnalysis = (ext.citation_analysis && typeof ext.citation_analysis === 'object')
    ? ext.citation_analysis as CitationAnalysis : null;

  // Keyword analysis data (semantics Tab)
  const keywordAnalysis = (ext.keyword_analysis && typeof ext.keyword_analysis === 'object'
    && (ext.keyword_analysis as KeywordAnalysis).total_keywords > 0)
    ? ext.keyword_analysis as KeywordAnalysis : null;

  const handleTabKeyDown = (e: React.KeyboardEvent) => {
    const tabIds = TABS.map(t => t.id);
    const currentIndex = tabIds.indexOf(activeTab);
    if (e.key === 'ArrowRight') {
      e.preventDefault();
      const next = (currentIndex + 1) % tabIds.length;
      setActiveTab(tabIds[next]);
    } else if (e.key === 'ArrowLeft') {
      e.preventDefault();
      const prev = (currentIndex - 1 + tabIds.length) % tabIds.length;
      setActiveTab(tabIds[prev]);
    } else if (e.key === 'Home') {
      e.preventDefault();
      setActiveTab(tabIds[0]);
    } else if (e.key === 'End') {
      e.preventDefault();
      setActiveTab(tabIds[tabIds.length - 1]);
    }
  };

  const isBaseline = content.category === 'baseline';

  return (
    <div className="p-6 space-y-6">
      {/* Header */}
      {data.headline && (
        <div>
          <div className="flex items-center gap-2 mb-1">
            <h1 className="text-xl font-bold text-[var(--text-primary)]">{data.headline}</h1>
            {isBaseline && (
              <span className="px-1.5 py-0.5 text-xs font-medium rounded bg-violet-500/15 text-violet-300 border border-violet-500/30">
                基线
              </span>
            )}
          </div>
          {data.subtitle && (
            <p className="text-[15px] text-[var(--text-secondary)]">{data.subtitle}</p>
          )}
        </div>
      )}

      {/* Tab Navigation */}
      <div
        role="tablist"
        onKeyDown={handleTabKeyDown}
        className="flex gap-1 border-b border-[var(--border-subtle)] pb-0 overflow-x-auto"
      >
        {TABS.map((tab) => (
          <button
            key={tab.id}
            id={`tab-${tab.id}`}
            role="tab"
            aria-selected={activeTab === tab.id}
            aria-controls={`tabpanel-${tab.id}`}
            tabIndex={activeTab === tab.id ? 0 : -1}
            onClick={() => setActiveTab(tab.id)}
            className={cn(
              'px-3 py-2 text-sm font-medium transition-colors border-b-2 -mb-px whitespace-nowrap',
              activeTab === tab.id
                ? 'text-[#6366F1] border-[#6366F1]'
                : 'text-[var(--text-secondary)] border-transparent hover:text-[var(--text-primary)]'
            )}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* ====== OVERVIEW TAB ====== */}
      {activeTab === 'overview' && (
        <div role="tabpanel" id={`tabpanel-${activeTab}`} aria-labelledby={`tab-${activeTab}`} className="space-y-6">
          {/* Score Card */}
          {data.overallScore !== undefined && (
            <div className="flex items-center gap-6 p-5 bg-[var(--bg-elevated)] border border-[var(--border-subtle)] rounded-xl">
              <div className="text-center">
                <div className={cn(
                  'text-4xl font-bold',
                  data.overallScore >= 70 ? 'text-emerald-400' :
                  data.overallScore >= 40 ? 'text-amber-400' : 'text-red-400'
                )}>
                  {typeof data.overallScore === 'number' ? data.overallScore.toFixed(1) : data.overallScore}
                </div>
                <div className="text-[13px] text-[var(--text-secondary)] mt-1">BWVS 指数</div>

                {/* Delta vs previous (Step 9) */}
                {deltaPrev?.bwvs_index ? (
                  <div className={cn(
                    'text-[13px] mt-1 font-medium',
                    deltaPrev.bwvs_index.direction === 'up' ? 'text-[#22C55E]' :
                    deltaPrev.bwvs_index.direction === 'down' ? 'text-[#EF4444]' :
                    'text-[var(--text-tertiary)]'
                  )}>
                    {deltaPrev.bwvs_index.direction === 'up' ? '+' : ''}
                    {(deltaPrev.bwvs_index.value ?? 0).toFixed(1)} vs 上次
                  </div>
                ) : data.overallScore !== undefined && !deltaPrev && (
                  <div className="text-xs text-[var(--text-disabled)] mt-1 italic">首次分析</div>
                )}
              </div>
              <div className="flex-1">
                <div className="text-[15px] font-medium text-[var(--text-primary)] mb-1">{data.scoreBand}</div>
                <div className="w-full h-2 bg-[var(--bg-tertiary)] rounded-full overflow-hidden">
                  <div
                    className={cn(
                      'h-full rounded-full transition-all',
                      data.overallScore >= 70 ? 'bg-emerald-500' :
                      data.overallScore >= 40 ? 'bg-amber-500' : 'bg-red-500'
                    )}
                    style={{ width: `${Math.min(100, data.overallScore)}%` }}
                  />
                </div>
              </div>
            </div>
          )}

          {/* Degradation notice */}
          {degradationNote && (
            <div
              className="flex items-start gap-2 p-3 rounded-lg text-[13px]"
              style={{
                background: 'rgba(245, 158, 11, 0.08)',
                border: '1px solid rgba(245, 158, 11, 0.2)',
                color: 'var(--text-secondary, #A3A3A3)',
              }}
            >
              <span style={{ color: 'var(--warning, #F59E0B)' }}>*</span>
              <span>{degradationNote}</span>
            </div>
          )}

          {/* BWVS Breakdown */}
          {bwvsBreakdown && data.overallScore !== undefined && (
            <BwvsBreakdownSection
              breakdown={bwvsBreakdown}
              overallScore={data.overallScore}
              scoreBand={data.scoreBand}
              competitor={competitorBreakdown}
            />
          )}

          {/* Metrics Grid */}
          {data.metrics && (
            <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
              {Object.entries(data.metrics).map(([key, value]) => (
                <div key={key} className="p-3 bg-[var(--bg-elevated)] border border-[var(--border-subtle)] rounded-lg">
                  <div className="text-[13px] text-[var(--text-secondary)]">
                    {typeof value === 'object' && value !== null && 'label' in value
                      ? (value as { label?: string }).label || key : key}
                  </div>
                  <div className="text-lg font-semibold text-[var(--text-primary)] mt-0.5">
                    {formatMetricValue(value)}
                  </div>
                </div>
              ))}
            </div>
          )}

          {/* Sentiment Distribution */}
          {Object.keys(sentimentDist).length > 0 && (
            <div className="p-4 bg-[var(--bg-elevated)] border border-[var(--border-subtle)] rounded-lg">
              <h4 className="text-[15px] font-medium text-[var(--text-primary)] mb-3">情感分布</h4>
              <div className="flex gap-4">
                {Object.entries(sentimentDist).map(([key, val]) => (
                  <div key={key} className="flex items-center gap-2">
                    <div className={cn(
                      'w-3 h-3 rounded-full',
                      key === 'positive' ? 'bg-emerald-500' :
                      key === 'negative' ? 'bg-red-500' : 'bg-[var(--text-tertiary)]'
                    )} />
                    <span className="text-[13px] text-[var(--text-secondary)]">
                      {key === 'positive' ? '正面' : key === 'negative' ? '负面' : '中性'}: {val}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Key Findings */}
          {keyFindings.length > 0 && (
            <div>
              <h4 className="text-[15px] font-medium text-[var(--text-primary)] mb-3">关键发现</h4>
              <div className="space-y-2">
                {keyFindings.map((finding, i) => (
                  <div key={i} className="flex items-start gap-2 p-3 bg-[var(--bg-elevated)] border border-[var(--border-subtle)] rounded-lg">
                    <span className="text-[#6366F1] text-[15px] mt-0.5">&bull;</span>
                    <span className="text-[15px] text-[var(--text-primary)]">{finding}</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Executive Summary */}
          {data.content && (
            <div className="p-4 bg-[var(--bg-elevated)] border border-[var(--border-subtle)] rounded-lg">
              <h4 className="text-[15px] font-medium text-[var(--text-primary)] mb-2">执行摘要</h4>
              <p className="text-[15px] text-[var(--text-primary)] leading-relaxed whitespace-pre-wrap">{data.content}</p>
            </div>
          )}

          {/* Legacy: insights from old format */}
          {data.insights && data.insights.length > 0 && keyFindings.length === 0 && (
            <div>
              <h4 className="text-[15px] font-medium text-[var(--text-primary)] mb-3">关键发现</h4>
              <div className="space-y-2">
                {data.insights.map((insight, index) => (
                  <div key={index} className="flex items-start gap-2 p-3 bg-[var(--bg-elevated)] border border-[var(--border-subtle)] rounded-lg">
                    <span className="text-[15px]">
                      {insight.type === 'strength' ? '  ' : insight.type === 'weakness' ? '! ' : '* '}
                    </span>
                    <div>
                      <div className="text-[15px] font-medium text-[var(--text-primary)]">{insight.title}</div>
                      {insight.description && insight.description !== insight.title && (
                        <div className="text-[13px] text-[var(--text-secondary)] mt-0.5">{insight.description}</div>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {/* ====== INDUSTRY TAB ====== */}
      {activeTab === 'industry' && (
        <div role="tabpanel" id={`tabpanel-${activeTab}`} aria-labelledby={`tab-${activeTab}`} className="space-y-4">
          {industryBackground ? (
            <>
              <div className="p-4 bg-[var(--bg-elevated)] border border-[var(--border-subtle)] rounded-lg">
                <h4 className="text-[15px] font-medium text-[var(--text-primary)] mb-2">行业背景</h4>
                <p className="text-[15px] text-[var(--text-primary)] leading-relaxed whitespace-pre-wrap">{industryBackground}</p>
              </div>

              {industryTrends.length > 0 && (
                <div>
                  <h4 className="text-[15px] font-medium text-[var(--text-primary)] mb-3">行业趋势</h4>
                  <div className="space-y-2">
                    {industryTrends.map((item, i) => {
                      const trendText = typeof item === 'string' ? item
                        : (item && typeof item === 'object' && 'trend' in item) ? String((item as Record<string, unknown>).trend) : String(item);
                      const sourceText = (item && typeof item === 'object' && 'source' in item)
                        ? String((item as Record<string, unknown>).source) : null;
                      return (
                        <div key={i} className="flex items-start gap-2 p-3 bg-[var(--bg-elevated)] border border-[var(--border-subtle)] rounded-lg">
                          <span className="text-[#3B82F6] text-[15px] mt-0.5">&bull;</span>
                          <div className="flex-1 min-w-0">
                            <span className="text-[15px] text-[var(--text-primary)]">{trendText}</span>
                            {sourceText && (
                              <span className="text-[13px] text-[var(--text-tertiary)] ml-2">— {sourceText}</span>
                            )}
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </div>
              )}

              {industryOpportunities.length > 0 && (
                <div>
                  <h4 className="text-[15px] font-medium text-[var(--text-primary)] mb-3">机会点</h4>
                  <div className="space-y-2">
                    {industryOpportunities.map((item, i) => {
                      const oppText = typeof item === 'string' ? item
                        : (item && typeof item === 'object') ? String((item as Record<string, unknown>).opportunity || (item as Record<string, unknown>).text || JSON.stringify(item)) : String(item);
                      return (
                        <div key={i} className="flex items-start gap-2 p-3 bg-[var(--bg-elevated)] border border-[var(--border-subtle)] rounded-lg">
                          <span className="text-[#22C55E] text-[15px] mt-0.5">&bull;</span>
                          <span className="text-[15px] text-[var(--text-primary)]">{oppText}</span>
                        </div>
                      );
                    })}
                  </div>
                </div>
              )}

              <div
                className="p-3 rounded-lg text-[13px]"
                style={{
                  background: 'rgba(99, 102, 241, 0.06)',
                  border: '1px solid rgba(99, 102, 241, 0.15)',
                  color: 'var(--text-tertiary, #8A8A8A)',
                }}
              >
                * 行业洞察基于 AI 分析结果生成，仅供参考，不构成投资或商业决策建议。
              </div>
            </>
          ) : (
            <EmptyState text="暂无行业洞察数据，完成分析后将自动生成" />
          )}
        </div>
      )}

      {/* ====== PLATFORMS TAB ====== */}
      {activeTab === 'platforms' && (
        <div role="tabpanel" id={`tabpanel-${activeTab}`} aria-labelledby={`tab-${activeTab}`} className="space-y-4">
          {/* Enhanced per-platform analysis cards */}
          {platformAnalysis.length > 0 ? (
            <div className="space-y-3">
              {platformAnalysis.map((pa, i) => {
                const name = String(pa.platform || pa.name || `Platform ${i + 1}`);
                const mentionRate = typeof pa.mention_rate === 'number' ? pa.mention_rate : null;
                const sentiment = typeof pa.sentiment === 'number' ? pa.sentiment : null;
                const totalQ = typeof pa.total_questions === 'number' ? pa.total_questions : 0;
                const mentions = typeof pa.mentions === 'number' ? pa.mentions : 0;
                const summary = typeof pa.summary === 'string' ? pa.summary : null;
                const status = typeof pa.status === 'string' ? pa.status : 'success';

                return (
                  <div key={i} className="p-4 bg-[var(--bg-elevated)] border border-[var(--border-subtle)] rounded-lg">
                    <div className="flex items-center justify-between mb-3">
                      <span className="text-[15px] font-medium text-[var(--text-primary)] capitalize">{name}</span>
                      <span className={cn(
                        'text-xs px-2 py-0.5 rounded-full',
                        status === 'success' ? 'bg-emerald-500/10 text-emerald-400' :
                        status === 'failed' ? 'bg-red-500/10 text-red-400' :
                        'bg-[var(--text-tertiary)]/10 text-[var(--text-tertiary)]'
                      )}>
                        {status === 'success' ? '成功' : status === 'failed' ? '失败' : status}
                      </span>
                    </div>
                    <div className="grid grid-cols-3 gap-3 mb-3">
                      <div>
                        <div className="text-xs text-[var(--text-tertiary)]">提及率</div>
                        <div className="text-sm font-semibold text-[var(--text-primary)]">
                          {mentionRate !== null ? `${(mentionRate * 100).toFixed(0)}%` : '--'}
                        </div>
                      </div>
                      <div>
                        <div className="text-xs text-[var(--text-tertiary)]">情感得分</div>
                        <div className="text-sm font-semibold text-[var(--text-primary)]">
                          {sentiment !== null ? sentiment.toFixed(1) : '--'}
                        </div>
                      </div>
                      <div>
                        <div className="text-xs text-[var(--text-tertiary)]">提及/总数</div>
                        <div className="text-sm font-semibold text-[var(--text-primary)]">
                          {mentions}/{totalQ}
                        </div>
                      </div>
                    </div>
                    {summary && (
                      <p className="text-[13px] text-[var(--text-secondary)] leading-relaxed">{summary}</p>
                    )}
                    {/* LLM descriptive content: optimization tips */}
                    {Array.isArray(pa.optimization_tips) && pa.optimization_tips.length > 0 && (
                      <div className="mt-3 pt-3 border-t border-[var(--border-subtle)]">
                        <div className="text-xs font-medium text-violet-400 mb-1.5">优化建议</div>
                        <ul className="space-y-1">
                          {(pa.optimization_tips as string[]).map((tip, ti) => (
                            <li key={ti} className="text-[13px] text-[var(--text-secondary)] flex items-start gap-1.5">
                              <span className="mt-1.5 w-1 h-1 rounded-full bg-violet-400 flex-shrink-0" />
                              {tip}
                            </li>
                          ))}
                        </ul>
                      </div>
                    )}
                    {/* LLM descriptive content: strengths & weaknesses */}
                    {(Array.isArray(pa.strengths) && pa.strengths.length > 0 || Array.isArray(pa.weaknesses) && (pa.weaknesses as unknown[]).length > 0) && (
                      <div className="mt-2 flex flex-wrap gap-1.5">
                        {Array.isArray(pa.strengths) && (pa.strengths as string[]).map((s, si) => (
                          <span key={`s-${si}`} className="text-xs px-1.5 py-0.5 rounded bg-emerald-500/10 text-emerald-400">{s}</span>
                        ))}
                        {Array.isArray(pa.weaknesses) && (pa.weaknesses as string[]).map((w, wi) => (
                          <span key={`w-${wi}`} className="text-xs px-1.5 py-0.5 rounded bg-red-500/10 text-red-400">{w}</span>
                        ))}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          ) : Object.keys(platformBreakdown).length > 0 ? (
            /* Fallback: legacy platform breakdown */
            <div className="space-y-3">
              {Object.entries(platformBreakdown).map(([platform, stats]) => {
                const total = stats.total || 0;
                const mentions = stats.mentions || 0;
                const success = stats.success || 0;
                const mentionRate = total > 0 ? (mentions / total * 100) : 0;
                return (
                  <div key={platform} className="p-4 bg-[var(--bg-elevated)] border border-[var(--border-subtle)] rounded-lg">
                    <div className="flex items-center justify-between mb-2">
                      <span className="text-[15px] font-medium text-[var(--text-primary)] capitalize">{platform}</span>
                      <span className="text-[13px] text-[var(--text-secondary)]">{success}/{total} 成功</span>
                    </div>
                    <div className="flex items-center gap-4">
                      <div className="flex-1">
                        <div className="w-full h-2 bg-[var(--bg-tertiary)] rounded-full overflow-hidden">
                          <div
                            className="h-full bg-[#6366F1] rounded-full"
                            style={{ width: `${mentionRate}%` }}
                          />
                        </div>
                      </div>
                      <span className="text-[15px] font-medium text-[var(--text-secondary)] w-16 text-right">
                        {mentionRate.toFixed(0)}%
                      </span>
                    </div>
                  </div>
                );
              })}
            </div>
          ) : (
            <EmptyState text="暂无平台分析数据" />
          )}
        </div>
      )}

      {/* ====== COMPETITORS TAB ====== */}
      {activeTab === 'competitors' && (
        <div role="tabpanel" id={`tabpanel-${activeTab}`} aria-labelledby={`tab-${activeTab}`} className="space-y-4">
          {/* Competitor overview */}
          {competitorOverview && (
            <div className="p-4 bg-[var(--bg-elevated)] border border-[var(--border-subtle)] rounded-lg">
              <h4 className="text-[15px] font-medium text-[var(--text-primary)] mb-2">竞品概览</h4>
              <p className="text-[15px] text-[var(--text-primary)] leading-relaxed whitespace-pre-wrap">{competitorOverview}</p>
            </div>
          )}

          {/* Competitor comparison matrix */}
          {competitorMatrix.length > 0 ? (
            <>
            <div className="overflow-x-auto">
              <table className="w-full text-[13px] border-collapse">
                <thead>
                  <tr className="border-b border-[var(--border-subtle)]">
                    <th className="text-left py-2 px-3 text-[var(--text-secondary)] font-medium">品牌</th>
                    <th className="text-right py-2 px-3 text-[var(--text-secondary)] font-medium">BWVS</th>
                    <th className="text-right py-2 px-3 text-[var(--text-secondary)] font-medium">提及率</th>
                    <th className="text-right py-2 px-3 text-[var(--text-secondary)] font-medium">情感</th>
                    <th className="text-right py-2 px-3 text-[var(--text-secondary)] font-medium">覆盖度</th>
                  </tr>
                </thead>
                <tbody>
                  {competitorMatrix.map((row, i) => {
                    const isSelf = row.is_self === true;
                    return (
                      <tr
                        key={i}
                        className={cn(
                          'border-b border-[var(--border-subtle)]',
                          isSelf && 'bg-[#6366F1]/5'
                        )}
                      >
                        <td className={cn('py-2 px-3 font-medium', isSelf ? 'text-[#6366F1]' : 'text-[var(--text-primary)]')}>
                          {String(row.name || row.brand || '')}
                          {isSelf && <span className="ml-1 text-xs text-[#6366F1]">(你)</span>}
                        </td>
                        <td className="text-right py-2 px-3 text-[var(--text-primary)]">
                          {typeof row.bwvs === 'number' ? row.bwvs.toFixed(1) : '--'}
                        </td>
                        <td className="text-right py-2 px-3 text-[var(--text-primary)]">
                          {typeof row.mention_rate === 'number' ? `${(row.mention_rate * 100).toFixed(0)}%` : '--'}
                        </td>
                        <td className="text-right py-2 px-3 text-[var(--text-primary)]">
                          {typeof row.sentiment === 'number' ? row.sentiment.toFixed(1) : '--'}
                        </td>
                        <td className="text-right py-2 px-3 text-[var(--text-primary)]">
                          {typeof row.coverage === 'number' ? `${(row.coverage * 100).toFixed(0)}%` : '--'}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          {/* Competitor detail cards */}
          {competitorMatrix.filter(r => !r.is_self).some(r => r.vs_brand || r.advantage_reasons || r.learnings) && (
            <div className="space-y-3 mt-4">
              <h4 className="text-[15px] font-medium text-[var(--text-primary)]">竞品详情</h4>
              {competitorMatrix.filter(r => !r.is_self).map((row, i) => {
                const hasDetail = row.vs_brand || Array.isArray(row.advantage_reasons) || Array.isArray(row.learnings);
                if (!hasDetail) return null;
                return (
                  <div key={i} className="p-4 bg-[var(--bg-elevated)] border border-[var(--border-subtle)] rounded-lg">
                    <div className="flex items-center gap-2 mb-2">
                      <span className="text-[15px] font-medium text-[var(--text-primary)]">{String(row.name || row.brand || '')}</span>
                      {typeof row.vs_brand === 'string' && (
                        <span className="text-xs px-1.5 py-0.5 rounded bg-violet-500/10 text-violet-400">{row.vs_brand}</span>
                      )}
                    </div>
                    {Array.isArray(row.advantage_reasons) && (row.advantage_reasons as string[]).length > 0 && (
                      <div className="mb-2">
                        <div className="text-xs text-[var(--text-tertiary)] mb-1">竞争优势</div>
                        <ul className="space-y-0.5">
                          {(row.advantage_reasons as string[]).map((r, ri) => (
                            <li key={ri} className="text-[13px] text-[var(--text-secondary)] flex items-start gap-1.5">
                              <span className="mt-1.5 w-1 h-1 rounded-full bg-amber-400 flex-shrink-0" />
                              {r}
                            </li>
                          ))}
                        </ul>
                      </div>
                    )}
                    {Array.isArray(row.learnings) && (row.learnings as string[]).length > 0 && (
                      <div>
                        <div className="text-xs text-[var(--text-tertiary)] mb-1">可借鉴</div>
                        <ul className="space-y-0.5">
                          {(row.learnings as string[]).map((l, li) => (
                            <li key={li} className="text-[13px] text-[var(--text-secondary)] flex items-start gap-1.5">
                              <span className="mt-1.5 w-1 h-1 rounded-full bg-blue-400 flex-shrink-0" />
                              {l}
                            </li>
                          ))}
                        </ul>
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          )}
          </>
          ) : (strengths.length > 0 || weaknesses.length > 0 || opportunities.length > 0 || threats.length > 0) ? (
            /* Fallback: SWOT Analysis */
            <div className="grid grid-cols-2 gap-3">
              <SwotCard title="优势" items={strengths.map(s => typeof s === 'string' ? s : s.title)} color="emerald" icon="S" />
              <SwotCard title="劣势" items={weaknesses.map(w => typeof w === 'string' ? w : w.title)} color="red" icon="W" />
              <SwotCard title="机会" items={opportunities} color="blue" icon="O" />
              <SwotCard title="威胁" items={threats} color="amber" icon="T" />
            </div>
          ) : (
            <EmptyState text="暂无竞品分析数据" />
          )}

          {/* Differentiation strategy */}
          {differentiationStrategy && (
            <div className="p-4 bg-[var(--bg-elevated)] border border-[var(--border-subtle)] rounded-lg">
              <h4 className="text-[15px] font-medium text-[var(--text-primary)] mb-2">差异化策略</h4>
              <p className="text-[15px] text-[var(--text-primary)] leading-relaxed whitespace-pre-wrap">{differentiationStrategy}</p>
            </div>
          )}
        </div>
      )}

      {/* ====== RECOMMENDATIONS TAB ====== */}
      {activeTab === 'recommendations' && (
        <div role="tabpanel" id={`tabpanel-${activeTab}`} aria-labelledby={`tab-${activeTab}`} className="space-y-6">

          {/* Section 1: Brand Strengths */}
          {strengths.length > 0 && (
            <div>
              <h4 className="text-[15px] font-medium text-[var(--text-primary)] mb-3">品牌优势</h4>
              <div className="space-y-3">
                {strengths.map((s, i) => {
                  const isStructured = typeof s === 'object' && s !== null;
                  const item = isStructured ? s as StrengthItem : null;
                  return (
                    <div
                      key={i}
                      className="p-4 bg-[var(--bg-elevated)] rounded-lg border-l-2"
                      style={{
                        borderLeftColor: '#22C55E',
                        borderTop: '1px solid var(--border-subtle)',
                        borderRight: '1px solid var(--border-subtle)',
                        borderBottom: '1px solid var(--border-subtle)',
                      }}
                    >
                      <div className="flex items-center gap-2 mb-1.5">
                        <span className="text-[15px] font-medium text-[var(--text-primary)]">
                          {item ? item.title : String(s)}
                        </span>
                        {item?.eeat_factor && (
                          <span className="text-xs px-1.5 py-0.5 rounded bg-emerald-500/15 text-emerald-400 font-medium">
                            {item.eeat_factor}
                          </span>
                        )}
                      </div>
                      {item && (
                        <>
                          {item.scenario && (
                            <div className="flex items-center gap-1.5 mb-1.5">
                              <span className="text-[13px] text-[var(--text-tertiary)]">场景:</span>
                              <span className="text-[13px] text-[var(--text-secondary)]">{item.scenario}</span>
                            </div>
                          )}
                          {item.platforms && item.platforms.length > 0 && (
                            <div className="flex items-center gap-1.5 mb-1.5">
                              <span className="text-[13px] text-[var(--text-tertiary)]">平台:</span>
                              <div className="flex gap-1 flex-wrap">
                                {item.platforms.map((p, pi) => (
                                  <span key={pi} className="text-xs px-1.5 py-0.5 rounded bg-[var(--bg-tertiary)] text-[var(--text-secondary)]">{p}</span>
                                ))}
                              </div>
                            </div>
                          )}
                          {item.evidence && (
                            <p className="text-[13px] text-[var(--text-secondary)] leading-relaxed mt-1">{item.evidence}</p>
                          )}
                        </>
                      )}
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {/* Section 2: Weaknesses / Areas to Improve */}
          {weaknesses.length > 0 && (
            <div>
              <h4 className="text-[15px] font-medium text-[var(--text-primary)] mb-3">待改进项</h4>
              <div className="space-y-3">
                {weaknesses.map((w, i) => {
                  const isStructured = typeof w === 'object' && w !== null;
                  const item = isStructured ? w as WeaknessItem : null;
                  return (
                    <div
                      key={i}
                      className="p-4 bg-[var(--bg-elevated)] rounded-lg border-l-2"
                      style={{
                        borderLeftColor: '#F59E0B',
                        borderTop: '1px solid var(--border-subtle)',
                        borderRight: '1px solid var(--border-subtle)',
                        borderBottom: '1px solid var(--border-subtle)',
                      }}
                    >
                      <span className="text-[15px] font-medium text-[var(--text-primary)]">
                        {item ? item.title : String(w)}
                      </span>
                      {item && (
                        <>
                          {item.scenario && (
                            <div className="flex items-center gap-1.5 mt-1.5">
                              <span className="text-[13px] text-[var(--text-tertiary)]">场景:</span>
                              <span className="text-[13px] text-[var(--text-secondary)]">{item.scenario}</span>
                            </div>
                          )}
                          {item.platforms && item.platforms.length > 0 && (
                            <div className="flex items-center gap-1.5 mt-1.5">
                              <span className="text-[13px] text-[var(--text-tertiary)]">平台:</span>
                              <div className="flex gap-1 flex-wrap">
                                {item.platforms.map((p, pi) => (
                                  <span key={pi} className="text-xs px-1.5 py-0.5 rounded bg-[var(--bg-tertiary)] text-[var(--text-secondary)]">{p}</span>
                                ))}
                              </div>
                            </div>
                          )}
                          {item.evidence && (
                            <p className="text-[13px] text-[var(--text-secondary)] leading-relaxed mt-1.5">{item.evidence}</p>
                          )}
                          {item.improvement_hint && (
                            <div className="mt-2 pt-2 border-t border-[var(--border-subtle)]">
                              <span className="text-[13px] text-[#6366F1] font-medium">改进方向: </span>
                              <span className="text-[13px] text-[var(--text-secondary)]">{item.improvement_hint}</span>
                            </div>
                          )}
                        </>
                      )}
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {/* Section 3: EEAT Action Plan */}
          {data.recommendations && data.recommendations.length > 0 ? (
            <div>
              <h4 className="text-[15px] font-medium text-[var(--text-primary)] mb-3">EEAT 行动方案</h4>
              <div className="space-y-3">
                {data.recommendations.map((rec, index) => {
                  const priorityColor = rec.priority === 1
                    ? '#EF4444'
                    : rec.priority === 2
                    ? '#F59E0B'
                    : '#22C55E';
                  return (
                    <div
                      key={index}
                      className="p-4 bg-[var(--bg-elevated)] rounded-lg border-l-2"
                      style={{
                        borderLeftColor: priorityColor,
                        borderTop: '1px solid var(--border-subtle)',
                        borderRight: '1px solid var(--border-subtle)',
                        borderBottom: '1px solid var(--border-subtle)',
                      }}
                    >
                      <div className="flex items-center gap-2 mb-2">
                        <span className={cn(
                          'text-xs font-bold px-2 py-0.5 rounded',
                          rec.priority === 1 ? 'bg-red-500/20 text-red-400' :
                          rec.priority === 2 ? 'bg-amber-500/20 text-amber-400' :
                          'bg-emerald-500/20 text-emerald-400'
                        )}>
                          P{rec.priority}
                        </span>
                        <span className="text-[15px] font-medium text-[var(--text-primary)]">{rec.title}</span>
                        {rec.eeat_dimension && (
                          <span className="text-xs px-1.5 py-0.5 rounded bg-violet-500/15 text-violet-400 font-medium">
                            {rec.eeat_dimension}
                          </span>
                        )}
                      </div>
                      {rec.rationale && (
                        <p className="text-[13px] text-[var(--text-primary)] leading-relaxed mb-2">{rec.rationale}</p>
                      )}
                      {/* EEAT detail fields */}
                      {(rec.current_strength || rec.expected_impact || rec.difficulty || rec.timeline) && (
                        <div className="grid grid-cols-2 gap-x-4 gap-y-1.5 mt-2 pt-2 border-t border-[var(--border-subtle)]">
                          {rec.current_strength && (
                            <div>
                              <span className="text-xs text-[var(--text-tertiary)]">当前优势</span>
                              <p className="text-[13px] text-[var(--text-secondary)]">{rec.current_strength}</p>
                            </div>
                          )}
                          {rec.expected_impact && (
                            <div>
                              <span className="text-xs text-[var(--text-tertiary)]">预期效果</span>
                              <p className="text-[13px] text-[var(--text-secondary)]">{rec.expected_impact}</p>
                            </div>
                          )}
                          {rec.difficulty && (
                            <div>
                              <span className="text-xs text-[var(--text-tertiary)]">难度</span>
                              <p className="text-[13px] text-[var(--text-secondary)]">{rec.difficulty}</p>
                            </div>
                          )}
                          {rec.timeline && (
                            <div>
                              <span className="text-xs text-[var(--text-tertiary)]">时间线</span>
                              <p className="text-[13px] text-[var(--text-secondary)]">{rec.timeline}</p>
                            </div>
                          )}
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            </div>
          ) : strengths.length === 0 && weaknesses.length === 0 ? (
            <EmptyState text="暂无优化建议" />
          ) : null}

          {/* Action Plan */}
          {Object.keys(actionPlan).length > 0 && (
            <div>
              <h4 className="text-[15px] font-medium text-[var(--text-primary)] mb-3">行动计划</h4>
              <div className="space-y-3">
                {actionPlan.short_term && actionPlan.short_term.length > 0 && (
                  <ActionPlanSection title="短期 (1-3个月)" items={actionPlan.short_term} color="emerald" />
                )}
                {actionPlan.medium_term && actionPlan.medium_term.length > 0 && (
                  <ActionPlanSection title="中期 (3-6个月)" items={actionPlan.medium_term} color="blue" />
                )}
                {actionPlan.long_term && actionPlan.long_term.length > 0 && (
                  <ActionPlanSection title="长期 (6-12个月)" items={actionPlan.long_term} color="violet" />
                )}
              </div>
            </div>
          )}
        </div>
      )}

      {/* ====== CITATIONS TAB ====== */}
      {activeTab === 'citations' && (
        <div role="tabpanel" id={`tabpanel-${activeTab}`} aria-labelledby={`tab-${activeTab}`} className="space-y-6">
          {citationAnalysis && citationAnalysis.total_citations > 0 ? (
            <>
              {/* A. Hero Card: Official citation rate */}
              <div className="p-5 bg-[var(--bg-elevated)] border border-[var(--border-subtle)] rounded-xl">
                <div className="flex items-center gap-6">
                  <div className="text-center min-w-[100px]">
                    <div className={cn(
                      'text-4xl font-bold',
                      (citationAnalysis.official_share ?? 0) >= 30 ? 'text-emerald-400' :
                      (citationAnalysis.official_share ?? 0) >= 10 ? 'text-amber-400' : 'text-red-400'
                    )}>
                      {(citationAnalysis.official_share ?? 0).toFixed(1)}%
                    </div>
                    <div className="text-[13px] text-[var(--text-secondary)] mt-1">官网引用占比</div>
                  </div>
                  <div className="flex-1 space-y-2">
                    <div className="grid grid-cols-3 gap-3">
                      <div className="text-center p-2 rounded-lg" style={{ backgroundColor: 'rgba(99,102,241,0.06)' }}>
                        <div className="text-lg font-bold text-[var(--text-primary)]">{citationAnalysis.total_citations}</div>
                        <div className="text-[11px] text-[var(--text-tertiary)]">总引用数</div>
                      </div>
                      <div className="text-center p-2 rounded-lg" style={{ backgroundColor: 'rgba(99,102,241,0.06)' }}>
                        <div className="text-lg font-bold text-[var(--text-primary)]">{citationAnalysis.unique_domains}</div>
                        <div className="text-[11px] text-[var(--text-tertiary)]">独立域名</div>
                      </div>
                      <div className="text-center p-2 rounded-lg" style={{ backgroundColor: 'rgba(99,102,241,0.06)' }}>
                        <div className="text-lg font-bold text-[var(--text-primary)]">{citationAnalysis.official_citations}</div>
                        <div className="text-[11px] text-[var(--text-tertiary)]">官网引用</div>
                      </div>
                    </div>
                    {/* Progress bar */}
                    <div className="flex items-center gap-2">
                      <div className="flex-1 h-2 rounded-full bg-[var(--bg-tertiary)] overflow-hidden">
                        <div
                          className={cn(
                            'h-full rounded-full transition-all',
                            citationAnalysis.official_share >= 30 ? 'bg-emerald-400' :
                            citationAnalysis.official_share >= 10 ? 'bg-amber-400' : 'bg-red-400'
                          )}
                          style={{ width: `${Math.min(citationAnalysis.official_share, 100)}%` }}
                        />
                      </div>
                      <span className="text-[11px] text-[var(--text-tertiary)] w-16 text-right">
                        {citationAnalysis.brand_domain || '未配置'}
                      </span>
                    </div>
                  </div>
                </div>
                <p className="text-[11px] text-[var(--text-tertiary)] mt-3 leading-relaxed">
                  AI 平台在回答用户问题时，引用您官网内容的比例。比例越高，说明您的官方内容被 AI 认可为权威来源的程度越高。
                </p>
              </div>

              {/* B. Top 10 Domain Ranking */}
              {citationAnalysis.top_domains.length > 0 && (
                <div>
                  <h3 className="text-[15px] font-medium text-[var(--text-primary)] mb-3">引用来源排行</h3>
                  <div className="space-y-2">
                    {citationAnalysis.top_domains.map((item, i) => (
                      <div
                        key={item.domain}
                        className="flex items-center gap-3 p-3 bg-[var(--bg-elevated)] border border-[var(--border-subtle)] rounded-lg"
                      >
                        <span className={cn(
                          'w-6 h-6 rounded-full flex items-center justify-center text-xs font-bold flex-shrink-0',
                          i < 3 ? 'bg-[#6366F1]/20 text-[#6366F1]' : 'bg-[var(--bg-tertiary)] text-[var(--text-tertiary)]'
                        )}>
                          {i + 1}
                        </span>
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-2">
                            <span className="text-[13px] font-medium text-[var(--text-primary)] truncate">{item.domain}</span>
                            {item.is_official && (
                              <span className="text-[10px] font-bold px-1.5 py-0.5 rounded bg-emerald-500/10 text-emerald-400 flex-shrink-0">
                                官方
                              </span>
                            )}
                          </div>
                          <div className="flex items-center gap-2 mt-1">
                            <div className="flex-1 h-1.5 rounded-full bg-[var(--bg-tertiary)] overflow-hidden">
                              <div
                                className={cn('h-full rounded-full', item.is_official ? 'bg-emerald-400' : 'bg-[#6366F1]')}
                                style={{ width: `${Math.min(item.share, 100)}%` }}
                              />
                            </div>
                            <span className="text-[11px] text-[var(--text-tertiary)] w-20 text-right flex-shrink-0">
                              {item.count}次 ({(item.share ?? 0).toFixed(1)}%)
                            </span>
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* C. Per-platform citation stats */}
              {Object.keys(citationAnalysis.platform_citation_stats).length > 0 && (
                <div>
                  <h3 className="text-[15px] font-medium text-[var(--text-primary)] mb-3">各平台引用能力</h3>
                  <div className="grid grid-cols-2 gap-3">
                    {Object.entries(citationAnalysis.platform_citation_stats).map(([platform, stats]) => {
                      const platformNames = PLATFORM_NAMES;
                      const dotColors = PLATFORM_COLORS;
                      return (
                        <div
                          key={platform}
                          className="p-3 bg-[var(--bg-elevated)] border border-[var(--border-subtle)] rounded-lg"
                        >
                          <div className="flex items-center gap-2 mb-2">
                            <span className="w-2 h-2 rounded-full flex-shrink-0" style={{ backgroundColor: dotColors[platform] || '#6366F1' }} />
                            <span className="text-[13px] font-medium text-[var(--text-primary)]">{platformNames[platform] || platform}</span>
                          </div>
                          {stats.total_citations > 0 ? (
                            <div className="space-y-1.5">
                              <div className="flex justify-between text-[11px]">
                                <span className="text-[var(--text-tertiary)]">引用总数</span>
                                <span className="text-[var(--text-primary)] font-medium">{stats.total_citations}</span>
                              </div>
                              <div className="flex justify-between text-[11px]">
                                <span className="text-[var(--text-tertiary)]">独立域名</span>
                                <span className="text-[var(--text-primary)] font-medium">{stats.unique_domains}</span>
                              </div>
                              <div className="flex justify-between text-[11px]">
                                <span className="text-[var(--text-tertiary)]">官网引用</span>
                                <span className="text-[var(--text-primary)] font-medium">{stats.official_count ?? 0} ({(stats.official_share ?? 0).toFixed(1)}%)</span>
                              </div>
                              {stats.top_domains && stats.top_domains.length > 0 && (
                                <div className="mt-1.5 pt-1.5" style={{ borderTop: '1px solid var(--border-subtle)' }}>
                                  <div className="text-[10px] text-[var(--text-tertiary)] mb-1">Top 引用源</div>
                                  {stats.top_domains.slice(0, 3).map((d) => (
                                    <div key={d.domain} className="flex justify-between text-[10px] text-[var(--text-secondary)]">
                                      <span className="truncate">{d.domain}</span>
                                      <span className="flex-shrink-0 ml-2">{d.count}</span>
                                    </div>
                                  ))}
                                </div>
                              )}
                            </div>
                          ) : (
                            <p className="text-[11px] text-[var(--text-tertiary)]">该平台未返回引用信息</p>
                          )}
                        </div>
                      );
                    })}
                  </div>
                </div>
              )}

              {/* D. Data note */}
              <div
                className="p-3 rounded-lg text-[11px] text-[var(--text-tertiary)] leading-relaxed"
                style={{ backgroundColor: 'rgba(99,102,241,0.06)', border: '1px solid rgba(99,102,241,0.15)' }}
              >
                {citationAnalysis.note || '引用数据基于各 AI 平台回答中的参考来源提取。不同平台的引用能力差异较大：Kimi 和豆包通过 API 获取结构化引用，数据较完整；DeepSeek 通过浏览器抓取，覆盖率可能较低。'}
              </div>
            </>
          ) : (
            <EmptyState text={citationAnalysis ? '本次分析未检测到引用来源数据' : '暂无引用来源数据，完成分析后将自动生成'} />
          )}
        </div>
      )}

      {/* ====== SEMANTICS TAB ====== */}
      {activeTab === 'semantics' && (
        <div role="tabpanel" id={`tabpanel-${activeTab}`} aria-labelledby={`tab-${activeTab}`} className="space-y-6">
          {keywordAnalysis ? (
            <WordCloudSection analysis={keywordAnalysis} />
          ) : (
            <EmptyState text="暂无语义分析数据，完成分析后将自动生成" />
          )}
        </div>
      )}

      {/* ====== RISKS TAB ====== */}
      {activeTab === 'risks' && (
        <div role="tabpanel" id={`tabpanel-${activeTab}`} aria-labelledby={`tab-${activeTab}`} className="space-y-4">
          {risks.length > 0 ? (
            <div className="space-y-3">
              {risks.map((risk, i) => {
                const level = typeof risk.level === 'string' ? risk.level : 'medium';
                const levelColor = level === 'high' ? '#EF4444' : level === 'medium' ? '#F59E0B' : '#3B82F6';
                const levelLabel = level === 'high' ? '高风险' : level === 'medium' ? '中风险' : '低风险';
                return (
                  <div
                    key={i}
                    className="p-4 bg-[var(--bg-elevated)] rounded-lg border-l-2"
                    style={{
                      borderLeftColor: levelColor,
                      borderTop: '1px solid var(--border-subtle)',
                      borderRight: '1px solid var(--border-subtle)',
                      borderBottom: '1px solid var(--border-subtle)',
                    }}
                  >
                    <div className="flex items-center gap-2 mb-2">
                      <span
                        className="text-xs font-bold px-1.5 py-0.5 rounded"
                        style={{
                          backgroundColor: `${levelColor}20`,
                          color: levelColor,
                        }}
                      >
                        {levelLabel}
                      </span>
                      <span className="text-[15px] font-medium text-[var(--text-primary)]">
                        {String(risk.title || risk.name || `风险 ${i + 1}`)}
                      </span>
                    </div>
                    {typeof risk.description === 'string' && (
                      <p className="text-[13px] text-[var(--text-primary)] leading-relaxed mb-2">{risk.description}</p>
                    )}
                    {typeof risk.mitigation === 'string' && (
                      <div className="text-[13px] text-[var(--text-secondary)]">
                        <span className="text-[#6366F1] font-medium">应对策略: </span>
                        {risk.mitigation}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          ) : (
            <EmptyState text="暂无风险评估数据" />
          )}
        </div>
      )}
    </div>
  );
}

function SwotCard({ title, items, color, icon }: { title: string; items: string[]; color: string; icon: string }) {
  if (items.length === 0) return null;
  const colorMap: Record<string, { bg: string; text: string; badge: string }> = {
    emerald: { bg: 'bg-emerald-500/5', text: 'text-emerald-400', badge: 'bg-emerald-500/20' },
    red: { bg: 'bg-red-500/5', text: 'text-red-400', badge: 'bg-red-500/20' },
    blue: { bg: 'bg-blue-500/5', text: 'text-blue-400', badge: 'bg-blue-500/20' },
    amber: { bg: 'bg-amber-500/5', text: 'text-amber-400', badge: 'bg-amber-500/20' },
  };
  const c = colorMap[color] || colorMap.blue;
  return (
    <div className={cn('p-3 rounded-lg border border-[var(--border-subtle)]', c.bg)}>
      <div className="flex items-center gap-2 mb-2">
        <span className={cn('text-xs font-bold px-1.5 py-0.5 rounded', c.badge, c.text)}>{icon}</span>
        <span className={cn('text-[15px] font-medium', c.text)}>{title}</span>
      </div>
      <ul className="space-y-1">
        {items.map((item, i) => (
          <li key={i} className="text-[13px] text-[var(--text-secondary)] flex items-start gap-1.5">
            <span className={cn('mt-1.5 w-1 h-1 rounded-full flex-shrink-0', c.text.replace('text-', 'bg-'))} />
            {item}
          </li>
        ))}
      </ul>
    </div>
  );
}

function ActionPlanSection({ title, items, color }: { title: string; items: string[]; color: string }) {
  const colorMap: Record<string, string> = {
    emerald: 'border-l-emerald-500',
    blue: 'border-l-blue-500',
    violet: 'border-l-violet-500',
  };
  return (
    <div className={cn('pl-3 border-l-2', colorMap[color] || 'border-l-gray-500')}>
      <div className="text-[13px] font-medium text-[var(--text-secondary)] mb-1.5">{title}</div>
      <ul className="space-y-1">
        {items.map((item, i) => (
          <li key={i} className="text-[13px] text-[var(--text-secondary)]">&bull; {item}</li>
        ))}
      </ul>
    </div>
  );
}

function EmptyState({ text }: { text: string }) {
  return (
    <div className="flex items-center justify-center py-12 text-[15px] text-[var(--text-tertiary)]">
      {text}
    </div>
  );
}
