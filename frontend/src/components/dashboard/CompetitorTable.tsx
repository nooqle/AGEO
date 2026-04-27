import { chart } from '@/styles/chart-theme';
import type {
  CompetitorRow,
  DashboardCompetitorPressureCard,
  DashboardScenarioMatrixCell,
  DashboardScenarioMatrixRow,
} from '@/types/dashboard';

interface CompetitorTableProps {
  data: CompetitorRow[];
  brandName?: string;
  brandVisibility?: number | null;
  brandMentionRate?: number | null;
  officialCitationRate?: number | null;
  standalone?: boolean;
  summaryCards?: DashboardCompetitorPressureCard[];
  scenarioMatrix?: DashboardScenarioMatrixRow[];
}

interface LegacyPressureRow {
  competitor: string;
  shared: number;
  competitorOnly: number;
  brandOnly: number;
  pressure: 'high' | 'medium' | 'low';
  topConflicts: string[];
}

const pressureTone = {
  high: { color: chart.colors.red, bg: `${chart.colors.red}1a`, label: '高压力' },
  medium: { color: chart.colors.yellow, bg: `${chart.colors.yellow}1a`, label: '中压力' },
  low: { color: chart.colors.green, bg: `${chart.colors.green}1a`, label: '低压力' },
} as const;

const stateTone = {
  win: { color: chart.colors.green, bg: `${chart.colors.green}1a`, label: '占优' },
  present: { color: chart.colors.source, bg: `${chart.colors.source}1a`, label: '已进入' },
  absent: { color: chart.colors.red, bg: `${chart.colors.red}1a`, label: '缺席' },
} as const;

function normalizePressure(level: string | undefined) {
  if (level === 'high' || level === 'medium' || level === 'low') return level;
  return 'medium';
}

function normalizeState(state: string | undefined) {
  if (state === 'win' || state === 'present' || state === 'absent') return state;
  return 'absent';
}

function findBrandState(states: DashboardScenarioMatrixCell[], brandName?: string) {
  if (!states.length) return null;
  const normalizedBrand = (brandName || '').trim().toLowerCase();
  const direct = states.find((item) => item.brand.trim().toLowerCase() === normalizedBrand);
  if (direct) return direct;
  const alias = states.find((item) => ['本品牌', '我方', '品牌'].includes(item.brand.trim()));
  if (alias) return alias;
  return states[0] ?? null;
}

function buildLegacyPressureRows(data: CompetitorRow[], brandVisibility?: number | null, brandMentionRate?: number | null): LegacyPressureRow[] {
  return data.map((item) => {
    const mentionGap = item.mentionRate - (brandMentionRate ?? 0);
    const visibilityGap = item.visibility - (brandVisibility ?? 0);
    const pressure = mentionGap > 0.1 || visibilityGap > 10 ? 'high' : mentionGap > 0.04 || visibilityGap > 4 ? 'medium' : 'low';
    return {
      competitor: item.name,
      shared: mentionGap > -0.02 ? 1 : 0,
      competitorOnly: mentionGap > 0.05 || visibilityGap > 5 ? 1 : 0,
      brandOnly: mentionGap < -0.05 && visibilityGap < -5 ? 1 : 0,
      pressure,
      topConflicts: [`${item.name} 在多个核心场景与品牌形成直接竞争。`],
    };
  });
}

export function CompetitorTable({ data, brandName, brandVisibility, brandMentionRate, standalone = false, summaryCards = [], scenarioMatrix = [] }: CompetitorTableProps) {
  const hasV2 = summaryCards.length > 0 || scenarioMatrix.length > 0;
  const legacyRows = buildLegacyPressureRows(data, brandVisibility, brandMentionRate);
  if (!hasV2 && data.length === 0) return null;

  const cards = hasV2
    ? summaryCards
    : legacyRows.map((row) => ({
        competitor: row.competitor,
        shared_scenarios: row.shared,
        competitor_only_scenarios: row.competitorOnly,
        brand_only_scenarios: row.brandOnly,
        pressure_level: row.pressure,
        top_conflict_scenarios: row.topConflicts,
      }));

  const matrixRows = hasV2 ? scenarioMatrix : [];

  return (
    <div className="space-y-4">
      {standalone && (
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
          {cards.slice(0, 6).map((card) => {
            const tone = pressureTone[normalizePressure(card.pressure_level)];
            return (
              <div key={card.competitor} className="rounded-2xl p-4" style={{ background: 'var(--bg-tertiary)', border: '1px solid var(--border-subtle)' }}>
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <div className="mb-2 text-xs" style={{ color: 'var(--text-tertiary)' }}>竞争对手</div>
                    <div className="text-lg font-semibold" style={{ color: 'var(--text-primary)' }}>{card.competitor}</div>
                  </div>
                  <span className="rounded-full px-2 py-0.5 text-xs font-medium" style={{ color: tone.color, backgroundColor: tone.bg }}>{tone.label}</span>
                </div>
                <div className="mt-4 grid grid-cols-3 gap-2 text-center text-sm">
                  <div className="rounded-xl bg-[var(--bg-secondary)] p-3"><div className="text-xs text-[var(--text-tertiary)]">共享场景</div><div className="mt-1 font-semibold text-[var(--text-primary)]">{card.shared_scenarios}</div></div>
                  <div className="rounded-xl bg-[var(--bg-secondary)] p-3"><div className="text-xs text-[var(--text-tertiary)]">竞品独占</div><div className="mt-1 font-semibold text-[var(--text-primary)]">{card.competitor_only_scenarios}</div></div>
                  <div className="rounded-xl bg-[var(--bg-secondary)] p-3"><div className="text-xs text-[var(--text-tertiary)]">我方独占</div><div className="mt-1 font-semibold text-[var(--text-primary)]">{card.brand_only_scenarios}</div></div>
                </div>
                {card.top_conflict_scenarios && card.top_conflict_scenarios.length > 0 && (
                  <div className="mt-4 space-y-2">
                    {card.top_conflict_scenarios.slice(0, 2).map((item, index) => (
                      <div key={`${card.competitor}-${index}`} className="text-sm leading-6" style={{ color: 'var(--text-secondary)' }}>{item}</div>
                    ))}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}

      <div className="overflow-hidden rounded-2xl" style={{ background: 'var(--bg-tertiary)', border: '1px solid var(--border-subtle)' }}>
        <div className="px-4 py-3" style={{ borderBottom: '1px solid var(--border-subtle)' }}>
          <h3 className="text-sm font-medium" style={{ color: 'var(--text-primary)' }}>{standalone ? '竞品争夺矩阵' : '竞品争夺'}</h3>
          <p className="mt-1 text-xs" style={{ color: 'var(--text-tertiary)' }}>按场景查看谁在和品牌正面争夺，以及当前胜负关系。</p>
        </div>

        {hasV2 ? (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[980px]">
              <thead style={{ background: 'var(--bg-elevated)' }}>
                <tr>
                  <th className="px-4 py-3 text-left text-xs font-medium uppercase" style={{ color: 'var(--text-tertiary)' }}>争夺场景</th>
                  <th className="px-4 py-3 text-left text-xs font-medium uppercase" style={{ color: 'var(--text-tertiary)' }}>当前胜者</th>
                  <th className="px-4 py-3 text-left text-xs font-medium uppercase" style={{ color: 'var(--text-tertiary)' }}>我方状态</th>
                  <th className="px-4 py-3 text-left text-xs font-medium uppercase" style={{ color: 'var(--text-tertiary)' }}>竞品状态</th>
                  <th className="px-4 py-3 text-left text-xs font-medium uppercase" style={{ color: 'var(--text-tertiary)' }}>争夺焦点</th>
                </tr>
              </thead>
              <tbody>
                {matrixRows.map((row) => {
                  const myState = findBrandState(row.competitor_states, brandName);
                  const myStateTone = stateTone[normalizeState(myState?.state)];
                  const rivals = row.competitor_states.filter((item) => item.brand !== myState?.brand);
                  return (
                    <tr key={row.scenario_id || row.scenario_label} style={{ borderBottom: '1px solid var(--border-subtle)' }}>
                      <td className="px-4 py-4 align-top"><div className="text-sm font-medium" style={{ color: 'var(--text-primary)' }}>{row.scenario_label}</div></td>
                      <td className="px-4 py-4 align-top text-sm font-medium" style={{ color: 'var(--text-primary)' }}>{row.winner_brand || '--'}</td>
                      <td className="px-4 py-4 align-top">
                        <div className="flex flex-wrap items-center gap-2">
                          <span className="rounded-full px-2 py-0.5 text-xs font-medium" style={{ color: myStateTone.color, backgroundColor: myStateTone.bg }}>{myState?.brand || brandName || '本品牌'} · {myStateTone.label}</span>
                          {myState?.official_cited && <span className="rounded-full bg-emerald-500/10 px-2 py-0.5 text-xs font-medium text-emerald-400">官网被引</span>}
                        </div>
                      </td>
                      <td className="px-4 py-4 align-top">
                        <div className="flex flex-wrap gap-2">
                          {rivals.length > 0 ? rivals.map((item, index) => {
                            const tone = stateTone[normalizeState(item.state)];
                            return <span key={`${row.scenario_id}-${item.brand}-${index}`} className="rounded-full px-2 py-0.5 text-xs font-medium" style={{ color: tone.color, backgroundColor: tone.bg }}>{item.brand} · {tone.label}{item.official_cited ? ' · 官网被引' : ''}</span>;
                          }) : <span className="text-sm text-[var(--text-secondary)]">--</span>}
                        </div>
                      </td>
                      <td className="px-4 py-4 align-top text-sm leading-6" style={{ color: 'var(--text-secondary)' }}>{row.recommended_focus || '建议优先补位并强化差异化内容。'}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="space-y-3 p-4">
            {legacyRows.map((row) => {
              const tone = pressureTone[row.pressure];
              return (
                <div key={row.competitor} className="rounded-2xl border border-[var(--border-subtle)] bg-[var(--bg-elevated)] p-4">
                  <div className="flex items-center justify-between gap-3"><div className="text-sm font-medium text-[var(--text-primary)]">{row.competitor}</div><span className="rounded-full px-2 py-0.5 text-xs font-medium" style={{ color: tone.color, backgroundColor: tone.bg }}>{tone.label}</span></div>
                  <div className="mt-3 text-sm leading-6 text-[var(--text-secondary)]">共享 {row.shared} 个场景，竞品独占 {row.competitorOnly} 个场景，我方独占 {row.brandOnly} 个。</div>
                  {row.topConflicts[0] && <div className="mt-2 text-sm leading-6 text-[var(--text-secondary)]">{row.topConflicts[0]}</div>}
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
