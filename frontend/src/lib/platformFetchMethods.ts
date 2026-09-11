export const COLLECTION_PLATFORMS = [
  { id: 'deepseek', label: 'DeepSeek' },
  { id: 'doubao', label: '豆包' },
  { id: 'kimi', label: 'Kimi' },
  { id: 'yuanbao', label: '元宝' },
] as const;

export type CollectionPlatform = typeof COLLECTION_PLATFORMS[number]['id'];
export type PlatformFetchMethod = 'api' | 'browser';
export type PlatformFetchMethods = Record<CollectionPlatform, PlatformFetchMethod>;

export function defaultPlatformFetchMethods(): PlatformFetchMethods {
  return { deepseek: 'browser', doubao: 'browser', kimi: 'browser', yuanbao: 'browser' };
}

export function platformFetchMethodsFromScope(scope: Record<string, unknown> | null | undefined): Partial<PlatformFetchMethods> {
  const raw = scope?.platform_fetch_methods;
  if (raw && typeof raw === 'object' && !Array.isArray(raw)) {
    const methods: Partial<PlatformFetchMethods> = {};
    for (const { id } of COLLECTION_PLATFORMS) {
      const method = (raw as Record<string, unknown>)[id];
      if (method === 'api' || method === 'browser') methods[id] = method;
    }
    return methods;
  }
  if (scope?.fetch_mode === 'fast') return { deepseek: 'browser', doubao: 'api', kimi: 'api', yuanbao: 'api' };
  return scope?.fetch_mode === 'full' ? defaultPlatformFetchMethods() : {};
}

/** Only interpret persisted scope here; never substitute the current editor draft. */
export function describePlatformFetchMethods(
  scope: Record<string, unknown> | null | undefined,
  platforms: readonly string[],
): string {
  if (!scope) return '采集方式未记录';
  const raw = scope.platform_fetch_methods;
  const explicit = raw && typeof raw === 'object' && !Array.isArray(raw)
    ? raw as Record<string, unknown> : null;
  const legacy = !explicit && (scope.fetch_mode === 'fast' || scope.fetch_mode === 'full');
  if (!explicit && !legacy) return '采集方式未记录';
  const methods = platformFetchMethodsFromScope(scope);
  const publicPlatforms = platforms.map((id) => id === 'hunyuan' ? 'yuanbao' : id);
  const enabled = COLLECTION_PLATFORMS.filter(({ id }) => publicPlatforms.includes(id));
  const browserCount = enabled.filter(({ id }) => methods[id] === 'browser').length;
  const apiCount = enabled.filter(({ id }) => methods[id] === 'api').length;
  const detail = enabled.map(({ id, label }) => `${label} ${methods[id] === 'browser' ? '浏览器' : methods[id] === 'api' ? 'API' : '未记录'}`).join('、');
  const legacyHint = legacy ? (scope.fetch_mode === 'fast'
    ? '；旧版 fast 配置，元宝实际方式需查采集记录'
    : '；旧版 full 配置') : '';
  return `浏览器 ${browserCount} / API ${apiCount}${detail ? ` · ${detail}` : ''}${legacyHint}`;
}
