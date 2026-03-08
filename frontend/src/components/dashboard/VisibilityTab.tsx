import type { DashboardScenarioRow } from '@/types/dashboard';
import { EmptyState } from '@/components/ui/empty-state';
import { RiScan2Line } from '@remixicon/react';
import { chart } from '@/styles/chart-theme';

interface VisibilityTabProps {
  data: Array<{ date: string; score: number; platform?: string }>;
  entityId?: string | null;
  brandName?: string;
  officialDomain?: string;
  officialCitationRate?: number | null;
  scenarioRows?: DashboardScenarioRow[];
}

const priorityTone = {
  high: { color: chart.colors.red, bg: `${chart.colors.red}1a`, label: '????' },
  medium: { color: chart.colors.yellow, bg: `${chart.colors.yellow}1a`, label: '????' },
  low: { color: chart.colors.green, bg: `${chart.colors.green}1a`, label: '????' },
} as const;

const battleStatusTone = {
  advantage: { color: chart.colors.green, bg: `${chart.colors.green}1a`, label: '??' },
  defend: { color: chart.colors.cyan, bg: `${chart.colors.cyan}1a`, label: '??' },
  contested: { color: chart.colors.yellow, bg: `${chart.colors.yellow}1a`, label: '??' },
  missing: { color: chart.colors.red, bg: `${chart.colors.red}1a`, label: '??' },
} as const;

const riskTone = {
  high: { color: chart.colors.red, bg: `${chart.colors.red}1a`, label: '???' },
  medium: { color: chart.colors.yellow, bg: `${chart.colors.yellow}1a`, label: '???' },
  low: { color: chart.colors.green, bg: `${chart.colors.green}1a`, label: '???' },
} as const;

function normalizePriority(value: string | undefined) {
  if (value === 'high' || value === 'medium' || value === 'low') {
    return value;
  }
  return 'medium';
}

function normalizeBattleStatus(value: string | undefined) {
  if (value === 'advantage' || value === 'defend' || value === 'contested' || value === 'missing') {
    return value;
  }
  return 'missing';
}

function normalizeRisk(value: string | undefined) {
  if (value === 'high' || value === 'medium' || value === 'low') {
    return value;
  }
  return 'medium';
}

function sortScenarioRows(rows: DashboardScenarioRow[]) {
  const priorityOrder = { high: 0, medium: 1, low: 2 } as const;
  const riskOrder = { high: 0, medium: 1, low: 2 } as const;

  return [...rows].sort((a, b) => {
    const priorityDiff =
      priorityOrder[normalizePriority(a.scenario_priority)] -
      priorityOrder[normalizePriority(b.scenario_priority)];
    if (priorityDiff !== 0) return priorityDiff;

    const riskDiff = riskOrder[normalizeRisk(a.risk_level)] - riskOrder[normalizeRisk(b.risk_level)];
    if (riskDiff !== 0) return riskDiff;

    return a.scenario_label.localeCompare(b.scenario_label, 'zh-CN');
  });
}

export function VisibilityTab({
  brandName,
  officialDomain,
  officialCitationRate,
  scenarioRows = [],
}: VisibilityTabProps) {
  if (scenarioRows.length === 0) {
    return (
      <EmptyState
        icon={RiScan2Line}
        title="????????"
        description="???????????????????????????????????????"
      />
    );
  }

  const sortedRows = sortScenarioRows(scenarioRows);
  const groups = {
    advantage: sortedRows.filter((row) => normalizeBattleStatus(row.battle_status) === 'advantage'),
    defend: sortedRows.filter((row) => normalizeBattleStatus(row.battle_status) === 'defend'),
    contested: sortedRows.filter((row) => normalizeBattleStatus(row.battle_status) === 'contested'),
    missing: sortedRows.filter((row) => normalizeBattleStatus(row.battle_status) === 'missing'),
  };

  const summaryCards = [
    {
      label: '????',
      value: String(sortedRows.length),
      desc: brandName ? `${brandName} ???????????` : '?????????????',
    },
    {
      label: '????',
      value: String(sortedRows.filter((row) => row.brand_present).length),
      desc: '?????????????',
    },
    {
      label: '????',
      value: String(groups.missing.length),
      desc: '????????????????',
    },
    {
      label: '???????',
      value: officialCitationRate != null ? `${officialCitationRate.toFixed(1)}%` : '--',
      desc: officialDomain ? `??? ${officialDomain} ???????` : '????????????',
    },
  ];

  const orderedGroups: Array<{
    key: 'missing' | 'contested' | 'defend' | 'advantage';
    title: string;
    description: string;
  }> = [
    { key: 'missing', title: '????', description: '????????????????????????' },
    { key: 'contested', title: '????', description: '?????????????????????????' },
    { key: 'defend', title: '????', description: '?????????????????????' },
    { key: 'advantage', title: '????', description: '???????????????????????' },
  ];

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-4">
        {summaryCards.map((card) => (
          <div
            key={card.label}
            className="rounded-2xl p-4"
            style={{
              background: 'var(--bg-tertiary)',
              border: '1px solid var(--border-subtle)',
            }}
          >
            <div className="mb-2 text-xs" style={{ color: 'var(--text-tertiary)' }}>
              {card.label}
            </div>
            <div className="mb-2 text-2xl font-semibold" style={{ color: 'var(--text-primary)' }}>
              {card.value}
            </div>
            <div className="text-sm leading-6" style={{ color: 'var(--text-secondary)' }}>
              {card.desc}
            </div>
          </div>
        ))}
      </div>

      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
        {orderedGroups.map((group) => {
          const rows = groups[group.key];
          const tone = battleStatusTone[group.key];
          return (
            <div
              key={group.key}
              className="rounded-2xl p-4"
              style={{
                background: 'var(--bg-tertiary)',
                border: '1px solid var(--border-subtle)',
              }}
            >
              <div className="flex items-center justify-between gap-3">
                <div>
                  <div className="mb-2 text-xs" style={{ color: 'var(--text-tertiary)' }}>
                    {group.title}
                  </div>
                  <div className="text-2xl font-semibold" style={{ color: 'var(--text-primary)' }}>
                    {rows.length}
                  </div>
                </div>
                <span
                  className="rounded-full px-2 py-0.5 text-xs font-medium"
                  style={{ color: tone.color, backgroundColor: tone.bg }}
                >
                  {tone.label}
                </span>
              </div>
              <div className="mt-2 text-sm leading-6" style={{ color: 'var(--text-secondary)' }}>
                {group.description}
              </div>
            </div>
          );
        })}
      </div>

      <div className="space-y-4">
        {orderedGroups.map((group) => {
          const rows = groups[group.key];
          if (rows.length === 0) return null;

          const groupTone = battleStatusTone[group.key];
          return (
            <section
              key={group.key}
              className="overflow-hidden rounded-2xl"
              style={{
                background: 'var(--bg-tertiary)',
                border: '1px solid var(--border-subtle)',
              }}
            >
              <div
                className="flex items-center justify-between gap-3 px-4 py-3"
                style={{ borderBottom: '1px solid var(--border-subtle)' }}
              >
                <div>
                  <h3 className="text-sm font-medium" style={{ color: 'var(--text-primary)' }}>
                    {group.title}
                  </h3>
                  <p className="mt-1 text-xs" style={{ color: 'var(--text-tertiary)' }}>
                    {group.description}
                  </p>
                </div>
                <span
                  className="rounded-full px-2 py-0.5 text-xs font-medium"
                  style={{ color: groupTone.color, backgroundColor: groupTone.bg }}
                >
                  {rows.length} ???
                </span>
              </div>

              <div className="grid gap-4 p-4 xl:grid-cols-2">
                {rows.map((row) => {
                  const priority = priorityTone[normalizePriority(row.scenario_priority)];
                  const risk = riskTone[normalizeRisk(row.risk_level)];
                  const battle = battleStatusTone[normalizeBattleStatus(row.battle_status)];

                  return (
                    <article
                      key={row.scenario_id || row.scenario_label}
                      className="rounded-2xl border border-[var(--border-subtle)] bg-[var(--bg-elevated)] p-4"
                    >
                      <div className="flex flex-wrap items-start justify-between gap-3">
                        <div className="min-w-0 flex-1">
                          <div className="text-sm font-medium" style={{ color: 'var(--text-primary)' }}>
                            {row.scenario_label}
                          </div>
                          {row.query_examples?.[0] && (
                            <div className="mt-1 text-xs leading-5" style={{ color: 'var(--text-tertiary)' }}>
                              ?????{row.query_examples[0]}
                            </div>
                          )}
                        </div>
                        <div className="flex flex-wrap gap-2">
                          <span className="rounded-full px-2 py-0.5 text-xs font-medium" style={{ color: priority.color, backgroundColor: priority.bg }}>
                            {priority.label}
                          </span>
                          <span className="rounded-full px-2 py-0.5 text-xs font-medium" style={{ color: battle.color, backgroundColor: battle.bg }}>
                            {battle.label}
                          </span>
                          <span className="rounded-full px-2 py-0.5 text-xs font-medium" style={{ color: risk.color, backgroundColor: risk.bg }}>
                            {risk.label}
                          </span>
                        </div>
                      </div>

                      <div className="mt-4 grid gap-3 md:grid-cols-2 text-sm" style={{ color: 'var(--text-secondary)' }}>
                        <div>?????{row.present_platforms.join(' / ') || '--'}</div>
                        <div>?????{row.official_citation_present ? '???????' : '???????'}</div>
                        <div>?????{row.competitors_present.join(' / ') || '--'}</div>
                        <div>?????{row.winner_brands.join(' / ') || '--'}</div>
                      </div>

                      {(row.evidence || row.action_hint) && (
                        <div className="mt-4 space-y-2 text-sm leading-6">
                          {row.evidence && (
                            <div style={{ color: 'var(--text-secondary)' }}>
                              ?????{row.evidence}
                            </div>
                          )}
                          {row.action_hint && (
                            <div style={{ color: 'var(--text-primary)' }}>
                              ?????{row.action_hint}
                            </div>
                          )}
                        </div>
                      )}
                    </article>
                  );
                })}
              </div>
            </section>
          );
        })}
      </div>
    </div>
  );
}
