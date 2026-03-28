import { PLATFORM_NAMES } from '@/config/platforms';

export const PLATFORM_DISPLAY_NAMES: Record<string, string> = {
  ...PLATFORM_NAMES,
};

export function getPlatformDisplayName(platform: string | null | undefined): string {
  if (!platform) return '--';
  return PLATFORM_DISPLAY_NAMES[platform] || platform;
}
