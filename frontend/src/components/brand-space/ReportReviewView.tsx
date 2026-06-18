import { AlertTriangle, CheckCircle2, FileCheck2, GitBranch, Lock, Route, ShieldAlert } from 'lucide-react';
import styles from './BrandSpace.module.css';
import { reportGuardrails, traceSteps } from '@/mocks/brandSpaceMock';
import type { BrandSpaceGraphUpdate, BrandSpaceReport, ReportGuardrailResult } from '@/types/brandSpace';

interface ReportReviewViewProps {
  report?: BrandSpaceReport | null;
  graphUpdate?: BrandSpaceGraphUpdate | null;
  guardrails?: ReportGuardrailResult[];
  onGenerateReport?: () => void;
  isGenerating?: boolean;
}

function classNames(...classes: Array<string | false | undefined>) {
  return classes.filter(Boolean).join(' ');
}

function strategicTerms(report?: BrandSpaceReport | null) {
  const raw = report?.payload?.strategic_terms;
  if (!Array.isArray(raw)) {
    return [
      ['健康管理', '已增强', '多平台正向证据支撑核心关联。'],
      ['监管信息', '留在风险层', '风险分处于 3-5 区间，需要审阅后再升级。'],
      ['竞品候选', '待审阅', '比较语境存在，但置信度低于自动入圈阈值。'],
    ];
  }
  return raw.map((item) => {
    const row = item as Record<string, unknown>;
    return [
      String(row.word ?? ''),
      String(row.state ?? ''),
      String(row.reason ?? ''),
    ];
  });
}

export function ReportReviewView({
  report,
  graphUpdate,
  guardrails = reportGuardrails,
  onGenerateReport,
  isGenerating = false,
}: ReportReviewViewProps) {
  const hasBlock = guardrails.some((guardrail) => guardrail.severity === 'block');
  const title = report?.title ?? '图谱更新解读草稿';
  const summary =
    report?.summary ??
    '这份草稿解读一次图谱更新。它可以解释已接受的补丁和待处理风险，但竞品声明仍在审阅时不能发布。';
  const terms = strategicTerms(report);

  return (
    <div className="grid gap-4 2xl:grid-cols-[minmax(0,1fr)_360px]">
      <article className={classNames(styles.surface, 'rounded-xl p-6')}>
        <div className="mb-5 flex flex-wrap items-start justify-between gap-3 border-b pb-5" style={{ borderColor: 'var(--border-subtle)' }}>
          <div>
            <p className="text-xs font-medium uppercase text-[var(--text-tertiary)]">图谱更新报告</p>
            <h1 className="mt-2 text-2xl font-semibold text-[var(--text-primary)]">{title}</h1>
            <p className="mt-2 max-w-3xl text-sm leading-6 text-[var(--text-secondary)]">{summary}</p>
          </div>
          <button
            type="button"
            disabled={Boolean(report) && hasBlock}
            onClick={report ? undefined : onGenerateReport}
            className="inline-flex h-10 items-center gap-2 rounded-lg px-3 text-sm font-semibold"
            style={{
              background: Boolean(report) && hasBlock ? 'var(--bg-tertiary)' : 'var(--brand-primary)',
              color: Boolean(report) && hasBlock ? 'var(--text-tertiary)' : 'var(--brand-contrast)',
            }}
          >
            {Boolean(report) && hasBlock ? <Lock className="h-4 w-4" /> : <FileCheck2 className="h-4 w-4" />}
            {report ? '发布' : isGenerating ? '生成中' : '生成报告'}
          </button>
        </div>

        <div className="space-y-6">
          <section>
            <h2 className="text-base font-semibold text-[var(--text-primary)]">图谱变化摘要</h2>
            <p className="mt-2 text-sm leading-7 text-[var(--text-secondary)]">
              {graphUpdate
                ? `本次更新从 ${graphUpdate.before_graph_version} 进入 ${graphUpdate.after_graph_version}，状态为 ${graphUpdate.status}。报告只解读这次图谱更新，不改写图谱事实。`
                : '本次运行增强了品牌与营养、健康管理的连接，同时把监管和价格相关信号留在正式正向圈层之外。竞品压力目前只是候选关系，升级前需要人工审阅。'}
            </p>
          </section>

          <section className="grid gap-3 md:grid-cols-3">
            {[
              ['自动应用', String(graphUpdate?.summary?.auto_applied ?? '1'), '低风险计数和连接强度更新'],
              ['待审阅', String(graphUpdate?.summary?.needs_review ?? '2'), '新实体、风险、竞品候选'],
              ['阻断结论', String(graphUpdate?.summary?.blocked ?? '1'), '证据不足或规则阻断'],
            ].map(([label, value, detail]) => (
              <div key={label} className="rounded-xl border p-4" style={{ borderColor: 'var(--border-subtle)', background: 'var(--bg-elevated)' }}>
                <p className="text-xs text-[var(--text-tertiary)]">{label}</p>
                <p className="mt-2 text-2xl font-semibold text-[var(--text-primary)]">{value}</p>
                <p className="mt-2 text-xs leading-5 text-[var(--text-secondary)]">{detail}</p>
              </div>
            ))}
          </section>

          <section>
            <h2 className="text-base font-semibold text-[var(--text-primary)]">战略词分段</h2>
            <div className="mt-3 overflow-hidden rounded-xl border" style={{ borderColor: 'var(--border-subtle)' }}>
              {terms.map(([word, state, reason]) => (
                <div key={word} className="grid gap-3 border-b p-3 text-sm last:border-b-0 md:grid-cols-[160px_180px_1fr]" style={{ borderColor: 'var(--border-subtle)' }}>
                  <span className="font-semibold text-[var(--text-primary)]">{word}</span>
                  <span className="text-[var(--text-secondary)]">{state}</span>
                  <span className="text-[var(--text-tertiary)]">{reason}</span>
                </div>
              ))}
            </div>
          </section>
        </div>
      </article>

      <aside className="space-y-4">
        <section className={classNames(styles.surface, 'rounded-xl p-4')}>
          <div className="flex items-center gap-2">
            <ShieldAlert className="h-4 w-4 text-[var(--error)]" />
            <h2 className="text-sm font-semibold text-[var(--text-primary)]">报告校验</h2>
          </div>
          <div className="mt-3 space-y-3">
            {guardrails.map((guardrail) => (
              <div
                key={guardrail.id}
                className={classNames(
                  guardrail.severity === 'block' && styles.guardrailBlock,
                  'rounded-xl border p-3',
                )}
                style={{ borderColor: guardrail.severity === 'block' ? undefined : 'var(--border-subtle)', background: guardrail.severity === 'block' ? undefined : 'var(--bg-elevated)' }}
              >
                <div className="flex items-center gap-2">
                  {guardrail.severity === 'pass' ? <CheckCircle2 className="h-4 w-4 text-[var(--success)]" /> : null}
                  {guardrail.severity === 'warn' ? <AlertTriangle className="h-4 w-4 text-[var(--warning)]" /> : null}
                  {guardrail.severity === 'block' ? <Lock className="h-4 w-4 text-[var(--error)]" /> : null}
                  <span className="text-sm font-semibold text-[var(--text-primary)]">{guardrail.title}</span>
                </div>
                <p className="mt-2 text-xs leading-5 text-[var(--text-secondary)]">{guardrail.message}</p>
              </div>
            ))}
          </div>
        </section>

        <section className={classNames(styles.surface, 'rounded-xl p-4')}>
          <div className="flex items-center gap-2">
            <Route className="h-4 w-4 text-[var(--brand-primary)]" />
            <h2 className="text-sm font-semibold text-[var(--text-primary)]">追溯链</h2>
          </div>
          <div className="mt-4 space-y-3">
            {traceSteps.map((step, index) => (
              <div key={step.id} className="relative flex gap-3">
                <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-[var(--brand-bg)] text-xs font-semibold text-[var(--brand-text)]">
                  {index + 1}
                </span>
                <div>
                  <p className="text-xs font-medium text-[var(--text-primary)]">{step.label}</p>
                  <p className="mt-1 text-xs leading-5 text-[var(--text-secondary)]">{step.value}</p>
                </div>
              </div>
            ))}
          </div>
        </section>

        <section className={classNames(styles.surface, 'rounded-xl p-4')}>
          <div className="flex items-start gap-3">
            <GitBranch className="mt-0.5 h-4 w-4 text-[var(--brand-primary)]" />
            <p className="text-xs leading-5 text-[var(--text-secondary)]">
              推荐下一张画布：审阅接受或拒绝候选竞品关系后，再运行竞品对比画布。
            </p>
          </div>
        </section>
      </aside>
    </div>
  );
}
