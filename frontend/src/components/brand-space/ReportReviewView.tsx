import { AlertTriangle, Archive, CheckCircle2, Download, FileCheck2, Lock, Quote, ShieldAlert } from 'lucide-react';
import styles from './BrandSpace.module.css';
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
  onOpenAssets?: () => void;
  onOpenBoard?: () => void;
  isGenerating?: boolean;
  selectedReportId?: string | null;
}

type AnyRecord = Record<string, unknown>;

function classNames(...classes: Array<string | false | undefined>) {
  return classes.filter(Boolean).join(' ');
}

function asRecord(value: unknown): AnyRecord {
  return typeof value === 'object' && value !== null ? (value as AnyRecord) : {};
}

function asArray(value: unknown): AnyRecord[] {
  return Array.isArray(value)
    ? value.filter((item): item is AnyRecord => typeof item === 'object' && item !== null)
    : [];
}

function text(value: unknown, fallback = '') {
  return typeof value === 'string' && value.trim() ? value : fallback;
}

function numeric(value: unknown, fallback = 0) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
}

function percent(value: unknown) {
  const ratio = numeric(value);
  return `${Math.round(ratio * 1000) / 10}%`;
}

function payloadArray(report: BrandSpaceReport | null | undefined, key: string): AnyRecord[] {
  return asArray(report?.payload?.[key]);
}

function legacyClaims(report?: BrandSpaceReport | null): AnyRecord[] {
  return payloadArray(report, 'claims').map((item, index) => ({
    id: text(item.claim_id ?? item.patch_id, `legacy-claim-${index}`),
    title: text(item.label, '图谱结论'),
    body: text(item.statement),
    severity: text(item.state, '待解读'),
    data_points: [],
    keywords: Array.isArray(item.platforms) ? item.platforms.map(String) : [],
  }));
}

function legacyPlatformRows(report?: BrandSpaceReport | null) {
  return payloadArray(report, 'platform_differences').map((item) => ({
    platform: text(item.platform, '未记录平台'),
    answer_count: numeric(item.evidence_count),
    profile: `${numeric(item.patch_count)} 个图谱变化，覆盖 ${numeric(item.question_count)} 个问题。`,
    risk_context_rate: 0,
    active_mentions: 0,
    transformation_mentions: 0,
    quote: null,
  }));
}

function storyPayload(report?: BrandSpaceReport | null) {
  return asRecord(report?.payload?.storyline_report);
}

function downloadMarkdown(title: string, markdown: string) {
  if (!markdown || typeof window === 'undefined') return;
  const blob = new Blob([markdown], { type: 'text/markdown;charset=utf-8' });
  const url = window.URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = `${title.replace(/[\\/:*?"<>|]/g, '-')}.md`;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  window.URL.revokeObjectURL(url);
}

function guardrailKey(guardrail: ReportGuardrailResult, index: number) {
  return guardrail.id || guardrail.guardrailKey || guardrail.guardrail_key || `${guardrail.title}-${index}`;
}

function statusDotClass(severity: string) {
  if (severity === 'high') return 'bg-[var(--error)]';
  if (severity === 'medium') return 'bg-[var(--warning)]';
  return 'bg-[var(--brand-primary)]';
}

const publicationStatusLabels: Record<string, string> = {
  draft: '草稿',
  needs_review: '待审阅',
  publishable: '可发布',
  published: '已发布',
  pre_graph_update: '非图谱报告',
};

export function ReportReviewView({
  report,
  reports = [],
  graphUpdate,
  guardrails = [],
  onGenerateReport,
  onPublishReport,
  onSelectReport,
  onOpenAssets,
  onOpenBoard,
  isGenerating = false,
  selectedReportId,
}: ReportReviewViewProps) {
  const story = storyPayload(report);
  const sampleScope = asRecord(story.sample_scope ?? report?.payload?.sample_scope);
  const structuralJudgments = asArray(story.structural_judgments ?? report?.payload?.structural_judgments);
  const valuePillars = asArray(story.value_pillars ?? report?.payload?.value_pillars);
  const blindSpot = asRecord(story.blind_spot ?? report?.payload?.blind_spot);
  const platformProfiles = asArray(story.platform_profiles ?? report?.payload?.platform_profiles);
  const entityRanking = asArray(story.entity_ranking);
  const evidenceQuotes = asArray(story.evidence_quotes ?? report?.payload?.evidence_quotes);
  const actionPlan = asArray(story.action_plan ?? report?.payload?.action_plan);
  const reportMarkdown = text(story.markdown ?? report?.payload?.report_markdown);
  const hasStory = Boolean(story.title || structuralJudgments.length || valuePillars.length);
  const title = text(story.title, report?.title ?? '品牌 AI 认知图景');
  const subtitle = text(
    story.subtitle,
    report?.summary ??
      '生成报告后，这里会展示核心裁决、平台证据、价值支柱状态和下一轮验证动作。',
  );
  const summary = text(
    story.summary,
    report?.summary ?? '报告会从图谱和回答证据中提炼结构性判断，避免逐词填模板。',
  );
  const judgments = structuralJudgments.length ? structuralJudgments : legacyClaims(report);
  const platformRows = platformProfiles.length ? platformProfiles : legacyPlatformRows(report);
  const blockingGuardrails = guardrails.filter((guardrail) => guardrail.severity === 'block');
  const hasBlock = guardrails.some((guardrail) => guardrail.severity === 'block');
  const publicationStatus = text(report?.publication_status ?? report?.payload?.publication_status);
  const sourceType = text(report?.source_type ?? report?.payload?.source_type);
  const missingGraphUpdateForReport = !report && !graphUpdate;
  const metrics: Array<[string, string]> = [
    ['有效回答', String(sampleScope.answer_count ?? '-')],
    ['问题覆盖', String(sampleScope.question_count ?? '-')],
    ['平台覆盖', String(sampleScope.platform_count ?? '-')],
    ['主动提及率', sampleScope.active_mention_rate !== undefined ? percent(sampleScope.active_mention_rate) : '-'],
  ];
  const publishDisabled =
    isGenerating ||
    missingGraphUpdateForReport ||
    (Boolean(report) && (hasBlock || publicationStatus === 'published' || sourceType === 'pre_graph_update' || !onPublishReport));
  const buttonLabel = !report
    ? isGenerating
      ? '生成中'
      : missingGraphUpdateForReport
        ? '等待图谱更新'
        : '生成报告'
    : hasBlock
      ? '无法发布'
      : sourceType === 'pre_graph_update'
        ? '非图谱报告'
        : publicationStatus === 'published'
          ? '已发布'
          : isGenerating
            ? '处理中'
            : '发布报告';

  return (
    <div className="space-y-5">
      {reports.length ? (
        <section className={classNames(styles.surface, 'rounded-xl px-4 py-3')}>
          <div className="flex gap-2 overflow-x-auto pb-1">
            {reports.map((item) => {
              const selected = (selectedReportId ?? report?.id) === item.id;
              return (
                <button
                  key={item.id}
                  type="button"
                  onClick={() => onSelectReport?.(item.id)}
                  className="min-w-[220px] rounded-xl border px-3 py-2 text-left transition"
                  aria-pressed={selected}
                  aria-label={`查看报告版本 v${item.version}：${item.title}`}
                  style={{
                    borderColor: selected ? 'var(--brand-border)' : 'var(--border-subtle)',
                    background: selected ? 'var(--brand-bg)' : 'var(--bg-elevated)',
                  }}
                >
                  <div className="flex items-center justify-between gap-2">
                    <span className="text-xs font-semibold text-[var(--text-primary)]">v{item.version}</span>
                    <span className="text-[11px] text-[var(--text-tertiary)]">
                      {publicationStatusLabels[item.publication_status] ?? item.publication_status}
                    </span>
                  </div>
                  <p className="mt-1 truncate text-sm font-medium text-[var(--text-primary)]">{item.title}</p>
                </button>
              );
            })}
          </div>
        </section>
      ) : null}

      <article className={classNames(styles.reportReader, styles.surface)}>
        <header className={styles.reportHero}>
          <div>
            <p className="text-xs font-semibold uppercase text-[var(--brand-text)]">图谱更新解读报告</p>
            <h1 className="mt-3 max-w-4xl text-[28px] font-semibold leading-tight text-[var(--text-primary)] md:text-[34px]">
              {title}
            </h1>
            <p className="mt-3 max-w-4xl text-[15px] leading-7 text-[var(--text-secondary)]">{subtitle}</p>
            {missingGraphUpdateForReport ? (
              <p className="mt-2 text-sm font-medium text-[var(--warning)]">
                需要先完成一次图谱更新，才能生成图谱解读报告。
              </p>
            ) : null}
            {blockingGuardrails.length ? (
              <div
                className="mt-4 rounded-xl border p-3"
                style={{
                  borderColor: 'color-mix(in srgb, var(--error) 42%, var(--border-subtle) 58%)',
                  background: 'color-mix(in srgb, var(--error) 8%, var(--bg-elevated) 92%)',
                }}
              >
                <div className="flex items-center gap-2 text-sm font-semibold text-[var(--error)]">
                  <Lock className="h-4 w-4" />
                  <span>发布护栏阻断</span>
                </div>
                <ul className="mt-2 space-y-1 text-sm leading-6 text-[var(--text-secondary)]">
                  {blockingGuardrails.slice(0, 3).map((guardrail, index) => (
                    <li key={guardrailKey(guardrail, index)}>
                      {guardrail.title}：{guardrail.message}
                    </li>
                  ))}
                </ul>
              </div>
            ) : null}
          </div>
          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              disabled={!reportMarkdown}
              onClick={() => downloadMarkdown(title, reportMarkdown)}
              className="inline-flex h-10 items-center gap-2 rounded-lg border px-3 text-sm font-semibold text-[var(--text-secondary)] disabled:opacity-45"
              style={{ borderColor: 'var(--border-subtle)', background: 'var(--bg-elevated)' }}
            >
              <Download className="h-4 w-4" />
              导出 Markdown
            </button>
            <button
              type="button"
              disabled={!onOpenAssets}
              onClick={onOpenAssets}
              className="inline-flex h-10 items-center gap-2 rounded-lg border px-3 text-sm font-semibold text-[var(--text-secondary)] disabled:opacity-45"
              style={{ borderColor: 'var(--border-subtle)', background: 'var(--bg-elevated)' }}
            >
              <Archive className="h-4 w-4" />
              查看相关资产
            </button>
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
        </header>

        {missingGraphUpdateForReport ? (
          <section className={styles.verdictBlock}>
            <p className="text-xs font-semibold uppercase text-[var(--text-tertiary)]">等待图谱更新</p>
            <p className="mt-3 max-w-3xl text-[20px] font-semibold leading-9 text-[var(--text-primary)]">
              当前运行还没有可解读的图谱更新，报告不会复用其他运行或脚手架数据。
            </p>
            <p className="mt-3 max-w-3xl text-sm leading-7 text-[var(--text-secondary)]">
              完成一次画布运行并生成图谱更新后，这里才会展示报告版本、发布护栏、证据链和行动建议。
            </p>
            {onOpenBoard ? (
              <button
                type="button"
                onClick={onOpenBoard}
                className="mt-5 inline-flex h-10 items-center rounded-lg bg-[var(--brand-primary)] px-4 text-sm font-semibold text-[var(--brand-contrast)]"
              >
                去画布运行
              </button>
            ) : null}
          </section>
        ) : null}

        <div className={missingGraphUpdateForReport ? 'hidden' : undefined}>
        <section className={styles.verdictBlock}>
          <p className="text-xs font-semibold uppercase text-[var(--text-tertiary)]">核心判断</p>
          <p className="mt-3 max-w-4xl text-[20px] font-semibold leading-9 text-[var(--text-primary)]">
            {summary}
          </p>
          <div className="mt-6 grid gap-3 md:grid-cols-4">
            {metrics.map(([label, value]) => (
              <div key={label} className={styles.reportMetric}>
                <p>{label}</p>
                <strong>{value}</strong>
              </div>
            ))}
          </div>
        </section>

        <section className={styles.reportSection}>
          <div className={styles.sectionIntro}>
            <span>01</span>
            <div>
              <h2>这一轮数据先说明什么</h2>
              <p>先看结构性判断，再进入平台原文和图谱解释。</p>
            </div>
          </div>
          <div className="space-y-4">
            {judgments.slice(0, 5).map((judgment, index) => (
              <div key={text(judgment.id, `${judgment.title}-${index}`)} className={styles.judgmentRow}>
                <span className={classNames('mt-2 h-2.5 w-2.5 rounded-full', statusDotClass(text(judgment.severity)))} />
                <div>
                  <h3>{text(judgment.title, '结构性判断')}</h3>
                  <p>{text(judgment.body)}</p>
                  {asArray(judgment.data_points).length ? (
                    <div className="mt-3 flex flex-wrap gap-2">
                      {asArray(judgment.data_points).map((point, pointIndex) => (
                        <span key={`${text(point.label)}-${pointIndex}`} className={styles.dataChip}>
                          {text(point.label)}：{String(point.value ?? '-')}
                        </span>
                      ))}
                    </div>
                  ) : null}
                </div>
              </div>
            ))}
          </div>
        </section>

        <section className={styles.reportSection}>
          <div className={styles.sectionIntro}>
            <span>02</span>
            <div>
              <h2>AI 档案全景</h2>
              <p>每个平台给品牌贴的标签不同，报告需要把这种差异讲清楚。</p>
            </div>
          </div>
          <div className="grid gap-4 lg:grid-cols-2">
            {platformRows.slice(0, 4).map((platform, index) => {
              const quote = asRecord(platform.quote);
              return (
                <div key={`${text(platform.platform, 'platform')}-${index}`} className={styles.platformProfile}>
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <h3>{text(platform.platform, '未记录平台')}</h3>
                      <p>{text(platform.profile, '平台画像待生成。')}</p>
                    </div>
                    <strong>{numeric(platform.answer_count)}</strong>
                  </div>
                  <div className="mt-4 grid grid-cols-3 gap-2 text-xs">
                    <span>风险语境 {percent(platform.risk_context_rate)}</span>
                    <span>主动提及 {numeric(platform.active_mentions)}</span>
                    <span>转型叙事 {numeric(platform.transformation_mentions)}</span>
                  </div>
                  {quote.excerpt ? (
                    <blockquote className={styles.quoteBlock}>
                      <Quote className="h-4 w-4" />
                      <p>{text(quote.excerpt)}</p>
                    </blockquote>
                  ) : null}
                </div>
              );
            })}
          </div>
          {entityRanking.length ? (
            <div className={styles.entityTable}>
              {entityRanking.slice(0, 8).map((entity, index) => (
                <div key={`${text(entity.label)}-${index}`}>
                  <span>{index + 1}</span>
                  <strong>{text(entity.label, '未命名实体')}</strong>
                  <em>{numeric(entity.mention_count)} 次 / {numeric(entity.platform_count)} 平台</em>
                </div>
              ))}
            </div>
          ) : null}
        </section>

        <section className={styles.reportSection}>
          <div className={styles.sectionIntro}>
            <span>03</span>
            <div>
              <h2>{hasStory ? '价值支柱状态' : '图谱结论状态'}</h2>
              <p>每一段只讲一个差距故事，避免逐词重复。</p>
            </div>
          </div>
          <div className="space-y-6">
            {valuePillars.length ? (
              valuePillars.map((pillar, index) => (
                <section key={`${text(pillar.name)}-${index}`} className={styles.pillarSection}>
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div>
                      <p className="text-xs font-semibold text-[var(--brand-text)]">{text(pillar.gap_label)}</p>
                      <h3>{text(pillar.name)}｜{text(pillar.headline)}</h3>
                    </div>
                    <div className="flex gap-2">
                      <span className={styles.dataChip}>可见度 {percent(pillar.visibility)}</span>
                      <span className={styles.dataChip}>可信度 {percent(pillar.credibility)}</span>
                    </div>
                  </div>
                  <p className="mt-3 text-[15px] leading-8 text-[var(--text-secondary)]">{text(pillar.reading)}</p>
                  <p className="mt-2 text-[14px] leading-7 text-[var(--text-tertiary)]">目标：{text(pillar.target)}</p>
                  <div className="mt-4 grid gap-3 md:grid-cols-2">
                    {asArray(pillar.quotes).slice(0, 2).map((quote, quoteIndex) => (
                      <blockquote key={`${text(quote.platform)}-${quoteIndex}`} className={styles.quoteBlock}>
                        <Quote className="h-4 w-4" />
                        <div>
                          <strong>{text(quote.platform, '未记录平台')}</strong>
                          <p>{text(quote.excerpt)}</p>
                        </div>
                      </blockquote>
                    ))}
                  </div>
                </section>
              ))
            ) : (
              <p className="text-sm leading-7 text-[var(--text-secondary)]">
                当前报告没有新的价值支柱结构。请从本次图谱更新重新生成图谱解读报告。
              </p>
            )}
          </div>
        </section>

        <section className={styles.reportSection}>
          <div className={styles.sectionIntro}>
            <span>04</span>
            <div>
              <h2>AI 盲区</h2>
              <p>品牌是否会被主动推荐，要看不含品牌名的问题。</p>
            </div>
          </div>
          <div className={styles.blindSpotPanel}>
            <div>
              <strong>{blindSpot.active_mention_rate !== undefined ? percent(blindSpot.active_mention_rate) : '-'}</strong>
              <p>{text(blindSpot.diagnosis, '主动提及分析待生成。')}</p>
            </div>
            <div className="space-y-3">
              {asArray(blindSpot.examples).slice(0, 3).map((example, index) => (
                <div key={`${text(example.platform)}-${index}`} className={styles.missedQuestion}>
                  <p>{text(example.question)}</p>
                  <span>{text(example.platform)}：{text(example.excerpt)}</span>
                </div>
              ))}
            </div>
          </div>
        </section>

        <section className={styles.reportSection}>
          <div className={styles.sectionIntro}>
            <span>05</span>
            <div>
              <h2>从数据到行动</h2>
              <p>行动数量控制在三件以内，并给出下一轮验证口径。</p>
            </div>
          </div>
          <div className="grid gap-4 md:grid-cols-3">
            {actionPlan.length ? (
              actionPlan.map((action, index) => (
                <div key={`${text(action.title)}-${index}`} className={styles.actionCard}>
                  <span>{index + 1}</span>
                  <h3>{text(action.title)}</h3>
                  <p>{text(action.why)}</p>
                  <strong>做法</strong>
                  <p>{text(action.do)}</p>
                  <strong>验证</strong>
                  <p>{text(action.validation)}</p>
                </div>
              ))
            ) : (
              <p className="text-sm leading-7 text-[var(--text-secondary)]">生成报告后显示本轮最优先的 3 个动作。</p>
            )}
          </div>
        </section>

        {evidenceQuotes.length ? (
          <section className={styles.reportSection}>
            <div className={styles.sectionIntro}>
              <span>附</span>
              <div>
                <h2>证据样本</h2>
                <p>保留平台原文，让判断可以回到回答本身。</p>
              </div>
            </div>
            <div className="grid gap-3 md:grid-cols-2">
              {evidenceQuotes.slice(0, 6).map((quote, index) => (
                <blockquote key={`${text(quote.platform)}-${index}`} className={styles.quoteBlock}>
                  <Quote className="h-4 w-4" />
                  <div>
                    <strong>{text(quote.platform, '未记录平台')}</strong>
                    <p>{text(quote.excerpt)}</p>
                  </div>
                </blockquote>
              ))}
            </div>
          </section>
        ) : null}

        <section className={styles.reportSection}>
          <div className="flex items-center gap-2">
            <ShieldAlert className="h-4 w-4 text-[var(--error)]" />
            <h2 className="text-base font-semibold text-[var(--text-primary)]">报告校验</h2>
          </div>
          <div className="mt-3 grid gap-3 md:grid-cols-2">
            {guardrails.length ? (
              guardrails.map((guardrail, index) => (
                <div
                  key={guardrailKey(guardrail, index)}
                  className={classNames(
                    guardrail.severity === 'block' && styles.guardrailBlock,
                    'rounded-xl border p-3',
                  )}
                  style={{
                    borderColor: guardrail.severity === 'block' ? undefined : 'var(--border-subtle)',
                    background: guardrail.severity === 'block' ? undefined : 'var(--bg-elevated)',
                  }}
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
              <p className="text-sm leading-7 text-[var(--text-secondary)]">这个版本没有结构化校验记录。</p>
            )}
          </div>
        </section>
        </div>
      </article>
    </div>
  );
}
