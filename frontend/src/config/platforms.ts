export const PLATFORM_NAMES: Record<string, string> = {
  kimi: 'Kimi',
  deepseek: 'DeepSeek',
  doubao: '豆包',
  yuanbao: '元宝',
  zhipu: '智谱',
};

export const PLATFORM_COLORS: Record<string, string> = {
  deepseek: '#4F6F88',
  kimi: '#1F7A6B',
  doubao: '#B7792B',
  yuanbao: '#7B6A4C',
  zhipu: '#3F8F62',
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
