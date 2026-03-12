import { PolarAngleAxis, PolarGrid, Radar, RadarChart, ResponsiveContainer } from 'recharts';
import type { DashboardRadarBoard } from '@/types/dashboard';
import { chart } from '@/styles/chart-theme';

interface RadarBoardReportProps {
  data: DashboardRadarBoard;
}

export function RadarBoardReport({ data }: RadarBoardReportProps) {
  return (
    <div className="space-y-6">
      <section
        className="rounded-[24px] border p-7"
        style={{
          borderColor: 'var(--border-subtle)',
          background: 'linear-gradient(180deg, color-mix(in srgb, var(--bg-tertiary) 90%, #edf5f2 10%), color-mix(in srgb, var(--bg-elevated) 98%, #f6f1e8 2%))',
        }}
      >
        <h3 className="text-[28px] font-semibold tracking-[-0.03em] text-[var(--text-primary)]">用五个维度概括整体战况</h3>
        <p className="mt-3 max-w-4xl text-[14px] leading-7 text-[var(--text-secondary)]">{data.headline}</p>
      </section>

      <div className="grid gap-6 xl:grid-cols-[0.92fr_1.08fr]">
        <section className="rounded-[24px] border bg-[var(--bg-tertiary)] p-6" style={{ borderColor: 'var(--border-subtle)' }}>
          <div className="h-[320px]">
            <ResponsiveContainer width="100%" height="100%">
              <RadarChart data={data.dimensions} outerRadius="70%">
                <PolarGrid stroke="var(--border-subtle)" />
                <PolarAngleAxis dataKey="label" tick={{ fill: chart.colors.secondary, fontSize: 11 }} />
                <Radar dataKey="score" stroke={chart.colors.primary} fill={chart.colors.primary} fillOpacity={0.12} />
              </RadarChart>
            </ResponsiveContainer>
          </div>
        </section>

        <section className="space-y-3">
          {data.dimensions.map((item) => (
            <article key={item.id} className="rounded-[18px] border bg-[var(--bg-tertiary)] p-5" style={{ borderColor: 'var(--border-subtle)' }}>
              <div className="flex items-start justify-between gap-4">
                <div className="min-w-0 flex-1">
                  <div className="text-[16px] font-semibold text-[var(--text-primary)]">{item.label}</div>
                  <div className="mt-2 text-[14px] leading-7 text-[var(--text-secondary)]">{item.summary}</div>
                </div>
                <div className="text-right">
                  <div className="text-[30px] font-semibold leading-none tracking-[-0.04em] text-[var(--text-primary)]">{item.score}</div>
                  <div className="mt-1 text-[11px] text-[var(--text-tertiary)]">分</div>
                </div>
              </div>
            </article>
          ))}
        </section>
      </div>
    </div>
  );
}
