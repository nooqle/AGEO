'use client';

import { useEffect, useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { DashboardBrandSidebar } from './DashboardBrandSidebar';
import { DashboardPeriodMonitoring } from './DashboardPeriodMonitoring';
import { DashboardTodoStrip } from './DashboardTodoStrip';
import { MonitoringTab } from './MonitoringTab';
import { HeroSection } from './HeroSection';
import { useDashboardStore } from '@/stores/dashboardStore';
import { useEntityStore } from '@/stores/entityStore';
import { useSessionStore } from '@/stores/sessionStore';
import { api } from '@/services/api';
import { toast } from '@/components/ui/toast';
import { uniqueAiSourceDisplayNames } from '@/lib/aiSourceDisplay';
import type {
  DashboardHomeData,
  DashboardLatestReport,
  DashboardMonitorMode,
  DashboardTodoItem,
} from '@/types/dashboard';

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
  const status = home?.monitoring_plan?.status;
  if (status === 'active') return '正在监测';
  if (status === 'paused') return '暂停监测';
  return '待监测';
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

function reportTodoStorageKey(brandId: string, reportRef: string): string {
  return `specta.dashboard.report.viewed.${brandId}.${reportRef}`;
}

function isReportTodoViewed(brandId: string | null, reportRef: string | null | undefined): boolean {
  if (!brandId || !reportRef || typeof window === 'undefined') return false;
  return window.localStorage.getItem(reportTodoStorageKey(brandId, reportRef)) === '1';
}

function markReportTodoViewed(brandId: string | null, reportRef: string | null | undefined) {
  if (!brandId || !reportRef || typeof window === 'undefined') return;
  window.localStorage.setItem(reportTodoStorageKey(brandId, reportRef), '1');
}

function buildDashboardCommandDraft({
  input,
  brandName,
  home,
  aiSourceLabels,
  selectedMonitorMode,
  hasMonitoringContext,
}: {
  input: string;
  brandName: string;
  home?: DashboardHomeData | null;
  aiSourceLabels: string[];
  selectedMonitorMode: DashboardMonitorMode;
  hasMonitoringContext: boolean;
}): string {
  const trimmedInput = input.trim();
  const monitorModeLabel = MONITOR_MODE_LABELS[selectedMonitorMode];
  const latestReport = home?.latest_report;
  const monitoringPlan = home?.monitoring_plan;

  if (!hasMonitoringContext) {
    const requirement = trimmedInput ? `补充要求：${trimmedInput}。` : '';
    return `我想为「${brandName}」建立或补齐「${monitorModeLabel}」计划。${requirement}请先按现有流程确认品牌信息，再生成该分析模式的问题集给我确认。`;
  }

  const contextParts = [
    `品牌：${brandName}`,
    `分析视图：${monitorModeLabel}`,
    latestReport?.question_set_label || monitoringPlan?.question_set_label
      ? `问题集：${latestReport?.question_set_label || monitoringPlan?.question_set_label}`
      : null,
    latestReport?.sample_summary
      ? `样本：${latestReport.sample_summary}`
      : monitoringPlan
        ? `计划：${monitoringPlan.question_count} 个问题`
        : null,
    aiSourceLabels.length ? `AI来源：${aiSourceLabels.join('、')}` : null,
  ].filter((item): item is string => Boolean(item));

  const question = trimmedInput || '请解释当前 Dashboard 的主要变化，并告诉我下一步应该处理什么。';
  return `基于 Dashboard 当前上下文（${contextParts.join('；')}），请回答：${question}`;
}

export function DashboardPage({ onNewAnalysis }: DashboardPageProps) {
  const router = useRouter();
  const searchParams = useSearchParams();
  const isMonitoringMode = searchParams.get('tab') === 'monitoring';
  const [isOpeningDashboardChat, setIsOpeningDashboardChat] = useState(false);
  const [viewedReportVersion, setViewedReportVersion] = useState(0);
  const {
    selectedBrandId,
    setSelectedBrandId,
    homeMonitorMode: selectedMonitorMode,
    setHomeMonitorMode,
    home,
    isHomeLoading,
    homeError,
    fetchHome,
  } = useDashboardStore();
  const { entities, isLoading: entitiesLoading, error: entityError, fetchEntities } = useEntityStore();
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
    } else if (!selectedBrandId || !entities.some((entity) => entity.id === selectedBrandId)) {
      setSelectedBrandId(entities[0].id);
    }
  }, [selectedBrandId, entities, setSelectedBrandId]);

  const selectedBrand = entities.find((entity) => entity.id === selectedBrandId);
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

  const visibleTodoItem = (() => {
    void viewedReportVersion;
    const items = home?.todo_items || [];
    const backendItem = items.find((item) => {
      if (item.kind !== 'unread_latest_report') return true;
      return !isReportTodoViewed(selectedBrandId, item.ref_id || item.id);
    }) || null;
    if (backendItem) return backendItem;
    if (
      selectedBrand &&
      !isHomeLoading &&
      hasSelectedBrandAnalysis &&
      resolveMonitoringStatusLabel(home) === '待监测'
    ) {
      return {
        id: 'open_monitoring_plan',
        kind: 'monitoring_plan_incomplete',
        priority: 2,
        title: '开启周期监测',
        description: '当前品牌已有分析上下文，但还没有启用周期监测。开启后会按计划生成报告和趋势。',
        action: 'setup_plan',
        action_label: '开启监测',
        monitor_mode: selectedMonitorMode,
        monitoring_plan_id: home?.monitoring_plan?.id ?? null,
        ref_id: null,
        report_created_at: null,
      } satisfies DashboardTodoItem;
    }
    return null;
  })();

  const handleMonitorModeChange = (mode: DashboardMonitorMode) => {
    setHomeMonitorMode(mode);
  };

  const handleDashboardCommand = async (input: string) => {
    if (!selectedBrand || isOpeningDashboardChat) {
      if (!selectedBrand) onNewAnalysis?.();
      return;
    }

    setIsOpeningDashboardChat(true);
    try {
      const session = await api.getOrCreateSessionByEntity(selectedBrand.id);
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
      if (home?.latest_report?.sample_summary) {
        params.set('sample_summary', home.latest_report.sample_summary);
      } else if (home?.monitoring_plan) {
        params.set(
          'sample_summary',
          `${home.monitoring_plan.question_count} 个问题 · ${home.monitoring_plan.endpoint_labels.length} 个 AI 来源`,
        );
      }
      if (home?.monitoring_plan?.id) {
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
      params.set('draft', buildDashboardCommandDraft({
        input,
        brandName: selectedBrand.name,
        home,
        aiSourceLabels,
        selectedMonitorMode,
        hasMonitoringContext: hasSelectedMonitorModeContext,
      }));
      params.set('autosend', '1');
      router.push(`/chat/${session.id}?${params.toString()}`);
    } catch (error) {
      setIsOpeningDashboardChat(false);
      toast.error(error instanceof Error ? error.message : '打开 AI 对话失败，请稍后重试。');
    }
  };

  const handleOpenLatestReport = () => {
    if (!home?.latest_report?.session_id) return;
    const reportRef = latestReportRef(home.latest_report);
    markReportTodoViewed(selectedBrandId, reportRef);
    setViewedReportVersion((version) => version + 1);
    const params = new URLSearchParams();
    const artifactTarget = home.latest_report.artifact_id || home.latest_report.output_id;
    if (artifactTarget) {
      params.set('artifact_id', artifactTarget);
    }
    if (home.latest_report.output_id) {
      params.set('output_id', home.latest_report.output_id);
    }
    const query = params.toString();
    router.push(`/chat/${home.latest_report.session_id}${query ? `?${query}` : ''}`);
  };

  const handleTodoAction = (item: DashboardTodoItem) => {
    if (item.action === 'latest_report') {
      handleOpenLatestReport();
      return;
    }
    const prompt =
      item.kind === 'monitoring_plan_incomplete'
        ? '请帮我开启周期监测并完成分析计划设置。'
        : '请帮我完成品牌基本信息与问题生成。';
    void handleDashboardCommand(prompt);
  };

  const mainContent = (
    <div className="space-y-4">
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
          <DashboardTodoStrip item={visibleTodoItem} onAction={handleTodoAction} />
          <DashboardPeriodMonitoring
            home={home}
            selectedMonitorMode={selectedMonitorMode}
            selectedBrandName={selectedBrandName}
            onMonitorModeChange={handleMonitorModeChange}
            isLoading={isHomeLoading}
          />
        </>
      ) : null}
    </div>
  );

  return (
    <div className="dashboard-page-bg relative flex flex-1 flex-col overflow-auto">
      <div className="relative mx-auto w-full max-w-[1920px] px-5 py-4 lg:px-7 lg:py-5 2xl:px-10">
        {hasData && !isMonitoringMode ? (
          <div className="grid gap-5 xl:grid-cols-[248px_minmax(0,1fr)]">
            <DashboardBrandSidebar
              entities={entities}
              selectedBrandId={selectedBrandId}
              onSelectBrand={setSelectedBrandId}
              onAddBrand={onNewAnalysis}
            />
            {mainContent}
          </div>
        ) : (
          mainContent
        )}

        {hasData && isMonitoringMode && selectedBrand ? (
          <div className="mt-4 space-y-5">
            <section
              className="rounded-[24px] border bg-[var(--bg-tertiary)] px-6 py-5"
              style={{ borderColor: 'var(--border-subtle)' }}
            >
              <div className="flex flex-wrap items-center justify-between gap-4">
                <div>
                  <div className="text-[11px] font-medium tracking-[0.16em] text-[var(--text-tertiary)]">
                    持续监测
                  </div>
                  <h2 className="mt-2 text-[22px] font-semibold text-[var(--text-primary)]">
                    {selectedBrand.name} 的持续监测
                  </h2>
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
            <MonitoringTab entityId={selectedBrandId} brandName={selectedBrandName} />
          </div>
        ) : null}
      </div>
    </div>
  );
}
