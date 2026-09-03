export type ApiErrorContext =
  | 'default'
  | 'questionSetSave'
  | 'questionSetUpdate'
  | 'runStart'
  | 'runCancel'
  | 'fileUpload'
  | 'questionTableAnalysis'
  | 'schedulerHealth'
  | 'exportOutput';

type ErrorDefinition = {
  code: string;
  message: string;
  retryable: boolean;
};

const STATUS_ERRORS: Record<number, ErrorDefinition> = {
  400: { code: 'INVALID_REQUEST', message: '提交内容有误，请检查后重试。', retryable: false },
  401: { code: 'AUTH_REQUIRED', message: '登录状态已过期，请重新登录后继续。', retryable: false },
  403: { code: 'PERMISSION_DENIED', message: '当前账号没有执行此操作的权限，请联系管理员。', retryable: false },
  404: { code: 'RESOURCE_NOT_FOUND', message: '目标内容已不存在，请刷新页面后重试。', retryable: false },
  409: { code: 'RESOURCE_CONFLICT', message: '内容已发生变化，请刷新后重新操作。', retryable: false },
  413: { code: 'REQUEST_TOO_LARGE', message: '提交内容过大，请减少内容后重试。', retryable: false },
  422: { code: 'VALIDATION_FAILED', message: '提交内容有误，请检查后重试。', retryable: false },
  429: { code: 'RATE_LIMITED', message: '操作过于频繁，请稍后重试。', retryable: true },
  500: { code: 'INTERNAL_ERROR', message: '系统暂时无法完成请求，请稍后重试。', retryable: true },
  502: { code: 'SERVICE_UNAVAILABLE', message: '服务暂时不可用，请稍后重试。', retryable: true },
  503: { code: 'SERVICE_UNAVAILABLE', message: '服务暂时不可用，请稍后重试。', retryable: true },
  504: { code: 'SERVICE_UNAVAILABLE', message: '服务响应超时，请稍后重试。', retryable: true },
};

const CONTEXT_ERRORS: Partial<Record<ApiErrorContext, ErrorDefinition>> = {
  questionSetSave: {
    code: 'QUESTION_SET_SAVE_FAILED',
    message: '题库暂时无法保存，当前填写内容已保留，请稍后重新保存。',
    retryable: true,
  },
  questionSetUpdate: {
    code: 'QUESTION_SET_UPDATE_FAILED',
    message: '题库暂时无法更新，当前修改内容已保留，请稍后重新保存。',
    retryable: true,
  },
  runStart: {
    code: 'RUN_START_FAILED',
    message: '采集任务暂时无法启动，请稍后重试。',
    retryable: true,
  },
  runCancel: {
    code: 'RUN_CANCEL_FAILED',
    message: '采集任务暂时无法停止，请刷新任务状态后重试。',
    retryable: true,
  },
  fileUpload: {
    code: 'FILE_UPLOAD_FAILED',
    message: '文件暂时无法上传，请稍后重试。',
    retryable: true,
  },
  questionTableAnalysis: {
    code: 'QUESTION_TABLE_ANALYSIS_FAILED',
    message: '问题表格暂时无法解析，请检查文件后重试。',
    retryable: true,
  },
  schedulerHealth: {
    code: 'SCHEDULER_STATUS_UNAVAILABLE',
    message: '暂时无法获取调度服务状态，请稍后重试。',
    retryable: true,
  },
  exportOutput: {
    code: 'EXPORT_FAILED',
    message: '文件暂时无法导出，请稍后重试。',
    retryable: true,
  },
};

const NETWORK_ERRORS: Partial<Record<ApiErrorContext, ErrorDefinition>> = {
  questionSetSave: {
    code: 'QUESTION_SET_SAVE_UNKNOWN',
    message: '暂时无法确认题库是否保存成功，请先刷新题库列表确认后再操作。',
    retryable: false,
  },
  questionSetUpdate: {
    code: 'QUESTION_SET_UPDATE_UNKNOWN',
    message: '暂时无法确认题库是否更新成功，请先刷新题库列表确认后再操作。',
    retryable: false,
  },
  runStart: {
    code: 'RUN_START_UNKNOWN',
    message: '暂时无法确认采集任务是否已启动，请刷新任务状态后再操作。',
    retryable: false,
  },
  runCancel: {
    code: 'RUN_CANCEL_UNKNOWN',
    message: '暂时无法确认采集任务是否已停止，请刷新任务状态后再操作。',
    retryable: false,
  },
};

const DEFAULT_ERROR: ErrorDefinition = {
  code: 'OPERATION_FAILED',
  message: '系统暂时无法完成操作，请稍后重试。',
  retryable: true,
};

const DEFAULT_NETWORK_ERROR: ErrorDefinition = {
  code: 'NETWORK_UNAVAILABLE',
  message: '网络连接异常，请检查网络后重试。',
  retryable: true,
};

export class ApiError extends Error {
  readonly code: string;
  readonly status: number | null;
  readonly retryable: boolean;
  readonly requestId: string | null;

  constructor(options: {
    code: string;
    message: string;
    status?: number | null;
    retryable?: boolean;
    requestId?: string | null;
  }) {
    super(options.message);
    this.name = 'ApiError';
    this.code = options.code;
    this.status = options.status ?? null;
    this.retryable = options.retryable ?? false;
    this.requestId = options.requestId ?? null;
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function safeUserMessage(value: unknown): string | null {
  if (typeof value !== 'string') return null;
  const message = value.trim();
  const containsTechnicalDetail = [
    /<\/?[a-z][^>]*>/i,
    /traceback|stack trace|sqlalchemy/i,
    /\b[A-Za-z_$][\w$]*(?:Error|Exception)\b/,
    /name ['"].+['"] is not defined/i,
    /\bFile\s+["']?[^"'\s]+["']?,?\s+line\s+\d+/i,
    /\bat\s+(?:async\s+)?(?:[^\s(]+\s+)?\(?[^)\s]+:\d+:\d+\)?/,
    /\bat\s+(?:async\s+)?[A-Za-z_$][\w$.[\]<>]*\s*\(/,
    /\b(?:GET|POST|PATCH|PUT|DELETE)\s+https?:\/\//i,
    /\b(?:SELECT|INSERT\s+INTO|UPDATE\s+\w+\s+SET|DELETE\s+FROM|ALTER\s+TABLE|CREATE\s+TABLE|DROP\s+TABLE)\b/i,
    /[A-Za-z]:\\/,
    /(?:^|[\s"'(])\/(?:app|usr|var|home|opt|tmp|etc|srv|workspace|root|mnt)\//i,
    /\/(?:[\w.-]+\/)+[\w.-]+\.(?:py|pyc|ts|tsx|js|jsx|sql)(?::\d+(?::\d+)?)?/i,
  ].some((pattern) => pattern.test(message));
  if (
    !message
    || message.length > 240
    || !/[\u3400-\u9fff]/u.test(message)
    || containsTechnicalDetail
  ) {
    return null;
  }
  return message;
}

function statusDefinition(status: number, context: ApiErrorContext): ErrorDefinition {
  if (status >= 500 && CONTEXT_ERRORS[context]) {
    return CONTEXT_ERRORS[context] as ErrorDefinition;
  }
  return STATUS_ERRORS[status] ?? DEFAULT_ERROR;
}

export async function apiErrorFromResponse(
  response: Response,
  context: ApiErrorContext = 'default',
): Promise<ApiError> {
  const fallback = statusDefinition(response.status, context);
  let code = fallback.code;
  let message = fallback.message;
  let retryable = fallback.retryable;

  try {
    const payload: unknown = await response.clone().json();
    if (isRecord(payload)) {
      const error = isRecord(payload.error) ? payload.error : null;
      const structuredCode = error && typeof error.code === 'string' ? error.code.trim() : '';
      const structuredMessage = error
        ? safeUserMessage(error.userMessage ?? error.user_message)
        : null;

      if (structuredCode && structuredMessage) {
        code = structuredCode;
        message = structuredMessage;
        retryable = typeof error?.retryable === 'boolean' ? error.retryable : retryable;
      } else if (response.status >= 400 && response.status < 500) {
        const legacyMessage = safeUserMessage(payload.detail ?? payload.message);
        if (legacyMessage) message = legacyMessage;
      }
    }
  } catch {
    // Proxy HTML and malformed responses intentionally fall back to managed copy.
  }

  return new ApiError({
    code,
    message,
    status: response.status,
    retryable,
    requestId: response.headers.get('x-trace-id') ?? response.headers.get('x-request-id'),
  });
}

export function apiErrorFromNetworkFailure(
  context: ApiErrorContext = 'default',
): ApiError {
  const definition = NETWORK_ERRORS[context] ?? CONTEXT_ERRORS[context] ?? DEFAULT_NETWORK_ERROR;
  return new ApiError({
    ...definition,
    status: null,
  });
}
