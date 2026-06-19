import { AlertTriangle, CheckCircle2, FileCheck2, GitBranch, Lock, Route, ShieldAlert } from 'lucide-react';
import styles from './BrandSpace.module.css';
import { reportGuardrails } from '@/mocks/brandSpaceMock';
import type {
  BrandSpaceGraphUpdate,
  BrandSpaceReport,
  BrandSpaceReportSummary,
  ReportGuardrailResult,
} from '@/types/brandSpace';

interface ReportReviewViewProps {
  report?: BrandSpaceReport | null;
  reports?: BrandSpaceReportSummary[];
  graphUpdate?: BrandSpaceGraphUpdate | null;
  guardrails?: ReportGuardrailResult[];
  onGenerateReport?: () => void;
  onPublishReport?: () => void;
  onSelectReport?: (reportId: string) => void;
  isGenerating?: boolean;
  selectedReportId?: string | null;
}

function classNames(...classes: Array<string | false | undefined>) {
  return classes.filter(Boolean).join(' ');
}

function strategicTerms(report?: BrandSpaceReport | null) {
  const raw = report?.payload?.strategic_terms;
  if (!Array.isArray(raw)) {
    return [];
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

function payloadArray(report: BrandSpaceReport | null | undefined, key: string): Array<Record<string, unknown>> {
  const raw = report?.payload?.[key];
  return Array.isArray(raw) ? raw.filter((item): item is Record<string, unknown> => typeof item === 'object' && item !== null) : [];
}

function reportClaims(report?: BrandSpaceReport | null) {
  return payloadArray(report, 'claims').map((item) => ({
    id: String(item.claim_id ?? item.patch_id ?? item.label ?? ''),
    label: String(item.label ?? ''),
    state: String(item.state ?? item.status ?? ''),
    statement: String(item.statement ?? ''),
    platforms: Array.isArray(item.platforms) ? item.platforms.map(String) : [],
  }));
}

function traceChains(report?: BrandSpaceReport | null) {
  return payloadArray(report, 'trace_chains').map((item) => ({
    id: String(item.trace_chain_id ?? item.patch_id ?? ''),
    label: String(item.label ?? ''),
    steps: Array.isArray(item.steps)
      ? item.steps
          .filter((step): step is Record<string, unknown> => typeof step === 'object' && step !== null)
          .map((step) => ({
            type: String(step.type ?? ''),
            label: String(step.label ?? ''),
            value: String(step.value ?? ''),
          }))
      : [],
  }));
}

function platformDifferences(report?: BrandSpaceReport | null) {
  return payloadArray(report, 'platform_differences').map((item) => ({
    platform: String(item.platform ?? ''),
    evidenceCount: Number(item.evidence_count ?? 0),
    patchCount: Number(item.patch_count ?? 0),
    questionCount: Number(item.question_count ?? 0),
  }));
}

function guardrailKey(guardrail: ReportGuardrailResult, index: number) {
  return guardrail.id || guardrail.guardrailKey || guardrail.guardrail_key || `${guardrail.title}-${index}`;
}

export function ReportReviewView({
  report,
  reports = [],
  graphUpdate,
  guardrails = report ? [] : reportGuardrails,
  onGenerateReport,
  onPublishReport,
  onSelectReport,
  isGenerating = false,
  selectedReportId,
}: ReportReviewViewProps) {
  const hasBlock = guardrails.some((guardrail) => guardrail.severity === 'block');
  const title = report?.title ?? '图谱更新解读草稿';
  const summary =
    report?.summary ??
    '这份草稿解读一次图谱更新。它可以解释已接受的补丁和待处理风险，但竞品声明仍在审阅时不能发布。';
  const terms = strategicTerms(report);
  const claims = reportClaims(report);
  const chains = traceChains(report);
  const platformRows = platformDifferences(report);
  const publicationStatus = String(report?.publication_status ?? report?.payload?.publication_status ?? '');
  const sourceType = String(report?.source_type ?? report?.payload?.source_type ?? '');
  const canShowGraphUpdate = Boolean(graphUpdate && sourceType !== 'pre_graph_update');
  const publishDisabled =
    isGenerating ||
    (!report && !graphUpdate) ||
    (Boolean(report) && (hasBlock || publicationStatus === 'published' || sourceType === 'pre_graph_update' || !onPublishReport));
  const buttonLabel = !report
    ? isGenerating
      ? '生成中'
      : '生成报告'
    : hasBlock
      ? '无法发布'
      : sourceType === 'pre_graph_update'
        ? '历史报告'
        : publicationStatus === 'published'
          ? '已发布'
          : isGenerating
            ? '处理中'
            : '发布报告';

  return (
    <div className="space-y-4">
      {reports.length ? (
        <section className={classNames(styles.surface, 'rounded-xl p-4')}>
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <h2 className="text-sm font-semibold text-[var(--text-primary)]">报告版本</h2>
              <p className="mt-1 text-xs text-[var(--text-secondary)]">Graph Update 报告和旧报告分开标记，旧报告只可查阅。</p>
            </div>
            <span className="text-xs text-[var(--text-tertiary)]">{reports.length} 个版本</span>
          </div>
          <div className="mt-3 flex gap-2 overflow-x-auto pb-1">
            {reports.map((item) => {
              const selected = (selectedReportId ?? report?.id) === item.id;
              return (
                <button
                  key={item.id}
                  type="button"
                  onClick={() => onSelectReport?.(item.id)}
                  className="min-w-[220px] rounded-xl border p-3 text-left transition"
                  style={{
                    borderColor: selected ? 'var(--brand-border)' : 'var(--border-subtle)',
                    background: selected ? 'var(--brand-bg)' : 'var(--bg-elevated)',
                  }}
                >
                  <div className="flex items-center justify-between gap-2">
                    <span className="text-xs font-semibold text-[var(--text-primary)]">v{item.version}</span>
                    <span className="text-[11px] text-[var(--text-tertiary)]">
                      {item.source_type === 'pre_graph_update' ? '旧报告' : item.publication_status}
                    </span>
                  </div>
                  <p className="mt-2 truncate text-sm font-medium text-[var(--text-primary)]">{item.title}</p>
                  <p className="mt-1 line-clamp-2 text-xs leading-5 text-[var(--text-secondary)]">{item.summary}</p>
                </button>
              );
            })}
          </div>
        </section>
      ) : null}

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
              disabled={publishDisabled}
              onClick={report ? onPublishReport : onGenerateReport}
              className="inline-flex h-10 items-center gap-2 rounded-lg px-3 text-sm font-semibold"
              style={{
                background: publishDisabled ? 'var(--bg-tertiary)' : 'var(--brand-primary)',
                color: publishDisabled ? 'var(--text-tertiary)' : 'var(--brand-contrast)',
              }}
            >
              {Boolean(report) && hasBlock ? <Lock className="h-4 w-4" /> : <FileCheck2 className="h-4 w-4" />}
              {buttonLabel}
            </button>
          </div>

        <div className="space-y-6">
          <section>
            <h2 className="text-base font-semibold text-[var(--text-primary)]">图谱变化摘要</h2>
            <p className="mt-2 text-sm leading-7 text-[var(--text-secondary)]">
              {canShowGraphUpdate && graphUpdate
                ? `本次更新从 ${graphUpdate.before_graph_version} 进入 ${graphUpdate.after_graph_version}，状态为 ${graphUpdate.status}。报告只解读这次图谱更新，不改写图谱事实。`
                : sourceType === 'pre_graph_update'
                  ? '这是旧报告版本，没有 Graph Update 追溯链，不能作为当前图谱事实源发布。'
                  : '生成 Graph Update 报告后，这里会显示版本变化、审阅状态和发布边界。'}
            </p>
          </section>

          <section className="grid gap-3 md:grid-cols-3">
            {[
              ['自动应用', String(canShowGraphUpdate ? graphUpdate?.summary?.auto_applied ?? '0' : '0'), '低风险计数和连接强度更新'],
              ['待审阅', String(canShowGraphUpdate ? graphUpdate?.summary?.needs_review ?? '0' : '0'), '新实体、风险、竞品候选'],
              ['阻断结论', String(canShowGraphUpdate ? graphUpdate?.summary?.blocked ?? '0' : '0'), '证据不足或规则阻断'],
            ].map(([label, value, detail]) => (
              <div key={label} className="rounded-xl border p-4" style={{ borderColor: 'var(--border-subtle)', background: 'var(--bg-elevated)' }}>
                <p className="text-xs text-[var(--text-tertiary)]">{label}</p>
                <p className="mt-2 text-2xl font-semibold text-[var(--text-primary)]">{value}</p>
                <p className="mt-2 text-xs leading-5 text-[var(--text-secondary)]">{detail}</p>
              </div>
            ))}
          </section>

          {terms.length ? (
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
          ) : null}

          {claims.length ? (
            <section>
              <h2 className="text-base font-semibold text-[var(--text-primary)]">关键结论</h2>
              <div className="mt-3 space-y-3">
                {claims.slice(0, 6).map((claim) => (
                  <div key={claim.id} className="rounded-xl border p-4" style={{ borderColor: 'var(--border-subtle)', background: 'var(--bg-elevated)' }}>
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <p className="text-sm font-semibold text-[var(--text-primary)]">{claim.label}</p>
                      <span className="text-xs text-[var(--text-tertiary)]">{claim.state}</span>
                    </div>
                    <p className="mt-2 text-xs leading-5 text-[var(--text-secondary)]">{claim.statement}</p>
                    {claim.platforms.length ? (
                      <p className="mt-2 text-xs text-[var(--text-tertiary)]">{claim.platforms.join(' / ')}</p>
                    ) : null}
                  </div>
                ))}
              </div>
            </section>
          ) : null}

          {platformRows.length ? (
            <section>
              <h2 className="text-base font-semibold text-[var(--text-primary)]">平台差异</h2>
              <div className="mt-3 grid gap-3 md:grid-cols-2 xl:grid-cols-4">
                {platformRows.map((row) => (
                  <div key={row.platform} className="rounded-xl border p-3" style={{ borderColor: 'var(--border-subtle)', background: 'var(--bg-elevated)' }}>
                    <p className="text-sm font-semibold text-[var(--text-primary)]">{row.platform}</p>
                    <p className="mt-2 text-xs text-[var(--text-secondary)]">{row.evidenceCount} 条证据 · {row.patchCount} 个补丁</p>
                    <p className="mt-1 text-xs text-[var(--text-tertiary)]">{row.questionCount} 个问题来源</p>
                  </div>
                ))}
              </div>
            </section>
          ) : null}
        </div>
      </article>

      <aside className="space-y-4">
        <section className={classNames(styles.surface, 'rounded-xl p-4')}>
          <div className="flex items-center gap-2">
            <ShieldAlert className="h-4 w-4 text-[var(--error)]" />
            <h2 className="text-sm font-semibold text-[var(--text-primary)]">报告校验</h2>
          </div>
          <div className="mt-3 space-y-3">
            {guardrails.length ? (
              guardrails.map((guardrail, index) => (
                <div
                  key={guardrailKey(guardrail, index)}
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
              ))
            ) : (
              <p className="text-xs leading-5 text-[var(--text-secondary)]">这个版本没有结构化校验记录；旧报告不会作为 Graph Update 事实源发布。</p>
            )}
          </div>
        </section>

        <section className={classNames(styles.surface, 'rounded-xl p-4')}>
          <div className="flex items-center gap-2">
            <Route className="h-4 w-4 text-[var(--brand-primary)]" />
            <h2 className="text-sm font-semibold text-[var(--text-primary)]">追溯链</h2>
          </div>
          <div className="mt-4 space-y-3">
            {chains.length ? (
              chains.slice(0, 3).map((chain) => (
                <div key={chain.id} className="rounded-xl border p-3" style={{ borderColor: 'var(--border-subtle)', background: 'var(--bg-elevated)' }}>
                  <p className="text-xs font-semibold text-[var(--text-primary)]">{chain.label}</p>
                  <div className="mt-3 space-y-3">
                    {chain.steps.map((step, index) => (
                      <div key={`${chain.id}-${step.type}-${index}`} className="relative flex gap-3">
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
                </div>
              ))
            ) : (
              <p className="text-xs leading-5 text-[var(--text-secondary)]">生成报告后显示结论到补丁、答案、问题和平台的追溯链。</p>
            )}
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
    </div>
  );
}
