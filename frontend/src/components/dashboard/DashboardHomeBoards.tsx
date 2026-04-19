'use client';

import type { DashboardHomeData } from '@/types/dashboard';
import { MentionBoard } from './MentionBoard';
import { SourceBoard } from './SourceBoard';
import { RadarBoard } from './RadarBoard';
import { DashboardSectionHeader } from './DashboardSectionHeader';
import { DashboardMonitoringKpiRow } from './DashboardMonitoringKpiRow';
import { DashboardSiteConfidenceCard } from './DashboardSiteConfidenceCard';

export type DashboardBoardId = 'mention' | 'source' | 'radar';

interface DashboardHomeBoardsProps {
  home: DashboardHomeData;
  onSelectBoard: (board: DashboardBoardId) => void;
  onOpenMonitoring?: () => void;
  onOpenLatestSiteConfidenceReport?: () => void;
}

export function DashboardHomeBoards({
  home,
  onSelectBoard,
  onOpenMonitoring,
  onOpenLatestSiteConfidenceReport,
}: DashboardHomeBoardsProps) {
  return (
    <section className="dashboard-shell rounded-[30px] px-6 py-6">
      <DashboardSectionHeader
        title="核心指标"
        action={(
          <div className="text-right">
            <div className="text-[11px] tracking-[0.12em] text-[var(--text-tertiary)]">连续监测总览</div>
            <div className="mt-1 text-[13px] text-[var(--text-secondary)]">{home.summary.headline}</div>
          </div>
        )}
      />

      <DashboardMonitoringKpiRow home={home} onOpenMonitoring={onOpenMonitoring} />

      <div className="mt-5 max-w-[420px]">
        <DashboardSiteConfidenceCard
          data={home.site_confidence_card}
          onOpenLatestReport={onOpenLatestSiteConfidenceReport}
        />
      </div>

      <div className="mt-5 grid gap-5 xl:grid-cols-3">
        <MentionBoard data={home.mention_board} onClick={() => onSelectBoard('mention')} />
        <SourceBoard data={home.source_board} onClick={() => onSelectBoard('source')} />
        <RadarBoard data={home.radar_board} onClick={() => onSelectBoard('radar')} />
      </div>
    </section>
  );
}
