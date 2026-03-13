import { getPlatformDisplayName } from '@/lib/platformLabel';
import { getSourceLabel } from '@/lib/sourceLabel';
import type {
  DashboardMentionBoard,
  DashboardMentionItem,
  DashboardScenarioInsight,
} from '@/types/dashboard';

interface MentionBoardReportProps {
  data: DashboardMentionBoard;
}

const sentimentText = {
  positive: '正向',
  neutral: '中性',
  negative: '负向',
} as const;

const sentimentTone = {
  positive: 'bg-emerald-500/10 text-emerald-500 border-emerald-500/20',
  neutral:
    'bg-[var(--bg-tertiary)] text-[var(--text-secondary)] border-[var(--border-subtle)]',
  negative: 'bg-red-500/10 text-red-500 border-red-500/20',
  missing:
    'bg-[var(--bg-secondary)] text-[var(--text-tertiary)] border-[var(--border-subtle)]',
} as const;

const PLATFORM_ORDER = ['doubao', 'kimi', 'hunyuan', 'deepseek'] as const;

type ScenarioGroup = {
  scenarioId: string;
  scenarioLabel: string;
  platforms: Map<string, DashboardMentionItem>;
  citationDomains: Set<string>;
  evidence: string[];
  positive: number;
  neutral: number;
  negative: number;
  officialCitationPresent: boolean;
};

type ScenarioActionCard = {
  scenario_id: string;
  scenario_label: string;
  reason: string;
  action: string;
  platforms: string[];
};

function cleanNarrativeText(value: string | undefined): string {
  if (!value) return '';
  return value
    .replace(/bwvs[^。！？]*[。！？]?/gi, '')
    .replace(/引用得分为[^。！？]*[。！？]?/g, '')
    .replace(/品牌口碑基础/g, '品牌认知基础')
    .replace(/全平台权威性背书/g, '权威来源背书')
    .replace(/提及率为[^。；]*[。；]?/g, '')
    .replace(/仅偶尔出现[。；]?/g, '')
    .replace(/\s{2,}/g, ' ')
    .trim();
}

function isMeaningfulScenarioLabel(value: string | undefined): boolean {
  const label = String(value || '').trim();
  if (!label) return false;
  const lowered = label.toLowerCase();
  if (lowered.includes('bwvs')) return false;
  if (
    ['未命名问题', '问题待补全', '回答样本', '引用样本', '品牌认知基础', '权威来源背书'].some(
      (token) => label.includes(token),
    )
  ) {
    return false;
  }
  return true;
}

function buildScenarioLabel(item: DashboardMentionItem): string {
  if (isMeaningfulScenarioLabel(item.scenario_label)) {
    return item.scenario_label;
  }
  const citationTitle = item.citation_titles?.find(Boolean);
  if (citationTitle) return citationTitle;
  const citationDomain = item.citation_domains?.find(Boolean);
  if (citationDomain) return getSourceLabel(citationDomain, false) || citationDomain;
  return '问题待补全';
}

function groupMentionsByScenario(items: DashboardMentionItem[]) {
  const groups = new Map<string, ScenarioGroup>();

  for (const item of items) {
    const key = item.scenario_id || item.scenario_label || `${item.platform}-${item.evidence || ''}`;
    if (!groups.has(key)) {
      groups.set(key, {
        scenarioId: item.scenario_id,
        scenarioLabel: buildScenarioLabel(item),
        platforms: new Map(),
        citationDomains: new Set(),
        evidence: [],
        positive: 0,
        neutral: 0,
        negative: 0,
        officialCitationPresent: false,
      });
    }
    const group = groups.get(key)!;
    if (item.platform) {
      group.platforms.set(item.platform, item);
    }
    item.citation_domains?.forEach((domain) => domain && group.citationDomains.add(domain));
    if (item.evidence) {
      group.evidence.push(item.evidence);
    }
    if (item.sentiment === 'positive') group.positive += 1;
    else if (item.sentiment === 'negative') group.negative += 1;
    else group.neutral += 1;
    group.officialCitationPresent = group.officialCitationPresent || Boolean(item.official_citation_present);
  }

  return Array.from(groups.values())
    .filter((item) => isMeaningfulScenarioLabel(item.scenarioLabel))
    .sort((a, b) => {
      const scoreA = a.platforms.size * 10 + a.positive * 2 - a.negative;
      const scoreB = b.platforms.size * 10 + b.positive * 2 - b.negative;
      return scoreB - scoreA;
    });
}

function buildStrongScenarios(groups: ScenarioGroup[]): ScenarioActionCard[] {
  const strongest = groups
    .filter((item) => item.positive > 0 || item.officialCitationPresent || item.platforms.size > 1)
    .sort(
      (a, b) =>
        b.platforms.size * 10 +
        b.positive * 3 +
        (b.officialCitationPresent ? 4 : 0) -
        (a.platforms.size * 10 + a.positive * 3 + (a.officialCitationPresent ? 4 : 0)),
    )[0];

  if (!strongest) return [];

  return [{
    scenario_id: strongest.scenarioId,
    scenario_label: strongest.scenarioLabel,
    reason: strongest.officialCitationPresent
      ? '这个场景里品牌已经进入答案，并且已有品牌自有内容被引用，说明当前表达方式已经开始被 AI 采纳。'
      : `这个场景里品牌已经在 ${strongest.platforms.size} 个平台进入回答，属于当前最值得继续放大的优势场景。`,
    action:
      '下一步建议：打开引用内容置信度报告，确认这个场景里哪些高置信度内容被采纳了，再沿着同一表达方式扩展到相邻问题。',
    platforms: Array.from(strongest.platforms.keys()),
  }];
}

function buildWeakScenarios(
  competitorMentions: DashboardMentionItem[],
  brandGroups: ScenarioGroup[],
  fallbackWeak: DashboardScenarioInsight[],
): ScenarioActionCard[] {
  const brandScenarioKeys = new Set(brandGroups.map((item) => item.scenarioId || item.scenarioLabel));
  const groupedCompetitor = new Map<
    string,
    {
      scenarioId: string;
      scenarioLabel: string;
      competitors: Set<string>;
      platforms: Set<string>;
    }
  >();

  competitorMentions.forEach((item) => {
    const key = item.scenario_id || item.scenario_label || `${item.platform}-${item.competitor || ''}`;
    if (!groupedCompetitor.has(key)) {
      groupedCompetitor.set(key, {
        scenarioId: item.scenario_id,
        scenarioLabel: buildScenarioLabel(item),
        competitors: new Set(),
        platforms: new Set(),
      });
    }
    const group = groupedCompetitor.get(key)!;
    if (item.competitor) group.competitors.add(item.competitor);
    if (item.platform) group.platforms.add(item.platform);
  });

  const missingByCompetitor = Array.from(groupedCompetitor.values())
    .filter(
      (item) =>
        isMeaningfulScenarioLabel(item.scenarioLabel) &&
        !brandScenarioKeys.has(item.scenarioId || item.scenarioLabel),
    )
    .map((item) => ({
      scenario_id: item.scenarioId,
      scenario_label: item.scenarioLabel,
      reason: `${Array.from(item.competitors).join('、') || '竞品'}已在这个场景先进入答案，品牌当前还没有稳定站住。`,
      action:
        '下一步建议：进入用户画像分析，继续拆开这个问题背后的人群、预算和使用场景，找到被竞品抢走的是哪类细分需求，再补相应内容。',
      platforms: Array.from(item.platforms),
    }));

  if (missingByCompetitor.length > 0) {
    return missingByCompetitor.slice(0, 2);
  }

  return fallbackWeak
    .filter((item) => isMeaningfulScenarioLabel(item.scenario_label))
    .map((item) => ({
      scenario_id: item.scenario_id,
      scenario_label: item.scenario_label,
      reason: cleanNarrativeText(item.reason) || '当前仍需补强该类问题中的品牌出现率。',
      action:
        '下一步建议：从用户画像分析继续下钻，把这个场景拆到更细的人群与需求层，再决定优先补哪些对比页、FAQ 或案例内容。',
      platforms: item.platforms ?? [],
    }))
    .slice(0, 2);
}

export function MentionBoardReport({ data }: MentionBoardReportProps) {
  const mentionRate = data.mention_rate != null ? `${(data.mention_rate * 100).toFixed(1)}%` : '--';
  const groupedBrandMentions = groupMentionsByScenario(data.report.brand_mentions);
  const positiveScenarioCount = groupedBrandMentions.filter((item) => item.positive > item.negative).length;
  const negativeScenarioCount = groupedBrandMentions.filter((item) => item.negative > item.positive).length;
  const strongScenarios = buildStrongScenarios(groupedBrandMentions);
  const weakScenarios = buildWeakScenarios(
    data.report.competitor_mentions,
    groupedBrandMentions,
    data.report.weak_scenarios,
  );

  return (
    <div className="space-y-6">
      <section className="dashboard-report-panel rounded-[26px] p-6 md:p-7">
        <div className="grid gap-4 md:grid-cols-4">
          <div
            className="rounded-[18px] border bg-[var(--bg-elevated)] px-5 py-4"
            style={{ borderColor: 'var(--border-subtle)' }}
          >
            <div className="text-[11px] tracking-[0.12em] text-[var(--text-tertiary)]">提及率</div>
            <div className="mt-2 text-[30px] font-semibold tracking-[-0.04em] text-[var(--text-primary)]">
              {mentionRate}
            </div>
          </div>
          <div
            className="rounded-[18px] border bg-[var(--bg-elevated)] px-5 py-4"
            style={{ borderColor: 'var(--border-subtle)' }}
          >
            <div className="text-[11px] tracking-[0.12em] text-[var(--text-tertiary)]">被提及问题</div>
            <div className="mt-2 text-[30px] font-semibold tracking-[-0.04em] text-[var(--text-primary)]">
              {groupedBrandMentions.length}
            </div>
          </div>
          <div
            className="rounded-[18px] border bg-[var(--bg-elevated)] px-5 py-4"
            style={{ borderColor: 'var(--border-subtle)' }}
          >
            <div className="text-[11px] tracking-[0.12em] text-[var(--text-tertiary)]">正向提及</div>
            <div className="mt-2 text-[30px] font-semibold tracking-[-0.04em] text-[var(--text-primary)]">
              {positiveScenarioCount}
            </div>
          </div>
          <div
            className="rounded-[18px] border bg-[var(--bg-elevated)] px-5 py-4"
            style={{ borderColor: 'var(--border-subtle)' }}
          >
            <div className="text-[11px] tracking-[0.12em] text-[var(--text-tertiary)]">负向提及</div>
            <div className="mt-2 text-[30px] font-semibold tracking-[-0.04em] text-[var(--text-primary)]">
              {negativeScenarioCount}
            </div>
          </div>
        </div>
      </section>

      <div className="grid gap-6 xl:grid-cols-[1.2fr_0.8fr]">
        <section
          className="dashboard-report-panel rounded-[24px] p-6"
          style={{ borderColor: 'var(--border-subtle)' }}
        >
          <div className="flex items-center justify-between gap-3 border-b border-[var(--border-subtle)] pb-3">
            <h4 className="text-[18px] font-semibold text-[var(--text-primary)]">品牌被提及的问题</h4>
            <span className="text-[12px] text-[var(--text-tertiary)]">{groupedBrandMentions.length} 个问题</span>
          </div>
          <div className="mt-4 space-y-3">
            {groupedBrandMentions.length > 0 ? (
              groupedBrandMentions.map((item, index) => (
                <article
                  key={`${item.scenarioId || item.scenarioLabel}-${index}`}
                  className="rounded-[18px] border bg-[var(--bg-elevated)] p-5"
                  style={{ borderColor: 'var(--border-subtle)' }}
                >
                  <div className="text-[16px] font-semibold text-[var(--text-primary)]">{item.scenarioLabel}</div>
                  <div className="mt-3 grid gap-2 sm:grid-cols-2 xl:grid-cols-4">
                    {PLATFORM_ORDER.map((platform) => {
                      const mention = item.platforms.get(platform);
                      const tone = mention
                        ? ((mention.sentiment as keyof typeof sentimentTone) || 'neutral')
                        : 'missing';
                      const text = mention
                        ? sentimentText[(mention.sentiment as keyof typeof sentimentText) || 'neutral'] || '中性'
                        : '未提及';
                      return (
                        <div
                          key={`${item.scenarioId || item.scenarioLabel}-${platform}`}
                          className={`rounded-[14px] border px-3 py-2.5 ${sentimentTone[tone]}`}
                        >
                          <div className="text-[11px] tracking-[0.08em]">
                            {getPlatformDisplayName(platform)}
                          </div>
                          <div className="mt-1 text-[14px] font-semibold">{text}</div>
                        </div>
                      );
                    })}
                  </div>
                  {item.evidence[0] ? (
                    <div className="mt-3 space-y-1">
                      <div className="text-[12px] font-medium text-[var(--text-secondary)]">涉及的答案</div>
                      <p className="text-[14px] leading-7 text-[var(--text-secondary)]">
                        {cleanNarrativeText(item.evidence[0])}
                      </p>
                    </div>
                  ) : null}
                  {item.citationDomains.size > 0 ? (
                    <div className="mt-3 space-y-1">
                      <div className="text-[12px] font-medium text-[var(--text-secondary)]">引用来源</div>
                      <div className="flex flex-wrap gap-2">
                        {Array.from(item.citationDomains)
                          .slice(0, 6)
                          .map((domain) => (
                            <span
                              key={`${item.scenarioId || item.scenarioLabel}-${domain}`}
                              className="rounded-full border border-[var(--border-subtle)] px-2.5 py-1 text-[11px] text-[var(--text-secondary)]"
                            >
                              {getSourceLabel(domain, false)}
                            </span>
                          ))}
                      </div>
                    </div>
                  ) : null}
                </article>
              ))
            ) : (
              <div className="rounded-[16px] border border-dashed border-[var(--border-subtle)] px-4 py-6 text-[14px] text-[var(--text-tertiary)]">
                当前还没有品牌提及明细。
              </div>
            )}
          </div>
        </section>

        <div className="space-y-6">
          <section
            className="dashboard-report-panel rounded-[24px] p-6"
            style={{ borderColor: 'var(--border-subtle)' }}
          >
            <h4 className="text-[18px] font-semibold text-[var(--text-primary)]">当前优势</h4>
            <div className="mt-4 space-y-3">
              {strongScenarios.length > 0 ? (
                strongScenarios.map((item) => (
                  <div
                    key={item.scenario_id || item.scenario_label}
                    className="rounded-[18px] border bg-[var(--bg-elevated)] p-5"
                    style={{ borderColor: 'var(--border-subtle)' }}
                  >
                    <div className="text-[15px] font-semibold text-[var(--text-primary)]">{item.scenario_label}</div>
                    <div className="mt-2 text-[14px] leading-7 text-[var(--text-secondary)]">
                      {cleanNarrativeText(item.reason)}
                    </div>
                    <div className="mt-4 rounded-[16px] bg-[var(--bg-secondary)] px-4 py-3 text-[13px] leading-7 text-[var(--text-secondary)]">
                      <span className="font-medium text-[var(--text-primary)]">下一步建议：</span>
                      {item.action}
                    </div>
                  </div>
                ))
              ) : (
                <div className="rounded-[16px] border border-dashed border-[var(--border-subtle)] px-4 py-6 text-[14px] text-[var(--text-tertiary)]">
                  当前还没有明确优势。
                </div>
              )}
            </div>
          </section>

          <section
            className="dashboard-report-panel rounded-[24px] p-6"
            style={{ borderColor: 'var(--border-subtle)' }}
          >
            <h4 className="text-[18px] font-semibold text-[var(--text-primary)]">当前补强</h4>
            <div className="mt-4 space-y-3">
              {weakScenarios.length > 0 ? (
                weakScenarios.map((item) => (
                  <div
                    key={item.scenario_id || item.scenario_label}
                    className="rounded-[18px] border bg-[var(--bg-elevated)] p-5"
                    style={{ borderColor: 'var(--border-subtle)' }}
                  >
                    <div className="text-[15px] font-semibold text-[var(--text-primary)]">{item.scenario_label}</div>
                    <div className="mt-2 text-[14px] leading-7 text-[var(--text-secondary)]">
                      {cleanNarrativeText(item.reason)}
                    </div>
                    <div className="mt-4 rounded-[16px] bg-[var(--bg-secondary)] px-4 py-3 text-[13px] leading-7 text-[var(--text-secondary)]">
                      <span className="font-medium text-[var(--text-primary)]">下一步建议：</span>
                      {item.action}
                    </div>
                  </div>
                ))
              ) : (
                <div className="rounded-[16px] border border-dashed border-[var(--border-subtle)] px-4 py-6 text-[14px] text-[var(--text-tertiary)]">
                  当前还没有明确补强项。
                </div>
              )}
            </div>
          </section>
        </div>
      </div>
    </div>
  );
}
