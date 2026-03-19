'use client';

import { useEffect, useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { motion } from 'framer-motion';
import { RiRobot2Line } from '@remixicon/react';
import { KPICard } from './KPICard';
import { VisibilityTab } from './VisibilityTab';
import { SourcesTab } from './SourcesTab';
import { OverviewTab } from './AEOTab';
import { OptimizationTab } from './OptimizationTab';
import { MonitoringTab } from './MonitoringTab';
import { HeroSection } from './HeroSection';
import { BrandCards } from './BrandCards';
import { CompetitorTable } from './CompetitorTable';
import { DashboardBrandOverview, type DashboardBrandArchiveData } from './DashboardBrandOverview';
import { DashboardHomeBoards, type DashboardBoardId } from './DashboardHomeBoards';
import { DashboardBoardDialog } from './DashboardBoardDialog';
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
  const isMonitoringMode = searchParams.get('tab') === 'monitoring';
  const [activeTab, setActiveTab] = useState<TabId>(initialTab);
  const [activeBoard, setActiveBoard] = useState<DashboardBoardId | null>(null);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [brandArchive, setBrandArchive] = useState<DashboardBrandArchiveData | null>(null);
  const { data, dateRange, selectedBrandId, setSelectedBrandId, fetchData } = useDashboardStore();
  const { entities, isLoading: entitiesLoading, error: entityError, fetchEntities } = useEntityStore();
  const { totalSessions, listError, fetchSessionList } = useSessionStore();

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
    let cancelled = false;

    const fetchBrandArchive = async () => {
      if (!selectedBrandId) {
        setBrandArchive(null);
        return;
      }

      try {
        const session = await api.getSessionByEntity(selectedBrandId);
        const outputs = await api.getOutputs(session.id);
        const workflowOutput = [...outputs]
          .filter((output) => output.type === 'workflow')
          .sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime())[0];

        if (!workflowOutput || cancelled) {
          setBrandArchive(null);
          return;
        }

        const raw = workflowOutput.data ?? {};
        const brandProfile = (raw.brandProfile ?? raw.brand_profile ?? null) as DashboardBrandArchiveData['brandProfile'];
        const competitors = Array.isArray(raw.competitors) ? raw.competitors : [];

        if (!cancelled) {
          setBrandArchive({
            brandProfile,
            competitors,
          });
        }
      } catch {
        if (!cancelled) {
          setBrandArchive(null);
        }
      }
    };

    void fetchBrandArchive();

    return () => {
      cancelled = true;
    };
  }, [selectedBrandId]);

  useEffect(() => {
    if (entities.length === 0) {
      if (selectedBrandId) setSelectedBrandId(null);
    } else if (!selectedBrandId || !entities.some((entity) => entity.id === selectedBrandId)) {
      setSelectedBrandId(entities[0].id);
    }
  }, [selectedBrandId, entities, setSelectedBrandId]);

  useEffect(() => {
    setActiveTab(initialTab);
  }, [initialTab]);

  const selectedBrand = entities.find((entity) => entity.id === selectedBrandId);
  const selectedBrandName = selectedBrand?.name;
  const hasLoadError = Boolean(entityError || listError);
  const fallbackOfficialDomain =
    selectedBrand?.domain?.replace(/^https?:\/\//, '').replace(/\/.*$/, '').toLowerCase() || '';
  const hasData = entities.length > 0;
  const isInitialLoading = entitiesLoading;
  const kpi = data?.kpi;
  const v2 = data?.v2;
  const home = v2?.home;
  const officialDomain = v2?.sources?.official_domain || fallbackOfficialDomain;
  const hasSelectedBrandAnalysis = Boolean(
    home ||
      selectedBrand?.lastAnalyzed ||
      v2?.overview?.status_summary ||
      (v2?.overview?.kpis ?? []).some((item) => item.value != null) ||
      (v2?.scenarios?.length ?? 0) > 0 ||
      (v2?.riskAction?.risks?.length ?? 0) > 0 ||
      (v2?.riskAction?.actions?.length ?? 0) > 0
  );

  const handleOpenBrandAnalysis = async () => {
    if (!selectedBrand) return;

    try {
      const session = await api.getOrCreateSessionByEntity(selectedBrand.id);
      router.push(`/chat/${session.id}?entity_id=${encodeURIComponent(selectedBrand.id)}&brand=${encodeURIComponent(selectedBrand.name)}`);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : '打开品牌分析失败，请稍后重试。');
    }
  };

  const handleSelectBoard = (board: DashboardBoardId) => {
    setActiveBoard(board);
    setDialogOpen(true);
  };

  const handleOpenMonitoring = () => {
    router.push('/dashboard?tab=monitoring');
  };

  const allSources = data?.sources || [];
  const sourceTotalCount = allSources.reduce((sum, item) => sum + item.count, 0);
  const officialSourceCount = allSources
    .filter((item) => officialDomain && item.source.toLowerCase().includes(officialDomain))
    .reduce((sum, item) => sum + item.count, 0);
  const oldOfficialCitationRate = normalizePercent(sourceTotalCount > 0 ? officialSourceCount / sourceTotalCount : null);

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

  const renderLegacyTab = () => {
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
    <div className="dashboard-page-bg relative flex flex-1 flex-col overflow-auto">
      <div className="pointer-events-none absolute inset-x-0 top-0 h-[420px] opacity-80">
        <div
          className="absolute left-[8%] top-[-80px] h-[280px] w-[280px] rounded-full blur-3xl"
          style={{ background: 'color-mix(in srgb, var(--color-primary) 12%, transparent)' }}
        />
        <div
          className="absolute right-[12%] top-[20px] h-[240px] w-[240px] rounded-full blur-3xl"
          style={{ background: 'color-mix(in srgb, #d5a159 14%, transparent)' }}
        />
      </div>

      <div className="relative mx-auto w-full max-w-[1920px] px-5 py-4 lg:px-7 lg:py-5 2xl:px-10">
        <div className="space-y-4">
          <HeroSection
            totalSessions={totalSessions}
            totalBrands={entities.length}
            isLoading={isInitialLoading}
            onNewAnalysis={onNewAnalysis ?? (() => {})}
          />

          {hasLoadError && (
            <motion.div
              className="rounded-[24px] border px-5 py-4"
              style={{
                background: 'color-mix(in srgb, var(--bg-elevated) 92%, #fff5e8 8%)',
                borderColor: 'color-mix(in srgb, #d79b45 26%, var(--border-subtle) 74%)',
              }}
              initial={{ opacity: 0, y: 12 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.3 }}
            >
              <div className="text-[13px] font-medium" style={{ color: 'var(--text-primary)' }}>
                当前首页未成功加载真实品牌数据
              </div>
              <p className="mt-2 text-[13px] leading-7" style={{ color: 'var(--text-secondary)' }}>
                这不是“历史为空”。而是品牌列表或会话列表接口本轮加载失败。先恢复接口，再重新加载首页。
              </p>
            </motion.div>
          )}

          <BrandCards onAddBrand={onNewAnalysis} />

          {hasData && !hasSelectedBrandAnalysis && selectedBrand && (
            <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.35 }}>
              <EmptyState
                icon={RiRobot2Line}
                title={`${selectedBrand.name} 尚未开始分析`}
                description="这个品牌还没有形成首页看板。先进入对话分析，完成首次采集后，这里才会出现提及率、内容引用率和五维雷达。"
                action={{
                  label: '进入首次分析',
                  onClick: () => {
                    void handleOpenBrandAnalysis();
                  },
                }}
              />
            </motion.div>
          )}

          {hasData && isMonitoringMode && selectedBrand && (
            <div className="space-y-5">
              <section className="rounded-[24px] border bg-[var(--bg-tertiary)] px-6 py-5" style={{ borderColor: 'var(--border-subtle)' }}>
                <div className="flex flex-wrap items-center justify-between gap-4">
                  <div>
                    <div className="text-[11px] font-medium tracking-[0.16em] text-[var(--text-tertiary)]">持续监测</div>
                    <h2 className="mt-2 text-[22px] font-semibold tracking-[-0.02em] text-[var(--text-primary)]">{selectedBrand.name} 的持续监测</h2>
                  </div>
                  <button
                    type="button"
                    onClick={() => router.push('/dashboard')}
                    className="rounded-full border px-4 py-2 text-[13px] font-medium"
                    style={{ borderColor: 'var(--border-subtle)', color: 'var(--text-secondary)' }}
                  >
                    返回首页看板
                  </button>
                </div>
              </section>
              <MonitoringTab entityId={selectedBrandId} brandName={selectedBrandName} contextCopy={v2?.monitoring_context_copy} />
            </div>
          )}

          {hasData && hasSelectedBrandAnalysis && !isMonitoringMode && home && (
            <div className="space-y-6">
              {selectedBrand && <DashboardBrandOverview entity={selectedBrand} archive={brandArchive} />}
              <DashboardHomeBoards
                home={home}
                onSelectBoard={handleSelectBoard}
                onOpenMonitoring={handleOpenMonitoring}
              />
              <DashboardBoardDialog open={dialogOpen} board={activeBoard} home={home} onClose={() => setDialogOpen(false)} />
            </div>
          )}

          {hasData && hasSelectedBrandAnalysis && !isMonitoringMode && !home && (
            <div className="space-y-6">
              <section className="rounded-[24px] border bg-[var(--bg-tertiary)] px-6 py-5" style={{ borderColor: 'var(--border-subtle)' }}>
                <div>
                  <div className="text-[11px] font-medium tracking-[0.16em] text-[var(--text-tertiary)]">兼容模式</div>
                  <h2 className="mt-2 text-[22px] font-semibold tracking-[-0.02em] text-[var(--text-primary)]">当前显示历史诊断面板</h2>
                  <p className="mt-2 max-w-3xl text-[14px] leading-7 text-[var(--text-secondary)]">
                    这个品牌已有历史分析结果，但首页三看板数据暂未就绪，所以先回退到旧版 dashboard 视图，避免页面空白。
                  </p>
                </div>
              </section>

              <div>
                {selectedBrandName && (
                  <div className="mb-3 flex items-center gap-2">
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

              <div className="flex flex-wrap gap-2">
                {TABS.filter((tab) => tab.id !== 'monitoring').map((tab) => (
                  <button
                    key={tab.id}
                    type="button"
                    onClick={() => setActiveTab(tab.id)}
                    className={`rounded-full px-3 py-1.5 text-sm transition-colors ${activeTab === tab.id ? 'text-white' : 'text-[var(--text-secondary)]'}`}
                    style={activeTab === tab.id ? { background: 'var(--color-primary)' } : { background: 'var(--bg-tertiary)' }}
                  >
                    {tab.label}
                  </button>
                ))}
              </div>

              {renderLegacyTab()}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
