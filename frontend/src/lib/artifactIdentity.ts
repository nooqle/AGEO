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

  return (
    (typeof artifactId === 'string' && artifactId.trim())
    || (typeof outputId === 'string' && outputId.trim())
    || `${sessionId}_${outputType}`
  );
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
