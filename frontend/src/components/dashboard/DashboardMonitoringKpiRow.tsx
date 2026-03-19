'use client';

import { KPICard } from './KPICard';
import type { DashboardBoardTrend, DashboardHomeData } from '@/types/dashboard';

interface DashboardMonitoringKpiRowProps {
  home: DashboardHomeData;
  onOpenMonitoring?: () => void;
}

function formatTrendValue(value: number | null, format: DashboardBoardTrend['value_format']) {
  if (value == null) return '--';
  if (format === 'percent') {
    return `${(value * 100).toFixed(1)}%`;
  }
  return Number.isInteger(value) ? String(value) : value.toFixed(1);
}

function getTrendCardData(
  trend: DashboardBoardTrend | null | undefined,
  fallbackValue: number | null | undefined,
  title: string,
  subtitle: string,
) {
  const value = trend?.current_value ?? fallbackValue ?? null;
  const sparklineData = (trend?.points || [])
    .map((point) => point.value)
    .filter((point): point is number => point != null);

  return {
    title,
    value: formatTrendValue(value, trend?.value_format || 'score'),
    subtitle: trend
      ? `${subtitle} · ${trend.period_label} · ${trend.data_point_count} 次监测`
      : `${subtitle} · 监测样本不足`,
    trend: trend?.change_absolute != null
      ? {
          value: trend.value_format === 'percent' ? trend.change_absolute * 100 : trend.change_absolute,
          isPositive: trend.change_absolute >= 0,
          unit: trend.value_format === 'percent' ? '%' : '',
        }
      : null,
    sparklineData,
  };
}

export function DashboardMonitoringKpiRow({ home, onOpenMonitoring }: DashboardMonitoringKpiRowProps) {
  const mentionCard = getTrendCardData(
    home.mention_board.trend,
    home.mention_board.mention_rate,
    '监测提及率',
    '连续监测问题中品牌被提及的比例',
  );
  const citationCard = getTrendCardData(
    home.source_board.trend,
    home.source_board.content_citation_rate,
    '监测内容引用率',
    '连续监测答案中引用品牌内容的比例',
  );
  const radarCard = getTrendCardData(
    home.radar_board.trend,
    null,
    '监测品牌可见度',
    '基于连续监测快照汇总的整体可见度',
  );

  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-3">
      {[mentionCard, citationCard, radarCard].map((card) => (
        <KPICard
          key={card.title}
          title={card.title}
          value={card.value}
          subtitle={card.subtitle}
          trend={card.trend}
          sparklineData={card.sparklineData}
          actionLabel={onOpenMonitoring ? home.monitoring_entry.cta_label : undefined}
          onClick={onOpenMonitoring}
        />
      ))}
    </div>
  );
}
