'use client';

import { useEffect, useRef, useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import {
  DashboardBrandSidebar,
  DashboardMobileBrandSwitcher,
} from './DashboardBrandSidebar';
import { BrandIntelligenceChatBubble } from './BrandIntelligenceChatBubble';
import { BrandIntelligenceRunBanner } from './BrandIntelligenceRunBanner';
import { DashboardChatTaskBanner } from './DashboardChatTaskBanner';
import { BrandOntologyHome } from './BrandOntologyHome';
import { HeroSection } from './HeroSection';
import { useDashboardStore } from '@/stores/dashboardStore';
import { useEntityStore } from '@/stores/entityStore';
import { useIntelligenceRunStore } from '@/stores/intelligenceRunStore';
import { useOntologyStore } from '@/stores/ontologyStore';
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
import type { AnalysisTask } from '@/types/task';
import { isActiveBrandIntelligenceRun } from '@/types/intelligenceRun';
import type { OntologyWorldSummary } from '@/types/ontology';

interface DashboardPageProps {
  onNewAnalysis?: () => void;
}

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

function createHandoffId(): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID();
  }
  return `${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function activeTaskTime(task: AnalysisTask): number {
  const parsed = Date.parse(task.started_at || task.created_at || '');
  return Number.isFinite(parsed) ? parsed : 0;
}

function compareDashboardActiveTasks(selectedBrandId: string | null) {
  return (a: AnalysisTask, b: AnalysisTask) => {
    const aWaiting = a.latest_run?.status === 'waiting_input';
    const bWaiting = b.latest_run?.status === 'waiting_input';
    if (aWaiting !== bWaiting) return aWaiting ? -1 : 1;

    if (selectedBrandId) {
      const aSelected = a.entity_id === selectedBrandId;
      const bSelected = b.entity_id === selectedBrandId;
      if (aSelected !== bSelected) return aSelected ? -1 : 1;
    }

    if (a.status !== b.status) return a.status === 'running' ? -1 : 1;
    return activeTaskTime(b) - activeTaskTime(a);
  };
}

export function DashboardPage({ onNewAnalysis }: DashboardPageProps) {
  const router = useRouter();
  const searchParams = useSearchParams();
  const requestedEntityId = searchParams.get('entity_id');
  const [isOpeningDashboardChat, setIsOpeningDashboardChat] = useState(false);
  const [activeAnalysisTasks, setActiveAnalysisTasks] = useState<AnalysisTask[]>([]);
  const [isAnalysisTaskLoading, setIsAnalysisTaskLoading] = useState(false);
  const isOpeningDashboardChatRef = useRef(false);
  const {
    selectedBrandId,
    setSelectedBrandId,
    homeMonitorMode: selectedMonitorMode,
    home,
    homeError,
    fetchHome,
  } = useDashboardStore();
  const { entities, isLoading: entitiesLoading, error: entityError, fetchEntities } = useEntityStore();
  const { worldsByEntity, fetchWorld } = useOntologyStore();
  const {
    runsByEntity,
    loadingByEntity: runLoadingByEntity,
    errorByEntity: runErrorByEntity,
    submittingByEntity: runSubmittingByEntity,
    fetchActiveRun,
    createRun,
    resumeRun,
    cancelRun,
  } = useIntelligenceRunStore();

  useEffect(() => {
    fetchEntities();
  }, [fetchEntities]);

  useEffect(() => {
    if (selectedBrandId) {
      void fetchHome();
      void fetchActiveRun(selectedBrandId);
    }
  }, [fetchActiveRun, fetchHome, selectedBrandId, selectedMonitorMode]);

  useEffect(() => {
    let cancelled = false;
    const fetchActiveAnalysisTasks = async () => {
      setIsAnalysisTaskLoading(true);
      try {
        const [running, pending] = await Promise.all([
          api.getUserTasks({
            status: 'running',
            triggeredBy: 'manual',
            limit: 10,
          }),
          api.getUserTasks({
            status: 'pending',
            triggeredBy: 'manual',
            limit: 10,
          }),
        ]);
        if (cancelled) return;
        const candidates = [...(running.tasks || []), ...(pending.tasks || [])]
          .filter((task) => Boolean(task.session_id))
          .sort(compareDashboardActiveTasks(selectedBrandId));
        setActiveAnalysisTasks(candidates);
      } catch {
        if (!cancelled) setActiveAnalysisTasks([]);
      } finally {
        if (!cancelled) setIsAnalysisTaskLoading(false);
      }
    };

    void fetchActiveAnalysisTasks();
    const timer = window.setInterval(() => {
      void fetchActiveAnalysisTasks();
    }, 6000);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [selectedBrandId]);

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
  const selectedRun = selectedBrandId ? runsByEntity[selectedBrandId] : null;
  const isSelectedRunActive = isActiveBrandIntelligenceRun(selectedRun);
  const visibleActiveAnalysisTask =
    activeAnalysisTasks.find((task) => selectedRun?.analysis_task_id !== task.id) ?? null;
  const visibleActiveTaskEntity = visibleActiveAnalysisTask
    ? entities.find((entity) => entity.id === visibleActiveAnalysisTask.entity_id)
    : null;
  const visibleActiveTaskBrandName =
    visibleActiveTaskEntity?.name ||
    (visibleActiveAnalysisTask?.entity_id === selectedBrand?.id ? (selectedBrand?.name ?? null) : null);
  const isVisibleActiveTaskCurrentBrand =
    Boolean(visibleActiveAnalysisTask && visibleActiveAnalysisTask.entity_id === selectedBrand?.id);
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
  const hasLoadError = Boolean(entityError);
  const hasData = entities.length > 0;
  const isInitialLoading = entitiesLoading;

  useEffect(() => {
    if (!selectedBrandId || !isSelectedRunActive) return;
    const timer = window.setInterval(() => {
      void fetchActiveRun(selectedBrandId);
      void fetchWorld(selectedBrandId);
    }, 6000);
    return () => window.clearInterval(timer);
  }, [fetchActiveRun, fetchWorld, isSelectedRunActive, selectedBrandId, selectedRun?.id, selectedRun?.status]);

  const openDashboardChat = async (
    input: string,
    options?: {
      autosend?: boolean;
      handoff?: { taskTitle?: string; taskGoal?: string };
      entrySource?: string;
      runContext?: {
        runId?: string;
        handoffId?: string;
        intent?: string;
      };
    },
  ) => {
    if (!selectedBrand) {
      onNewAnalysis?.();
      return;
    }

    const session = await api.getOrCreateSessionByEntity(selectedBrand.id);
    const draft = buildDashboardVisibleDraft(input);
    if (!draft) {
      router.push(`/chat/${session.id}`);
      return;
    }

    const params = new URLSearchParams();
    params.set('entity_id', selectedBrand.id);
    params.set('brand', selectedBrand.name);
    params.set('entry_source', options?.entrySource || 'dashboard_command_bar');
    params.set(
      'monitor_mode',
      selectedMonitorMode === 'scenario' ? 'scenario_monitoring' : 'panorama_monitoring',
    );
    if (options?.runContext?.runId) {
      params.set('run_id', options.runContext.runId);
    }
    if (options?.runContext?.handoffId) {
      params.set('handoff_id', options.runContext.handoffId);
    }
    if (options?.runContext?.intent) {
      params.set('intent', options.runContext.intent);
    }
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
  };

  const handleDashboardCommand = async (
    input: string,
    options?: Parameters<typeof openDashboardChat>[1],
  ) => {
    if (!selectedBrand || isOpeningDashboardChatRef.current) {
      if (!selectedBrand) onNewAnalysis?.();
      return;
    }

    isOpeningDashboardChatRef.current = true;
    setIsOpeningDashboardChat(true);
    try {
      await openDashboardChat(input, options);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : '打开对话失败，请稍后重试。');
    } finally {
      isOpeningDashboardChatRef.current = false;
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

  const handleOpenActiveAnalysisTaskChat = () => {
    if (!visibleActiveAnalysisTask?.session_id) return;
    const params = new URLSearchParams();
    if (visibleActiveTaskBrandName) params.set('brand', visibleActiveTaskBrandName);
    params.set('entry_source', 'dashboard_active_chat_task');
    const query = params.toString();
    router.push(`/chat/${visibleActiveAnalysisTask.session_id}${query ? `?${query}` : ''}`);
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

  const handleStartBrandIntelligenceRun = async () => {
    if (!selectedBrand?.id) return;
    try {
      await createRun(selectedBrand.id, {
        run_goal: '分析当前品牌在 AI 平台里的表现',
        analysis_mode: selectedMonitorMode,
        origin_surface: 'dashboard',
        origin_event_id: `dashboard-start:${selectedBrand.id}:${selectedMonitorMode}:${createHandoffId()}`,
        auto_dispatch: true,
        input_scope: {
          monitor_mode: selectedMonitorMode,
          sample_summary: brandWorldSampleSummary,
          current_metrics: brandWorldMetricSummary,
          ai_sources: aiSourceLabels,
        },
      });
      void fetchActiveRun(selectedBrand.id);
      void fetchWorld(selectedBrand.id);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : '开始分析失败，请稍后重试。');
    }
  };

  const handleResumeBrandIntelligenceRun = async () => {
    if (!selectedBrand?.id) return;
    if (!selectedRun) {
      await handleStartBrandIntelligenceRun();
      return;
    }
    try {
      await resumeRun(selectedBrand.id, selectedRun.id);
      void fetchActiveRun(selectedBrand.id);
      void fetchWorld(selectedBrand.id);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : '继续分析失败，请稍后重试。');
    }
  };

  const handleCancelBrandIntelligenceRun = async () => {
    if (!selectedBrand?.id || !selectedRun?.id) return;
    try {
      await cancelRun(selectedBrand.id, selectedRun.id);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : '取消任务失败，请稍后重试。');
    }
  };

  const handleOpenRunChat = async (intent = 'explain_current_intelligence') => {
    if (!selectedBrand?.id || isOpeningDashboardChatRef.current) {
      if (!selectedBrand) onNewAnalysis?.();
      return;
    }

    isOpeningDashboardChatRef.current = true;
    setIsOpeningDashboardChat(true);
    try {
      const handoffId = createHandoffId();
      const reusableRun = selectedRun?.status === 'cancelled' ? null : selectedRun;
      const run =
        reusableRun ||
        (await createRun(selectedBrand.id, {
          run_goal: '解释当前品牌在 AI 平台里的表现',
          analysis_mode: selectedMonitorMode,
          origin_surface: 'dashboard_chat_bubble',
          origin_event_id: `dashboard-chat:${selectedBrand.id}:${selectedMonitorMode}:${intent}:${handoffId}`,
          auto_dispatch: false,
          input_scope: {
            monitor_mode: selectedMonitorMode,
            sample_summary: brandWorldSampleSummary,
            current_metrics: brandWorldMetricSummary,
            ai_sources: aiSourceLabels,
          },
        }));

      const draft = run.requires_user_action
        ? '我需要确认当前情报任务的下一步。'
        : run.status === 'failed'
          ? '请解释这次分析为什么失败，并给我下一步处理建议。'
          : '请基于当前品牌情报解释重点、证据和下一步建议。';

      await openDashboardChat(draft, {
        autosend: false,
        entrySource: 'dashboard_chat_bubble',
        runContext: { runId: run.id, handoffId, intent },
        handoff: {
          taskTitle: run.message || '当前品牌情报任务',
          taskGoal: run.run_goal || '解释当前品牌在 AI 平台里的表现',
        },
      });
    } catch (error) {
      toast.error(error instanceof Error ? error.message : '打开对话失败，请稍后重试。');
    } finally {
      isOpeningDashboardChatRef.current = false;
      setIsOpeningDashboardChat(false);
    }
  };

  const mainContent = (
    <div className="space-y-4">
      {(!hasData || !selectedBrand) ? (
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

      {!hasLoadError && homeError && (
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

      {hasData && selectedBrand ? (
        <>
          <BrandIntelligenceRunBanner
            run={selectedRun}
            isLoading={runLoadingByEntity[selectedBrand.id]}
            isSubmitting={runSubmittingByEntity[selectedBrand.id]}
            error={runErrorByEntity[selectedBrand.id]}
            onStart={() => {
              void handleStartBrandIntelligenceRun();
            }}
            onResume={() => {
              void handleResumeBrandIntelligenceRun();
            }}
            onCancel={() => {
              void handleCancelBrandIntelligenceRun();
            }}
            onOpenChat={() => {
              void handleOpenRunChat();
            }}
          />
          <DashboardChatTaskBanner
            task={visibleActiveAnalysisTask}
            brandName={visibleActiveTaskBrandName}
            isCurrentBrandTask={isVisibleActiveTaskCurrentBrand}
            isLoading={isAnalysisTaskLoading}
            onOpenChat={handleOpenActiveAnalysisTaskChat}
          />
          <BrandOntologyHome
            entityId={selectedBrand.id}
            brandName={selectedBrand.name}
            brandDomain={selectedBrand.domain}
            brandIndustry={selectedBrand.industry}
            brandUpdatedAt={selectedBrand.updatedAt}
            dashboardHome={home}
            hasLatestReport={Boolean(home?.latest_report?.session_id)}
            onOpenLatestReport={handleOpenLatestReport}
            onAskIntelligence={(prompt, handoff, options) => {
              if (options?.autosend) {
                void handleResumeBrandIntelligenceRun();
                return;
              }
              void handleDashboardCommand(prompt, {
                autosend: false,
                handoff,
              });
            }}
            onOpenMonitoringSettings={handleOpenMonitoringSettings}
            isAskingIntelligence={isOpeningDashboardChat || Boolean(runSubmittingByEntity[selectedBrand.id])}
          />
        </>
      ) : null}
    </div>
  );

  return (
    <div className="dashboard-page-bg relative flex flex-1 flex-col">
      <div className="relative mx-auto w-full max-w-[1920px] px-5 pb-28 pt-4 lg:px-7 lg:pb-24 lg:pt-5 2xl:px-10">
        {hasData ? (
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

      </div>
      {hasData && selectedBrand ? (
        <BrandIntelligenceChatBubble
          run={selectedRun}
          isOpening={isOpeningDashboardChat}
          onOpenChat={() => {
            void handleOpenRunChat();
          }}
        />
      ) : null}
    </div>
  );
}
