/**
 * Pure projection helpers for association circle (knife 1).
 */

import type { DashboardHomeData } from '@/types/dashboard';
import type {
  OntologyAssociationCircleProjection,
  OntologyWorldSummary,
} from '@/types/ontology';
import { DEFAULT_CENTER_TERMS } from './constants';

export function normalizeCenterTerms(value?: unknown): string[] {
  if (!Array.isArray(value)) return DEFAULT_CENTER_TERMS;
  const result = value.map((item) => String(item || '').trim()).filter(Boolean);
  return result.length ? Array.from(new Set(result)).slice(0, 3) : DEFAULT_CENTER_TERMS;
}

export function firstSampleNumber(...values: unknown[]): number {
  for (const value of values) {
    const numericValue = toNumber(value);
    if (numericValue > 0) return numericValue;
  }
  return 0;
}

export function toNumber(value: unknown): number {
  return typeof value === 'number' && Number.isFinite(value) ? Math.round(value) : 0;
}

export function sampleAnswerCount(sampleScope: Record<string, unknown>): number {
  return firstSampleNumber(
    sampleScope.answer_count,
    sampleScope.valid_answer_count,
    sampleScope.total_answer_count,
  );
}

export function sampleQuestionCount(sampleScope: Record<string, unknown>): number {
  return firstSampleNumber(sampleScope.question_count, sampleScope.total_question_count);
}

export function samplePlatformCount(sampleScope: Record<string, unknown>): number {
  const platforms = Array.isArray(sampleScope.platforms) ? sampleScope.platforms.length : 0;
  return firstSampleNumber(
    sampleScope.platform_count,
    sampleScope.valid_platform_count,
    platforms,
  );
}

export function readLiveExtractionStats(sampleScope: Record<string, unknown>) {
  return {
    answerCount: sampleAnswerCount(sampleScope),
    signalCount: firstSampleNumber(sampleScope.signal_count),
    eventCount: firstSampleNumber(sampleScope.extraction_event_count),
  };
}

export function buildAssociationProjection(
  world?: OntologyWorldSummary | null,
  home?: DashboardHomeData | null,
): OntologyAssociationCircleProjection {
  if (world?.association_circle_projection) {
    return {
      ...world.association_circle_projection,
      center_terms: normalizeCenterTerms(world.association_circle_projection.center_terms),
      nodes: Array.isArray(world.association_circle_projection.nodes)
        ? world.association_circle_projection.nodes
        : [],
      question_bank: Array.isArray(world.association_circle_projection.question_bank)
        ? world.association_circle_projection.question_bank
        : [],
      evidence_samples: Array.isArray(world.association_circle_projection.evidence_samples)
        ? world.association_circle_projection.evidence_samples
        : [],
      platform_comparison: Array.isArray(world.association_circle_projection.platform_comparison)
        ? world.association_circle_projection.platform_comparison
        : [],
      association_actions: Array.isArray(world.association_circle_projection.association_actions)
        ? world.association_circle_projection.association_actions
        : [],
      report_narrative_sections: Array.isArray(
        world.association_circle_projection.report_narrative_sections,
      )
        ? world.association_circle_projection.report_narrative_sections
        : [],
      evidence_findings: Array.isArray(world.association_circle_projection.evidence_findings)
        ? world.association_circle_projection.evidence_findings
        : [],
      analysis_tool_trace: Array.isArray(world.association_circle_projection.analysis_tool_trace)
        ? world.association_circle_projection.analysis_tool_trace
        : [],
      report_outline: Array.isArray(world.association_circle_projection.report_outline)
        ? world.association_circle_projection.report_outline
        : [],
      strategy_validation: Array.isArray(world.association_circle_projection.strategy_validation)
        ? world.association_circle_projection.strategy_validation
        : [],
      source_appendix: Array.isArray(world.association_circle_projection.source_appendix)
        ? world.association_circle_projection.source_appendix
        : [],
    };
  }
  return {
    dashboard_variant: 'amway_association_circle',
    analysis_mode: 'brand_association_circle',
    report_kind: 'brand_association_circle',
    status: 'not_generated',
    center_terms: normalizeCenterTerms(home?.center_terms),
    nodes: [],
    question_bank: [],
    evidence_samples: [],
    platform_comparison: [],
    association_actions: [],
    report_narrative_sections: [],
    evidence_findings: [],
    analysis_tool_trace: [],
    report_outline: [],
    strategy_validation: [],
    source_appendix: [],
    sample_scope: {},
    executive_summary: {},
  };
}
