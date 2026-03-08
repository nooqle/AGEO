'use client';

import { Cell, Pie, PieChart, ResponsiveContainer, Tooltip } from 'recharts';
import { RiCompass3Line, RiPieChart2Line } from '@remixicon/react';
import type { DashboardSourcesV2, PlatformData, SourceData } from '@/types/dashboard';
import { EmptyState } from '@/components/ui/empty-state';
import { PIE_COLORS, tooltipStyle } from '@/styles/chart-theme';

interface SourcesTabProps {
  data: SourceData[];
  officialDomain?: string;
  officialCitationRate?: number | null;
  platforms?: PlatformData[];
  sourcesV2?: DashboardSourcesV2 | null;
}

function normalizePercent(value: number | null | undefined) {
  if (value == null) return null;
  return value <= 1 ? value * 100 : value;
}

export function SourcesTab({ data, officialDomain, officialCitationRate, platforms = [], sourcesV2 }: SourcesTabProps) {
  const topDomains = sourcesV2?.top_domains && sourcesV2.top_domains.length > 0
    ? sourcesV2.top_domains.map((item) => ({
        source: item.source,
        count: item.count,
        percentage: normalizePercent(item.percentage) ?? 0,
        isOfficial: Boolean(item.is_official),
      }))
    : [...data].sort((a, b) => b.count - a.count).slice(0, 5).map((item) => ({
        source: item.source,
        count: item.count,
        percentage: item.percentage,
        isOfficial: officialDomain ? item.source.toLowerCase().includes(officialDomain) : false,
      }));

  const displayOfficialCitationRate = normalizePercent(sourcesV2?.official_citation_rate ?? officialCitationRate);
  const totalCitations = sourcesV2?.total_citations ?? data.reduce((sum, item) => sum + item.count, 0);
  const uniqueDomains = sourcesV2?.unique_domains ?? (topDomains.length || data.length);
  const officialSourceCount = topDomains.filter((item) => item.isOfficial).length;
  const platformStats = sourcesV2?.platform_citation_stats ?? [];
  const pieData = topDomains.length > 0 ? topDomains : data;

  if (pieData.length === 0 && platformStats.length === 0) {
    return (
      <EmptyState
        icon={RiPieChart2Line}
        title="暂无信息源数据"
        description="完成数据分析后即可查看官网引用率和来源结构。"
      />
    );
  }

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {[
          {
            label: '官网引用率',
            value: displayOfficialCitationRate != null ? `${displayOfficialCitationRate.toFixed(1)}%` : '--',
            desc: officialDomain ? `当前按 ${officialDomain} 识别官网来源。` : '当前品牌未配置官网域名。',
          },
          {
            label: '独立来源数',
            value: String(uniqueDomains),
            desc: `累计引用 ${totalCitations} 次，覆盖 ${uniqueDomains} 个来源。`,
          },
          {
            label: '官网来源命中',
            value: String(officialSourceCount),
            desc: officialSourceCount > 0 ? '官网已进入当前来源结构。' : '官网还未稳定进入当前来源结构。',
          },
        ].map((card) => (
          <div
            key={card.label}
            className="rounded-2xl p-4"
            style={{
              background: 'var(--bg-tertiary)',
              border: '1px solid var(--border-subtle)',
            }}
          >
            <div className="text-xs mb-2" style={{ color: 'var(--text-tertiary)' }}>
              {card.label}
            </div>
            <div className="text-2xl font-semibold mb-2" style={{ color: 'var(--text-primary)' }}>
              {card.value}
            </div>
            <div className="text-sm leading-6" style={{ color: 'var(--text-secondary)' }}>
              {card.desc}
            </div>
          </div>
        ))}
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-[1fr_1fr] gap-6">
        <div
          className="rounded-2xl p-4"
          style={{
            background: 'var(--bg-tertiary)',
            border: '1px solid var(--border-subtle)',
          }}
        >
          <h3 className="text-sm font-medium mb-4" style={{ color: 'var(--text-primary)' }}>
            来源结构分布
          </h3>
          <ResponsiveContainer width="100%" height={300}>
            <PieChart>
              <Pie
                data={pieData}
                cx="50%"
                cy="50%"
                innerRadius={60}
                outerRadius={100}
                dataKey="percentage"
                nameKey="source"
                label={(entry) =>
                  `${((entry as unknown as Record<string, unknown>).source ?? '')} ${Number((entry as unknown as Record<string, unknown>).percentage ?? 0).toFixed(0)}%`
                }
              >
                {pieData.map((_, index) => (
                  <Cell key={index} fill={PIE_COLORS[index % PIE_COLORS.length]} />
                ))}
              </Pie>
              <Tooltip contentStyle={tooltipStyle} />
            </PieChart>
          </ResponsiveContainer>
        </div>

        <div
          className="rounded-2xl p-4"
          style={{
            background: 'var(--bg-tertiary)',
            border: '1px solid var(--border-subtle)',
          }}
        >
          <h3 className="text-sm font-medium mb-4" style={{ color: 'var(--text-primary)' }}>
            Top Domains
          </h3>
          <div className="space-y-3">
            {topDomains.map((source, index) => (
              <div key={source.source} className="flex items-center gap-3">
                <div
                  className="w-3 h-3 rounded-full flex-shrink-0"
                  style={{ backgroundColor: PIE_COLORS[index % PIE_COLORS.length] }}
                />
                <div className="flex-1 min-w-0">
                  <div className="flex items-center justify-between gap-3">
                    <div className="min-w-0">
                      <div className="text-sm truncate" style={{ color: 'var(--text-primary)' }}>
                        {source.source}
                      </div>
                      <div className="text-xs" style={{ color: source.isOfficial ? 'var(--status-success)' : 'var(--text-tertiary)' }}>
                        {source.isOfficial ? '官网来源' : '外部来源'}
                      </div>
                    </div>
                    <span className="text-sm" style={{ color: 'var(--text-secondary)' }}>
                      {source.count}
                    </span>
                  </div>
                  <div className="mt-1 h-1.5 rounded-full overflow-hidden" style={{ background: 'var(--border-subtle)' }}>
                    <div
                      className="h-full rounded-full transition-all"
                      style={{
                        width: `${source.percentage}%`,
                        backgroundColor: PIE_COLORS[index % PIE_COLORS.length],
                      }}
                    />
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>

      <div
        className="rounded-2xl p-4"
        style={{
          background: 'var(--bg-tertiary)',
          border: '1px solid var(--border-subtle)',
        }}
      >
        <div className="flex items-center gap-2 mb-4">
          <RiCompass3Line className="w-5 h-5" style={{ color: 'var(--color-primary)' }} />
          <h3 className="text-sm font-medium" style={{ color: 'var(--text-primary)' }}>
            平台引用差异
          </h3>
        </div>
        {platformStats.length > 0 ? (
          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-4">
            {platformStats.map((platform) => (
              <div key={platform.platform} className="rounded-xl p-4" style={{ background: 'var(--bg-elevated)' }}>
                <div className="text-sm font-medium mb-2" style={{ color: 'var(--text-primary)' }}>
                  {platform.platform}
                </div>
                <div className="text-xs space-y-1" style={{ color: 'var(--text-secondary)' }}>
                  <div>官网引用率 {(normalizePercent(platform.official_citation_rate) ?? 0).toFixed(1)}%</div>
                  <div>Top 来源 {platform.top_domains[0]?.domain || '--'}</div>
                  <div>样本来源数 {platform.top_domains.length}</div>
                </div>
              </div>
            ))}
          </div>
        ) : platforms.length > 0 ? (
          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-4">
            {platforms.map((platform) => (
              <div key={platform.platform} className="rounded-xl p-4" style={{ background: 'var(--bg-elevated)' }}>
                <div className="text-sm font-medium mb-2" style={{ color: 'var(--text-primary)' }}>
                  {platform.platform}
                </div>
                <div className="text-xs space-y-1" style={{ color: 'var(--text-secondary)' }}>
                  <div>品牌提及率 {(platform.mentionRate * 100).toFixed(1)}%</div>
                  <div>平均排名 {platform.avgRanking.toFixed(1)}</div>
                  <div>情感 {(platform.sentiment * 100).toFixed(0)}%</div>
                </div>
              </div>
            ))}
          </div>
        ) : (
          <p className="text-sm" style={{ color: 'var(--text-tertiary)' }}>
            当前还没有平台级引用差异数据，先用来源分布判断官网是否进入答案链路。
          </p>
        )}
      </div>
    </div>
  );
}
