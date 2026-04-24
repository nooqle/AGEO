'use client';

import { useEffect, useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { DashboardBrandOverview, type DashboardBrandArchiveData } from './DashboardBrandOverview';
import { DashboardHomeBoards } from './DashboardHomeBoards';
import { MonitoringTab } from './MonitoringTab';
import { HeroSection } from './HeroSection';
import { BrandCards } from './BrandCards';
import { useDashboardStore } from '@/stores/dashboardStore';
import { useEntityStore } from '@/stores/entityStore';
import { useSessionStore } from '@/stores/sessionStore';
import { EmptyState } from '@/components/ui/empty-state';
import { api } from '@/services/api';
import { toast } from '@/components/ui/toast';

interface DashboardPageProps {
  onNewAnalysis?: () => void;
}

export function DashboardPage({ onNewAnalysis }: DashboardPageProps) {
  const router = useRouter();
  const searchParams = useSearchParams();
  const isMonitoringMode = searchParams.get('tab') === 'monitoring';
  const [brandArchive, setBrandArchive] = useState<DashboardBrandArchiveData | null>(null);
  const [isOpeningLatestReport, setIsOpeningLatestReport] = useState(false);
  const {
    selectedBrandId,
    setSelectedBrandId,
    home,
    isHomeLoading,
    homeError,
    fetchHome,
  } = useDashboardStore();
  const { entities, isLoading: entitiesLoading, error: entityError, fetchEntities } = useEntityStore();
  const { totalSessions, listError, fetchSessionList } = useSessionStore();

  useEffect(() => {
    fetchEntities();
    fetchSessionList();
  }, [fetchEntities, fetchSessionList]);

  useEffect(() => {
    if (selectedBrandId && !isMonitoringMode) {
      void fetchHome();
    }
  }, [fetchHome, isMonitoringMode, selectedBrandId]);

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

  const selectedBrand = entities.find((entity) => entity.id === selectedBrandId);
  const selectedBrandName = selectedBrand?.name;
  const hasLoadError = Boolean(entityError || listError);
  const hasData = entities.length > 0;
  const isInitialLoading = entitiesLoading;
  const hasSelectedBrandAnalysis = Boolean(
    home?.latest_report ||
      home?.summary?.headline ||
      (home?.metrics?.length ?? 0) > 0
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

  const handleOpenLatestReport = () => {
    if (!home?.latest_report?.session_id) return;
    setIsOpeningLatestReport(true);
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
            <div
              className="rounded-[24px] border px-5 py-4"
              style={{
                background: 'color-mix(in srgb, var(--bg-elevated) 92%, #fff5e8 8%)',
                borderColor: 'color-mix(in srgb, #d79b45 26%, var(--border-subtle) 74%)',
              }}
            >
              <div className="text-[13px] font-medium" style={{ color: 'var(--text-primary)' }}>
                首页加载失败
              </div>
              <p className="mt-2 text-[13px] leading-7" style={{ color: 'var(--text-secondary)' }}>
                请刷新重试。
              </p>
            </div>
          )}

          {!hasLoadError && homeError && !isMonitoringMode && (
            <div
              className="rounded-[24px] border px-5 py-4"
              style={{
                background: 'color-mix(in srgb, var(--bg-elevated) 94%, #eef4ff 6%)',
                borderColor: 'color-mix(in srgb, var(--color-primary) 22%, var(--border-subtle) 78%)',
              }}
            >
              <div className="text-[13px] font-medium" style={{ color: 'var(--text-primary)' }}>
                分析加载失败
              </div>
              <p className="mt-2 text-[13px] leading-7" style={{ color: 'var(--text-secondary)' }}>
                请稍后重试。
              </p>
            </div>
          )}

          <BrandCards onAddBrand={onNewAnalysis} />

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
              <MonitoringTab entityId={selectedBrandId} brandName={selectedBrandName} />
            </div>
          )}

          {hasData && !isMonitoringMode && selectedBrand && isHomeLoading && !hasSelectedBrandAnalysis && (
            <div className="space-y-4">
              <div className="h-32 rounded-[28px] animate-shimmer" />
              <div className="grid gap-4 lg:grid-cols-3">
                <div className="h-36 rounded-[24px] animate-shimmer" />
                <div className="h-36 rounded-[24px] animate-shimmer" />
                <div className="h-36 rounded-[24px] animate-shimmer" />
              </div>
              <div className="h-80 rounded-[28px] animate-shimmer" />
            </div>
          )}

          {hasData && !isMonitoringMode && selectedBrand && !isHomeLoading && hasSelectedBrandAnalysis && home && (
            <div className="space-y-6">
              <DashboardBrandOverview entity={selectedBrand} archive={brandArchive} />
              <DashboardHomeBoards home={home} onOpenLatestReport={handleOpenLatestReport} isOpeningLatestReport={isOpeningLatestReport} />
            </div>
          )}

          {hasData && !isMonitoringMode && selectedBrand && !isHomeLoading && !hasSelectedBrandAnalysis && !homeError && (
            <EmptyState
              title={`${selectedBrand.name} 暂无最近分析`}
              description="完成分析后显示最新报告。"
              action={{
                label: '进入品牌分析',
                onClick: () => {
                  void handleOpenBrandAnalysis();
                },
              }}
            />
          )}
        </div>
      </div>
    </div>
  );
}
