import type { Session, Message, Output, AgentControlResponse, ConfirmationResponse } from '@/types/api';
import type { DashboardData } from '@/types/dashboard';
import { buildDashboardV2Data } from '@/adapters/dashboardV2';
import { buildDashboardHomeData, enrichDashboardHomeWithMonitoringTrends } from '@/adapters/dashboardHome';
import { normalizeEntity } from '@/types/entity';
import type { CreateEntityInput, UpdateEntityInput } from '@/types/entity';
import type { TouchpointTree } from '@/types/touchpoint';
import type { Attachment } from '@/components/chat/Message/AttachmentCard';
import type { SessionListResponse } from '@/types/session';
import type { SnapshotSummary, SnapshotTrendPoint, SnapshotCompare } from '@/types/snapshot';
import type { AnalysisTask, TaskRunRecord } from '@/types/task';
import type { LLMObservabilitySnapshot } from '@/types/observability';
import type {
  AuthUser,
  InvitationRedeemInput,
  OtpLoginInput,
  RegistrationApplication,
  RegistrationApplicationCreateInput,
  TokenResponse,
  VerificationSendCodeInput,
  VerificationSendCodeResponse,
} from '@/types/auth';
import type {
  AdminUserRecord,
  AdminUserUpdateInput,
  OrganizationRecord,
  OrganizationUpdateInput,
} from '@/types/accountAdmin';
import type {
  ControlPlaneCustomerDetail,
  ControlPlaneCustomerSummary,
  ControlPlaneObservabilitySnapshot,
  ControlPlaneTaskSummary,
} from '@/types/controlPlane';
import type {
  SkillDefinition,
  SkillVersion,
  UpdateSkillInput,
} from '@/types/skill';
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
import type {
  AioCanvasConfig,
  AioResumeGateResult,
  AioTakeoverMode,
  AioTakeoverRecord,
  AioVncUrl,
} from '@/types/aio';
import { getStoredAccessToken } from '@/lib/auth-storage';

export const API_URL =
  process.env.NEXT_PUBLIC_API_URL || 'http://127.0.0.1:8001/api/v1';

export function getApiBaseUrl(): string {
  return API_URL;
}

type RequestOptions = Pick<RequestInit, 'signal'>;

class ApiService {
  private normalizeAioMode(value: unknown): AioTakeoverMode {
    if (value === 'vnc' || value === 'vnc_fallback') {
      return 'vnc_fallback';
    }
    if (value === 'canvas_cdp') {
      return 'canvas_cdp';
    }
    return 'vnc_fallback';
  }

  private getAuthToken() {
    const token = getStoredAccessToken();
    if (token) return token;
    if (process.env.NODE_ENV === 'development') return 'dev-token';
    return null;
  }

  private buildHeaders(options: RequestInit = {}): HeadersInit {
    const token = this.getAuthToken();
    const authHeader = token ? { Authorization: `Bearer ${token}` } : {};
    return {
      'Content-Type': 'application/json',
      ...authHeader,
      ...(typeof options.headers === 'object' ? options.headers : {}),
    } as HeadersInit;
  }

  private async request<T>(
    endpoint: string,
    options: RequestInit = {}
  ): Promise<T> {
    const url = `${API_URL}${endpoint}`;
    const response = await fetch(url, {
      ...options,
      headers: this.buildHeaders(options),
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

  private async requestByPath<T>(
    path: string,
    options: RequestInit = {},
  ): Promise<T> {
    const response = await fetch(path, {
      ...options,
      headers: this.buildHeaders(options),
    });

    if (!response.ok) {
      const error = await response.json().catch(() => ({}));
      throw new Error(error.detail || `Request failed: ${response.status}`);
    }

    if (response.status === 204) {
      return undefined as T;
    }

    return response.json();
  }

  // Auth
  async sendVerificationCode(payload: VerificationSendCodeInput) {
    return this.request<VerificationSendCodeResponse>('/auth/verification/send-code', {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  }

  async createRegistrationApplication(payload: RegistrationApplicationCreateInput) {
    return this.request<RegistrationApplication>('/auth/registration-applications', {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  }

  async redeemInviteCode(payload: InvitationRedeemInput) {
    return this.request<TokenResponse>('/auth/invite/redeem', {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  }

  async listRegistrationApplications() {
    return this.request<RegistrationApplication[]>('/auth/registration-applications');
  }

  async approveRegistrationApplication(applicationId: string, organizationId?: string | null) {
    return this.request<RegistrationApplication>(`/auth/registration-applications/${applicationId}/approve`, {
      method: 'POST',
      body: JSON.stringify({ organization_id: organizationId ?? null }),
    });
  }

  async issueInviteCode(applicationId: string, organizationId?: string | null) {
    return this.request<RegistrationApplication>(`/auth/registration-applications/${applicationId}/issue-invite`, {
      method: 'POST',
      body: JSON.stringify({ organization_id: organizationId ?? null }),
    });
  }

  async rejectRegistrationApplication(applicationId: string, reviewNote?: string) {
    return this.request<RegistrationApplication>(`/auth/registration-applications/${applicationId}/reject`, {
      method: 'POST',
      body: JSON.stringify({ review_note: reviewNote ?? null }),
    });
  }

  async loginWithOtp(payload: OtpLoginInput) {
    return this.request<TokenResponse>('/auth/login/otp', {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  }

  async getMe() {
    return this.request<AuthUser>('/auth/me');
  }

  async getAdminUsers() {
    return this.request<AdminUserRecord[]>('/account-admin/users');
  }

  async updateAdminUser(userId: string, payload: AdminUserUpdateInput) {
    return this.request<AdminUserRecord>(`/account-admin/users/${userId}`, {
      method: 'PATCH',
      body: JSON.stringify(payload),
    });
  }

  async getOrganizations() {
    return this.request<OrganizationRecord[]>('/account-admin/organizations');
  }

  async updateOrganization(organizationId: string, payload: OrganizationUpdateInput) {
    return this.request<OrganizationRecord>(`/account-admin/organizations/${organizationId}`, {
      method: 'PATCH',
      body: JSON.stringify(payload),
    });
  }

  async getControlPlaneCustomers(days: number = 7) {
    return this.request<ControlPlaneCustomerSummary[]>(`/control-plane/customers?days=${days}`);
  }

  async getControlPlaneTasks(options?: {
    days?: number;
    status?: string;
    organizationId?: string;
    limit?: number;
  }) {
    const query = new URLSearchParams();
    if (options?.days) query.set('days', String(options.days));
    if (options?.status) query.set('status', options.status);
    if (options?.organizationId) query.set('organization_id', options.organizationId);
    if (options?.limit) query.set('limit', String(options.limit));
    const qs = query.toString();
    return this.request<ControlPlaneTaskSummary[]>(`/control-plane/tasks${qs ? `?${qs}` : ''}`);
  }

  async getControlPlaneCustomerDetail(organizationId: string, options?: { days?: number; recentTaskLimit?: number }) {
    const query = new URLSearchParams();
    if (options?.days) query.set('days', String(options.days));
    if (options?.recentTaskLimit) query.set('recent_task_limit', String(options.recentTaskLimit));
    const qs = query.toString();
    return this.request<ControlPlaneCustomerDetail>(
      `/control-plane/customers/${organizationId}${qs ? `?${qs}` : ''}`
    );
  }

  async getControlPlaneObservability(options?: {
    days?: number;
    organizationId?: string;
    limit?: number;
  }) {
    const query = new URLSearchParams();
    if (options?.days) query.set('days', String(options.days));
    if (options?.organizationId) query.set('organization_id', options.organizationId);
    if (options?.limit) query.set('limit', String(options.limit));
    const qs = query.toString();
    return this.request<ControlPlaneObservabilitySnapshot>(
      `/control-plane/observability${qs ? `?${qs}` : ''}`
    );
  }

  async getAioTakeover(takeoverId: string) {
    const response = await this.request<{ takeover: Record<string, unknown> }>(`/aio/takeovers/${takeoverId}`);
    return this.normalizeAioTakeover(response.takeover);
  }

  async getAioTakeoverCanvasConfig(path: string) {
    const response = await this.requestByPath<Record<string, unknown>>(path);
    return this.normalizeAioCanvasConfig(response);
  }

  async getAioTakeoverVncUrl(path: string) {
    const response = await this.requestByPath<Record<string, unknown>>(path);
    return this.normalizeAioVncUrl(response);
  }

  async heartbeatAioTakeover(
    path: string,
    payload: { frontendId: string; mode: 'canvas_cdp' | 'vnc_fallback' },
  ) {
    const response = await this.requestByPath<{ takeover: Record<string, unknown> }>(path, {
      method: 'POST',
      body: JSON.stringify({
        frontend_id: payload.frontendId,
        mode: payload.mode,
      }),
    });
    return this.normalizeAioTakeover(response.takeover);
  }

  async openAioTakeover(
    path: string,
    payload: {
      frontendId?: string | null;
      mode: 'canvas_cdp' | 'vnc_fallback';
    },
  ) {
    const response = await this.requestByPath<{ takeover: Record<string, unknown> }>(path, {
      method: 'POST',
      body: JSON.stringify({
        frontend_id: payload.frontendId ?? null,
        mode: payload.mode,
      }),
    });
    return this.normalizeAioTakeover(response.takeover);
  }

  async resolveAioTakeover(
    path: string,
    payload: {
      frontendId: string;
      mode: 'canvas_cdp' | 'vnc_fallback';
      resumeGateResult?: AioResumeGateResult;
      clientObservation?: string;
    },
  ) {
    const response = await this.requestByPath<{ takeover: Record<string, unknown> }>(path, {
      method: 'POST',
      body: JSON.stringify({
        frontend_id: payload.frontendId,
        mode: payload.mode,
        resume_gate_result: payload.resumeGateResult ?? 'pass',
        client_observation: payload.clientObservation ?? 'user_claimed_done',
      }),
    });
    return this.normalizeAioTakeover(response.takeover);
  }

  async cancelAioTakeover(
    path: string,
    payload: {
      frontendId?: string | null;
      reason?: string;
    },
  ) {
    const response = await this.requestByPath<{ takeover: Record<string, unknown> }>(path, {
      method: 'POST',
      body: JSON.stringify({
        frontend_id: payload.frontendId ?? null,
        reason: payload.reason ?? 'user_cancelled',
      }),
    });
    return this.normalizeAioTakeover(response.takeover);
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

  async getOrCreateSessionByEntity(entityId: string) {
    try {
      return await this.getSessionByEntity(entityId);
    } catch {
      try {
        return await this.createSession(entityId);
      } catch {
        // If create lost a race against another request, fetch once more.
        return await this.getSessionByEntity(entityId);
      }
    }
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

  async getAnalyticsOverview(
    brandId?: string,
    dateRange: string = 'month',
    options?: RequestOptions,
  ) {
    const params = new URLSearchParams({ date_range: dateRange });
    if (brandId) params.set('brand_id', brandId);
    return this.request<{ kpi: DashboardData['kpi'] }>(
      `/analytics/overview?${params}`,
      options,
    );
  }

  async getAnalyticsVisibility(
    brandId?: string,
    dateRange: string = 'month',
    options?: RequestOptions,
  ) {
    const params = new URLSearchParams({ date_range: dateRange });
    if (brandId) params.set('brand_id', brandId);
    return this.request<{ visibility: DashboardData['visibility'] }>(
      `/analytics/visibility?${params}`,
      options,
    );
  }

  async getAnalyticsPlatforms(brandId?: string, options?: RequestOptions) {
    const params = new URLSearchParams();
    if (brandId) params.set('brand_id', brandId);
    const query = params.toString();
    return this.request<{ platforms: DashboardData['platforms'] }>(
      `/analytics/platforms${query ? `?${query}` : ''}`,
      options,
    );
  }

  async getAnalyticsSources(brandId?: string, options?: RequestOptions) {
    const params = new URLSearchParams();
    if (brandId) params.set('brand_id', brandId);
    const query = params.toString();
    return this.request<{ sources: DashboardData['sources'] }>(
      `/analytics/sources${query ? `?${query}` : ''}`,
      options,
    );
  }

  async getAnalyticsAeo(brandId?: string, options?: RequestOptions) {
    const params = new URLSearchParams();
    if (brandId) params.set('brand_id', brandId);
    const query = params.toString();
    return this.request<{ aeoMetrics: DashboardData['aeoMetrics'] }>(
      `/analytics/aeo${query ? `?${query}` : ''}`,
      options,
    );
  }

  async getAnalyticsSentiment(brandId?: string, options?: RequestOptions) {
    const params = new URLSearchParams();
    if (brandId) params.set('brand_id', brandId);
    const query = params.toString();
    return this.request<{ sentiment: DashboardData['sentiment'] }>(
      `/analytics/sentiment${query ? `?${query}` : ''}`,
      options,
    );
  }

  async getAnalyticsCompetitors(brandId?: string, options?: RequestOptions) {
    const params = new URLSearchParams();
    if (brandId) params.set('brand_id', brandId);
    const query = params.toString();
    return this.request<{ competitors: DashboardData['competitors'] }>(
      `/analytics/competitors${query ? `?${query}` : ''}`,
      options,
    );
  }

  async getAnalyticsOverviewV2(
    brandId?: string,
    dateRange: string = 'month',
    options?: RequestOptions,
  ) {
    const params = new URLSearchParams({ date_range: dateRange });
    if (brandId) params.set('brand_id', brandId);
    return this.request<Record<string, unknown>>(
      `/analytics/v2/overview?${params}`,
      options,
    );
  }

  async getAnalyticsScenariosV2(brandId?: string, options?: RequestOptions) {
    const params = new URLSearchParams();
    if (brandId) params.set('brand_id', brandId);
    const query = params.toString();
    return this.request<Record<string, unknown>>(
      `/analytics/v2/scenarios${query ? `?${query}` : ''}`,
      options,
    );
  }

  async getAnalyticsCompetitorBattlesV2(
    brandId?: string,
    options?: RequestOptions,
  ) {
    const params = new URLSearchParams();
    if (brandId) params.set('brand_id', brandId);
    const query = params.toString();
    return this.request<Record<string, unknown>>(
      `/analytics/v2/competitor-battles${query ? `?${query}` : ''}`,
      options,
    );
  }

  async getAnalyticsSourcesV2(brandId?: string, options?: RequestOptions) {
    const params = new URLSearchParams();
    if (brandId) params.set('brand_id', brandId);
    const query = params.toString();
    return this.request<Record<string, unknown>>(
      `/analytics/v2/sources${query ? `?${query}` : ''}`,
      options,
    );
  }

  async getAnalyticsDashboardHomeV2(
    brandId?: string,
    options?: RequestOptions,
  ) {
    const params = new URLSearchParams();
    if (brandId) params.set('brand_id', brandId);
    const query = params.toString();
    return this.request<Record<string, unknown>>(
      `/analytics/v2/dashboard-home${query ? `?${query}` : ''}`,
      options,
    );
  }

  async getAnalyticsRisksActionsV2(
    brandId?: string,
    options?: RequestOptions,
  ) {
    const params = new URLSearchParams();
    if (brandId) params.set('brand_id', brandId);
    const query = params.toString();
    return this.request<Record<string, unknown>>(
      `/analytics/v2/risks-actions${query ? `?${query}` : ''}`,
      options,
    );
  }

  async getAnalyticsAll(
    brandId?: string,
    dateRange: string = 'month',
    options?: RequestOptions,
  ): Promise<DashboardData> {
    const [overview, visibility, platforms, sources, aeo, sentiment, competitors, overviewV2, scenariosV2, competitorBattlesV2, sourcesV2, risksActionsV2, homeV2, monitoringTrendSummary, mentionTrend, contentCitationTrend, bwvsTrend] = await Promise.allSettled([
      this.getAnalyticsOverview(brandId, dateRange, options),
      this.getAnalyticsVisibility(brandId, dateRange, options),
      this.getAnalyticsPlatforms(brandId, options),
      this.getAnalyticsSources(brandId, options),
      this.getAnalyticsAeo(brandId, options),
      this.getAnalyticsSentiment(brandId, options),
      this.getAnalyticsCompetitors(brandId, options),
      this.getAnalyticsOverviewV2(brandId, dateRange, options),
      this.getAnalyticsScenariosV2(brandId, options),
      this.getAnalyticsCompetitorBattlesV2(brandId, options),
      this.getAnalyticsSourcesV2(brandId, options),
      this.getAnalyticsRisksActionsV2(brandId, options),
      this.getAnalyticsDashboardHomeV2(brandId, options),
      brandId ? this.getMonitoringTrendSummary(brandId, options) : Promise.resolve(undefined),
      brandId ? this.getMonitoringTrend(brandId, 'mention_rate', 8, options) : Promise.resolve(undefined),
      brandId ? this.getMonitoringTrend(brandId, 'content_citation_rate', 8, options) : Promise.resolve(undefined),
      brandId ? this.getMonitoringTrend(brandId, 'bwvs_index', 8, options) : Promise.resolve(undefined),
    ]);

    const ensure = <T,>(result: PromiseSettledResult<T>, fallback: T): T =>
      result.status === 'fulfilled' ? result.value : fallback;
    const optional = <T,>(result: PromiseSettledResult<T>): T | undefined =>
      result.status === 'fulfilled' ? result.value : undefined;

    const v2 = buildDashboardV2Data({
      overview: optional(overviewV2),
      scenarios: optional(scenariosV2),
      competitorBattles: optional(competitorBattlesV2),
      sources: optional(sourcesV2),
      risksActions: optional(risksActionsV2),
    });
    if (v2) {
      v2.home = enrichDashboardHomeWithMonitoringTrends(
        buildDashboardHomeData(optional(homeV2)),
        optional(monitoringTrendSummary),
        {
          mention_rate: optional(mentionTrend)?.trend,
          content_citation_rate: optional(contentCitationTrend)?.trend,
          bwvs_index: optional(bwvsTrend)?.trend,
        },
      );
    }

    return {
      kpi: ensure(overview, { kpi: { brandVisibility: null, mentionRate: null, shareOfVoice: null, visibilityTrend: null, mentionTrend: null, sovTrend: null } }).kpi,
      visibility: ensure(visibility, { visibility: [] }).visibility,
      platforms: ensure(platforms, { platforms: [] }).platforms,
      sources: ensure(sources, { sources: [] }).sources,
      aeoMetrics: ensure(aeo, { aeoMetrics: [] }).aeoMetrics,
      sentiment: ensure(sentiment, { sentiment: [] }).sentiment,
      optimizations: [],
      competitors: ensure(competitors, { competitors: [] }).competitors,
      v2,
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
      body: JSON.stringify({
        name: data.name,
        aliases: data.aliases,
        domain: data.domain,
        industry: data.industry,
        description: data.description,
        visibility_scope: data.visibilityScope,
      }),
    });
    return normalizeEntity(raw);
  }

  async updateEntity(entityId: string, data: UpdateEntityInput) {
    const raw = await this.request<Record<string, unknown>>(`/entities/${entityId}`, {
      method: 'PUT',
      body: JSON.stringify({
        ...(data.name !== undefined ? { name: data.name } : {}),
        ...(data.aliases !== undefined ? { aliases: data.aliases } : {}),
        ...(data.domain !== undefined ? { domain: data.domain } : {}),
        ...(data.industry !== undefined ? { industry: data.industry } : {}),
        ...(data.description !== undefined ? { description: data.description } : {}),
        ...(data.visibilityScope !== undefined ? { visibility_scope: data.visibilityScope } : {}),
      }),
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
  async getSessionTasks(
    sessionId: string,
    params?: { status?: string; limit?: number; offset?: number }
  ) {
    const query = new URLSearchParams();
    if (params?.status) query.set('status_filter', params.status);
    if (params?.limit) query.set('limit', String(params.limit));
    if (params?.offset) query.set('offset', String(params.offset));
    const qs = query.toString();
    return this.request<{ tasks: AnalysisTask[]; total: number }>(
      `/sessions/${sessionId}/tasks${qs ? `?${qs}` : ''}`
    ).catch(() => ({ tasks: [] as AnalysisTask[], total: 0 }));
  }

  /** Get the active (PENDING/RUNNING) task for a session */
  async getActiveTask(sessionId: string): Promise<AnalysisTask | null> {
    const resp = await this.request<{ task: AnalysisTask | null }>(
      `/sessions/${sessionId}/tasks/active`
    ).catch(() => ({ task: null }));
    return resp.task;
  }

  async getTask(sessionId: string, taskId: string): Promise<AnalysisTask | null> {
    const resp = await this.request<{ task: AnalysisTask | null }>(
      `/sessions/${sessionId}/tasks/${taskId}`
    ).catch(() => ({ task: null }));
    return resp.task;
  }

  async getTaskRuns(
    sessionId: string,
    taskId: string,
    limit: number = 20
  ): Promise<{ task_id: string; runs: TaskRunRecord[]; limit: number }> {
    return this.request<{ task_id: string; runs: TaskRunRecord[]; limit: number }>(
      `/sessions/${sessionId}/tasks/${taskId}/runs?limit=${limit}`
    );
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

  async getTaskObservability(params?: {
    entityId?: string;
    days?: number;
    limit?: number;
  }): Promise<LLMObservabilitySnapshot> {
    const query = new URLSearchParams();
    if (params?.entityId) query.set('entity_id', params.entityId);
    if (params?.days) query.set('days', String(params.days));
    if (params?.limit) query.set('limit', String(params.limit));
    const qs = query.toString();
    return this.request<LLMObservabilitySnapshot>(`/tasks/observability${qs ? `?${qs}` : ''}`);
  }

  // =========================================================================
  // Skill Registry API
  // =========================================================================

  async getSkills(): Promise<SkillDefinition[]> {
    const response = await this.request<{ skills: SkillDefinition[] }>('/skills');
    return response.skills;
  }

  async updateSkill(skillId: string, data: UpdateSkillInput): Promise<SkillDefinition> {
    return this.request<SkillDefinition>(`/skills/${skillId}`, {
      method: 'PATCH',
      body: JSON.stringify(data),
    });
  }

  async getSkillVersions(skillId: string): Promise<SkillVersion[]> {
    return this.request<SkillVersion[]>(`/skills/${skillId}/versions`);
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
    metric: string = 'mention_rate',
    limit: number = 50,
    options?: RequestOptions,
  ): Promise<{ trend: TrendDataPoint[]; metric: string }> {
    const params = new URLSearchParams({
      brand_id: entityId,
      metric,
      limit: String(limit),
    });
    return this.request<{ trend: TrendDataPoint[]; metric: string }>(
      `/analytics/trend?${params}`,
      options,
    );
  }

  /** Get trend summary for all core metrics of an entity */
  async getMonitoringTrendSummary(
    entityId: string,
    options?: RequestOptions,
  ): Promise<TrendSummaryResponse> {
    const params = new URLSearchParams({ brand_id: entityId });
    return this.request<TrendSummaryResponse>(
      `/analytics/trend/summary?${params}`,
      options,
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

  private normalizeAioTakeover(raw: Record<string, unknown>): AioTakeoverRecord {
    const bundle = (raw.access_bundle ?? {}) as Record<string, unknown>;
    return {
      takeoverId: String(raw.takeover_id || ''),
      sessionId: String(raw.session_id || ''),
      platform: String(raw.platform || ''),
      mode: this.normalizeAioMode(raw.mode),
      reason: String(raw.reason || ''),
      takeoverState: (raw.takeover_state as AioTakeoverRecord['takeoverState']) || 'issued',
      frontendId: typeof raw.frontend_id === 'string' ? raw.frontend_id : null,
      requestedAt: typeof raw.requested_at === 'string' ? raw.requested_at : null,
      issuedAt: typeof raw.issued_at === 'string' ? raw.issued_at : null,
      expiresAt: typeof raw.expires_at === 'string' ? raw.expires_at : null,
      lastHeartbeatAt: typeof raw.last_heartbeat_at === 'string' ? raw.last_heartbeat_at : null,
      resumeGateResult:
        typeof raw.resume_gate_result === 'string' ? raw.resume_gate_result : null,
      targetUrl: typeof raw.target_url === 'string' ? raw.target_url : null,
      accessBundle: {
        openPath: typeof bundle.open_path === 'string' ? bundle.open_path : null,
        canvasConfigPath: String(bundle.canvas_config_path || ''),
        vncUrlPath: String(bundle.vnc_url_path || ''),
        heartbeatPath: String(bundle.heartbeat_path || ''),
        resolvePath: String(bundle.resolve_path || ''),
        cancelPath: String(bundle.cancel_path || ''),
        targetUrl: typeof bundle.target_url === 'string' ? bundle.target_url : null,
      },
    };
  }

  private normalizeAioCanvasConfig(raw: Record<string, unknown>): AioCanvasConfig {
    return {
      mode: this.normalizeAioMode(raw.mode),
      takeoverId: String(raw.takeover_id || ''),
      cdpEndpoint: String(raw.cdp_endpoint || ''),
      expiresAt: typeof raw.expires_at === 'string' ? raw.expires_at : null,
      heartbeatIntervalMs:
        typeof raw.heartbeat_interval_ms === 'number' ? raw.heartbeat_interval_ms : 10000,
      targetUrl: typeof raw.target_url === 'string' ? raw.target_url : null,
    };
  }

  private normalizeAioVncUrl(raw: Record<string, unknown>): AioVncUrl {
    return {
      mode: this.normalizeAioMode(raw.mode),
      takeoverId: String(raw.takeover_id || ''),
      url: String(raw.url || ''),
      expiresAt: typeof raw.expires_at === 'string' ? raw.expires_at : null,
      upstreamVncAvailable:
        typeof raw.upstream_vnc_available === 'boolean'
          ? raw.upstream_vnc_available
          : false,
    };
  }
}

export const api = new ApiService();
