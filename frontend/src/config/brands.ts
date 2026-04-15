/**
 * Brand configuration
 * Default example brands shown in the empty state
 */

export interface ExampleBrand {
  name: string;
  emoji: string;
}

export interface FeatureHighlight {
  key: 'brandMention' | 'contentCitation' | 'competitionScene';
  title: string;
  desc: string;
}

// Default example brands - can be fetched from API in production
export const DEFAULT_EXAMPLE_BRANDS: ExampleBrand[] = [
  { name: '观夏', emoji: '🌸' },
  { name: '野兽派', emoji: '🌹' },
  { name: '蕉内', emoji: '👕' },
  { name: '瑞幸咖啡', emoji: '☕' },
];

// Feature highlights shown in empty state
export const FEATURE_HIGHLIGHTS: FeatureHighlight[] = [
  { key: 'brandMention', title: '品牌提及', desc: '看品牌被哪些问题提及' },
  { key: 'contentCitation', title: '内容引用', desc: '看哪些内容真正进入答案' },
  { key: 'competitionScene', title: '竞争场景', desc: '看哪些竞品正在抢占位置' },
];

// Input area placeholders
export const INPUT_PLACEHOLDERS = {
  executing: '当前分析仍在进行中，您可先查看右侧结果面板...',
  confirmation: '输入回复或点击上方按钮确认...',
  default: '输入品牌名称开始分析，如：观夏',
} as const;

// API endpoint to fetch popular brands (optional)
export const POPULAR_BRANDS_API = '/api/v1/brands/popular';

/**
 * Fetch popular brands from API
 * Falls back to default brands if API fails
 */
export async function fetchPopularBrands(): Promise<ExampleBrand[]> {
  try {
    const response = await fetch(POPULAR_BRANDS_API);
    if (!response.ok) {
      throw new Error('Failed to fetch popular brands');
    }
    const data = await response.json();
    return data.brands || DEFAULT_EXAMPLE_BRANDS;
  } catch (error) {
    console.warn('Failed to fetch popular brands, using defaults:', error);
    return DEFAULT_EXAMPLE_BRANDS;
  }
}
