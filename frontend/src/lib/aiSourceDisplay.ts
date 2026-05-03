function normalizeFetchMethod(value?: string | null): 'api' | 'browser' | '' {
  const normalized = value?.trim().toLowerCase() || '';
  if (['api', 'app_api', 'llm_api', 'messages_api'].includes(normalized)) return 'api';
  if (['browser', 'web', 'webpage', 'web_page', '网页版'].includes(normalized)) return 'browser';
  return '';
}

export function normalizeAiSourceDisplayName(
  value?: string | null,
  fetchMethod?: string | null,
): string {
  const raw = value?.trim() || '';
  if (!raw) return '';

  const parts = raw
    .split(/[、,，/|]/)
    .map((item) => item.trim())
    .filter(Boolean);
  if (parts.length > 1) {
    return uniqueAiSourceDisplayNames(parts).join('、');
  }

  const normalized = raw.toLowerCase();
  const method = normalizeFetchMethod(fetchMethod);
  const hasApi = method === 'api' || normalized.includes('api');
  const hasBrowser =
    method === 'browser' ||
    normalized.includes('web') ||
    normalized.includes('browser') ||
    raw.includes('网页');

  if (raw.includes('豆包') || normalized.includes('doubao')) {
    if (hasApi) return '豆包API';
    if (hasBrowser) return '豆包网页版';
    return '豆包';
  }
  if (raw.includes('元宝') || normalized.includes('yuanbao')) {
    if (hasApi) return '元宝API';
    if (hasBrowser) return '元宝网页版';
    return '元宝';
  }
  if (raw.includes('Kimi') || normalized.includes('kimi')) {
    if (hasApi) return 'Kimi API';
    if (hasBrowser) return 'Kimi 网页版';
    return 'Kimi';
  }
  if (raw.includes('DeepSeek') || normalized.includes('deepseek')) {
    if (hasApi) return 'DeepSeek API';
    return 'DeepSeek网页版';
  }

  return raw;
}

export function uniqueAiSourceDisplayNames(values: Array<string | null | undefined>): string[] {
  const labels = new Set<string>();
  values.forEach((value) => {
    const label = normalizeAiSourceDisplayName(value);
    if (label) labels.add(label);
  });
  return Array.from(labels);
}
