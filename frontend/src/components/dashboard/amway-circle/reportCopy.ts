/**
 * Pure report copy / period helpers for association-circle (knife 5, zero behavior).
 */

import type {
  OntologyAssociationCircleEvidenceFinding,
  OntologyAssociationCircleNode,
  OntologyAssociationCircleProjection,
} from '@/types/ontology';
import { commercialReportCopy } from './evidenceHelpers';
import {
  nodeCountPhrase,
  nodeEvidenceCount,
  scoreNumber,
} from './nodeMetrics';
import type { AssociationMapGroup } from './types';

export function readTrackingProjection(projection: OntologyAssociationCircleProjection) {
  const tracking = projection.tracking_projection;
  return tracking && typeof tracking === 'object' ? tracking as Record<string, unknown> : null;
}

export function readPeriodView(projection: OntologyAssociationCircleProjection) {
  const tracking = readTrackingProjection(projection);
  const periodView = tracking?.period_view;
  return periodView && typeof periodView === 'object' ? periodView as Record<string, unknown> : null;
}

export function buildPeriodScopeText(periodView: Record<string, unknown> | null | undefined) {
  return buildPeriodSummaryText(periodView?.current_period);
}

export function buildPreviousPeriodScopeText(periodView: Record<string, unknown> | null | undefined) {
  return buildPeriodSummaryText(periodView?.previous_period);
}

export function buildPeriodSummaryText(value: unknown) {
  if (!value || typeof value !== 'object') return '';
  const period = value as Record<string, unknown>;
  const runCount = Number(period.run_count || 0);
  const start = formatPeriodDate(period.start_at);
  const end = formatPeriodDate(period.end_at);
  const range = start && end ? `${start} 至 ${end}` : '当前可用周期';
  return `${range} / ${runCount || 0} 轮采集`;
}

export function formatPeriodDate(value: unknown) {
  const text = String(value || '').trim();
  if (!text) return '';
  const date = new Date(text);
  if (Number.isNaN(date.getTime())) return text.slice(0, 10);
  const parts = new Intl.DateTimeFormat('en-CA', {
    timeZone: 'Asia/Shanghai',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).formatToParts(date);
  const values = Object.fromEntries(parts.map((part) => [part.type, part.value]));
  return `${values.year}-${values.month}-${values.day}`;
}

export function periodChangeRows(periodView: Record<string, unknown> | null | undefined) {
  const rows = periodView?.change_top5;
  return Array.isArray(rows)
    ? rows.filter((item): item is Record<string, unknown> => Boolean(item && typeof item === 'object'))
    : [];
}

export function periodChangeLabel(value: string) {
  return {
    new: '新增',
    dropped: '消失',
    track_moved: '轨道变化',
    strengthened: '增强',
    weakened: '减弱',
  }[value] || '变化';
}

export function signedNumber(value: unknown) {
  const num = Number(value || 0);
  if (!Number.isFinite(num) || num === 0) return '0';
  return num > 0 ? `+${Math.round(num)}` : String(Math.round(num));
}

export function reportEvidenceLine(value: string) {
  const text = String(value || '').trim();
  return /^(AI 原文|平台原文|平台原文样本)/.test(text);
}

export function parseReportEvidenceLine(value: string) {
  const text = String(value || '').trim();
  const cleaned = text
    .replace(/^平台原文样本：/, '')
    .replace(/^平台原文：/, '')
    .replace(/^AI 原文：/, '');
  const platformMatch = cleaned.match(/^([^｜；:：]+)[｜；:：]/);
  const platform = platformMatch?.[1]?.trim() || '平台';
  const body = platformMatch ? cleaned.slice(platformMatch[0].length).trim() : cleaned;
  return { platform, body };
}

export function reportPlatformAccent(platform: string) {
  const value = platform.toLowerCase();
  if (value.includes('豆包')) return '#1f7a6b';
  if (value.includes('元宝')) return '#4f7f72';
  if (value.includes('kimi')) return '#b9822d';
  if (value.includes('deepseek')) return '#586f9a';
  return '#1f7a6b';
}

export function escapeRegexValue(value: string) {
  return value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

export function buildReportEntityTerms(
  groups: AssociationMapGroup[] | undefined,
  centerTerm?: string,
): string[] {
  const terms = new Set<string>();
  groups?.forEach((group) => {
    group.nodes.forEach((node) => {
      const term = String(node.term || '').trim();
      if (term.length >= 2) terms.add(term);
    });
  });
  ['豆包', '元宝', 'Kimi', 'DeepSeek', '安利', '安利中国', '纽崔莱'].forEach((term) => terms.add(term));
  if (centerTerm) {
    const trimmed = String(centerTerm).trim();
    if (trimmed.length >= 2) terms.add(trimmed);
  }
  return Array.from(terms).sort((a, b) => b.length - a.length);
}

export function evidenceFindingCopy(
  value: string | null | undefined,
  finding: OntologyAssociationCircleEvidenceFinding,
  nodes: OntologyAssociationCircleNode[],
) {
  const copy = commercialReportCopy(value);
  const nodeTerm = commercialReportCopy(finding.node_term);
  const node = nodes.find((item) => (
    (finding.node_id && item.node_id === finding.node_id)
    || commercialReportCopy(item.term) === nodeTerm
  ));
  if (!node) return copy;
  const count = nodeEvidenceCount(node);
  if (!count) return copy;
  const countPhrase = nodeCountPhrase(node, count);
  const escapedTerm = escapeRegexValue(nodeTerm);
  let normalized = copy
    .replace(
      new RegExp(`${escapedTerm}已经被\\s*\\d+\\s*条回答稳定带回品牌`, 'g'),
      `${nodeTerm}已通过 ${countPhrase}进入稳定资产区`,
    )
    .replace(
      new RegExp(`${escapedTerm}已有\\s*\\d+\\s*条回答证据`, 'g'),
      `${nodeTerm}已有 ${countPhrase}`,
    )
    .replace(/\d+\s*条回答提及/g, countPhrase)
    .replace(/\d+\s*条回答提到/g, countPhrase)
    .replace(/本周期证据\s*\d+\s*条/g, `本周期按 ${countPhrase}计量`);
  if (nodeTerm === '监管合规质疑') {
    normalized = regulatoryScopedReportCopy(normalized, nodes, true);
  }
  return normalized;
}

export function uniqueEvidenceFindingFacts(
  finding: OntologyAssociationCircleEvidenceFinding,
  nodes: OntologyAssociationCircleNode[],
  limit: number,
) {
  const canonicalize = (value: string) => value.replace(/[\s，。；、：:,.!?！？（）()]/g, '');
  const claim = evidenceFindingCopy(finding.claim, finding, nodes);
  const claimKey = canonicalize(claim);
  const seen = new Set<string>();
  const facts: string[] = [];
  for (const rawFact of finding.supporting_facts || []) {
    const fact = evidenceFindingCopy(rawFact, finding, nodes);
    const key = canonicalize(fact);
    if (!key || seen.has(key) || claimKey.includes(key)) continue;
    seen.add(key);
    facts.push(fact);
    if (facts.length >= limit) break;
  }
  return facts;
}

export function regulatoryScopedReportCopy(
  value: string | null | undefined,
  nodes: OntologyAssociationCircleNode[],
  forceRegulatoryScope = false,
) {
  const copy = commercialReportCopy(value);
  if (!copy.includes('监管合规质疑') && !forceRegulatoryScope) return copy;
  const node = nodes.find((item) => item.entity_id === 'evidence_regulation');
  const count = node ? nodeEvidenceCount(node) : 0;
  if (!count) return copy;
  const countPhrase = node ? nodeCountPhrase(node, count) : `${count} 次节点提及`;
  const platformCount = node ? scoreNumber(node.platform_count) : 0;
  let normalized = copy
    .replace(
      /监管合规质疑被\s*\d+\s*条回答提到/g,
      `监管合规质疑以质疑或风险语境出现 ${countPhrase}`,
    )
    .replace(
      /监管合规质疑在\s*\d+\s*条回答中以质疑或风险语境出现/g,
      `监管合规质疑以质疑或风险语境出现 ${countPhrase}`,
    )
    .replace(
      /监管合规质疑（\s*\d+\s*(?:条回答|次节点提及|条可确认回答)\s*）/g,
      `监管合规质疑（${countPhrase}）`,
    );
  if (forceRegulatoryScope) {
    normalized = normalized
      .replace(/^\s*\d+\s*条回答提及/g, countPhrase)
      .replace(/^\s*\d+\s*次节点提及/g, countPhrase)
      .replace(/^\s*本周期证据\s*\d+\s*条/g, `本周期按 ${countPhrase}计量`)
      .replace(
        /覆盖\s*\d+\s*个平台/g,
        platformCount ? `覆盖 ${platformCount} 个平台` : '平台覆盖待复核',
      );
  }
  return normalized;
}
