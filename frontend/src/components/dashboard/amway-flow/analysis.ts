/** Deterministic local analysis fallback for custom analysis nodes. */
import type { OntologyAssociationCircleProjection } from '@/types/ontology';
import type {
  FlowAnalysisDimension,
  FlowAnalysisResult,
  FlowAnalysisCard,
} from './types';

type ProjectionNodeLike = Record<string, unknown>;

function analysisNodeAnswerCount(node: ProjectionNodeLike): number {
  const value = Number(node.answer_count ?? node.mention_answer_count ?? 0);
  return Number.isFinite(value) ? value : 0;
}

export function runFlowAnalysis(
  dimensions: FlowAnalysisDimension[],
  projection: OntologyAssociationCircleProjection,
): FlowAnalysisResult {
  const cards: FlowAnalysisCard[] = [];
  const scope = (projection.sample_scope || {}) as Record<string, unknown>;
  const nodes = (projection.nodes || []) as unknown as ProjectionNodeLike[];

  if (dimensions.includes('platform')) {
    const validPlatforms = Array.isArray(scope.valid_platform_names) ? scope.valid_platform_names.map(String) : [];
    const requested = Array.isArray(scope.requested_platforms) ? scope.requested_platforms.map(String) : [];
    const missing = requested.filter((platform) => !validPlatforms.includes(platform));
    cards.push({
      title: '平台覆盖',
      lines: [
        `有效回答 ${Number(scope.valid_answer_count) || 0} 条，覆盖 ${validPlatforms.length}/${requested.length || validPlatforms.length} 个请求平台`,
        validPlatforms.length ? `产出平台：${validPlatforms.join('、')}` : '暂无有效产出平台',
        missing.length ? `未产出平台：${missing.join('、')}（建议下一轮重点观察）` : '请求平台全部有产出',
      ],
    });
  }

  if (dimensions.includes('entities')) {
    const sorted = [...nodes].sort((a, b) => analysisNodeAnswerCount(b) - analysisNodeAnswerCount(a));
    const top = sorted.slice(0, 10).filter((node) => analysisNodeAnswerCount(node) > 0);
    const byTrack = new Map<string, number>();
    nodes.forEach((node) => {
      const track = String(node.track || 'unknown');
      byTrack.set(track, (byTrack.get(track) || 0) + 1);
    });
    cards.push({
      title: '高频实体 Top 10',
      lines: [
        ...top.map((node, index) => `${index + 1}. ${String(node.term || node.node_id || '未命名')}（${analysisNodeAnswerCount(node)} 条回答）`),
        top.length ? '' : '暂无带回答计数的实体',
        `轨道分布：${Array.from(byTrack.entries()).map(([track, count]) => `${track} ${count}`).join(' / ') || '无'}`,
      ].filter(Boolean),
    });
  }

  if (dimensions.includes('risk')) {
    const riskNodes = nodes.filter((node) => String(node.track || '') === 'risk');
    const regulatory = nodes.filter((node) => {
      const text = `${String(node.term || '')} ${String(node.entity_type || '')}`;
      return text.includes('监管') || text.includes('合规');
    });
    const riskMap = ((projection as unknown as Record<string, unknown>).risk_map || {}) as Record<string, unknown>;
    cards.push({
      title: '风险信号',
      lines: [
        `风险轨节点 ${riskNodes.length} 个${riskNodes.length ? `：${riskNodes.slice(0, 5).map((node) => String(node.term || '')).filter(Boolean).join('、')}${riskNodes.length > 5 ? ' 等' : ''}` : ''}`,
        regulatory.length ? `监管/合规相关 ${regulatory.length} 个：${regulatory.slice(0, 3).map((node) => String(node.term || '')).filter(Boolean).join('、')}` : '未发现监管/合规相关节点',
        Object.keys(riskMap).length ? `风险地图字段：${Object.keys(riskMap).slice(0, 4).join('、')}` : '风险地图暂无数据',
      ],
    });
  }

  return {
    generatedAt: new Date().toISOString(),
    dimensions,
    cards,
  };
}
