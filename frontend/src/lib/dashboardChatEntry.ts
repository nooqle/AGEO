import { buildDashboardChatUrlWithHandoff } from './dashboardChatHandoff';

export function buildBrandMonitoringSetupDraft(brandName: string): string {
  const safeBrandName = brandName.trim() || '新品牌';
  return `我想为「${safeBrandName}」建立品牌监测。请先按现有流程确认品牌信息，再生成监测问题集给我确认。`;
}

export function buildBrandMonitoringChatUrl({
  sessionId,
  entityId,
  brandName,
}: {
  sessionId: string;
  entityId: string;
  brandName: string;
}): string {
  const safeBrandName = brandName.trim() || '新品牌';
  const params = new URLSearchParams();
  params.set('entity_id', entityId);
  params.set('brand', safeBrandName);
  params.set('entry_source', 'dashboard_new_brand');
  params.set('monitor_mode', 'panorama_monitoring');
  params.set('draft', buildBrandMonitoringSetupDraft(safeBrandName));
  params.set('autosend', '1');
  return buildDashboardChatUrlWithHandoff(
    sessionId,
    Object.fromEntries(params.entries()),
  );
}
