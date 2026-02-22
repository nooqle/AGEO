/**
 * Brand configuration
 * Default example brands shown in the empty state
 */

export interface ExampleBrand {
  name: string;
  emoji: string;
}

// Default example brands - can be fetched from API in production
export const DEFAULT_EXAMPLE_BRANDS: ExampleBrand[] = [
  { name: '观夏', emoji: '🌸' },
  { name: '野兽派', emoji: '🌹' },
  { name: '蕉内', emoji: '👕' },
  { name: '瑞幸咖啡', emoji: '☕' },
];

// Feature highlights shown in empty state
export const FEATURE_HIGHLIGHTS = [
  { icon: '📊', title: '声量分析', desc: '多平台数据采集' },
  { icon: '👥', title: '画像洞察', desc: '精准用户分析' },
  { icon: '📈', title: '优化建议', desc: '可落地执行方案' },
];

// Input area placeholders
export const INPUT_PLACEHOLDERS = {
  executing: 'Agent 正在分析品牌数据，您可查看右侧报告面板...',
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
