/**
 * Pure orbit map visual helpers (knife 4a, zero behavior).
 */

import type {
  AssociationMapGroupKey,
  AssociationNodeFilterKey,
  CommercialOrbitEntry,
} from './types';

export function orbitToneColor(groupKey: AssociationMapGroupKey) {
  if (groupKey === 'risk') return 'var(--evidence-risk)';
  if (groupKey === 'growth') return 'var(--evidence-opportunity)';
  if (groupKey === 'story') return 'var(--text-tertiary)';
  return 'var(--brand-primary)';
}

export function selectedRelationLineColor(groupKey: AssociationMapGroupKey) {
  return orbitToneColor(groupKey);
}

export function orbitTrackColor(track: AssociationNodeFilterKey) {
  if (track === 'stable') return 'var(--brand-primary)';
  if (track === 'opportunity') return 'var(--evidence-opportunity)';
  return 'var(--text-tertiary)';
}

export function orbitFocusedEntry(entry: CommercialOrbitEntry, focusGroupKey: AssociationMapGroupKey | null) {
  return Boolean(focusGroupKey && entry.groupKey === focusGroupKey);
}

export function orbitNodeFillColor(entry: CommercialOrbitEntry, focusGroupKey: AssociationMapGroupKey | null) {
  if (focusGroupKey && entry.groupKey === focusGroupKey) return orbitToneColor(entry.groupKey);
  return `color-mix(in srgb, var(--text-secondary) 76%, ${orbitToneColor(entry.groupKey)} 24%)`;
}

export function orbitHaloColor(groupKey: AssociationMapGroupKey) {
  if (groupKey === 'risk') return 'rgba(185, 80, 70, 0.14)';
  if (groupKey === 'growth') return 'rgba(186, 122, 38, 0.15)';
  if (groupKey === 'story') return 'rgba(115, 121, 111, 0.13)';
  return 'rgba(31, 122, 107, 0.16)';
}

export function scrollOrbitMapIntoView(target: Element) {
  const map = target.closest('[data-amway-orbit-map="true"]');
  window.setTimeout(() => {
    map?.scrollIntoView({ behavior: 'smooth', block: 'center' });
  }, 0);
}
