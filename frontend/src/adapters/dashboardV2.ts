import type { DashboardV2Data } from '@/types/dashboard';

function toNullableNumber(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null;
}

function normalizeScenarioRow(row: Record<string, unknown>) {
  return {
    scenario_id: String(row.scenarioId ?? ''),
    scenario_label: String(row.scenarioLabel ?? ''),
    scenario_priority: String(row.scenarioPriority ?? 'medium'),
    brand_present: Boolean(row.brandPresent),
    present_platforms: Array.isArray(row.presentPlatforms) ? row.presentPlatforms.map(String) : [],
    official_citation_present: Boolean(row.officialCitationPresent),
    official_sources: Array.isArray(row.officialSourceDomains) ? row.officialSourceDomains.map(String) : [],
    competitors_present: Array.isArray(row.competitorsPresent) ? row.competitorsPresent.map(String) : [],
    winner_brands: Array.isArray(row.winnerBrands) ? row.winnerBrands.map(String) : [],
    battle_status: String(row.battleStatus ?? 'missing'),
    risk_level: String(row.riskLevel ?? 'low'),
    action_hint: String(row.actionHint ?? ''),
    evidence: typeof row.evidence === 'string' ? row.evidence : undefined,
    query_examples: Array.isArray(row.queryExamples) ? row.queryExamples.map(String) : [],
  };
}

function normalizeCompetitorCard(row: Record<string, unknown>) {
  return {
    competitor: String(row.competitor ?? ''),
    shared_scenarios: Number(row.sharedScenarios ?? 0),
    competitor_only_scenarios: Number(row.competitorOnlyScenarios ?? 0),
    brand_only_scenarios: Number(row.brandOnlyScenarios ?? 0),
    pressure_level: String(row.pressureLevel ?? 'low'),
    top_conflict_scenarios: Array.isArray(row.topConflictScenarios) ? row.topConflictScenarios.map(String) : [],
  };
}

function normalizeScenarioMatrixRow(row: Record<string, unknown>) {
  const brandStates = row.brandStates && typeof row.brandStates === 'object' ? row.brandStates as Record<string, Record<string, unknown>> : {};
  return {
    scenario_id: String(row.scenarioId ?? ''),
    scenario_label: String(row.scenarioLabel ?? ''),
    winner_brand: String(row.winnerBrand ?? ''),
    battle_status: String(row.battleStatus ?? 'missing'),
    recommended_focus: typeof row.recommendedFocus === 'string' ? row.recommendedFocus : undefined,
    competitor_states: Object.entries(brandStates).map(([brand, state]) => ({
      brand,
      state: String(state?.state ?? 'absent'),
      official_cited: Boolean(state?.officialCited),
    })),
  };
}

function normalizeRiskItem(row: Record<string, unknown>) {
  return {
    risk_id: String(row.riskId ?? ''),
    risk_type: String(row.riskType ?? ''),
    scenario_label: String(row.scenarioLabel ?? ''),
    severity: String(row.severity ?? 'low'),
    reason: String(row.reason ?? ''),
    impact_summary: String(row.reason ?? ''),
    evidence: typeof row.evidence === 'string' ? row.evidence : undefined,
    recommended_action_ref: typeof row.mitigationHint === 'string' ? row.mitigationHint : undefined,
  };
}

function normalizeActionItem(row: Record<string, unknown>) {
  return {
    action_id: String(row.scenarioId ?? row.scenarioLabel ?? row.action ?? ''),
    priority: typeof row.priority === 'number' ? row.priority : String(row.priority ?? ''),
    scenario_label: String(row.scenarioLabel ?? ''),
    action: String(row.action ?? ''),
    target: String(row.target ?? ''),
    expected_metric: typeof row.expectedImpact === 'string' ? row.expectedImpact : undefined,
    related_competitors: Array.isArray(row.relatedCompetitors) ? row.relatedCompetitors.map(String) : [],
    status: 'not_started' as const,
  };
}

function normalizeSourcesV2(row: Record<string, unknown>) {
  const platformStats = row.platformCitationStats && typeof row.platformCitationStats === 'object'
    ? row.platformCitationStats as Record<string, Record<string, unknown>>
    : {};
  return {
    official_citation_rate: typeof row.officialCitationRate === 'number' ? row.officialCitationRate : null,
    official_domain: typeof row.brandDomain === 'string' ? row.brandDomain : null,
    total_citations: typeof row.totalCitations === 'number' ? row.totalCitations : null,
    unique_domains: typeof row.uniqueDomains === 'number' ? row.uniqueDomains : null,
    top_domains: Array.isArray(row.topDomains)
      ? row.topDomains.map((item) => {
          const domain = item as Record<string, unknown>;
          return {
            source: String(domain.domain ?? ''),
            count: Number(domain.count ?? 0),
            percentage: Number(domain.share ?? 0),
            is_official: Boolean(domain.isOfficial),
          };
        })
      : [],
    platform_citation_stats: Object.entries(platformStats).map(([platform, stats]) => ({
      platform,
      official_citation_rate: Number(stats.officialCitationRate ?? 0),
      top_domains: Array.isArray(stats.topDomains)
        ? stats.topDomains.map((item) => {
            const domain = item as Record<string, unknown>;
            return {
              domain: String(domain.domain ?? ''),
              count: Number(domain.count ?? 0),
            };
          })
        : [],
    })),
  };
}

export function buildDashboardV2Data(payload: {
  overview?: Record<string, unknown>;
  scenarios?: Record<string, unknown>;
  competitorBattles?: Record<string, unknown>;
  sources?: Record<string, unknown>;
  risksActions?: Record<string, unknown>;
}): DashboardV2Data | null {
  const overview = payload.overview;
  const scenarios = payload.scenarios;
  const competitorBattles = payload.competitorBattles;
  const sources = payload.sources;
  const risksActions = payload.risksActions;

  if (!overview && !scenarios && !competitorBattles && !sources && !risksActions) {
    return null;
  }

  const overviewKpi = overview?.kpi && typeof overview.kpi === 'object' ? overview.kpi as Record<string, unknown> : {};
  const overviewSummary = overview?.summary && typeof overview.summary === 'object' ? overview.summary as Record<string, unknown> : {};

  return {
    overview: {
      status_summary: typeof overviewSummary.statusSummary === 'string' ? overviewSummary.statusSummary : undefined,
      kpis: [
        { id: 'brand_mention_rate', label: '品牌提及率', value: toNullableNumber(overviewKpi.brandMentionRate), unit: '%', trend: toNullableNumber(overviewKpi.mentionRateTrend), trendUnit: '%', targetTab: 'scenarios' },
        { id: 'official_citation_rate', label: '官网引用率', value: toNullableNumber(overviewKpi.officialCitationRate), unit: '%', trend: toNullableNumber(overviewKpi.officialCitationRateTrend), trendUnit: '%', targetTab: 'sources' },
        { id: 'scenario_hit_count', label: '有效场景数', value: toNullableNumber(overviewKpi.effectiveScenarioCount), trend: toNullableNumber(overviewKpi.effectiveScenarioTrend), targetTab: 'scenarios' },
        { id: 'missing_high_value_scenario_count', label: '缺席高价值场景数', value: toNullableNumber(overviewKpi.missingHighValueScenarioCount), trend: toNullableNumber(overviewKpi.missingHighValueScenarioTrend), targetTab: 'riskAction' },
        { id: 'high_risk_scenario_count', label: '高风险场景数', value: toNullableNumber(overviewKpi.highRiskScenarioCount), trend: toNullableNumber(overviewKpi.highRiskScenarioTrend), targetTab: 'riskAction' },
      ],
      key_scenarios: Array.isArray(overview?.topScenarios)
        ? overview.topScenarios.map((item) => normalizeScenarioRow(item as Record<string, unknown>))
        : [],
      competitor_pressure: Array.isArray(overview?.competitorPressure)
        ? overview.competitorPressure.map((item) => normalizeCompetitorCard(item as Record<string, unknown>))
        : [],
      recommended_actions: Array.isArray(overview?.actionQueue)
        ? overview.actionQueue.map((item) => normalizeActionItem(item as Record<string, unknown>))
        : [],
    },
    scenarios: Array.isArray(scenarios?.scenarios)
      ? scenarios.scenarios.map((item) => normalizeScenarioRow(item as Record<string, unknown>))
      : [],
    competitorBattle: {
      summary_cards: Array.isArray(competitorBattles?.competitors)
        ? competitorBattles.competitors.map((item) => normalizeCompetitorCard(item as Record<string, unknown>))
        : [],
      scenario_matrix: Array.isArray(competitorBattles?.scenarioMatrix)
        ? competitorBattles.scenarioMatrix.map((item) => normalizeScenarioMatrixRow(item as Record<string, unknown>))
        : [],
    },
    sources: sources?.sourceOverview && typeof sources.sourceOverview === 'object'
      ? normalizeSourcesV2(sources.sourceOverview as Record<string, unknown>)
      : undefined,
    riskAction: {
      risks: Array.isArray(risksActions?.risks)
        ? risksActions.risks.map((item) => normalizeRiskItem(item as Record<string, unknown>))
        : [],
      actions: Array.isArray(risksActions?.actionQueue)
        ? risksActions.actionQueue.map((item) => normalizeActionItem(item as Record<string, unknown>))
        : [],
    },
  };
}
