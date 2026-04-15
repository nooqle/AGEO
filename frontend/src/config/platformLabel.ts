import { PLATFORM_NAMES } from '@/config/platforms';

export const PLATFORM_DISPLAY_NAMES: Record<string, string> = {
  ...PLATFORM_NAMES,
};

export function normalizePublicPlatformId(
  platform: string | null | undefined,
): string | undefined {
  const normalized = platform?.trim().toLowerCase();
  if (!normalized) return undefined;
  return normalized === 'hunyuan' ? 'yuanbao' : normalized;
}

export function getPlatformDisplayName(platform: string | null | undefined): string {
  const normalized = normalizePublicPlatformId(platform);
  if (!normalized) return '--';
  return PLATFORM_DISPLAY_NAMES[normalized] || normalized;
}
