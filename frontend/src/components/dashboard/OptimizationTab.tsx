'use client';

import {
  RiAlarmWarningLine,
  RiArrowRightUpLine,
  RiCheckboxCircleLine,
  RiFlagLine,
  RiTimeLine,
} from '@remixicon/react';
import type {
  CompetitorRow,
  DashboardActionItem,
  DashboardRiskItem,
  OptimizationUnit,
} from '@/types/dashboard';
import { EmptyState } from '@/components/ui/empty-state';
import { chart } from '@/styles/chart-theme';

interface OptimizationTabProps {
  data: OptimizationUnit[];
  brandName?: string;
  brandMentionRate?: number | null;
  brandVisibility?: number | null;
  officialCitationRate?: number | null;
  officialDomain?: string;
  competitors?: CompetitorRow[];
  riskActionV2?: {
    risks?: DashboardRiskItem[];
    actions?: DashboardActionItem[];
  } | null;
}

interface RiskCard {
  id: string;
  severity: 'high' | 'medium' | 'low';
  riskType: string;
  scenarioLabel: string;
  reason: string;
  impactSummary: string;
  evidence: string;
}

interface ActionCard {
  id: string;
  priority: 'high' | 'medium' | 'low';
  scenarioLabel: string;
  action: string;
  target: string;
  expectedMetric: string;
  relatedCompetitors: string[];
  status: 'not_started' | 'in_progress' | 'done';
}

const severityTone = {
  high: { color: chart.colors.red, bg: `${chart.colors.red}1a`, label: '高风险' },
  medium: { color: chart.colors.yellow, bg: `${chart.colors.yellow}1a`, label: '中风险' },
  low: { color: chart.colors.green, bg: `${chart.colors.green}1a`, label: '低风险' },
} as const;

const priorityTone = {
  high: { color: chart.colors.red, bg: `${chart.colors.red}1a`, label: 'P1' },
  medium: { color: chart.colors.yellow, bg: `${chart.colors.yellow}1a`, label: 'P2' },
  low: { color: chart.colors.green, bg: `${chart.colors.green}1a`, label: 'P3' },
} as const;

function normalizePriority(priority: DashboardActionItem['priority'] | OptimizationUnit['priority']): ActionCard['priority'] {
  if (priority === 'high' || priority === 'medium' || priority === 'low') {
    return priority;
  }
  if (typeof priority === 'number') {
    return priority <= 1 ? 'high' : priority === 2 ? 'medium' : 'low';
  }
  if (typeof priority === 'string') {
    const upper = priority.toUpperCase();
    if (upper === 'P0' || upper === 'P1' || upper === 'HIGH') return 'high';
    if (upper === 'P2' || upper === 'MEDIUM') return 'medium';
  }
  return 'low';
}

function normalizeRiskCard(item: DashboardRiskItem): RiskCard {
  return {
    id: item.risk_id,
    severity: item.severity === 'high' || item.severity === 'medium' ? item.severity : 'low',
    riskType: item.risk_type,
    scenarioLabel: item.scenario_label,
    reason: item.reason,
    impactSummary: item.impact_summary,
    evidence: item.evidence || '待补充',
  };
}

function normalizeActionCard(item: DashboardActionItem): ActionCard {
  return {
    id: item.action_id,
    priority: normalizePriority(item.priority),
    scenarioLabel: item.scenario_label,
    action: item.action,
    target: item.target,
    expectedMetric: item.expected_metric || '待补充',
    relatedCompetitors: item.related_competitors || [],
    status: item.status === 'done' || item.status === 'in_progress' ? item.status : 'not_started',
  };
}

function deriveRiskAndActionCards(
  brandName: string | undefined,
  brandMentionRate: number | null | undefined,
  brandVisibility: number | null | undefined,
  officialCitationRate: number | null | undefined,
  officialDomain: string | undefined,
  competitors: CompetitorRow[],
  units: OptimizationUnit[]
): { risks: RiskCard[]; actions: ActionCard[] } {
  const sortedCompetitors = [...competitors].sort(
    (a, b) => b.mentionRate - a.mentionRate || b.visibility - a.visibility
  );

  const competitorRisks = sortedCompetitors.slice(0, 3).map((competitor, index) => {
    const visibilityGap = competitor.visibility - (brandVisibility ?? 0);
    const mentionGap = competitor.mentionRate - (brandMentionRate ?? 0);
    const severity: RiskCard['severity'] =
      visibilityGap > 10 || mentionGap > 0.12 ? 'high' : visibilityGap > 4 || mentionGap > 0.05 ? 'medium' : 'low';

    return {
      id: `competitor-risk-${index}`,
      severity,
      riskType: visibilityGap > 10 ? '竞品替代' : '品牌存在感弱',
      scenarioLabel: `${brandName || '当前品牌'} vs ${competitor.name}`,
      reason: `${competitor.name} 当前提及率 ${(competitor.mentionRate * 100).toFixed(1)}%，可见度 ${competitor.visibility.toFixed(1)}。`,
      impactSummary:
        severity === 'high'
          ? '用户在高意图回答中更容易先看到竞品，品牌可能持续缺席。'
          : '该场景已出现压力，如果不及时修复容易被竞品稳定占位。',
      evidence: `平均排名 ${competitor.avgRanking.toFixed(1)}，情感 ${(competitor.sentiment * 100).toFixed(0)}%。`,
    };
  });

  const citationRisk: RiskCard[] =
    officialCitationRate != null && officialCitationRate < 8
      ? [
          {
            id: 'official-citation-risk',
            severity: 'high',
            riskType: '官网未被引用',
            scenarioLabel: '官网引用链路',
            reason: officialDomain
              ? `${officialDomain} 还没有稳定进入 AI 回答的引用链路。`
              : '当前品牌缺少官网域名配置，无法稳定判断官网是否进入引用链路。',
            impactSummary: '品牌即使被提及，也缺少可验证的官方证据，可信度会继续受限。',
            evidence: `当前官网引用率 ${officialCitationRate.toFixed(1)}%。`,
          },
        ]
      : [];

  const optimizationActions: ActionCard[] = units.slice(0, 3).map((unit, index) => ({
    id: `optimization-action-${index}`,
    priority: normalizePriority(unit.priority),
    scenarioLabel: unit.query,
    action: `优化与“${unit.query}”相关的回答素材。`,
    target: unit.currentRank != null ? `将当前排名从 #${unit.currentRank} 拉升到 #${unit.targetRank}` : `进入 Top ${unit.targetRank}`,
    expectedMetric: '提升提及率与回答前排出现概率',
    relatedCompetitors: [],
    status: unit.status === 'optimized' ? 'done' : unit.status === 'in_progress' ? 'in_progress' : 'not_started',
  }));

  const derivedActions: ActionCard[] = [
    {
      id: 'action-content-gap',
      priority: competitorRisks[0]?.severity === 'high' ? 'high' : 'medium',
      scenarioLabel: competitorRisks[0]?.scenarioLabel || '重点高意图场景',
      action: '补齐对比型和决策型内容，统一官网答案结构。',
      target: '让品牌在重点场景稳定进入回答，并减少竞品独占。',
      expectedMetric: '提升品牌提及率与整体可见度',
      relatedCompetitors: competitorRisks[0] ? [competitorRisks[0].scenarioLabel.split(' vs ')[1]] : [],
      status: 'not_started',
    },
    {
      id: 'action-official-citation',
      priority: officialCitationRate != null && officialCitationRate < 8 ? 'high' : 'medium',
      scenarioLabel: '官网引用链路',
      action: '整理官网核心页面的标准表述，补齐可被 AI 直接引用的信息块。',
      target: officialDomain ? `提升 ${officialDomain} 的被引用概率。` : '补齐官网域名配置并提升官网被引用概率。',
      expectedMetric: '提升官网引用率',
      relatedCompetitors: [],
      status: 'not_started',
    },
  ];

  return {
    risks: [...citationRisk, ...competitorRisks].slice(0, 4),
    actions: [...optimizationActions, ...derivedActions].slice(0, 4),
  };
}

export function OptimizationTab({
  data,
  brandName,
  brandMentionRate,
  brandVisibility,
  officialCitationRate,
  officialDomain,
  competitors = [],
  riskActionV2,
}: OptimizationTabProps) {
  const normalizedV2Risks = riskActionV2?.risks?.map(normalizeRiskCard) ?? [];
  const normalizedV2Actions = riskActionV2?.actions?.map(normalizeActionCard) ?? [];
  const fallback = deriveRiskAndActionCards(
    brandName,
    brandMentionRate,
    brandVisibility,
    officialCitationRate,
    officialDomain,
    competitors,
    data
  );

  const risks = normalizedV2Risks.length > 0 ? normalizedV2Risks : fallback.risks;
  const actions = normalizedV2Actions.length > 0 ? normalizedV2Actions : fallback.actions;

  if (risks.length === 0 && actions.length === 0) {
    return (
      <EmptyState
        icon={RiFlagLine}
        title="暂无风险与动作"
        description="完成完整分析流程后即可查看风险定位和优先动作。"
      />
    );
  }

  return (
    <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">
      <div
        className="rounded-2xl p-5"
        style={{
          background: 'var(--bg-tertiary)',
          border: '1px solid var(--border-subtle)',
        }}
      >
        <div className="flex items-center gap-2 mb-4">
          <RiAlarmWarningLine className="w-5 h-5" style={{ color: chart.colors.red }} />
          <h3 className="text-sm font-medium" style={{ color: 'var(--text-primary)' }}>
            风险卡片
          </h3>
        </div>
        <div className="space-y-4">
          {risks.map((risk) => (
            <div key={risk.id} className="rounded-xl p-4" style={{ background: 'var(--bg-elevated)' }}>
              <div className="flex items-start justify-between gap-3 mb-3">
                <div>
                  <div className="text-xs mb-1" style={{ color: 'var(--text-tertiary)' }}>
                    {risk.riskType}
                  </div>
                  <div className="text-sm font-medium" style={{ color: 'var(--text-primary)' }}>
                    {risk.scenarioLabel}
                  </div>
                </div>
                <span
                  className="px-2 py-0.5 rounded-full text-xs font-medium"
                  style={{
                    color: severityTone[risk.severity].color,
                    backgroundColor: severityTone[risk.severity].bg,
                  }}
                >
                  {severityTone[risk.severity].label}
                </span>
              </div>
              <div className="space-y-2 text-sm leading-6" style={{ color: 'var(--text-secondary)' }}>
                <p>{risk.reason}</p>
                <p>{risk.impactSummary}</p>
                <p style={{ color: 'var(--text-tertiary)' }}>判断依据：{risk.evidence}</p>
              </div>
            </div>
          ))}
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
          <RiArrowRightUpLine className="w-5 h-5" style={{ color: chart.colors.green }} />
          <h3 className="text-sm font-medium" style={{ color: 'var(--text-primary)' }}>
            动作卡片
          </h3>
        </div>
        <div className="space-y-4">
          {actions.map((action) => (
            <div key={action.id} className="rounded-xl p-4" style={{ background: 'var(--bg-elevated)' }}>
              <div className="flex items-start justify-between gap-3 mb-3">
                <div>
                  <div className="text-xs mb-1" style={{ color: 'var(--text-tertiary)' }}>
                    {action.scenarioLabel}
                  </div>
                  <div className="text-sm font-medium" style={{ color: 'var(--text-primary)' }}>
                    {action.action}
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  <span
                    className="px-2 py-0.5 rounded-full text-xs font-medium"
                    style={{
                      color: priorityTone[action.priority].color,
                      backgroundColor: priorityTone[action.priority].bg,
                    }}
                  >
                    {priorityTone[action.priority].label}
                  </span>
                  {action.status === 'done' ? (
                    <RiCheckboxCircleLine className="w-4 h-4" style={{ color: chart.colors.green }} />
                  ) : action.status === 'in_progress' ? (
                    <RiTimeLine className="w-4 h-4" style={{ color: chart.colors.yellow }} />
                  ) : (
                    <RiFlagLine className="w-4 h-4" style={{ color: 'var(--text-tertiary)' }} />
                  )}
                </div>
              </div>
              <div className="space-y-2 text-sm leading-6" style={{ color: 'var(--text-secondary)' }}>
                <p>优化目标：{action.target}</p>
                <p>期望改善：{action.expectedMetric}</p>
                <p>
                  相关竞品：
                  {action.relatedCompetitors.length > 0 ? action.relatedCompetitors.join('、') : '当前无明确竞品绑定'}
                </p>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
