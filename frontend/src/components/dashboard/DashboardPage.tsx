'use client';

import { useEffect, useMemo, useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { motion } from 'framer-motion';
import {
  RiAlarmWarningLine,
  RiDashboardLine,
  RiEyeLine,
  RiPieChartLine,
  RiRobot2Line,
} from '@remixicon/react';
import { KPICard } from './KPICard';
import { VisibilityTab } from './VisibilityTab';
import { SourcesTab } from './SourcesTab';
import { OverviewTab } from './AEOTab';
import { OptimizationTab } from './OptimizationTab';
import { MonitoringTab } from './MonitoringTab';
import { HeroSection } from './HeroSection';
import { BrandCards } from './BrandCards';
import { CompetitorTable } from './CompetitorTable';
import { useDashboardStore } from '@/stores/dashboardStore';
import { useEntityStore } from '@/stores/entityStore';
import { useSessionStore } from '@/stores/sessionStore';
import type { DashboardV2KPI } from '@/types/dashboard';
import { EmptyState } from '@/components/ui/empty-state';
import { api } from '@/services/api';
import { toast } from '@/components/ui/toast';

const TABS = [
  { id: 'overview', label: '总览' },
  { id: 'scenarios', label: '场景' },
  { id: 'competition', label: '竞品争夺' },
  { id: 'sources', label: '信息源' },
  { id: 'actions', label: '风险与动作' },
  { id: 'monitoring', label: '监测' },
] as const;

type TabId = typeof TABS[number]['id'];

interface DashboardPageProps {
  onNewAnalysis?: () => void;
}

function normalizePercent(value: number | null | undefined): number | null {
  if (value == null) return null;
  return value <= 1 ? value * 100 : value;
}

function formatKpiValue(kpi: DashboardV2KPI): string {
  if (kpi.value == null) return '--';
  if (kpi.unit === '%') return `${kpi.value.toFixed(1)}%`;
  return Number.isInteger(kpi.value) ? String(kpi.value) : kpi.value.toFixed(1);
}

function resolveTargetTab(targetTab: string | undefined): TabId {
  switch (targetTab) {
    case 'overview':
      return 'overview';
    case 'sources':
      return 'sources';
    case 'riskAction':
    case 'actions':
      return 'actions';
    case 'monitoring':
      return 'monitoring';
    case 'competitors':
    case 'competition':
      return 'competition';
    case 'scenarios':
    default:
      return 'scenarios';
  }
}

function getKpiActionLabel(targetTab: string | undefined) {
  switch (resolveTargetTab(targetTab)) {
    case 'sources':
      return '查看信息源';
    case 'actions':
      return '查看风险';
    case 'competition':
      return '查看争夺';
    case 'monitoring':
      return '查看监测';
    case 'overview':
      return '查看总览';
    default:
      return '查看详情';
  }
}

export function DashboardPage({ onNewAnalysis }: DashboardPageProps) {
  const router = useRouter();
  const searchParams = useSearchParams();
  const urlTab = searchParams.get('tab') as TabId | null;
  const initialTab = urlTab && TABS.some((tab) => tab.id === urlTab) ? urlTab : 'overview';
  const [activeTab, setActiveTab] = useState<TabId>(initialTab);
  const { data, dateRange, selectedBrandId, setSelectedBrandId, fetchData } = useDashboardStore();
  const { entities, isLoading: entitiesLoading, fetchEntities } = useEntityStore();
  const { totalSessions, fetchSessionList } = useSessionStore();

  useEffect(() => {
    fetchEntities();
    fetchSessionList();
  }, [fetchEntities, fetchSessionList]);

  useEffect(() => {
    if (selectedBrandId) {
      fetchData();
    }
  }, [dateRange, selectedBrandId, fetchData]);

  useEffect(() => {
    if (entities.length === 0) {
      if (selectedBrandId) setSelectedBrandId(null);
    } else if (!selectedBrandId || !entities.some((entity) => entity.id === selectedBrandId)) {
      setSelectedBrandId(entities[0].id);
    }
  }, [selectedBrandId, entities, setSelectedBrandId]);

  const selectedBrand = entities.find((entity) => entity.id === selectedBrandId);
  const selectedBrandName = selectedBrand?.name;
  const fallbackOfficialDomain =
    selectedBrand?.domain?.replace(/^https?:\/\//, '').replace(/\/.*$/, '').toLowerCase() || '';
  const officialDomain = data?.v2?.sources?.official_domain || fallbackOfficialDomain;
  const hasData = entities.length > 0;
  const isInitialLoading = entitiesLoading;
  const hasSelectedBrandAnalysis = Boolean(
    selectedBrand?.lastAnalyzed ||
      data?.v2?.overview?.status_summary ||
      (data?.v2?.overview?.kpis ?? []).some((item) => item.value != null) ||
      (data?.v2?.scenarios?.length ?? 0) > 0 ||
      (data?.v2?.riskAction?.risks?.length ?? 0) > 0 ||
      (data?.v2?.riskAction?.actions?.length ?? 0) > 0
  );

  const handleOpenBrandAnalysis = async () => {
    if (!selectedBrand) return;

    try {
      const existing = await api.getSessionByEntity(selectedBrand.id);
      router.push(`/chat/${existing.id}?brand=${encodeURIComponent(selectedBrand.name)}`);
      return;
    } catch {}

    try {
      const created = await api.createSession(selectedBrand.id);
      router.push(`/chat/${created.id}?brand=${encodeURIComponent(selectedBrand.name)}`);
    } catch {
      toast.error('????????');
    }
  };

  const kpi = data?.kpi;
  const v2 = data?.v2;
  const oldOfficialCitationRate = useMemo(() => {
    const allSources = data?.sources || [];
    const sourceTotalCount = allSources.reduce((sum, item) => sum + item.count, 0);
    const officialSourceCount = allSources
      .filter((item) => officialDomain && item.source.toLowerCase().includes(officialDomain))
      .reduce((sum, item) => sum + item.count, 0);
    const ratio = sourceTotalCount > 0 ? officialSourceCount / sourceTotalCount : null;
    return normalizePercent(ratio);
  }, [data?.sources, officialDomain]);

  const fallbackBrandMentionRate = normalizePercent(kpi?.mentionRate ?? null);
  const fallbackScenarioHitCount = Math.max(
    data?.platforms?.filter((item) => item.mentionRate > 0.12).length || 0,
    data?.competitors?.filter((item) => item.mentionRate >= Math.max((kpi?.mentionRate ?? 0) * 0.65, 0.12)).length || 0
  );
  const fallbackMissingCount =
    data?.competitors?.filter((item) => {
      const mentionGap = item.mentionRate - (kpi?.mentionRate ?? 0);
      const visibilityGap = item.visibility - (kpi?.brandVisibility ?? 0);
      return mentionGap > 0.05 || visibilityGap > 6;
    }).length || 0;
  const fallbackHighRiskCount =
    (data?.competitors?.filter(
      (item) => item.mentionRate - (kpi?.mentionRate ?? 0) > 0.1 || item.visibility - (kpi?.brandVisibility ?? 0) > 10
    ).length || 0) + (oldOfficialCitationRate != null && oldOfficialCitationRate < 8 ? 1 : 0);

  const displayKpis: DashboardV2KPI[] =
    v2?.overview?.kpis && v2.overview.kpis.length > 0
      ? v2.overview.kpis.map((item) => {
          const isRateKpi = item.unit === '%';
          return {
            ...item,
            value: isRateKpi ? normalizePercent(item.value) : item.value,
            trend: isRateKpi ? normalizePercent(item.trend) : item.trend,
          };
        })
      : [
          {
            id: 'brand_mention_rate',
            label: '品牌提及率',
            value: fallbackBrandMentionRate,
            unit: '%',
            subtitle: '样本周期内被提及 / 总回答数',
            targetTab: 'scenarios',
          },
          {
            id: 'official_citation_rate',
            label: '官网引用率',
            value: oldOfficialCitationRate,
            unit: '%',
            subtitle: '官网域名被引用 / 总来源数',
            targetTab: 'sources',
          },
          {
            id: 'scenario_hit_count',
            label: '有效场景数',
            value: fallbackScenarioHitCount,
            subtitle: '基于平台覆盖与竞品压力估算',
            targetTab: 'scenarios',
          },
          {
            id: 'missing_high_value_scenario_count',
            label: '缺席高价值场景数',
            value: fallbackMissingCount,
            subtitle: '竞品领先或官网引用缺失的重点场景',
            targetTab: 'actions',
          },
          {
            id: 'high_risk_scenario_count',
            label: '高风险场景数',
            value: fallbackHighRiskCount,
            subtitle: '需要优先处理的高压场景',
            targetTab: 'actions',
          },
        ];

  const renderTab = () => {
    switch (activeTab) {
      case 'overview':
        return (
          <OverviewTab
            brandName={selectedBrandName}
            officialDomain={officialDomain}
            kpi={kpi}
            sources={data?.sources || []}
            platforms={data?.platforms || []}
            competitors={data?.competitors || []}
            officialCitationRate={displayKpis.find((item) => item.id === 'official_citation_rate')?.value ?? oldOfficialCitationRate}
            scenarioHitCount={displayKpis.find((item) => item.id === 'scenario_hit_count')?.value ?? fallbackScenarioHitCount}
            missingHighValueScenarioCount={displayKpis.find((item) => item.id === 'missing_high_value_scenario_count')?.value ?? fallbackMissingCount}
            highRiskScenarioCount={displayKpis.find((item) => item.id === 'high_risk_scenario_count')?.value ?? fallbackHighRiskCount}
            overviewV2={v2?.overview}
          />
        );
      case 'scenarios':
        return (
          <VisibilityTab
            data={data?.visibility || []}
            entityId={selectedBrandId}
            brandName={selectedBrandName}
            officialDomain={officialDomain}
            officialCitationRate={displayKpis.find((item) => item.id === 'official_citation_rate')?.value ?? oldOfficialCitationRate}
            scenarioRows={v2?.scenarios}
          />
        );
      case 'competition':
        return (
          <CompetitorTable
            data={data?.competitors || []}
            brandName={selectedBrandName}
            brandVisibility={kpi?.brandVisibility ?? null}
            brandMentionRate={kpi?.mentionRate ?? null}
            officialCitationRate={displayKpis.find((item) => item.id === 'official_citation_rate')?.value ?? oldOfficialCitationRate}
            standalone
            summaryCards={v2?.competitorBattle?.summary_cards}
            scenarioMatrix={v2?.competitorBattle?.scenario_matrix}
          />
        );
      case 'sources':
        return (
          <SourcesTab
            data={data?.sources || []}
            officialDomain={officialDomain}
            officialCitationRate={displayKpis.find((item) => item.id === 'official_citation_rate')?.value ?? oldOfficialCitationRate}
            platforms={data?.platforms || []}
            sourcesV2={v2?.sources}
          />
        );
      case 'actions':
        return (
          <OptimizationTab
            data={data?.optimizations || []}
            brandName={selectedBrandName}
            brandMentionRate={kpi?.mentionRate ?? null}
            brandVisibility={kpi?.brandVisibility ?? null}
            officialCitationRate={displayKpis.find((item) => item.id === 'official_citation_rate')?.value ?? oldOfficialCitationRate}
            officialDomain={officialDomain}
            competitors={data?.competitors || []}
            riskActionV2={v2?.riskAction}
          />
        );
      case 'monitoring':
        return (
          <MonitoringTab
            entityId={selectedBrandId}
            brandName={selectedBrandName}
            contextCopy={v2?.monitoring_context_copy}
          />
        );
      default:
        return null;
    }
  };

  return (
    <div className="flex-1 flex flex-col overflow-auto">
      <div className="px-6 py-4">
        <div className="mb-4">
          <HeroSection
            totalSessions={totalSessions}
            totalBrands={entities.length}
            isLoading={isInitialLoading}
            onNewAnalysis={onNewAnalysis ?? (() => {})}
          />
        </div>

        {hasData && hasSelectedBrandAnalysis && (
          <div className="mb-8">
            {selectedBrandName && (
              <div className="flex items-center gap-2 mb-3">
                <span className="text-sm font-medium" style={{ color: 'var(--text-primary)' }}>
                  {selectedBrandName}
                </span>
                <span className="text-xs" style={{ color: 'var(--text-tertiary)' }}>
                  当前诊断面板
                </span>
              </div>
            )}
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-5">
              {displayKpis.slice(0, 5).map((item) => (
                <KPICard
                  key={item.id}
                  title={item.label}
                  value={formatKpiValue(item)}
                  subtitle={item.subtitle || 'Dashboard V2 指标'}
                  tooltip={item.subtitle}
                  trend={item.trend != null ? { value: item.trend, isPositive: item.trend >= 0, unit: item.trendUnit ?? item.unit } : null}
                  actionLabel={getKpiActionLabel(item.targetTab)}
                  onClick={() => setActiveTab(resolveTargetTab(item.targetTab))}
                />
              ))}
            </div>
          </div>
        )}

        <div className="mb-8">
          <BrandCards />
        </div>

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
                { icon: RiEyeLine, title: '场景覆盖', desc: '识别品牌已经进入回答的关键场景' },
                { icon: RiDashboardLine, title: '竞品争夺', desc: '定位被竞品抢走的重点场景' },
                { icon: RiPieChartLine, title: '信息源结构', desc: '判断官网是否进入 AI 引用链路' },
                { icon: RiAlarmWarningLine, title: '风险与动作', desc: '把缺口收束成可执行的优先动作' },
              ].map((item) => (
                <div
                  key={item.title}
                  className="rounded-xl p-5 text-center"
                  style={{
                    background: 'var(--bg-tertiary)',
                    border: '1px dashed var(--border-subtle)',
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
          </motion.div>
        )}

        {hasData && !hasSelectedBrandAnalysis && selectedBrand && (
          <motion.div
            className="mb-8"
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.35 }}
          >
            <EmptyState
              icon={RiRobot2Line}
              title={`${selectedBrand.name} 尚未开始分析`}
              description="这个品牌还没有生成任何品牌诊断结果。先进入对话分析，完成首次采集后，这里才会显示场景、竞品争夺、风险与动作。"
              action={{
                label: '进入首次分析',
                onClick: () => { void handleOpenBrandAnalysis(); },
              }}
            />
          </motion.div>
        )}

        {hasData && hasSelectedBrandAnalysis && (
          <div className="space-y-6">
            <div className="flex flex-wrap gap-2">
              {TABS.map((tab) => (
                <button
                  key={tab.id}
                  type="button"
                  onClick={() => setActiveTab(tab.id)}
                  className={`px-3 py-1.5 rounded-full text-sm transition-colors ${activeTab === tab.id ? 'text-white' : 'text-[var(--text-secondary)]'}`}
                  style={activeTab === tab.id ? { background: 'var(--color-primary)' } : { background: 'var(--bg-tertiary)' }}
                >
                  {tab.label}
                </button>
              ))}
            </div>
            {renderTab()}
          </div>
        )}
      </div>
    </div>
  );
}
