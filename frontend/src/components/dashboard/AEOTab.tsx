'use client';

import {
  RiAlarmWarningLine,
  RiArrowRightUpLine,
  RiCompass3Line,
  RiFocus3Line,
  RiShieldCheckLine,
} from '@remixicon/react';
import { EmptyState } from '@/components/ui/empty-state';
import { chart } from '@/styles/chart-theme';
import type {
  CompetitorRow,
  DashboardActionItem,
  DashboardCompetitorPressureCard,
  DashboardOverviewV2,
  KPIData,
  PlatformData,
  SourceData,
} from '@/types/dashboard';

interface OverviewTabProps {
  brandName?: string;
  officialDomain?: string;
  kpi?: KPIData | null;
  sources: SourceData[];
  platforms: PlatformData[];
  competitors: CompetitorRow[];
  officialCitationRate: number | null;
  scenarioHitCount: number;
  missingHighValueScenarioCount: number;
  highRiskScenarioCount: number;
  overviewV2?: DashboardOverviewV2 | null;
}

function toPercent(value: number | null | undefined) {
  if (value == null) return '--';
  const normalized = value <= 1 ? value * 100 : value;
  return `${normalized.toFixed(1)}%`;
}

function buildOpportunityText(item: { scenario_label: string; action_hint: string; battle_status: string }) {
  if (item.action_hint) {
    return `${item.scenario_label}：${item.action_hint}`;
  }
  return `${item.scenario_label} 当前状态为 ${item.battle_status || '待补充'}。`;
}

function buildActionText(item: DashboardActionItem) {
  const scenario = item.scenario_label ? `${item.scenario_label}：` : '';
  return `${scenario}${item.action}`;
}

export function OverviewTab({
  brandName,
  officialDomain,
  kpi,
  sources,
  platforms,
  competitors,
  officialCitationRate,
  scenarioHitCount,
  missingHighValueScenarioCount,
  highRiskScenarioCount,
  overviewV2,
}: OverviewTabProps) {
  if (!overviewV2 && !kpi && sources.length === 0 && competitors.length === 0) {
    return (
      <EmptyState
        icon={RiCompass3Line}
        title="暂无总览数据"
        description="完成品牌分析后即可查看诊断摘要、重点场景和建议动作。"
      />
    );
  }

  const activePlatforms = platforms.filter((item) => item.mentionRate > 0.12);
  const topCompetitors = [...competitors]
    .sort((a, b) => b.mentionRate - a.mentionRate || b.visibility - a.visibility)
    .slice(0, 3);
  const topSource = [...sources].sort((a, b) => b.count - a.count)[0];

  const opportunities = overviewV2?.key_scenarios && overviewV2.key_scenarios.length > 0
    ? overviewV2.key_scenarios.slice(0, 3).map(buildOpportunityText)
    : [
        scenarioHitCount > 0
          ? `已建立 ${scenarioHitCount} 个有效场景，可优先固化已进入回答的平台表现。`
          : '当前还没有稳定的有效场景，建议先聚焦最核心的高意图问答。',
        officialCitationRate != null && officialCitationRate > 12
          ? '官网已经进入部分答案链路，可以继续扩张到更多高价值场景。'
          : '官网引用仍偏弱，信息源建设会直接影响品牌可信度。',
        topSource
          ? `当前最常见引用源是 ${topSource.source}，可以对照官网内容补齐同类叙事。`
          : '来源结构尚不稳定，先补齐官网和高权威信息源的基础内容。',
      ];

  const actionTexts = overviewV2?.recommended_actions && overviewV2.recommended_actions.length > 0
    ? overviewV2.recommended_actions.slice(0, 3).map(buildActionText)
    : [
        missingHighValueScenarioCount > 0
          ? `优先补齐 ${missingHighValueScenarioCount} 个被竞品抢占的重点场景。`
          : '优先把已有优势场景做成稳定引用和固定表达。',
        highRiskScenarioCount > 0
          ? `针对 ${highRiskScenarioCount} 个高风险场景建立单独监测和内容修复动作。`
          : '当前高风险压力可控，适合转向扩量和细化场景。',
        officialDomain
          ? `围绕 ${officialDomain} 统一官网答案结构，提升被引用概率。`
          : '尽快补充品牌官网域名配置，便于后续判断官网引用效果。',
      ];

  const pressureCards: DashboardCompetitorPressureCard[] = overviewV2?.competitor_pressure && overviewV2.competitor_pressure.length > 0
    ? overviewV2.competitor_pressure.slice(0, 3)
    : topCompetitors.map((competitor) => ({
        competitor: competitor.name,
        shared_scenarios: 0,
        competitor_only_scenarios: 0,
        brand_only_scenarios: 0,
        pressure_level: competitor.mentionRate > (kpi?.mentionRate ?? 0) ? 'high' : 'medium',
        top_conflict_scenarios: [],
      }));

  const summary = overviewV2?.status_summary || (
    brandName
      ? `${brandName} 当前品牌提及率 ${toPercent(kpi?.mentionRate)}，官网引用率 ${toPercent(officialCitationRate)}，在 ${activePlatforms.length} 个平台建立了稳定可见信号。`
      : `当前品牌提及率 ${toPercent(kpi?.mentionRate)}，官网引用率 ${toPercent(officialCitationRate)}，在 ${activePlatforms.length} 个平台建立了稳定可见信号。`
  );

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        {[
          {
            icon: RiCompass3Line,
            title: '当前诊断摘要',
            body: summary,
            tone: chart.colors.primary,
          },
          {
            icon: RiFocus3Line,
            title: '重点场景机会',
            body: opportunities[0],
            tone: chart.colors.source,
          },
          {
            icon: RiAlarmWarningLine,
            title: '风险暴露',
            body: `当前识别到 ${missingHighValueScenarioCount} 个缺席高价值场景，${highRiskScenarioCount} 个需要优先处理的高风险场景。`,
            tone: chart.colors.yellow,
          },
        ].map((card) => (
          <div
            key={card.title}
            className="rounded-2xl p-5"
            style={{
              background: 'linear-gradient(180deg, rgba(255,255,255,0.02), rgba(255,255,255,0))',
              border: '1px solid var(--border-subtle)',
            }}
          >
            <div className="flex items-center gap-3 mb-4">
              <div
                className="w-10 h-10 rounded-xl flex items-center justify-center"
                style={{ background: `${card.tone}1f`, color: card.tone }}
              >
                <card.icon className="w-5 h-5" />
              </div>
              <div className="text-sm font-medium" style={{ color: 'var(--text-primary)' }}>
                {card.title}
              </div>
            </div>
            <p className="text-sm leading-6" style={{ color: 'var(--text-secondary)' }}>
              {card.body}
            </p>
          </div>
        ))}
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-[1.3fr_0.9fr] gap-6">
        <div
          className="rounded-2xl p-5"
          style={{
            background: 'var(--bg-tertiary)',
            border: '1px solid var(--border-subtle)',
          }}
        >
          <div className="flex items-center gap-2 mb-4">
            <RiShieldCheckLine className="w-5 h-5" style={{ color: chart.colors.green }} />
            <h3 className="text-sm font-medium" style={{ color: 'var(--text-primary)' }}>
              重点场景机会
            </h3>
          </div>
          <div className="space-y-3">
            {opportunities.map((item) => (
              <div
                key={item}
                className="rounded-xl px-4 py-3 flex items-start gap-3"
                style={{ background: 'var(--bg-elevated)' }}
              >
                <RiArrowRightUpLine className="w-4 h-4 mt-0.5" style={{ color: chart.colors.green }} />
                <p className="text-sm leading-6" style={{ color: 'var(--text-secondary)' }}>
                  {item}
                </p>
              </div>
            ))}
          </div>
        </div>

        <div className="space-y-6">
          <div
            className="rounded-2xl p-5"
            style={{
              background: 'var(--bg-tertiary)',
              border: '1px solid var(--border-subtle)',
            }}
          >
            <div className="flex items-center gap-2 mb-4">
              <RiAlarmWarningLine className="w-5 h-5" style={{ color: chart.colors.yellow }} />
              <h3 className="text-sm font-medium" style={{ color: 'var(--text-primary)' }}>
                主要竞品压力
              </h3>
            </div>
            <div className="space-y-3">
              {pressureCards.length > 0 ? (
                pressureCards.map((competitor) => (
                  <div key={competitor.competitor} className="rounded-xl px-4 py-3" style={{ background: 'var(--bg-elevated)' }}>
                    <div className="flex items-center justify-between gap-3 mb-1">
                      <span className="text-sm font-medium" style={{ color: 'var(--text-primary)' }}>
                        {competitor.competitor}
                      </span>
                      <span className="text-xs" style={{ color: 'var(--text-tertiary)' }}>
                        {competitor.pressure_level === 'high' ? '高压力' : competitor.pressure_level === 'medium' ? '中压力' : '低压力'}
                      </span>
                    </div>
                    <p className="text-xs leading-5" style={{ color: 'var(--text-secondary)' }}>
                      共享场景 {competitor.shared_scenarios}，竞品独占 {competitor.competitor_only_scenarios}，我方独占 {competitor.brand_only_scenarios}。
                    </p>
                  </div>
                ))
              ) : (
                <p className="text-sm" style={{ color: 'var(--text-tertiary)' }}>
                  当前还没有明显的竞品压力信号。
                </p>
              )}
            </div>
          </div>

          <div
            className="rounded-2xl p-5"
            style={{
              background: 'var(--bg-tertiary)',
              border: '1px solid var(--border-subtle)',
            }}
          >
            <div className="flex items-center gap-2 mb-4">
              <RiFocus3Line className="w-5 h-5" style={{ color: chart.colors.primary }} />
              <h3 className="text-sm font-medium" style={{ color: 'var(--text-primary)' }}>
                建议优先动作
              </h3>
            </div>
            <div className="space-y-3">
              {actionTexts.map((item) => (
                <div key={item} className="rounded-xl px-4 py-3" style={{ background: 'var(--bg-elevated)' }}>
                  <p className="text-sm leading-6" style={{ color: 'var(--text-secondary)' }}>
                    {item}
                  </p>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
