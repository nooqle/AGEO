import { writeDashboardChatHandoff } from './dashboardChatHandoff';

export function buildBrandMonitoringSetupDraft(brandName: string): string {
  const safeBrandName = brandName.trim() || '新品牌';
  return `我想为「${safeBrandName}」建立品牌监测。先帮我生成品牌档案。`;
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
  if (writeDashboardChatHandoff(sessionId, Object.fromEntries(params.entries()))) {
    return `/chat/${sessionId}`;
  }
  return `/chat/${sessionId}?${params.toString()}`;
}
