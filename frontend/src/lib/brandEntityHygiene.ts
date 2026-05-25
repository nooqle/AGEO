import type { Entity } from '@/types/entity';

const INTERNAL_ENTITY_PATTERNS = [
  /(^|\s)(codex|smoke|e2e|debug|validation|postfix|cleanup)(\s|$)/i,
  /(^|\s)(test|testing)(\s|$)/i,
  /测试|验证|调试/,
  /\?{2,}/,
  /\b\d{8,}\b/,
];

const INTERNAL_DOMAIN_PATTERNS = [
  /(^|\.)example\.com$/i,
  /\.test$/i,
  /(^|[.-])(smoke|e2e|debug|validation|test)([.-]|$)/i,
  /\/e2e-\d+/i,
];

export function isLikelyInternalEntity(entity: Entity): boolean {
  if (entity.isInternalTestData) return true;
  if ((entity.hygieneLabels || []).length > 0) return true;

  const name = entity.name || '';
  const domain = entity.domain || '';
  return (
    INTERNAL_ENTITY_PATTERNS.some((pattern) => pattern.test(name)) ||
    INTERNAL_DOMAIN_PATTERNS.some((pattern) => pattern.test(domain))
  );
}

export function splitDashboardEntities(
  entities: Entity[],
  selectedBrandId?: string | null,
) {
  const primary: Entity[] = [];
  const internal: Entity[] = [];
  const duplicates: Entity[] = [];
  const preferredByIdentity = new Map<string, Entity>();
  const selectedEntity = entities.find((entity) => entity.id === selectedBrandId);
  const selectedIdentityKey =
    selectedEntity && !isLikelyInternalEntity(selectedEntity)
      ? entityIdentityKey(selectedEntity)
      : null;

  entities.forEach((entity) => {
    if (isLikelyInternalEntity(entity)) return;
    const key = entityIdentityKey(entity);
    if (!key) return;
    const current = preferredByIdentity.get(key);
    if (!current || compareEntityPriority(entity, current) > 0) {
      preferredByIdentity.set(key, entity);
    }
  });

  entities.forEach((entity) => {
    const isSelected = Boolean(selectedBrandId && entity.id === selectedBrandId);
    if (isLikelyInternalEntity(entity)) {
      internal.push(entity);
      return;
    }
    const key = entityIdentityKey(entity);
    const preferredId = key ? preferredByIdentity.get(key)?.id : null;
    if (!isSelected && selectedIdentityKey && key === selectedIdentityKey) {
      duplicates.push(entity);
      return;
    }
    if (!isSelected && preferredId && preferredId !== entity.id) {
      duplicates.push(entity);
      return;
    }
    primary.push(entity);
  });

  return { primary, internal, duplicates };
}

export function preferredDashboardEntity(entities: Entity[]): Entity | undefined {
  const { primary } = splitDashboardEntities(entities);
  return primary[0] || entities[0];
}

export function primaryBrandEntities(entities: Entity[]): Entity[] {
  return splitDashboardEntities(entities).primary;
}

export function cleanEntityDisplayText(
  value: string | null | undefined,
  fallback: string,
): string {
  const text = (value || '').trim();
  if (!text || /\?{2,}/.test(text)) return fallback;
  return text;
}

function entityIdentityKey(entity: Entity): string {
  const name = normalizeIdentityPart(entity.name);
  const domain = normalizeDomain(entity.domain);
  return `${name}::${domain}`;
}

function normalizeIdentityPart(value: string | null | undefined): string {
  return String(value || '')
    .trim()
    .toLowerCase()
    .replace(/\s+/g, ' ');
}

function normalizeDomain(value: string | null | undefined): string {
  return normalizeIdentityPart(value)
    .replace(/^https?:\/\//, '')
    .replace(/^www\./, '')
    .replace(/\/$/, '');
}

function compareEntityPriority(left: Entity, right: Entity): number {
  const leftStatus = left.status === 'active' ? 1 : 0;
  const rightStatus = right.status === 'active' ? 1 : 0;
  if (leftStatus !== rightStatus) return leftStatus - rightStatus;
  return (
    parseEntityTime(left.updatedAt || left.createdAt) -
    parseEntityTime(right.updatedAt || right.createdAt)
  );
}

function parseEntityTime(value: string | null | undefined): number {
  const time = Date.parse(String(value || ''));
  return Number.isFinite(time) ? time : 0;
}
