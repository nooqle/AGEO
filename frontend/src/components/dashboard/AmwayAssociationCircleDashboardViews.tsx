/**
 * Public shell for Amway association-circle dashboard views.
 * Keeps historical import paths stable; implementations live in ./amway-circle.
 */

export {
  buildAssociationMapGroups,
  buildAssociationProjection,
  normalizeCenterTerms,
  sampleAnswerCount,
} from './amway-circle';

export { CommercialOrbitView } from './amway-circle/CommercialOrbitView';
export { AssociationReportPanel } from './amway-circle/AssociationReportPanel';
export { AssociationProjectionLoadingPanel } from './amway-circle/AssociationProjectionLoadingPanel';
export { InfoPill } from './amway-circle/InfoPill';
