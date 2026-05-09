import type { Output } from '@/types/api';
import type { CanvasContentType } from '@/types/canvas';

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function isHistoryKnowledgeExport(
  outputType: CanvasContentType,
  payload: unknown,
): boolean {
  return (
    outputType === 'dataTable'
    && isRecord(payload)
    && String(payload.source_scope || '').trim() === 'knowledge_records'
  );
}

type CanonicalArtifactIdentityArgs = {
  sessionId: string;
  outputType: CanvasContentType;
  artifactId?: string | null;
  outputId?: string | null;
  payload?: unknown;
};

type RealtimeArtifactIdentityArgs = {
  outputType: CanvasContentType;
  artifactId?: string | null;
  outputId?: string | null;
  payload?: unknown;
};

const UUID_PREFIX_PATTERN = /^([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})(?:_|$)/i;
const UUID_SUFFIX_PATTERN = /_[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

function readString(payload: unknown, ...keys: string[]): string | undefined {
  if (!isRecord(payload)) {
    return undefined;
  }
  for (const key of keys) {
    const value = payload[key];
    if (typeof value === 'string' && value.trim()) {
      return value.trim();
    }
  }
  return undefined;
}

function extractSessionIdFromArtifactId(value?: string | null): string | null {
  const match = value?.trim().match(UUID_PREFIX_PATTERN);
  return match?.[1] ?? null;
}

function isConfidenceReport(payload: unknown, rawId?: string | null): boolean {
  const reportKind = readString(payload, 'report_kind', 'reportKind');
  const artifactKind = readString(payload, 'artifact_kind', 'artifactKind');
  const haystack = [reportKind, artifactKind, rawId].filter(Boolean).join(' ').toLowerCase();
  return haystack.includes('confidence_signal') || haystack.includes('confidence_analysis');
}

function isSiteConfidenceReport(payload: unknown, rawId?: string | null): boolean {
  const reportKind = readString(payload, 'report_kind', 'reportKind');
  const artifactKind = readString(payload, 'artifact_kind', 'artifactKind');
  const haystack = [reportKind, artifactKind, rawId].filter(Boolean).join(' ').toLowerCase();
  return haystack.includes('site_confidence_report') || haystack.includes('site_confidence');
}

function resolveReportGroupKey(payload: unknown, rawId?: string | null): string {
  if (isSiteConfidenceReport(payload, rawId)) {
    return 'report_site_confidence';
  }
  if (isConfidenceReport(payload, rawId)) {
    return 'report_confidence';
  }

  const reportKind = readString(payload, 'report_kind', 'reportKind');
  if (reportKind === 'panorama' || reportKind === 'baseline' || reportKind === 'panorama_monitoring') {
    return 'report_panorama';
  }
  if (reportKind === 'scenario' || reportKind === 'persona' || reportKind === 'scenario_monitoring') {
    return 'report_scenario';
  }

  const withoutRunSuffix = (rawId || '').replace(UUID_SUFFIX_PATTERN, '');
  if (/_report_panorama$/i.test(withoutRunSuffix)) {
    return 'report_panorama';
  }
  if (/_report_scenario$/i.test(withoutRunSuffix)) {
    return 'report_scenario';
  }
  return 'report';
}

function resolveContentGroupKey(outputType: CanvasContentType, payload: unknown, rawId?: string | null): string {
  if (outputType === 'report') {
    return resolveReportGroupKey(payload, rawId);
  }
  if (outputType === 'fetchResults') {
    return 'fetchResults';
  }
  if (outputType === 'questionList') {
    return 'questionList';
  }
  if (outputType === 'workflow') {
    return 'workflow';
  }
  if (outputType === 'pipeline') {
    return 'pipeline';
  }
  if (outputType === 'chart') {
    return 'chart';
  }
  if (outputType === 'dataTable') {
    return isHistoryKnowledgeExport(outputType, payload) ? 'knowledge_export_history' : 'dataTable';
  }
  return outputType;
}

export function resolveCanonicalArtifactId({
  sessionId,
  outputType,
  artifactId,
  outputId,
  payload,
}: CanonicalArtifactIdentityArgs): string {
  if (isHistoryKnowledgeExport(outputType, payload)) {
    return `${sessionId}_knowledge_export_history`;
  }

  const rawId =
    (typeof artifactId === 'string' && artifactId.trim())
    || (typeof outputId === 'string' && outputId.trim())
    || null;
  return `${sessionId}_${resolveContentGroupKey(outputType, payload, rawId)}`;
}

export function resolveCanonicalArtifactIdFromOutput(
  output: Pick<Output, 'session_id' | 'artifact_id' | 'id' | 'type' | 'data'>,
  outputType: CanvasContentType,
): string {
  return resolveCanonicalArtifactId({
    sessionId: output.session_id,
    outputType,
    artifactId: output.artifact_id,
    outputId: output.id,
    payload: output.data,
  });
}

export function resolveCanonicalArtifactIdFromRealtime({
  outputType,
  artifactId,
  outputId,
  payload,
}: RealtimeArtifactIdentityArgs): string {
  const rawId =
    (typeof artifactId === 'string' && artifactId.trim())
    || (typeof outputId === 'string' && outputId.trim())
    || null;
  const sessionId = extractSessionIdFromArtifactId(rawId);
  if (!sessionId) {
    return rawId || `${outputType}_artifact`;
  }
  return `${sessionId}_${resolveContentGroupKey(outputType, payload, rawId)}`;
}
