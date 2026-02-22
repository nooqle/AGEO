'use client';

import { useState, useEffect } from 'react';
import { useSearchParams } from 'next/navigation';
import { motion } from 'framer-motion';
import { RiDashboardLine, RiEyeLine, RiChatQuoteLine, RiPieChartLine, RiLightbulbLine } from '@remixicon/react';
import { KPICard } from './KPICard';
import { VisibilityTab } from './VisibilityTab';
import { PlatformTab } from './PlatformTab';
import { SourcesTab } from './SourcesTab';
import { AEOTab } from './AEOTab';
import { OptimizationTab } from './OptimizationTab';
import { MonitoringTab } from './MonitoringTab';
import { HeroSection } from './HeroSection';
import { BrandCards } from './BrandCards';
import { useDashboardStore } from '@/stores/dashboardStore';
import { useEntityStore } from '@/stores/entityStore';
import { useSessionStore } from '@/stores/sessionStore';

const TABS = [
  { id: 'visibility', label: '可见度' },
  { id: 'platform', label: '平台对比' },
  { id: 'sources', label: '来源分布' },
  { id: 'aeo', label: 'AEO 指标' },
  { id: 'optimization', label: '优化建议' },
  { id: 'monitoring', label: '监测' },
] as const;

type TabId = typeof TABS[number]['id'];

const AI_PLATFORMS = [
  { id: 'all', label: '全部平台' },
  { id: 'deepseek', label: 'DeepSeek' },
  { id: 'kimi', label: 'Kimi' },
  { id: 'doubao', label: '豆包' },
  { id: 'hunyuan', label: '混元' },
] as const;

interface DashboardPageProps {
  onNewAnalysis?: () => void;
}

export function DashboardPage({ onNewAnalysis }: DashboardPageProps) {
  const searchParams = useSearchParams();
  const urlTab = searchParams.get('tab') as TabId | null;
  const initialTab = urlTab && TABS.some((t) => t.id === urlTab) ? urlTab : 'visibility';
  const [activeTab, setActiveTab] = useState<TabId>(initialTab);
  const [selectedPlatform, setSelectedPlatform] = useState('all');
  const [lastUrlTab, setLastUrlTab] = useState(urlTab);

  // Sync tab state from URL search params (only on URL change, not on every render)
  if (urlTab !== lastUrlTab) {
    setLastUrlTab(urlTab);
    if (urlTab && TABS.some((t) => t.id === urlTab)) {
      setActiveTab(urlTab);
    }
  }
  const { data, dateRange, setDateRange, selectedBrandId, setSelectedBrandId, fetchData } = useDashboardStore();
  const { entities, isLoading: entitiesLoading, fetchEntities } = useEntityStore();
  const { totalSessions, fetchSessionList } = useSessionStore();

  // Fetch entities and sessions on mount (analytics data fetched after brand is selected)
  useEffect(() => {
    fetchEntities();
    fetchSessionList();
  }, [fetchEntities, fetchSessionList]);

  // Re-fetch analytics when dateRange or selected brand changes (only if brand is selected)
  useEffect(() => {
    if (selectedBrandId) {
      fetchData();
    }
  }, [dateRange, selectedBrandId, fetchData]);

  // Auto-select first brand, or reset if selected brand was deleted
  useEffect(() => {
    if (entities.length === 0) {
      if (selectedBrandId) setSelectedBrandId(null);
    } else if (!selectedBrandId || !entities.some((e) => e.id === selectedBrandId)) {
      setSelectedBrandId(entities[0].id);
    }
  }, [selectedBrandId, entities, setSelectedBrandId]);

  const kpi = data?.kpi;
  const bwvsBreakdown = kpi?.bwvsBreakdown;

  // Build BWVS tooltip with breakdown dimensions
  const bwvsTooltip = bwvsBreakdown
    ? `品牌可见度综合评分 (BWVS)\n\n` +
      `提及率 (40%):     ${bwvsBreakdown.mention_score?.toFixed(1) ?? '--'}\n` +
      `情感倾向 (25%):   ${bwvsBreakdown.sentiment_score?.toFixed(1) ?? '--'}\n` +
      `平台覆盖 (20%):   ${bwvsBreakdown.coverage_score?.toFixed(1) ?? '--'}\n` +
      `引用质量 (15%):   ${bwvsBreakdown.citation_score?.toFixed(1) ?? '--'}` +
      (bwvsBreakdown.citation_note ? ` *\n\n* ${bwvsBreakdown.citation_note}` : '') +
      `\n\n综合加权得分: ${kpi?.brandVisibility?.toFixed(1) ?? '--'}`
    : '品牌在AI搜索回答中被提及的加权可见度评分(0-100)';
  const hasData = entities.length > 0;
  const selectedBrandName = entities.find((e) => e.id === selectedBrandId)?.name;
  const isInitialLoading = entitiesLoading;

  // Filter platform-specific data when a platform is selected
  const filterByPlatform = <T,>(items: T[], platformKey = 'platform'): T[] => {
    if (selectedPlatform === 'all') return items;
    return items.filter((item) => {
      const val = (item as Record<string, unknown>)[platformKey];
      return typeof val === 'string' && val.toLowerCase().includes(selectedPlatform);
    });
  };

  const renderTab = () => {
    switch (activeTab) {
      case 'visibility':
        return <VisibilityTab data={filterByPlatform(data?.visibility || [])} />;
      case 'platform':
        return <PlatformTab data={filterByPlatform(data?.platforms || [])} />;
      case 'sources':
        return <SourcesTab data={data?.sources || []} />;
      case 'aeo':
        return <AEOTab data={data?.aeoMetrics || []} />;
      case 'optimization':
        return <OptimizationTab data={data?.optimizations || []} />;
      case 'monitoring':
        return <MonitoringTab entityId={selectedBrandId} />;
      default:
        return null;
    }
  };

  return (
    <div className="flex-1 flex flex-col overflow-auto">
      <div className="px-6 py-4">
        {/* Hero Section */}
        <div className="mb-4">
        <HeroSection
          totalSessions={totalSessions}
          totalBrands={entities.length}
          isLoading={isInitialLoading}
          onNewAnalysis={onNewAnalysis ?? (() => {})}
        />
        </div>

        {/* KPI Cards (only when has data) */}
        {hasData && (
          <div className="mb-8">
            {selectedBrandName && (
              <div className="flex items-center gap-2 mb-3">
                <span className="text-sm font-medium" style={{ color: 'var(--text-primary)' }}>
                  {selectedBrandName}
                </span>
                <span className="text-xs" style={{ color: 'var(--text-tertiary)' }}>的数据</span>
              </div>
            )}
            <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
              <KPICard
                title="品牌可见度"
                value={kpi?.brandVisibility != null ? kpi.brandVisibility.toFixed(1) : '--'}
                subtitle="BWVS 指数"
                tooltip={bwvsTooltip}
                trend={
                  kpi?.visibilityTrend != null
                    ? { value: kpi.visibilityTrend, isPositive: kpi.visibilityTrend >= 0 }
                    : null
                }
              />
              <KPICard
                title="提及率"
                value={kpi?.mentionRate != null ? `${(kpi.mentionRate * 100).toFixed(1)}%` : '--'}
                subtitle="AI 搜索可见性"
                tooltip="品牌在AI搜索回答中被直接提及的比例"
                trend={
                  kpi?.mentionTrend != null
                    ? { value: kpi.mentionTrend, isPositive: kpi.mentionTrend >= 0 }
                    : null
                }
              />
              <KPICard
                title="声量份额"
                value={kpi?.shareOfVoice != null ? `${(kpi.shareOfVoice * 100).toFixed(1)}%` : '--'}
                subtitle="相对竞品"
                tooltip="相对竞品的品牌声量占比"
                trend={
                  kpi?.sovTrend != null
                    ? { value: kpi.sovTrend, isPositive: kpi.sovTrend >= 0 }
                    : null
                }
              />
              <KPICard
                title="品牌数量"
                value={entities.length > 0 ? String(entities.length) : '--'}
                subtitle="已添加品牌"
                trend={null}
              />
            </div>

          </div>
        )}

        {/* Brand Cards */}
        <div className="mb-8">
          <BrandCards />
        </div>

        {/* Capability Preview (empty state) */}
        {!hasData && (
          <motion.div
            className="mb-8"
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.4, delay: 0.2 }}
          >
            <h3 className="text-sm font-medium mb-4" style={{ color: 'var(--text-secondary)' }}>
              分析完成后，您将看到
            </h3>
            <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
              {[
                { icon: RiEyeLine, title: '品牌可见度 (BWVS)', desc: '衡量品牌在 AI 回答中的综合曝光程度' },
                { icon: RiChatQuoteLine, title: '提及率', desc: '品牌被 AI 搜索引擎直接提及的频率' },
                { icon: RiPieChartLine, title: '声量份额', desc: '相对竞争对手的品牌话语权占比' },
                { icon: RiLightbulbLine, title: '优化建议', desc: '基于数据的 AEO 优化行动方案' },
              ].map((item) => (
                <div
                  key={item.title}
                  className="rounded-xl p-5 text-center"
                  style={{
                    background: 'var(--bg-tertiary)',
                    border: '1px dashed var(--border-default)',
                    opacity: 0.7,
                  }}
                >
                  <div
                    className="w-10 h-10 rounded-xl flex items-center justify-center mx-auto mb-3"
                    style={{ background: 'var(--bg-elevated)' }}
                  >
                    <item.icon className="w-5 h-5" style={{ color: 'var(--text-tertiary)' }} />
                  </div>
                  <div className="text-sm font-medium mb-1" style={{ color: 'var(--text-secondary)' }}>
                    {item.title}
                  </div>
                  <div className="text-xs" style={{ color: 'var(--text-tertiary)' }}>
                    {item.desc}
                  </div>
                </div>
              ))}
            </div>

            {/* Platform coverage */}
            <div className="flex items-center justify-center gap-3 mt-6">
              <span className="text-xs" style={{ color: 'var(--text-tertiary)' }}>覆盖主流 AI 搜索引擎</span>
              {['DeepSeek', 'Kimi', '豆包', '混元'].map((name) => (
                <span
                  key={name}
                  className="text-xs px-2 py-0.5 rounded"
                  style={{ background: 'var(--bg-tertiary)', color: 'var(--text-secondary)' }}
                >
                  {name}
                </span>
              ))}
            </div>
          </motion.div>
        )}

        {/* Analytics Tabs Section */}
        {hasData && (
          <div
            className="rounded-xl overflow-hidden"
            style={{
              border: '1px solid var(--border-default)',
              background: 'var(--bg-card)',
            }}
          >
            {/* Tab bar with filters */}
            <div
              className="px-6 pt-4 pb-0"
              style={{ borderBottom: '1px solid var(--border-default)' }}
            >
              <div className="flex items-center justify-between mb-4">
                <div className="flex items-center gap-3">
                  <RiDashboardLine className="w-5 h-5" style={{ color: 'var(--color-primary)' }} />
                  <h2 className="text-base font-semibold" style={{ color: 'var(--text-primary)' }}>
                    数据洞察
                  </h2>
                </div>
                <div className="flex items-center gap-3">
                  {/* Platform Filter */}
                  <div
                    className="flex gap-1 rounded-lg p-1"
                    style={{ background: 'var(--bg-tertiary)' }}
                  >
                    {AI_PLATFORMS.map((p) => (
                      <button
                        key={p.id}
                        onClick={() => setSelectedPlatform(p.id)}
                        className="px-3 py-1 text-xs font-medium rounded-md transition-colors cursor-pointer"
                        style={{
                          background: selectedPlatform === p.id ? 'var(--bg-elevated)' : 'transparent',
                          color: selectedPlatform === p.id ? 'var(--text-primary)' : 'var(--text-tertiary)',
                        }}
                      >
                        {p.label}
                      </button>
                    ))}
                  </div>

                  {/* Date Range Selector */}
                  <div
                    className="flex gap-1 rounded-lg p-1"
                    style={{ background: 'var(--bg-tertiary)' }}
                  >
                    {(['week', 'month', 'quarter'] as const).map((range) => (
                      <button
                        key={range}
                        onClick={() => setDateRange(range)}
                        className="px-3 py-1 text-xs font-medium rounded-md transition-colors cursor-pointer"
                        style={{
                          background: dateRange === range ? 'var(--bg-elevated)' : 'transparent',
                          color: dateRange === range ? 'var(--text-primary)' : 'var(--text-tertiary)',
                        }}
                      >
                        {range === 'week' ? '7D' : range === 'month' ? '30D' : '90D'}
                      </button>
                    ))}
                  </div>
                </div>
              </div>

              {/* Tabs */}
              <div className="flex gap-1 -mb-px">
                {TABS.map((tab) => (
                  <button
                    key={tab.id}
                    onClick={() => setActiveTab(tab.id)}
                    className="px-4 py-2 text-sm font-medium transition-colors border-b-2 cursor-pointer"
                    style={{
                      color: activeTab === tab.id ? 'var(--color-primary)' : 'var(--text-tertiary)',
                      borderColor: activeTab === tab.id ? 'var(--color-primary)' : 'transparent',
                    }}
                  >
                    {tab.label}
                  </button>
                ))}
              </div>
            </div>

            {/* Tab Content */}
            <div className="p-6">
              {renderTab()}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
