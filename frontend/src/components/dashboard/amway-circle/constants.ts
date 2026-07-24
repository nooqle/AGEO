/** Default center terms for Amway association-circle projection. */

export const DEFAULT_CENTER_TERMS = ['安利', '安利中国', '纽崔莱'];

export const DEFAULT_OVERVIEW_HIGHLIGHT_LIMIT = 28;
export const FOCUSED_TRACK_LABEL_LIMIT = 10;

export function platformLabel(platform: string): string {
  const normalized = platform.toLowerCase();
  if (normalized.includes('doubao')) return '豆包';
  if (
    normalized.includes('yuanbao')
    || normalized.includes('hunyuan')
    || normalized.includes('元宝')
  ) {
    return '腾讯元宝';
  }
  if (normalized.includes('kimi') || normalized.includes('moonshot')) return 'Kimi';
  if (normalized.includes('deepseek')) return 'DeepSeek';
  return platform || '未知平台';
}
