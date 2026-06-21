import type { Entity } from '@/types/entity';

const AMWAY_ASSOCIATION_ALIASES = new Set([
  '安利',
  '安利中国',
  '纽崔莱',
  'amway',
  'amway china',
  'amwaychina',
  'nutrilite',
]);

const AMWAY_ASSOCIATION_CENTER_OPTIONS = ['安利', '安利中国', '纽崔莱'];

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

  return {
    primary: sortPrimaryDashboardEntities(primary),
    internal,
    duplicates,
  };
}

export function preferredDashboardEntity(entities: Entity[]): Entity | undefined {
  const { primary } = splitDashboardEntities(entities);
  return primary.find(isAmwayAssociationEntity) || primary[0] || entities[0];
}

export function primaryBrandEntities(entities: Entity[]): Entity[] {
  return splitDashboardEntities(entities).primary;
}

export function isAmwayAssociationEntity(entity: Entity): boolean {
  if (entity.dashboardVariant === 'amway_association_circle') return true;
  if (process.env.NEXT_PUBLIC_ENABLE_AMWAY_ENTITY_FALLBACK !== 'true') {
    return false;
  }
  const candidates = [
    entity.name,
    entity.domain,
    ...(entity.aliases || []),
    ...(entity.centerTerms || []),
    ...(entity.associationBrandCluster || []),
  ].map((value) => normalizeIdentityPart(value));
  return candidates.some((value) => {
    const compact = value.replace(/\s+/g, '');
    return (
      AMWAY_ASSOCIATION_ALIASES.has(value) ||
      AMWAY_ASSOCIATION_ALIASES.has(compact) ||
      value.includes('amway') ||
      value.includes('nutrilite')
    );
  });
}

export function associationCenterOptionsForEntity(entity?: Entity | null): string[] {
  if (!entity || !isAmwayAssociationEntity(entity)) return [];
  const sourceTerms = entity.associationBrandCluster?.length
    ? entity.associationBrandCluster
    : entity.centerTerms;
  const terms = (sourceTerms?.length ? sourceTerms : AMWAY_ASSOCIATION_CENTER_OPTIONS)
    .map((value) => String(value || '').trim())
    .filter((value) => AMWAY_ASSOCIATION_CENTER_OPTIONS.includes(value));
  const uniqueTerms: string[] = [];
  terms.forEach((term) => {
    if (!uniqueTerms.includes(term)) uniqueTerms.push(term);
  });
  return uniqueTerms.length ? uniqueTerms.slice(0, 3) : AMWAY_ASSOCIATION_CENTER_OPTIONS;
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
  const leftAssociation = isAmwayAssociationEntity(left) ? 1 : 0;
  const rightAssociation = isAmwayAssociationEntity(right) ? 1 : 0;
  if (leftAssociation !== rightAssociation) {
    return leftAssociation - rightAssociation;
  }
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

function sortPrimaryDashboardEntities(entities: Entity[]): Entity[] {
  return [...entities].sort((left, right) => compareEntityPriority(right, left));
}
