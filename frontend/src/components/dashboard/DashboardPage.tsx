'use client';

import { useEffect, useState } from 'react';
import dynamic from 'next/dynamic';
import { useRouter, useSearchParams } from 'next/navigation';
import {
  DashboardBrandSidebar,
  DashboardMobileBrandSwitcher,
} from './DashboardBrandSidebar';
import { BrandOntologyHome } from './BrandOntologyHome';
import { HeroSection } from './HeroSection';
import { useDashboardStore } from '@/stores/dashboardStore';
import { useEntityStore } from '@/stores/entityStore';
import { useOntologyStore } from '@/stores/ontologyStore';
import { useSessionStore } from '@/stores/sessionStore';
import { api } from '@/services/api';
import { toast } from '@/components/ui/toast';
import { uniqueAiSourceDisplayNames } from '@/lib/aiSourceDisplay';
import {
  preferredDashboardEntity,
  splitDashboardEntities,
} from '@/lib/brandEntityHygiene';
import { buildDashboardChatUrlWithHandoff } from '@/lib/dashboardChatHandoff';
import type {
  DashboardHomeData,
  DashboardLatestReport,
  DashboardMonitorMode,
} from '@/types/dashboard';
import type { OntologyWorldSummary } from '@/types/ontology';

interface DashboardPageProps {
  onNewAnalysis?: () => void;
}

const MonitoringTab = dynamic(
  () => import('./MonitoringTab').then((module) => module.MonitoringTab),
  {
    ssr: false,
    loading: () => (
      <section
        className="rounded-[18px] border bg-[var(--bg-tertiary)] px-5 py-5"
        style={{ borderColor: 'var(--border-subtle)' }}
      >
        <div className="h-7 w-36 rounded-lg animate-shimmer" />
        <div className="mt-5 grid gap-3 md:grid-cols-3">
          {Array.from({ length: 3 }).map((_, index) => (
            <div key={index} className="h-28 rounded-[16px] animate-shimmer" />
          ))}
        </div>
      </section>
    ),
  },
);

const MONITOR_MODE_LABELS: Record<DashboardMonitorMode, string> = {
  panorama: '全景分析',
  scenario: '用户场景分析',
};

function resolveAiSourceLabels(home?: DashboardHomeData | null): string[] {
  return uniqueAiSourceDisplayNames((home?.platform_diagnosis || []).map((row) => row.platform));
}

function formatBrandWorldSampleSummary(
  scope?: {
    platform_count?: number;
    question_count?: number;
    answer_count?: number;
    citation_count?: number;
  },
): string | null {
  if (!scope) return null;
  const parts = [
    typeof scope.platform_count === 'number' ? `${scope.platform_count} 个平台` : null,
    typeof scope.question_count === 'number' ? `${scope.question_count} 个问题` : null,
    typeof scope.answer_count === 'number' ? `${scope.answer_count} 条答案样本` : null,
    typeof scope.citation_count === 'number' ? `${scope.citation_count} 次引用` : null,
  ].filter(Boolean);
  return parts.length ? parts.join(' · ') : null;
}

function formatBrandWorldMetricSummary(world?: OntologyWorldSummary | null): string | null {
  const metrics = world?.summary_projection?.metrics;
  if (!metrics) return null;
  const parts = [
    metrics.mention_rate?.display_value ? `AI 提及率 ${metrics.mention_rate.display_value}` : null,
    metrics.mention_ranking?.display_rank
      ? `提及排名 第 ${metrics.mention_ranking.display_rank} / ${metrics.mention_ranking.total || 1}`
      : metrics.mention_ranking?.sample_sufficiency?.rank_status_label
        ? `提及排名 ${metrics.mention_ranking.sample_sufficiency.rank_status_label}`
        : null,
    metrics.official_citation_rate?.display_value ? `官网引用率 ${metrics.official_citation_rate.display_value}` : null,
  ].filter(Boolean);
  return parts.length ? parts.join(' · ') : null;
}

function hasDashboardHomePayload(home?: DashboardHomeData | null): boolean {
  if (!home) return false;
  const latestReport = home.latest_report;
  const hasReportIdentity = Boolean(
    latestReport?.session_id ||
      latestReport?.artifact_id ||
      latestReport?.output_id ||
      latestReport?.report_kind,
  );
  const hasUsefulMetric = (home.metrics || []).some((metric) => metric.value != null);
  const headline = home.summary?.headline?.trim();
  const hasUsefulHeadline = Boolean(headline && headline !== '暂无最近分析');
  return hasReportIdentity || hasUsefulMetric || hasUsefulHeadline;
}

function resolveHomeMonitorMode(home?: DashboardHomeData | null): DashboardMonitorMode | null {
  if (!hasDashboardHomePayload(home)) return null;
  const reportKind = home?.latest_report?.report_kind;
  return reportKind === 'scenario' ||
    reportKind === 'scenario_monitoring' ||
    reportKind === 'persona'
    ? 'scenario'
    : 'panorama';
}

function resolveMonitoringStatusLabel(home?: DashboardHomeData | null): string {
  const plan = home?.monitoring_plan;
  const scheduleStatus = plan?.schedule_status;
  if (scheduleStatus === 'active') return '正在监测';
  if (scheduleStatus === 'paused') return '暂停监测';
  if (scheduleStatus === 'error') return '监测异常';
  if (scheduleStatus === 'completed') return '监测已完成';
  if (home?.has_active_monitoring_schedule && !plan) return '正在监测';
  const status = plan?.status;
  if (status === 'active') return plan?.schedule_id ? '正在监测' : '计划已就绪';
  if (status === 'paused') return '暂停监测';
  if (status === 'draft') return '计划草稿';
  return '未启用监测';
}

function latestReportRef(report?: DashboardLatestReport): string {
  return (
    report?.artifact_id ||
    report?.output_id ||
    report?.session_id ||
    report?.created_at ||
    ''
  );
}

function isRealMonitoringPlanId(planId: string | null | undefined): planId is string {
  return Boolean(planId && !planId.startsWith('schedule:'));
}

function reportTodoStorageKey(brandId: string, reportRef: string): string {
  return `specta.dashboard.report.viewed.${brandId}.${reportRef}`;
}

function markReportTodoViewed(brandId: string | null, reportRef: string | null | undefined) {
  if (!brandId || !reportRef || typeof window === 'undefined') return;
  window.localStorage.setItem(reportTodoStorageKey(brandId, reportRef), '1');
}

function buildDashboardVisibleDraft(input: string): string | null {
  const trimmedInput = input.trim();
  return trimmedInput || null;
}

function DashboardMonitoringEntry({
  brandName,
  monitorModeLabel,
  statusLabel,
  onOpen,
}: {
  brandName?: string;
  monitorModeLabel: string;
  statusLabel: string;
  onOpen: () => void;
}) {
  return (
    <section className="mt-5 border-t border-[var(--border-subtle)] pt-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="min-w-0">
          <div className="text-[12px] font-medium text-[var(--brand-primary)]">
            监测与样本
          </div>
          <p className="mt-1 text-[13px] leading-6 text-[var(--text-secondary)]">
            {brandName || '当前品牌'} · {monitorModeLabel} · {statusLabel}。开启监测后，会定期补充问题、回答、引用和指标。
          </p>
        </div>
        <button
          type="button"
          onClick={onOpen}
          className="min-h-10 rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-4 py-2 text-[13px] font-medium text-[var(--text-secondary)] transition-colors hover:border-[var(--brand-primary)] hover:text-[var(--brand-primary)]"
        >
          查看趋势与样本
        </button>
      </div>
    </section>
  );
}

export function DashboardPage({ onNewAnalysis }: DashboardPageProps) {
  const router = useRouter();
  const searchParams = useSearchParams();
  const isMonitoringMode = searchParams.get('tab') === 'monitoring';
  const shouldEditMonitoringSchedule = searchParams.get('edit_schedule') === '1';
  const requestedEntityId = searchParams.get('entity_id');
  const [isOpeningDashboardChat, setIsOpeningDashboardChat] = useState(false);
  const {
    selectedBrandId,
    setSelectedBrandId,
    homeMonitorMode: selectedMonitorMode,
    home,
    homeError,
    fetchHome,
  } = useDashboardStore();
  const { entities, isLoading: entitiesLoading, error: entityError, fetchEntities } = useEntityStore();
  const { worldsByEntity } = useOntologyStore();
  const { listError, fetchSessionList } = useSessionStore();

  useEffect(() => {
    fetchEntities();
    fetchSessionList();
  }, [fetchEntities, fetchSessionList]);

  useEffect(() => {
    if (selectedBrandId && !isMonitoringMode) {
      void fetchHome();
    }
  }, [fetchHome, isMonitoringMode, selectedBrandId, selectedMonitorMode]);

  useEffect(() => {
    if (entities.length === 0) {
      if (selectedBrandId) setSelectedBrandId(null);
      return;
    }
    if (
      requestedEntityId &&
      entities.some((entity) => entity.id === requestedEntityId) &&
      selectedBrandId !== requestedEntityId
    ) {
      setSelectedBrandId(requestedEntityId);
      return;
    }
    const visiblePrimary = splitDashboardEntities(entities, selectedBrandId).primary;
    const selectedIsPrimary = visiblePrimary.some(
      (entity) => entity.id === selectedBrandId,
    );
    if (!selectedBrandId || !selectedIsPrimary) {
      setSelectedBrandId((preferredDashboardEntity(entities) || entities[0]).id);
    }
  }, [requestedEntityId, selectedBrandId, entities, setSelectedBrandId]);

  const selectedBrand = entities.find((entity) => entity.id === selectedBrandId);
  const selectedWorld = selectedBrandId ? worldsByEntity[selectedBrandId] : null;
  const brandWorldSampleSummary = formatBrandWorldSampleSummary(
    selectedWorld?.summary_projection?.sample_scope,
  );
  const brandWorldMetricSummary = formatBrandWorldMetricSummary(selectedWorld);
  const selectedBrandName = selectedBrand?.name;
  const homeMonitorMode = resolveHomeMonitorMode(home);
  const homePlanMonitorMode = home?.monitoring_plan?.monitor_mode ?? null;
  const hasSelectedBrandAnalysis = hasDashboardHomePayload(home);
  const hasSelectedMonitorModeData = Boolean(
    hasSelectedBrandAnalysis && homeMonitorMode === selectedMonitorMode,
  );
  const hasSelectedMonitorModePlan = Boolean(
    home?.monitoring_plan && homePlanMonitorMode === selectedMonitorMode,
  );
  const hasSelectedMonitorModeContext = hasSelectedMonitorModeData || hasSelectedMonitorModePlan;
  const selectedMonitorModeLabel = MONITOR_MODE_LABELS[selectedMonitorMode];
  const aiSourceLabels = hasSelectedMonitorModeData
    ? resolveAiSourceLabels(home)
    : hasSelectedMonitorModePlan
      ? home?.monitoring_plan?.endpoint_labels || []
      : [];
  const hasLoadError = Boolean(entityError || listError);
  const hasData = entities.length > 0;
  const isInitialLoading = entitiesLoading;

  const handleDashboardCommand = async (
    input: string,
    options?: {
      autosend?: boolean;
      handoff?: { taskTitle?: string; taskGoal?: string };
    },
  ) => {
    if (!selectedBrand || isOpeningDashboardChat) {
      if (!selectedBrand) onNewAnalysis?.();
      return;
    }

    setIsOpeningDashboardChat(true);
    try {
      const session = await api.createSession();
      const draft = buildDashboardVisibleDraft(input);
      if (!draft) {
        router.push(`/chat/${session.id}`);
        return;
      }

      const params = new URLSearchParams();
      params.set('entity_id', selectedBrand.id);
      params.set('brand', selectedBrand.name);
      params.set('entry_source', 'dashboard_command_bar');
      params.set(
        'monitor_mode',
        selectedMonitorMode === 'scenario' ? 'scenario_monitoring' : 'panorama_monitoring',
      );
      if (home?.latest_report?.question_set_label) {
        params.set('question_set_label', home.latest_report.question_set_label);
      } else if (home?.monitoring_plan?.question_set_label) {
        params.set('question_set_label', home.monitoring_plan.question_set_label);
      }
      if (brandWorldSampleSummary) {
        params.set('sample_summary', brandWorldSampleSummary);
      }
      if (brandWorldMetricSummary) {
        params.set('current_metrics', brandWorldMetricSummary);
      }
      if (options?.handoff?.taskTitle) {
        params.set('task_title', options.handoff.taskTitle);
      }
      if (options?.handoff?.taskGoal) {
        params.set('task_goal', options.handoff.taskGoal);
      }
      params.set('clean_handoff', '1');
      if (isRealMonitoringPlanId(home?.monitoring_plan?.id)) {
        params.set('monitoring_plan_id', home.monitoring_plan.id);
      }
      if (home?.monitoring_plan?.question_set_ids?.length) {
        params.set('question_set_ids', home.monitoring_plan.question_set_ids.join(','));
      }
      if (home?.monitoring_plan?.endpoint_ids?.length) {
        params.set('endpoint_ids', home.monitoring_plan.endpoint_ids.join(','));
      }
      if (aiSourceLabels.length) {
        params.set('ai_sources', aiSourceLabels.join('、'));
      }
      params.set('draft', draft);
      if (options?.autosend !== false) {
        params.set('autosend', '1');
      }
      router.push(
        buildDashboardChatUrlWithHandoff(
          session.id,
          Object.fromEntries(params.entries()),
        ),
      );
    } catch (error) {
      toast.error(error instanceof Error ? error.message : '打开对话失败，请稍后重试。');
    } finally {
      setIsOpeningDashboardChat(false);
    }
  };

  const handleOpenLatestReport = () => {
    if (!home?.latest_report?.session_id) return;
    const reportRef = latestReportRef(home.latest_report);
    markReportTodoViewed(selectedBrandId, reportRef);
    const params = new URLSearchParams();
    const artifactTarget = home.latest_report.artifact_id || home.latest_report.output_id;
    if (artifactTarget) {
      params.set('artifact_id', artifactTarget);
    }
    if (home.latest_report.output_id) {
      params.set('output_id', home.latest_report.output_id);
    }
    if (selectedBrand?.id) {
      params.set('entity_id', selectedBrand.id);
      params.set('brand', selectedBrand.name);
      params.set('entry_source', 'dashboard_latest_report');
    }
    const targetUrl = buildDashboardChatUrlWithHandoff(
      home.latest_report.session_id,
      Object.fromEntries(params.entries()),
    );
    router.push(targetUrl);
  };

  const handleOpenMonitoringSettings = (context?: {
    recommendationId?: string;
    targetMetric?: string;
    contentFormat?: string;
  }) => {
    if (!selectedBrand?.id) return;
    const params = new URLSearchParams();
    params.set('section', 'monitoring');
    params.set('entity_id', selectedBrand.id);
    if (context?.recommendationId) params.set('recommendation_id', context.recommendationId);
    if (context?.targetMetric) params.set('monitor_metric', context.targetMetric);
    if (context?.contentFormat) params.set('content_format', context.contentFormat);
    router.push(`/settings?${params.toString()}`);
  };

  const mainContent = (
    <div className="space-y-4">
      {(!hasData || !selectedBrand || isMonitoringMode) ? (
        <HeroSection
          totalBrands={entities.length}
          selectedBrandName={selectedBrandName}
          selectedBrandDomain={selectedBrand?.domain}
          analysisLabel={selectedMonitorModeLabel}
          monitoringStatusLabel={resolveMonitoringStatusLabel(home)}
          hasMonitoringContext={hasSelectedMonitorModeContext}
          isLoading={isInitialLoading}
          onNewAnalysis={onNewAnalysis ?? (() => {})}
          onCommandSubmit={(value) => {
            void handleDashboardCommand(value);
          }}
          isCommandSubmitting={isOpeningDashboardChat}
        />
      ) : null}

      {hasLoadError && (
        <div
          className="rounded-[20px] border px-5 py-4"
          style={{
            background: 'color-mix(in srgb, var(--bg-elevated) 94%, var(--status-warning-bg) 6%)',
            borderColor: 'color-mix(in srgb, var(--status-warning) 18%, var(--border-subtle) 82%)',
          }}
        >
          <div className="text-[13px] font-medium text-[var(--text-primary)]">首页加载失败</div>
          <p className="mt-2 text-[13px] leading-7 text-[var(--text-secondary)]">请刷新重试。</p>
        </div>
      )}

      {!hasLoadError && homeError && !isMonitoringMode && (
        <div
          className="rounded-[20px] border px-5 py-4"
          style={{
            background: 'color-mix(in srgb, var(--bg-elevated) 94%, var(--status-info-bg) 6%)',
            borderColor: 'color-mix(in srgb, var(--status-info) 22%, var(--border-subtle) 78%)',
          }}
        >
          <div className="text-[13px] font-medium text-[var(--text-primary)]">分析加载失败</div>
          <p className="mt-2 text-[13px] leading-7 text-[var(--text-secondary)]">请稍后重试。</p>
        </div>
      )}

      {hasData && selectedBrand && !isMonitoringMode ? (
        <>
          <BrandOntologyHome
            entityId={selectedBrand.id}
            brandName={selectedBrand.name}
            brandDomain={selectedBrand.domain}
            brandIndustry={selectedBrand.industry}
            brandUpdatedAt={selectedBrand.updatedAt}
            dashboardHome={home}
            hasLatestReport={Boolean(home?.latest_report?.session_id)}
            onOpenLatestReport={handleOpenLatestReport}
            onAskIntelligence={(prompt, handoff) => {
              void handleDashboardCommand(prompt, { autosend: false, handoff });
            }}
            onOpenMonitoringSettings={handleOpenMonitoringSettings}
            isAskingIntelligence={isOpeningDashboardChat}
          />
          <DashboardMonitoringEntry
            brandName={selectedBrandName}
            monitorModeLabel={selectedMonitorModeLabel}
            statusLabel={resolveMonitoringStatusLabel(home)}
            onOpen={() => {
              const params = new URLSearchParams();
              params.set('tab', 'monitoring');
              params.set('entity_id', selectedBrand.id);
              router.push(`/dashboard?${params.toString()}`);
            }}
          />
        </>
      ) : null}
    </div>
  );

  return (
    <div className="dashboard-page-bg relative flex flex-1 flex-col">
      <div className="relative mx-auto w-full max-w-[1920px] px-5 py-4 lg:px-7 lg:py-5 2xl:px-10">
        {hasData && !isMonitoringMode ? (
          <div className="space-y-4 xl:space-y-0">
            <DashboardMobileBrandSwitcher
              entities={entities}
              selectedBrandId={selectedBrandId}
              onSelectBrand={setSelectedBrandId}
              onAddBrand={onNewAnalysis}
            />
            <div className="grid gap-5 xl:grid-cols-[248px_minmax(0,1fr)]">
              <div className="hidden xl:block">
                <DashboardBrandSidebar
                  entities={entities}
                  selectedBrandId={selectedBrandId}
                  onSelectBrand={setSelectedBrandId}
                  onAddBrand={onNewAnalysis}
                />
              </div>
              {mainContent}
            </div>
          </div>
        ) : (
          mainContent
        )}

        {hasData && isMonitoringMode && selectedBrand ? (
          <div className="mt-4 space-y-5">
            <section
              className="rounded-[18px] border bg-[var(--bg-tertiary)] px-6 py-5"
              style={{ borderColor: 'var(--border-subtle)' }}
            >
              <div className="flex flex-wrap items-center justify-between gap-4">
                <div>
                  <div className="text-[11px] font-medium tracking-[0.16em] text-[var(--text-tertiary)]">
                    监测与样本
                  </div>
                  <h2 className="mt-2 text-[22px] font-semibold text-[var(--text-primary)]">
                    {selectedBrand.name} 的监测与样本更新
                  </h2>
                </div>
                <button
                  type="button"
                  onClick={() => router.push('/dashboard')}
                  className="min-h-10 rounded-lg border px-4 py-2 text-[13px] font-medium"
                  style={{ borderColor: 'var(--border-subtle)', color: 'var(--text-secondary)' }}
                >
                  返回首页看板
                </button>
              </div>
            </section>
            <MonitoringTab
              entityId={selectedBrandId}
              brandName={selectedBrandName}
              autoEditSchedule={shouldEditMonitoringSchedule}
            />
          </div>
        ) : null}
      </div>
    </div>
  );
}
