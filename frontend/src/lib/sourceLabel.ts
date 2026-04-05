function normalizeDomain(domain: string | null | undefined): string {
  const raw = String(domain || '').trim().toLowerCase();
  if (!raw) return '';

  const withoutProtocol = raw.replace(/^https?:\/\//, '');
  const host = withoutProtocol.split('/')[0]?.split('?')[0]?.split('#')[0] || '';
  return host.replace(/:.*$/, '');
}

const EXACT_RULES = new Map<string, string>([
  ['baijiahao.baidu.com', '百家号（百度）'],
  ['zhidao.baidu.com', '百度知道'],
  ['tieba.baidu.com', '百度贴吧'],
  ['mp.weixin.qq.com', '微信公众号（微信）'],
  ['weixin.qq.com', '微信（腾讯）'],
  ['zhuanlan.zhihu.com', '知乎专栏'],
  ['zhihu.com', '知乎'],
  ['m.toutiao.com', '今日头条'],
  ['toutiao.com', '今日头条'],
  ['dongchedi.com', '懂车帝'],
  ['www.dongchedi.com', '懂车帝'],
  ['www-lf.dongchedi.com', '懂车帝'],
  ['autohome.com.cn', '汽车之家'],
  ['chejiahao.autohome.com.cn', '汽车之家'],
  ['m.autohome.com.cn', '汽车之家'],
  ['yiche.com', '易车'],
  ['www.yiche.com', '易车'],
  ['youjia.baidu.com', '有驾（百度）'],
  ['pcauto.com.cn', '太平洋汽车'],
  ['auto.sina.com.cn', '新浪汽车'],
  ['cnautonews.com', '中国汽车新闻网'],
  ['mp.sohu.com', '搜狐号（搜狐）'],
  ['sohu.com', '搜狐'],
  ['163.com', '网易（163）'],
  ['new.qq.com', '腾讯新闻'],
  ['kuaibao.qq.com', '腾讯快报'],
  ['xiaohongshu.com', '小红书'],
  ['weibo.com', '微博'],
  ['bilibili.com', '哔哩哔哩'],
  ['douyin.com', '抖音'],
  ['smzdm.com', '什么值得买'],
  ['post.smzdm.com', '什么值得买'],
  ['ithome.com', 'IT之家'],
  ['jd.com', '京东'],
  ['tmall.com', '天猫'],
  ['taobao.com', '淘宝'],
  ['pcdetail.taobao.com', '淘宝商品页'],
  ['zol.com.cn', '中关村在线（ZOL）'],
  ['wap.zol.com.cn', '中关村在线（ZOL）'],
  ['m.zol.com.cn', '中关村在线（ZOL）'],
  ['pconline.com.cn', '太平洋科技'],
  ['m.pconline.com.cn', '太平洋科技'],
  ['cet.com.cn', '中国经济新闻网'],
  ['philips.com.cn', '飞利浦'],
  ['zorba-asia.cn', '佐宝热线'],
  ['ifeng.com', '凤凰网'],
  ['sina.com.cn', '新浪'],
  ['people.com.cn', '人民网'],
  ['cctv.com', '央视网'],
  ['jiemian.com', '界面新闻'],
  ['36kr.com', '36氪'],
  ['thepaper.cn', '澎湃新闻'],
]);

const SUFFIX_RULES: Array<{ suffix: string; label: string }> = [
  { suffix: '.zhihu.com', label: '知乎' },
  { suffix: '.toutiao.com', label: '今日头条' },
  { suffix: '.dongchedi.com', label: '懂车帝' },
  { suffix: '.autohome.com.cn', label: '汽车之家' },
  { suffix: '.yiche.com', label: '易车' },
  { suffix: '.pcauto.com.cn', label: '太平洋汽车' },
  { suffix: '.qq.com', label: '腾讯内容（腾讯）' },
  { suffix: '.163.com', label: '网易（163）' },
  { suffix: '.weibo.com', label: '微博' },
  { suffix: '.xiaohongshu.com', label: '小红书' },
  { suffix: '.bilibili.com', label: '哔哩哔哩' },
  { suffix: '.douyin.com', label: '抖音' },
  { suffix: '.sohu.com', label: '搜狐' },
  { suffix: '.smzdm.com', label: '什么值得买' },
  { suffix: '.ithome.com', label: 'IT之家' },
  { suffix: '.taobao.com', label: '淘宝' },
  { suffix: '.jd.com', label: '京东' },
  { suffix: '.tmall.com', label: '天猫' },
  { suffix: '.zol.com.cn', label: '中关村在线（ZOL）' },
  { suffix: '.pconline.com.cn', label: '太平洋科技' },
];

function extractRootDomain(host: string): string {
  const parts = host.split('.').filter(Boolean);
  if (parts.length <= 2) return host;

  const tld2 = `${parts[parts.length - 2]}.${parts[parts.length - 1]}`;
  const knownSecondLevel = new Set(['com.cn', 'net.cn', 'org.cn', 'gov.cn']);
  if (knownSecondLevel.has(tld2) && parts.length >= 3) {
    return `${parts[parts.length - 3]}.${tld2}`;
  }
  return `${parts[parts.length - 2]}.${parts[parts.length - 1]}`;
}

function humanizeRootDomain(rootDomain: string): string {
  const base = rootDomain
    .replace(/\.(com|cn|net|org|gov)(\.cn)?$/i, '')
    .replace(/[-_]+/g, ' ')
    .trim();

  if (!base) return rootDomain;
  if (/^[a-z0-9]+$/i.test(base) && base.length <= 5) {
    return base.toUpperCase();
  }
  return base
    .split(' ')
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(' ');
}

export function getSourceLabel(
  domain: string | null | undefined,
  isOfficial = false
): string | null {
  const normalized = normalizeDomain(domain);
  if (!normalized) return null;
  if (isOfficial) return '官网';

  const exact = EXACT_RULES.get(normalized);
  if (exact) return exact;

  const suffix = SUFFIX_RULES.find((rule) => normalized.endsWith(rule.suffix));
  if (suffix) return suffix.label;

  const rootDomain = extractRootDomain(normalized);
  const rootExact = EXACT_RULES.get(rootDomain);
  if (rootExact) return rootExact;

  return `外部站点（${humanizeRootDomain(rootDomain)}）`;
}
