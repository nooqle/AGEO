'use client';

import { useState, useMemo } from 'react';
import { cn } from '@/lib/cn';
import type { KeywordAnalysis, KeywordItem } from '@/types/canvas';

interface WordCloudSectionProps {
  analysis: KeywordAnalysis;
}

import { getPlatformDisplayName } from '@/config/platformLabel';
import { getPlatformColor } from '@/config/platforms';

const TOP_N = 15;
const MIN_FONT_SIZE = 14;
const MAX_FONT_SIZE = 48;
const BRAND_INDIGO = '99, 102, 241';

/** Map normalized value (10-100) to font size (14-48px) */
function valueToFontSize(value: number): number {
  const ratio = (value - 10) / 90;
  return Math.round(MIN_FONT_SIZE + ratio * (MAX_FONT_SIZE - MIN_FONT_SIZE));
}

/** Map normalized value (10-100) to Indigo opacity tier */
function valueToColor(value: number): string {
  if (value >= 80) return `rgba(${BRAND_INDIGO}, 1)`;
  if (value >= 60) return `rgba(${BRAND_INDIGO}, 0.85)`;
  if (value >= 40) return `rgba(${BRAND_INDIGO}, 0.65)`;
  if (value >= 25) return `rgba(${BRAND_INDIGO}, 0.45)`;
  return `rgba(${BRAND_INDIGO}, 0.3)`;
}

export function WordCloudSection({ analysis }: WordCloudSectionProps) {
  const [selectedPlatform, setSelectedPlatform] = useState<string | null>(null);
  const [expandedKeyword, setExpandedKeyword] = useState<string | null>(null);

  const { keywords, platforms, total_keywords } = analysis;

  // Filter keywords by selected platform
  const filteredKeywords = useMemo(() => {
    if (!selectedPlatform) return keywords;
    return keywords.filter((kw) => kw.platforms.includes(selectedPlatform));
  }, [keywords, selectedPlatform]);

  // Top 15 for ranking list
  const rankingKeywords = useMemo(() => {
    return filteredKeywords.slice(0, TOP_N);
  }, [filteredKeywords]);

  if (!keywords || keywords.length === 0) {
    return (
      <div className="flex items-center justify-center py-12 text-[15px] text-[var(--text-tertiary)]">
        暂无语义分析数据，完成分析后将自动生成
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* A. Summary stats */}
      <div className="p-5 bg-[var(--bg-elevated)] border border-[var(--border-subtle)] rounded-xl">
        <div className="flex items-center gap-6">
          <div className="text-center min-w-[100px]">
            <div className="text-4xl font-bold text-[#6366F1]">
              {total_keywords}
            </div>
            <div className="text-[13px] text-[var(--text-secondary)] mt-1">核心关键词</div>
          </div>
          <div className="flex-1">
            <div className="grid grid-cols-2 gap-3">
              <div className="text-center p-2 rounded-lg" style={{ backgroundColor: 'rgba(99,102,241,0.06)' }}>
                <div className="text-lg font-bold text-[var(--text-primary)]">{platforms.length}</div>
                <div className="text-[11px] text-[var(--text-tertiary)]">覆盖平台</div>
              </div>
              <div className="text-center p-2 rounded-lg" style={{ backgroundColor: 'rgba(99,102,241,0.06)' }}>
                <div className="text-lg font-bold text-[var(--text-primary)]">
                  {keywords.length > 0
                    ? Math.round(keywords.reduce((sum, kw) => sum + kw.platforms.length, 0) / keywords.length * 10) / 10
                    : 0}
                </div>
                <div className="text-[11px] text-[var(--text-tertiary)]">平均平台覆盖</div>
              </div>
            </div>
          </div>
        </div>
        <p className="text-[11px] text-[var(--text-tertiary)] mt-3 leading-relaxed">
          基于 TF-IDF 算法从 AI 平台回答中提取的高频语义关键词。词越大表示在回答中出现频率越高、权重越大。
        </p>
      </div>

      {/* B. Platform filter */}
      {platforms.length > 1 && (
        <div className="flex items-center gap-2 flex-wrap">
          <span className="text-[13px] text-[var(--text-secondary)] mr-1">筛选平台:</span>
          <button
            onClick={() => setSelectedPlatform(null)}
            className={cn(
              'px-3 py-1.5 text-[12px] font-medium rounded-full border transition-colors',
              selectedPlatform === null
                ? 'bg-[#6366F1]/15 text-[#6366F1] border-[#6366F1]/30'
                : 'bg-[var(--bg-elevated)] text-[var(--text-secondary)] border-[var(--border-subtle)] hover:text-[var(--text-primary)]'
            )}
          >
            全部
          </button>
          {platforms.map((plat) => (
            <button
              key={plat}
              onClick={() => setSelectedPlatform(selectedPlatform === plat ? null : plat)}
              className={cn(
                'px-3 py-1.5 text-[12px] font-medium rounded-full border transition-colors flex items-center gap-1.5',
                selectedPlatform === plat
                  ? 'border-[var(--border-subtle)]'
                  : 'bg-[var(--bg-elevated)] text-[var(--text-secondary)] border-[var(--border-subtle)] hover:text-[var(--text-primary)]'
              )}
              style={selectedPlatform === plat ? {
                backgroundColor: `${getPlatformColor(plat) || '#6366F1'}15`,
                color: getPlatformColor(plat) || '#6366F1',
                borderColor: `${getPlatformColor(plat) || '#6366F1'}30`,
              } : undefined}
            >
              <span
                className="w-2 h-2 rounded-full flex-shrink-0"
                style={{ backgroundColor: getPlatformColor(plat) || '#6366F1' }}
              />
              {getPlatformDisplayName(plat)}
            </button>
          ))}
        </div>
      )}

      {/* C. Word Cloud visualization (flex-wrap) */}
      <div className="p-5 bg-[var(--bg-elevated)] border border-[var(--border-subtle)] rounded-xl">
        <h3 className="text-[15px] font-medium text-[var(--text-primary)] mb-4">语义词云</h3>
        {filteredKeywords.length > 0 ? (
          <div className="flex flex-wrap items-baseline justify-center gap-x-3 gap-y-2 py-4">
            {filteredKeywords.map((kw) => (
              <button
                key={kw.word}
                onClick={() => setExpandedKeyword(expandedKeyword === kw.word ? null : kw.word)}
                className={cn(
                  'transition-opacity hover:opacity-80 cursor-pointer leading-tight',
                  expandedKeyword && expandedKeyword !== kw.word && 'opacity-40'
                )}
                style={{
                  fontSize: `${valueToFontSize(kw.value)}px`,
                  color: valueToColor(kw.value),
                  fontWeight: kw.value >= 60 ? 700 : kw.value >= 35 ? 500 : 400,
                }}
                title={`${kw.word} (${kw.value.toFixed(0)}) - ${kw.platforms.map((p) => getPlatformDisplayName(p)).join(', ')}`}
              >
                {kw.word}
              </button>
            ))}
          </div>
        ) : (
          <div className="flex items-center justify-center py-8 text-[13px] text-[var(--text-tertiary)]">
            该平台暂无关键词数据
          </div>
        )}

        {/* Expanded keyword detail */}
        {expandedKeyword && (
          <ExpandedKeywordDetail
            keyword={filteredKeywords.find((kw) => kw.word === expandedKeyword) || null}
            onClose={() => setExpandedKeyword(null)}
          />
        )}
      </div>

      {/* D. Ranking list (top 15) */}
      {rankingKeywords.length > 0 && (
        <div>
          <h3 className="text-[15px] font-medium text-[var(--text-primary)] mb-3">关键词排行 Top {Math.min(TOP_N, rankingKeywords.length)}</h3>
          <div className="space-y-2">
            {rankingKeywords.map((kw, i) => (
              <div key={kw.word}>
                <button
                  onClick={() => setExpandedKeyword(expandedKeyword === kw.word ? null : kw.word)}
                  className="w-full flex items-center gap-3 p-3 bg-[var(--bg-elevated)] border border-[var(--border-subtle)] rounded-lg hover:border-[#6366F1]/30 transition-colors text-left"
                >
                  <span className={cn(
                    'w-6 h-6 rounded-full flex items-center justify-center text-xs font-bold flex-shrink-0',
                    i < 3 ? 'bg-[#6366F1]/20 text-[#6366F1]' : 'bg-[var(--bg-tertiary)] text-[var(--text-tertiary)]'
                  )}>
                    {i + 1}
                  </span>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="text-[13px] font-medium text-[var(--text-primary)]">{kw.word}</span>
                      <div className="flex items-center gap-1">
                        {kw.platforms.map((plat) => (
                          <span
                            key={plat}
                            className="w-1.5 h-1.5 rounded-full flex-shrink-0"
                            style={{ backgroundColor: getPlatformColor(plat) || '#6366F1' }}
                            title={getPlatformDisplayName(plat)}
                          />
                        ))}
                      </div>
                    </div>
                    <div className="flex items-center gap-2 mt-1">
                      <div className="flex-1 h-1.5 rounded-full bg-[var(--bg-tertiary)] overflow-hidden">
                        <div
                          className="h-full rounded-full bg-[#6366F1]"
                          style={{ width: `${kw.value}%` }}
                        />
                      </div>
                      <span className="text-[11px] text-[var(--text-tertiary)] w-10 text-right flex-shrink-0">
                        {kw.value.toFixed(0)}
                      </span>
                    </div>
                  </div>
                </button>

                {/* Inline expanded context */}
                {expandedKeyword === kw.word && kw.contexts.length > 0 && (
                  <div className="mt-1 ml-9 mr-3 mb-1">
                    <div className="p-3 rounded-lg border border-[var(--border-subtle)]" style={{ backgroundColor: 'rgba(99,102,241,0.04)' }}>
                      <div className="text-[11px] text-[var(--text-tertiary)] mb-2">上下文引用</div>
                      <div className="space-y-2">
                        {kw.contexts.map((ctx, ci) => (
                          <div key={ci} className="flex items-start gap-2">
                            <span
                              className="mt-0.5 w-2 h-2 rounded-full flex-shrink-0"
                              style={{ backgroundColor: getPlatformColor(ctx.platform) || '#6366F1' }}
                            />
                            <div className="min-w-0">
                              <span className="text-[10px] font-medium" style={{ color: getPlatformColor(ctx.platform) || '#6366F1' }}>
                                {getPlatformDisplayName(ctx.platform)}
                              </span>
                              <p className="text-[12px] text-[var(--text-secondary)] leading-relaxed mt-0.5 break-all">
                                {highlightWord(ctx.text, kw.word)}
                              </p>
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* E. Data note */}
      <div
        className="p-3 rounded-lg text-[11px] text-[var(--text-tertiary)] leading-relaxed"
        style={{ backgroundColor: 'rgba(99,102,241,0.06)', border: '1px solid rgba(99,102,241,0.15)' }}
      >
        语义词云基于 TF-IDF 算法从各 AI 平台回答中提取关键词。权重值越高，表示该词在所有回答中的区分度和重要性越大。点击关键词可查看原文上下文。
      </div>
    </div>
  );
}

/** Inline detail panel shown when a keyword is clicked in the word cloud */
function ExpandedKeywordDetail({
  keyword,
  onClose,
}: {
  keyword: KeywordItem | null;
  onClose: () => void;
}) {
  if (!keyword) return null;

  return (
    <div className="mt-3 p-4 rounded-lg border border-[#6366F1]/20" style={{ backgroundColor: 'rgba(99,102,241,0.04)' }}>
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <span className="text-[15px] font-bold text-[#6366F1]">{keyword.word}</span>
          <span className="text-[11px] text-[var(--text-tertiary)]">权重 {keyword.value.toFixed(0)}</span>
        </div>
        <button
          onClick={onClose}
          className="text-[var(--text-tertiary)] hover:text-[var(--text-primary)] transition-colors text-sm px-1"
          aria-label="关闭"
        >
          x
        </button>
      </div>

      {/* Platform badges */}
      <div className="flex items-center gap-1.5 mb-3">
        {keyword.platforms.map((plat) => (
          <span
            key={plat}
            className="text-[10px] font-medium px-2 py-0.5 rounded-full"
            style={{
              backgroundColor: `${getPlatformColor(plat) || '#6366F1'}15`,
              color: getPlatformColor(plat) || '#6366F1',
            }}
          >
            {getPlatformDisplayName(plat)}
          </span>
        ))}
      </div>

      {/* Context snippets */}
      {keyword.contexts.length > 0 && (
        <div className="space-y-2">
          {keyword.contexts.map((ctx, i) => (
            <div key={i} className="flex items-start gap-2">
              <span
                className="mt-1 w-2 h-2 rounded-full flex-shrink-0"
                style={{ backgroundColor: getPlatformColor(ctx.platform) || '#6366F1' }}
              />
              <p className="text-[12px] text-[var(--text-secondary)] leading-relaxed break-all">
                {highlightWord(ctx.text, keyword.word)}
              </p>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

/** Highlight the keyword within context text */
function highlightWord(text: string, word: string): React.ReactNode {
  if (!word || !text) return text;

  const parts: React.ReactNode[] = [];
  let remaining = text;
  let keyIdx = 0;

  while (remaining.length > 0) {
    const idx = remaining.indexOf(word);
    if (idx === -1) {
      parts.push(remaining);
      break;
    }
    if (idx > 0) {
      parts.push(remaining.slice(0, idx));
    }
    parts.push(
      <span key={keyIdx++} className="font-bold text-[#6366F1]">
        {word}
      </span>
    );
    remaining = remaining.slice(idx + word.length);
  }

  return <>{parts}</>;
}
