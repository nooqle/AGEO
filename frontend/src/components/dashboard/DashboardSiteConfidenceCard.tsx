'use client';

import { KPICard } from './KPICard';
import type { DashboardSiteConfidenceCard as DashboardSiteConfidenceCardData } from '@/types/dashboard';

interface DashboardSiteConfidenceCardProps {
  data?: DashboardSiteConfidenceCardData | null;
  onOpenLatestReport?: () => void;
}

function formatScore(score: number | null | undefined): string {
  if (score == null) {
    return '--';
  }
  return Number.isInteger(score) ? String(score) : score.toFixed(1);
}

function formatLatestEvaluatedAt(value: string | null | undefined): string {
  if (!value) {
    return '最近评估：暂无';
  }

  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return '最近评估：暂无';
  }

  return `最近评估：${new Intl.DateTimeFormat('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  }).format(date)}`;
}

export function DashboardSiteConfidenceCard({
  data,
  onOpenLatestReport,
}: DashboardSiteConfidenceCardProps) {
  const sparklineData = (data?.trend?.points || [])
    .map((point) => point.value)
    .filter((value): value is number => value != null);
  const canOpenLatestReport = Boolean(
    data?.latest_report?.session_id && data?.latest_report?.artifact_id && onOpenLatestReport
  );

  return (
    <KPICard
      title="官网 AI 友好度"
      value={formatScore(data?.score)}
      subtitle={formatLatestEvaluatedAt(data?.latest_evaluated_at)}
      trend={null}
      sparklineData={sparklineData}
      actionLabel={canOpenLatestReport ? '查看最新报告' : undefined}
      onClick={canOpenLatestReport ? onOpenLatestReport : undefined}
    />
  );
}
