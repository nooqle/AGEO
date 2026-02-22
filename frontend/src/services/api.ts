import type { Session, Message, Output, AgentControlResponse, ConfirmationResponse } from '@/types/api';
import type { DashboardData } from '@/types/dashboard';
import { normalizeEntity } from '@/types/entity';
import type { Entity, CreateEntityInput, UpdateEntityInput } from '@/types/entity';
import type { TouchpointTree } from '@/types/touchpoint';
import type { Attachment } from '@/components/chat/Message/AttachmentCard';
import type { SessionListResponse } from '@/types/session';
import type { SnapshotSummary, SnapshotTrendPoint, SnapshotCompare } from '@/types/snapshot';
import type { AnalysisTask } from '@/types/task';
import type {
  MonitoringSchedule,
  MonitoringAlert,
  BaselineData,
  TrendDataPoint,
  TrendSummaryResponse,
  RunHistoryEntry,
  CreateScheduleInput,
  UpdateScheduleInput,
  SchedulerHealth,
} from '@/types/monitoring';

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000/api/v1';

class ApiService {
  private getAuthToken() {
    if (typeof window === 'undefined') return null;
    const token = window.localStorage.getItem('access_token');
    if (token) return token;
    if (process.env.NODE_ENV === 'development') return 'dev-token';
    return null;
  }

  private async request<T>(
    endpoint: string,
    options: RequestInit = {}
  ): Promise<T> {
    const url = `${API_URL}${endpoint}`;
    const token = this.getAuthToken();
    const authHeader = token ? { Authorization: `Bearer ${token}` } : {};
    const response = await fetch(url, {
      ...options,
      headers: {
        'Content-Type': 'application/json',
        ...authHeader,
        ...(typeof options.headers === 'object' ? options.headers : {}),
      } as HeadersInit,
    });

    if (!response.ok) {
      const error = await response.json().catch(() => ({}));
      throw new Error(error.detail || `Request failed: ${response.status}`);
    }

    // Handle 204 No Content (e.g. DELETE responses)
    if (response.status === 204) {
      return undefined as T;
    }

    return response.json();
  }

  // Session management
  async createSession(entityId?: string) {
    const params = entityId ? `?entity_id=${entityId}` : '';
    return this.request<{ id: string; created_at: string; entity_id?: string }>(`/sessions${params}`, {
      method: 'POST',
    });
  }

  async getSession(sessionId: string) {
    return this.request<Session>(`/sessions/${sessionId}`);
  }

  async getSessionByEntity(entityId: string) {
    return this.request<{ id: string; entity_id: string; created_at: string }>(`/sessions/by-entity/${entityId}`);
  }

  async deleteSession(sessionId: string) {
    return this.request<void>(`/sessions/${sessionId}`, {
      method: 'DELETE',
    });
  }

  async listSessions(params?: { limit?: number; offset?: number; status?: string }) {
    const qs = new URLSearchParams();
    if (params?.limit) qs.set('limit', String(params.limit));
    if (params?.offset) qs.set('offset', String(params.offset));
    if (params?.status) qs.set('status', params.status);
    const query = qs.toString();
    return this.request<SessionListResponse>(`/sessions${query ? `?${query}` : ''}`);
  }

  // Message management
  async getMessages(sessionId: string, options?: { limit?: number; before?: string }) {
    const params = new URLSearchParams();
    if (options?.limit) params.set('limit', String(options.limit));
    if (options?.before) params.set('before', options.before);

    const query = params.toString();
    return this.request<Message[]>(`/sessions/${sessionId}/messages${query ? `?${query}` : ''}`);
  }

  async sendMessage(sessionId: string, content: string) {
    return this.request<Message>(`/sessions/${sessionId}/messages`, {
      method: 'POST',
      body: JSON.stringify({ content }),
    });
  }

  async rollbackAfterMessage(sessionId: string, messageId: string) {
    return this.request<{ success: boolean }>(`/sessions/${sessionId}/messages/${messageId}/after`, {
      method: 'DELETE',
    });
  }

  // Output management
  async getOutputs(sessionId: string) {
    return this.request<Output[]>(`/sessions/${sessionId}/outputs`);
  }

  async getOutput(sessionId: string, outputId: string) {
    return this.request<Output>(`/sessions/${sessionId}/outputs/${outputId}`);
  }

  async exportOutput(sessionId: string, outputId: string, format: 'pdf' | 'excel') {
    const token = this.getAuthToken();
    const headers: Record<string, string> = {};
    if (token) {
      headers['Authorization'] = `Bearer ${token}`;
    }
    const response = await fetch(
      `${API_URL}/sessions/${sessionId}/outputs/${outputId}/export?format=${format}`,
      { headers }
    );
    if (!response.ok) throw new Error('Export failed');
    return response.blob();
  }

  // Agent control
  async stopAgent(sessionId: string) {
    return this.request<AgentControlResponse>(`/sessions/${sessionId}/agent/stop`, {
      method: 'POST',
    });
  }

  async resumeAgent(sessionId: string) {
    return this.request<AgentControlResponse>(`/sessions/${sessionId}/agent/resume`, {
      method: 'POST',
    });
  }

  async sendConfirmation(sessionId: string, requestId: string, selection: string | Record<string, unknown>) {
    return this.request<ConfirmationResponse>(`/sessions/${sessionId}/agent/confirm`, {
      method: 'POST',
      body: JSON.stringify({ request_id: requestId, selection }),
    });
  }

  // =========================================================================
  // Analytics API
  // =========================================================================

  async getAnalyticsOverview(brandId?: string, dateRange: string = 'month') {
    const params = new URLSearchParams({ date_range: dateRange });
    if (brandId) params.set('brand_id', brandId);
    return this.request<{ kpi: DashboardData['kpi'] }>(`/analytics/overview?${params}`);
  }

  async getAnalyticsVisibility(brandId?: string, dateRange: string = 'month') {
    const params = new URLSearchParams({ date_range: dateRange });
    if (brandId) params.set('brand_id', brandId);
    return this.request<{ visibility: DashboardData['visibility'] }>(`/analytics/visibility?${params}`);
  }

  async getAnalyticsPlatforms(brandId?: string) {
    const params = new URLSearchParams();
    if (brandId) params.set('brand_id', brandId);
    const query = params.toString();
    return this.request<{ platforms: DashboardData['platforms'] }>(`/analytics/platforms${query ? `?${query}` : ''}`);
  }

  async getAnalyticsSources(brandId?: string) {
    const params = new URLSearchParams();
    if (brandId) params.set('brand_id', brandId);
    const query = params.toString();
    return this.request<{ sources: DashboardData['sources'] }>(`/analytics/sources${query ? `?${query}` : ''}`);
  }

  async getAnalyticsAeo(brandId?: string) {
    const params = new URLSearchParams();
    if (brandId) params.set('brand_id', brandId);
    const query = params.toString();
    return this.request<{ aeoMetrics: DashboardData['aeoMetrics'] }>(`/analytics/aeo${query ? `?${query}` : ''}`);
  }

  async getAnalyticsSentiment(brandId?: string) {
    const params = new URLSearchParams();
    if (brandId) params.set('brand_id', brandId);
    const query = params.toString();
    return this.request<{ sentiment: DashboardData['sentiment'] }>(`/analytics/sentiment${query ? `?${query}` : ''}`);
  }

  async getAnalyticsCompetitors(brandId?: string) {
    const params = new URLSearchParams();
    if (brandId) params.set('brand_id', brandId);
    const query = params.toString();
    return this.request<{ competitors: DashboardData['competitors'] }>(`/analytics/competitors${query ? `?${query}` : ''}`);
  }

  async getAnalyticsAll(brandId?: string, dateRange: string = 'month'): Promise<DashboardData> {
    const [overview, visibility, platforms, sources, aeo, sentiment, competitors] = await Promise.all([
      this.getAnalyticsOverview(brandId, dateRange),
      this.getAnalyticsVisibility(brandId, dateRange),
      this.getAnalyticsPlatforms(brandId),
      this.getAnalyticsSources(brandId),
      this.getAnalyticsAeo(brandId),
      this.getAnalyticsSentiment(brandId),
      this.getAnalyticsCompetitors(brandId),
    ]);

    return {
      kpi: overview.kpi,
      visibility: visibility.visibility,
      platforms: platforms.platforms,
      sources: sources.sources,
      aeoMetrics: aeo.aeoMetrics,
      sentiment: sentiment.sentiment,
      optimizations: [],
      competitors: competitors.competitors,
    };
  }

  // =========================================================================
  // Entity CRUD API
  // =========================================================================

  async listEntities() {
    const raw = await this.request<Record<string, unknown>[]>('/entities/');
    return raw.map(normalizeEntity);
  }

  async getEntity(entityId: string) {
    const raw = await this.request<Record<string, unknown>>(`/entities/${entityId}`);
    return normalizeEntity(raw);
  }

  async createEntity(data: CreateEntityInput) {
    const raw = await this.request<Record<string, unknown>>('/entities/', {
      method: 'POST',
      body: JSON.stringify(data),
    });
    return normalizeEntity(raw);
  }

  async updateEntity(entityId: string, data: UpdateEntityInput) {
    const raw = await this.request<Record<string, unknown>>(`/entities/${entityId}`, {
      method: 'PUT',
      body: JSON.stringify(data),
    });
    return normalizeEntity(raw);
  }

  async deleteEntity(entityId: string) {
    return this.request<void>(`/entities/${entityId}`, {
      method: 'DELETE',
    });
  }

  // =========================================================================
  // Touchpoint API
  // =========================================================================

  async getTouchpointTree(brandId?: string) {
    const params = new URLSearchParams();
    if (brandId) params.set('brand_id', brandId);
    const query = params.toString();
    return this.request<TouchpointTree>(`/touchpoints/tree${query ? `?${query}` : ''}`);
  }

  // =========================================================================
  // File Upload API
  // =========================================================================

  // =========================================================================
  // Snapshot API
  // =========================================================================

  async getSnapshots(entityId: string, page: number = 1, pageSize: number = 20) {
    const params = new URLSearchParams({
      page: String(page),
      page_size: String(pageSize),
    });
    return this.request<{ snapshots: SnapshotSummary[]; total: number; page: number; page_size: number }>(
      `/entities/${entityId}/snapshots?${params}`
    );
  }

  async getLatestSnapshot(entityId: string) {
    return this.request<SnapshotSummary>(`/entities/${entityId}/snapshots/latest`);
  }

  async getSnapshotTrend(entityId: string, limit: number = 10) {
    const params = new URLSearchParams({ limit: String(limit) });
    return this.request<{ trend: SnapshotTrendPoint[] }>(
      `/entities/${entityId}/snapshots/trend?${params}`
    );
  }

  async compareSnapshots(entityId: string, baseId: string, targetId: string) {
    const params = new URLSearchParams({ base: baseId, target: targetId });
    return this.request<SnapshotCompare>(
      `/entities/${entityId}/snapshots/compare?${params}`
    );
  }

  // =========================================================================
  // File Upload API
  // =========================================================================

  // =========================================================================
  // Task API (Cycle 3)
  // =========================================================================

  /** Get tasks for a session */
  async getSessionTasks(sessionId: string) {
    return this.request<{ tasks: AnalysisTask[]; total: number }>(
      `/sessions/${sessionId}/tasks`
    ).catch(() => ({ tasks: [] as AnalysisTask[], total: 0 }));
  }

  /** Get the active (PENDING/RUNNING) task for a session */
  async getActiveTask(sessionId: string): Promise<AnalysisTask | null> {
    const resp = await this.request<{ task: AnalysisTask | null }>(
      `/sessions/${sessionId}/tasks/active`
    ).catch(() => ({ task: null }));
    return resp.task;
  }

  /** Cancel a running task */
  async cancelTask(sessionId: string, taskId: string): Promise<AnalysisTask | null> {
    const resp = await this.request<{ task: AnalysisTask | null }>(
      `/sessions/${sessionId}/tasks/${taskId}/cancel`,
      { method: 'POST' }
    );
    return resp.task;
  }

  /** List all tasks for the current user across all sessions */
  async getUserTasks(params?: { status?: string; limit?: number; offset?: number }): Promise<{
    tasks: AnalysisTask[];
    total: number;
  }> {
    const query = new URLSearchParams();
    if (params?.status) query.set('status_filter', params.status);
    if (params?.limit) query.set('limit', String(params.limit));
    if (params?.offset) query.set('offset', String(params.offset));
    const qs = query.toString();
    return this.request(`/tasks${qs ? `?${qs}` : ''}`);
  }

  // =========================================================================
  // File Upload API
  // =========================================================================

  // =========================================================================
  // Monitoring Schedule API (Cycle 4)
  // =========================================================================

  /** Get the monitoring schedule for an entity (at most one active/paused) */
  async getEntitySchedule(entityId: string): Promise<MonitoringSchedule | null> {
    const resp = await this.request<{ schedules: MonitoringSchedule[]; total: number }>(
      `/monitoring/schedules/entity/${entityId}`
    );
    return resp.schedules?.[0] ?? null;
  }

  /** Create a new monitoring schedule */
  async createSchedule(data: CreateScheduleInput): Promise<MonitoringSchedule> {
    const resp = await this.request<{ schedule: MonitoringSchedule }>('/monitoring/schedules', {
      method: 'POST',
      body: JSON.stringify(data),
    });
    return resp.schedule;
  }

  /** Update an existing monitoring schedule */
  async updateSchedule(scheduleId: string, data: UpdateScheduleInput): Promise<MonitoringSchedule> {
    const resp = await this.request<{ schedule: MonitoringSchedule }>(`/monitoring/schedules/${scheduleId}`, {
      method: 'PATCH',
      body: JSON.stringify(data),
    });
    return resp.schedule;
  }

  /** Pause an active schedule */
  async pauseSchedule(scheduleId: string): Promise<MonitoringSchedule> {
    const resp = await this.request<{ schedule: MonitoringSchedule }>(
      `/monitoring/schedules/${scheduleId}/pause`,
      { method: 'POST' }
    );
    return resp.schedule;
  }

  /** Resume a paused schedule */
  async resumeSchedule(scheduleId: string): Promise<MonitoringSchedule> {
    const resp = await this.request<{ schedule: MonitoringSchedule }>(
      `/monitoring/schedules/${scheduleId}/resume`,
      { method: 'POST' }
    );
    return resp.schedule;
  }

  /** Delete a schedule */
  async deleteSchedule(scheduleId: string): Promise<void> {
    return this.request<void>(`/monitoring/schedules/${scheduleId}`, {
      method: 'DELETE',
    });
  }

  /** List all schedules for the current user */
  async listSchedules(params?: { status?: string; limit?: number; offset?: number }): Promise<{
    schedules: MonitoringSchedule[];
    total: number;
  }> {
    const query = new URLSearchParams();
    if (params?.status) query.set('status', params.status);
    if (params?.limit) query.set('limit', String(params.limit));
    if (params?.offset) query.set('offset', String(params.offset));
    const qs = query.toString();
    return this.request(`/monitoring/schedules${qs ? `?${qs}` : ''}`);
  }

  // =========================================================================
  // Monitoring Alerts API (Cycle 4)
  // =========================================================================

  /** Get monitoring alerts */
  async getMonitoringAlerts(params?: {
    entityId?: string;
    status?: string;
    limit?: number;
    offset?: number;
  }): Promise<{ alerts: MonitoringAlert[]; total: number }> {
    const query = new URLSearchParams();
    if (params?.entityId) query.set('entity_id', params.entityId);
    if (params?.status) query.set('status', params.status);
    if (params?.limit) query.set('limit', String(params.limit));
    if (params?.offset) query.set('offset', String(params.offset));
    const qs = query.toString();
    return this.request(`/monitoring/alerts${qs ? `?${qs}` : ''}`);
  }

  /** Get unread alert count */
  async getAlertUnreadCount(): Promise<{ unread_count: number }> {
    return this.request<{ unread_count: number }>('/monitoring/alerts/unread-count');
  }

  /** Mark a single alert as read */
  async markAlertRead(alertId: string): Promise<void> {
    return this.request<void>(`/monitoring/alerts/${alertId}/read`, {
      method: 'POST',
    });
  }

  /** Mark all alerts as read */
  async markAllAlertsRead(): Promise<void> {
    return this.request<void>('/monitoring/alerts/read-all', {
      method: 'POST',
    });
  }

  /** Dismiss an alert */
  async dismissAlert(alertId: string): Promise<void> {
    return this.request<void>(`/monitoring/alerts/${alertId}/dismiss`, {
      method: 'POST',
    });
  }

  // =========================================================================
  // Monitoring Trend API (Cycle 4) — uses /analytics/trend endpoints
  // =========================================================================

  /** Get trend data points for an entity and metric */
  async getMonitoringTrend(
    entityId: string,
    metric: string = 'bwvs_index',
    limit: number = 50
  ): Promise<{ trend: TrendDataPoint[]; metric: string }> {
    const params = new URLSearchParams({
      brand_id: entityId,
      metric,
      limit: String(limit),
    });
    return this.request<{ trend: TrendDataPoint[]; metric: string }>(
      `/analytics/trend?${params}`
    );
  }

  /** Get trend summary for all core metrics of an entity */
  async getMonitoringTrendSummary(
    entityId: string
  ): Promise<TrendSummaryResponse> {
    const params = new URLSearchParams({ brand_id: entityId });
    return this.request<TrendSummaryResponse>(
      `/analytics/trend/summary?${params}`
    );
  }

  // =========================================================================
  // Monitoring Run History API (Cycle 4)
  // =========================================================================

  /** Get run history for a schedule */
  async getMonitoringRunHistory(
    scheduleId: string,
    limit: number = 20
  ): Promise<{ tasks: RunHistoryEntry[]; schedule_id: string }> {
    const params = new URLSearchParams({ limit: String(limit) });
    return this.request<{ tasks: RunHistoryEntry[]; schedule_id: string }>(
      `/monitoring/schedules/${scheduleId}/history?${params}`
    );
  }

  /** Get baseline data for a monitoring schedule */
  async getScheduleBaseline(
    scheduleId: string
  ): Promise<{ baseline: BaselineData | null; has_baseline: boolean }> {
    return this.request<{ baseline: BaselineData | null; has_baseline: boolean }>(
      `/monitoring/schedules/${scheduleId}/baseline`
    );
  }

  /** Clear baseline data — next run will execute full A1→A5 pipeline */
  async clearScheduleBaseline(scheduleId: string): Promise<void> {
    return this.request<void>(
      `/monitoring/schedules/${scheduleId}/baseline`,
      { method: 'DELETE' }
    );
  }

  // =========================================================================
  // Scheduler Health API (Cycle 4)
  // =========================================================================

  /** Get scheduler health status.
   *  NOTE: /health/scheduler is mounted on the app root, not under /api/v1.
   *  We derive the base URL from API_URL by stripping the /api/v1 suffix.
   */
  async getSchedulerHealth(): Promise<SchedulerHealth> {
    const baseUrl = API_URL.replace(/\/api\/v1\/?$/, '');
    const token = this.getAuthToken();
    const authHeader = token ? { Authorization: `Bearer ${token}` } : {};
    const response = await fetch(`${baseUrl}/health/scheduler`, {
      headers: {
        'Content-Type': 'application/json',
        ...authHeader,
      } as HeadersInit,
    });
    if (!response.ok) {
      throw new Error(`Scheduler health check failed: ${response.status}`);
    }
    return response.json();
  }

  // =========================================================================
  // File Upload API
  // =========================================================================

  async uploadFile(file: File): Promise<Attachment> {
    const formData = new FormData();
    formData.append('file', file);

    const url = `${API_URL}/files/upload`;
    const token = this.getAuthToken();
    const headers: Record<string, string> = {};
    if (token) {
      headers['Authorization'] = `Bearer ${token}`;
    }

    const response = await fetch(url, {
      method: 'POST',
      headers,
      body: formData,
    });

    if (!response.ok) {
      const error = await response.json().catch(() => ({}));
      throw new Error(error.detail || `Upload failed: ${response.status}`);
    }

    return response.json();
  }
}

export const api = new ApiService();
