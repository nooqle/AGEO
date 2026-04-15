export const PLATFORM_NAMES: Record<string, string> = {
  kimi: 'Kimi',
  deepseek: 'DeepSeek',
  doubao: '豆包',
  yuanbao: '元宝',
  zhipu: '智谱',
};

export const PLATFORM_COLORS: Record<string, string> = {
  deepseek: '#4F8EF7',
  kimi: '#7C3AED',
  doubao: '#F59E0B',
  yuanbao: '#A855F7',
  zhipu: '#10B981',
};

export function normalizePlatformKey(platform: string | null | undefined): string | undefined {
  const normalized = platform?.trim().toLowerCase();
  if (!normalized) return undefined;
  return normalized === 'hunyuan' ? 'yuanbao' : normalized;
}

export function getPlatformColor(platform: string | null | undefined): string | undefined {
  const normalized = normalizePlatformKey(platform);
  if (!normalized) return undefined;
  return PLATFORM_COLORS[normalized];
}
