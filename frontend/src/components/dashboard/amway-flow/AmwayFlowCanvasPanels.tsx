'use client';

import { useMemo } from 'react';
import { Play, RotateCcw, Workflow, X } from 'lucide-react';
import type { BrandIntelligenceRun } from '@/types/intelligenceRun';
import type { AmwayQuestionHistorySet } from '@/types/amwayChina';
import type { OntologyAssociationCircleProjection } from '@/types/ontology';
import {
  ALL_PLATFORM_IDS,
  ANALYSIS_DIMENSION_META,
  CUSTOM_NODE_META,
  DEFAULT_ANALYSIS_DIMENSIONS,
  DEFAULT_CONTENT_PROMPT_TEMPLATE,
  NODE_DEFINITIONS,
  PLATFORM_META,
  STATUS_TEXT,
} from './constants';
import type {
  AmwayFlowNode,
  FlowAnalysisDimension,
  FlowAnalysisResult,
  FlowArtifactKey,
  FlowContentResult,
  FlowTopologyCustomNode,
} from './types';

export function nodeLabel(nodeId: string): string {
  if (nodeId.startsWith('platform-')) {
    const platform = PLATFORM_META.find((item) => `platform-${item.id}` === nodeId);
    return platform?.label || nodeId;
  }
  return NODE_DEFINITIONS.find((item) => item.id === nodeId)?.label || nodeId;
}

export function artifactTitle(artifact: FlowArtifactKey): string {
  switch (artifact) {
    case 'questions':
      return '问题列表';
    case 'answers':
      return '答案原文';
    case 'entities':
      return '抽取实体';
    case 'report':
      return '报告原文';
    case 'lexicon':
      return '实体词库';
    case 'analysisResult':
      return '分析结论';
    case 'contentDraft':
      return '内容草稿';
    default:
      return '';
  }
}

export function questionTextOf(record: Record<string, unknown>): string {
  return String(record.question_text || record.question || record.text || '').trim();
}

export function CustomNodeDetail({
  node,
  customNode,
  running = false,
  error = null,
  onUpdateConfig,
  onDelete,
  onRunAnalysis,
  onRunAnalysisBranch,
  onRunContent,
  onOpenArtifact,
}: {
  node: AmwayFlowNode;
  customNode: FlowTopologyCustomNode;
  running?: boolean;
  error?: string | null;
  onUpdateConfig: (nodeId: string, patch: Record<string, unknown>) => void;
  onDelete: (nodeId: string) => void;
  onRunAnalysis: (nodeId: string) => void;
  onRunAnalysisBranch: (nodeId: string) => void;
  onRunContent: (nodeId: string) => void;
  onOpenArtifact: (key: FlowArtifactKey) => void;
}) {
  const isAnalysis = customNode.type === 'analysis';
  const result = customNode.config.result as FlowAnalysisResult | FlowContentResult | undefined;
  const analysisResult = isAnalysis ? (result as FlowAnalysisResult | undefined) : undefined;
  const contentResult = !isAnalysis ? (result as FlowContentResult | undefined) : undefined;
  const dimensions = (Array.isArray(customNode.config.dimensions)
    ? (customNode.config.dimensions as string[]).filter((item): item is FlowAnalysisDimension =>
        item === 'platform' || item === 'entities' || item === 'risk')
    : DEFAULT_ANALYSIS_DIMENSIONS);
  const template = String(customNode.config.promptTemplate || DEFAULT_CONTENT_PROMPT_TEMPLATE);
  const nodeLabel = node.data?.label || customNode.config.label || CUSTOM_NODE_META[customNode.type].label;

  return (
    <div className="space-y-5">
      <p className="text-sm leading-6 text-[var(--text-secondary)]">
        {customNode.type === 'analysis'
          ? CUSTOM_NODE_META.analysis.description
          : CUSTOM_NODE_META.content.description}
        {nodeLabel ? `（${String(nodeLabel)}）` : ''}
      </p>

      <div>
        <label className="text-xs font-medium text-[var(--text-tertiary)]" htmlFor="custom-node-label">
          节点名称
        </label>
        <input
          id="custom-node-label"
          type="text"
          value={String(customNode.config.label || '')}
          placeholder={CUSTOM_NODE_META[customNode.type].label}
          onChange={(event) => onUpdateConfig(customNode.id, { label: event.target.value })}
          className="mt-1.5 h-9 w-full rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-primary)] px-3 text-sm text-[var(--text-primary)] outline-none transition focus:border-[var(--brand-primary)]"
        />
      </div>

      {isAnalysis ? (
        <div>
          <div className="text-xs font-medium text-[var(--text-tertiary)]">分析维度</div>
          <div className="mt-2 space-y-2">
            {(Object.keys(ANALYSIS_DIMENSION_META) as FlowAnalysisDimension[]).map((dimension) => {
              const meta = ANALYSIS_DIMENSION_META[dimension];
              const checked = dimensions.includes(dimension);
              return (
                <label
                  key={dimension}
                  className="flex cursor-pointer items-start gap-2.5 rounded-lg border border-[var(--border-subtle)] px-3 py-2 transition hover:border-[var(--border-strong)]"
                >
                  <input
                    type="checkbox"
                    checked={checked}
                    onChange={() => {
                      const next = checked
                        ? dimensions.filter((item) => item !== dimension)
                        : [...dimensions, dimension];
                      onUpdateConfig(customNode.id, { dimensions: next });
                    }}
                    className="mt-0.5 accent-[var(--brand-primary)]"
                  />
                  <span>
                    <span className="block text-sm font-medium text-[var(--text-primary)]">{meta.label}</span>
                    <span className="block text-xs text-[var(--text-tertiary)]">{meta.hint}</span>
                  </span>
                </label>
              );
            })}
          </div>
          <label className="mt-3 block text-xs font-medium text-[var(--text-tertiary)]" htmlFor="analysis-prompt">
            二级解读 Prompt（可选）
          </label>
          <textarea
            id="analysis-prompt"
            value={String(customNode.config.prompt || '')}
            onChange={(event) => onUpdateConfig(customNode.id, { prompt: event.target.value })}
            rows={3}
            placeholder="例如：重点对比竞品与风险信号，给出三条可执行建议"
            className="mt-1.5 w-full rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-primary)] px-3 py-2 text-[13px] leading-5 text-[var(--text-primary)] outline-none transition focus:border-[var(--brand-primary)]"
          />
          <div className="mt-3 flex flex-wrap gap-2">
            <button
              type="button"
              disabled={running}
              onClick={() => onRunAnalysis(customNode.id)}
              className="inline-flex h-9 items-center gap-1.5 rounded-lg border border-[var(--brand-primary)] bg-[var(--brand-primary)] px-3.5 text-sm font-semibold text-[var(--brand-contrast)] transition hover:bg-[var(--brand-hover)] disabled:opacity-60"
            >
              <Play size={13} fill="currentColor" aria-hidden />
              {running ? '运行中…' : '仅运行此节点'}
            </button>
            <button
              type="button"
              disabled={running}
              onClick={() => onRunAnalysisBranch(customNode.id)}
              className="inline-flex h-9 items-center gap-1.5 rounded-lg border border-[var(--border-strong)] bg-[var(--bg-primary)] px-3.5 text-sm font-medium text-[var(--text-primary)] transition hover:bg-[var(--bg-secondary)] disabled:opacity-60"
            >
              <Workflow size={13} aria-hidden />
              运行此分支
            </button>
          </div>
          <p className="mt-1.5 text-xs text-[var(--text-tertiary)]">
            「运行此分支」会连同下游已接线的内容创作节点一起执行（仍不重跑采集/抽取/报告）。
          </p>
          {analysisResult ? (
            <button
              type="button"
              onClick={() => onOpenArtifact('analysisResult')}
              className="mt-2 block text-xs font-medium text-[var(--brand-primary)] hover:underline"
            >
              查看分析结论（{new Date(analysisResult.generatedAt).toLocaleString('zh-CN', { month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit' })}
              {analysisResult.mode ? ` · ${analysisResult.mode === 'llm' ? 'LLM' : '确定性'}` : ''}）
            </button>
          ) : null}
        </div>
      ) : (
        <div>
          <label className="text-xs font-medium text-[var(--text-tertiary)]" htmlFor="custom-node-template">
            Prompt 模板
          </label>
          <textarea
            id="custom-node-template"
            value={template}
            onChange={(event) => onUpdateConfig(customNode.id, { promptTemplate: event.target.value })}
            rows={7}
            className="mt-1.5 w-full rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-primary)] px-3 py-2 text-[13px] leading-5 text-[var(--text-primary)] outline-none transition focus:border-[var(--brand-primary)]"
          />
          <p className="mt-1.5 text-xs leading-5 text-[var(--text-tertiary)]">
            可用变量：{'{{centerTerm}}'}（品牌）、{'{{entities}}'}（实体词库）、{'{{analysis}}'}（分析结论）。
          </p>
          <button
            type="button"
            disabled={running}
            onClick={() => onRunContent(customNode.id)}
            className="mt-3 inline-flex h-9 items-center gap-1.5 rounded-lg border border-[var(--brand-primary)] bg-[var(--brand-primary)] px-3.5 text-sm font-semibold text-[var(--brand-contrast)] transition hover:bg-[var(--brand-hover)] disabled:opacity-60"
          >
            <Play size={13} fill="currentColor" aria-hidden />
            {running ? '生成中…' : '生成草稿'}
          </button>
          {contentResult?.draft ? (
            <button
              type="button"
              onClick={() => onOpenArtifact('contentDraft')}
              className="mt-2 block text-xs font-medium text-[var(--brand-primary)] hover:underline"
            >
              查看内容草稿（{new Date(contentResult.generatedAt).toLocaleString('zh-CN', { month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit' })}
              {contentResult.mode ? ` · ${contentResult.mode === 'llm' ? 'LLM' : '模板'}` : ''}）
            </button>
          ) : null}
        </div>
      )}

      {error ? (
        <p className="rounded-lg border border-[rgba(220,38,38,0.25)] bg-[rgba(220,38,38,0.06)] px-3 py-2 text-xs leading-5 text-[var(--error)]">
          {error}
        </p>
      ) : null}

      <div className="border-t border-[var(--border-subtle)] pt-4">
        <button
          type="button"
          onClick={() => onDelete(customNode.id)}
          className="inline-flex h-9 items-center gap-1.5 rounded-lg border border-[var(--error)] px-3.5 text-sm font-medium text-[var(--error)] transition hover:bg-[rgba(220,38,38,0.06)]"
        >
          <X size={13} aria-hidden />
          删除节点
        </button>
        <p className="mt-1.5 text-xs text-[var(--text-tertiary)]">删除后与其相连的自定义连线会一并移除。</p>
      </div>
    </div>
  );
}

export function AnalysisResultArtifact({ result }: { result: FlowAnalysisResult }) {
  const modeLabel = result.mode === 'llm' ? 'LLM 二级解读' : '确定性分析';
  return (
    <div className="space-y-4">
      <p className="text-xs text-[var(--text-tertiary)]">
        生成于 {new Date(result.generatedAt).toLocaleString('zh-CN')}
        ，模式：{modeLabel}
        {result.fallback_reason ? `（降级：${result.fallback_reason}）` : ''}
      </p>
      {result.summary ? (
        <p className="rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-4 py-3 text-[13px] leading-6 text-[var(--text-primary)]">
          {result.summary}
        </p>
      ) : null}
      {result.cards.map((card) => (
        <section key={card.title} className="rounded-xl border border-[var(--border-subtle)] px-4 py-3">
          <h3 className="text-sm font-semibold text-[var(--text-primary)]">{card.title}</h3>
          <ul className="mt-2 space-y-1.5">
            {card.lines.map((line, index) => (
              <li key={index} className="text-[13px] leading-5 text-[var(--text-secondary)]">
                {line}
              </li>
            ))}
          </ul>
        </section>
      ))}
    </div>
  );
}

export function ContentDraftArtifact({
  result,
  template,
}: {
  result?: FlowContentResult;
  template: string;
}) {
  const draft = String(result?.draft || '').trim();
  const modeLabel = result?.mode === 'llm' ? 'LLM 生成' : '模板回填';
  return (
    <div className="space-y-4">
      <p className="text-xs text-[var(--text-tertiary)]">
        {result?.generatedAt
          ? `生成于 ${new Date(result.generatedAt).toLocaleString('zh-CN')}，模式：${modeLabel}`
          : '尚未生成草稿'}
        {result?.fallback_reason ? `（降级：${result.fallback_reason}）` : ''}
      </p>
      <pre className="whitespace-pre-wrap rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-4 py-3 text-[13px] leading-6 text-[var(--text-primary)]">
        {draft || '（空草稿）'}
      </pre>
      {result?.mode === 'template' || !draft ? (
        <details className="rounded-lg border border-[var(--border-subtle)] px-3 py-2">
          <summary className="cursor-pointer text-xs font-medium text-[var(--text-secondary)]">查看 Prompt 模板</summary>
          <pre className="mt-2 whitespace-pre-wrap text-[12px] leading-5 text-[var(--text-tertiary)]">{template}</pre>
        </details>
      ) : null}
    </div>
  );
}

export function FlowNodeDetail({
  node,
  activeRun,
  enabledPlatforms,
  plannedPlatformIds,
  questionSets,
  running,
  branchRunning = false,
  branchError = null,
  onRetry,
  onOpenRunSettings,
  onOpenArtifact,
  onOpenCircle,
  onRunDownstreamBranch,
}: {
  node: AmwayFlowNode;
  activeRun?: BrandIntelligenceRun | null;
  enabledPlatforms: string[];
  /** From execution plan (topology/run lock); preferred over switches for run display (F2). */
  plannedPlatformIds?: string[];
  questionSets: AmwayQuestionHistorySet[];
  running: boolean;
  branchRunning?: boolean;
  branchError?: string | null;
  onRetry: () => void;
  onOpenRunSettings: () => void;
  onOpenArtifact: (key: FlowArtifactKey) => void;
  onOpenCircle: () => void;
  onRunDownstreamBranch?: () => void;
}) {
  const inputScope = (activeRun?.input_scope || {}) as Record<string, unknown>;
  const boundSetId = typeof inputScope.uploaded_question_set_id === 'string' ? inputScope.uploaded_question_set_id : null;
  const boundSet = boundSetId ? questionSets.find((item) => item.id === boundSetId) || null : null;
  const boundSource = typeof inputScope.uploaded_question_source === 'string' ? inputScope.uploaded_question_source : null;
  const fetchModeLabel = inputScope.fetch_mode === 'fast' ? 'API 采集' : '浏览器采集';
  const previewQuestions = (boundSet?.questions || []).slice(0, 3);

  return (
    <div className="space-y-4">
      <p className="text-sm leading-6 text-[var(--text-secondary)]">{node.data.description}</p>

      {onRunDownstreamBranch ? (
        <section className="rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-3.5 py-3">
          <div className="text-xs font-medium text-[var(--text-tertiary)]">局部运行</div>
          <p className="mt-1 text-xs leading-5 text-[var(--text-secondary)]">
            边界：只重跑画布上的自定义节点（数据分析 / 内容创作），不重跑答案采集、实体抽取、图谱构建或报告生成内核。
          </p>
          <button
            type="button"
            disabled={branchRunning || running}
            onClick={onRunDownstreamBranch}
            className="mt-3 inline-flex h-9 items-center gap-1.5 rounded-lg border border-[var(--brand-primary)] bg-[var(--brand-primary)] px-3.5 text-sm font-semibold text-[var(--brand-contrast)] transition hover:bg-[var(--brand-hover)] disabled:opacity-60"
          >
            <Workflow size={13} aria-hidden />
            {branchRunning ? '分支运行中…' : '运行下游自定义节点'}
          </button>
          {branchError ? (
            <p className="mt-2 text-xs leading-5 text-[var(--error)]">{branchError}</p>
          ) : null}
        </section>
      ) : null}

      {node.id === 'question-set' ? (
        <section className="rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-3.5 py-3">
          <div className="text-xs font-medium text-[var(--text-tertiary)]">当前绑定</div>
          <div className="mt-1 text-sm font-semibold text-[var(--text-primary)]">
            {boundSet
              ? `${boundSet.title}（${boundSet.question_count} 题）`
              : boundSource
                ? `${boundSource}${typeof inputScope.uploaded_question_count === 'number' ? `（${inputScope.uploaded_question_count} 题）` : ''}`
                : '系统默认问题集'}
          </div>
          {previewQuestions.length ? (
            <ol className="mt-2 space-y-1 text-xs leading-5 text-[var(--text-secondary)]">
              {previewQuestions.map((question, index) => (
                <li key={index} className="truncate">
                  <span className="mr-1.5 tabular-nums text-[var(--text-tertiary)]">{index + 1}.</span>
                  {questionTextOf(question) || '（未命名问题）'}
                </li>
              ))}
            </ol>
          ) : null}
          <button
            type="button"
            onClick={onOpenRunSettings}
            className="mt-3 inline-flex h-9 items-center rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-primary)] px-3 text-xs font-medium text-[var(--brand-primary)] transition hover:border-[var(--brand-primary)]"
          >
            更换问题集
          </button>
        </section>
      ) : null}

      {node.id === 'fetch' ? (
        <section className="rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-3.5 py-3">
          <div className="text-xs font-medium text-[var(--text-tertiary)]">采集配置</div>
          <div className="mt-1 text-sm font-semibold text-[var(--text-primary)]">{fetchModeLabel}</div>
          <div className="mt-1 text-xs leading-5 text-[var(--text-secondary)]">
            {(() => {
              const planned = plannedPlatformIds && plannedPlatformIds.length >= 0
                ? plannedPlatformIds
                : null;
              const activeIds = planned && planned.length
                ? planned
                : enabledPlatforms;
              const skippedIds = ALL_PLATFORM_IDS.filter((id) => !activeIds.includes(id));
              const label = planned
                ? `计划平台：${activeIds.length}/${ALL_PLATFORM_IDS.length}`
                : `平台通道：${activeIds.length}/${ALL_PLATFORM_IDS.length} 启用`;
              const skipNote = skippedIds.length
                ? `（${planned ? '计划跳过' : '已停用'} ${skippedIds.map((id) => PLATFORM_META.find((item) => item.id === id)?.label || id).join('、')}）`
                : '';
              return `${label}${skipNote}`;
            })()}
          </div>
          <button
            type="button"
            onClick={onOpenRunSettings}
            className="mt-3 inline-flex h-9 items-center rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-primary)] px-3 text-xs font-medium text-[var(--brand-primary)] transition hover:border-[var(--brand-primary)]"
          >
            调整采集方式
          </button>
        </section>
      ) : null}

      {node.id === 'lexicon' ? (
        <button
          type="button"
          onClick={onOpenCircle}
          className="inline-flex h-9 items-center rounded-lg border border-[var(--border-subtle)] px-3 text-xs font-medium text-[var(--brand-primary)] hover:bg-[var(--brand-bg)]"
        >
          在品牌圈层页管理词库
        </button>
      ) : null}

      {node.data.outputs.length ? (
        <div>
          <div className="text-xs font-medium text-[var(--text-tertiary)]">节点产出</div>
          <div className="mt-2 space-y-1.5">
            {node.data.outputs.map((output) => (
              <button
                key={output.key}
                type="button"
                disabled={output.disabled}
                onClick={() => onOpenArtifact(output.key)}
                className="flex w-full items-center justify-between rounded-lg border border-[var(--border-subtle)] px-3 py-2 text-left text-sm text-[var(--text-primary)] transition hover:border-[var(--brand-primary)] disabled:cursor-not-allowed disabled:opacity-40"
              >
                <span>{output.label}</span>
                {typeof output.count === 'number' && output.count > 0 ? (
                  <span className="text-xs tabular-nums text-[var(--text-tertiary)]">{output.count}</span>
                ) : null}
              </button>
            ))}
          </div>
        </div>
      ) : null}

      {node.data.status === 'failed' && !running ? (
        <button
          type="button"
          onClick={onRetry}
          className="inline-flex h-10 w-full items-center justify-center gap-1.5 rounded-lg border border-[var(--brand-primary)] bg-[var(--brand-primary)] px-4 text-sm font-semibold text-[var(--brand-contrast)] transition hover:bg-[var(--brand-hover)]"
        >
          <RotateCcw size={14} aria-hidden />
          重新运行
        </button>
      ) : null}
    </div>
  );
}

export function ArtifactEmpty({ text }: { text: string }) {
  return <div className="py-10 text-center text-sm text-[var(--text-tertiary)]">{text}</div>;
}

export function QuestionsArtifact({
  questions,
}: {
  questions: OntologyAssociationCircleProjection['question_bank'];
}) {
  const list = (questions || []).slice(0, 120);
  if (!list.length) {
    return <ArtifactEmpty text="本轮问题列表会在运行后显示在这里。" />;
  }
  return (
    <ol className="space-y-2">
      {list.map((question, index) => (
        <li
          key={question.id || index}
          className="rounded-lg border border-[var(--border-subtle)] px-3 py-2 text-sm leading-6 text-[var(--text-primary)]"
        >
          <span className="mr-2 text-xs tabular-nums text-[var(--text-tertiary)]">{index + 1}.</span>
          {question.question_text || question.question || question.text || '（未命名问题）'}
        </li>
      ))}
    </ol>
  );
}

export function AnswersArtifact({
  appendix,
  fallback,
}: {
  appendix: OntologyAssociationCircleProjection['source_appendix'];
  fallback: OntologyAssociationCircleProjection['evidence_samples'];
}) {
  const groups = useMemo(() => {
    const byPlatform = new Map<string, Array<{ question: string; excerpt: string }>>();
    const push = (platform: unknown, question: unknown, excerpt: unknown) => {
      const platformLabel = String(platform || '未知平台');
      const text = String(excerpt || '').trim();
      if (!text) return;
      const list = byPlatform.get(platformLabel) || [];
      if (list.length < 40) {
        list.push({ question: String(question || '').trim(), excerpt: text });
      }
      byPlatform.set(platformLabel, list);
    };
    (appendix || []).forEach((item) => push(item.platform, item.question, item.answer_excerpt));
    if (!byPlatform.size) {
      (fallback || []).forEach((item) => push(item.platform, item.question, item.answer_excerpt));
    }
    return Array.from(byPlatform.entries());
  }, [appendix, fallback]);

  if (!groups.length) {
    return <ArtifactEmpty text="答案原文会在采集完成后显示在这里。" />;
  }
  return (
    <div className="space-y-5">
      {groups.map(([platform, items]) => (
        <section key={platform}>
          <h3 className="text-xs font-semibold text-[var(--text-tertiary)]">
            {platform} · {items.length} 条
          </h3>
          <div className="mt-2 space-y-2">
            {items.map((item, index) => (
              <details
                key={index}
                className="rounded-lg border border-[var(--border-subtle)] px-3 py-2 text-sm"
              >
                <summary className="cursor-pointer font-medium leading-6 text-[var(--text-primary)]">
                  {item.question || `回答 ${index + 1}`}
                </summary>
                <p className="mt-2 whitespace-pre-wrap text-[13px] leading-6 text-[var(--text-secondary)]">
                  {item.excerpt}
                </p>
              </details>
            ))}
          </div>
        </section>
      ))}
    </div>
  );
}

export function EntitiesArtifact({
  nodes,
}: {
  nodes: OntologyAssociationCircleProjection['nodes'];
}) {
  const list = useMemo(() => {
    return [...(nodes || [])]
      .sort((a, b) => Number(b.answer_count || 0) - Number(a.answer_count || 0))
      .slice(0, 100);
  }, [nodes]);
  if (!list.length) {
    return <ArtifactEmpty text="抽取出的实体会在这里列出。" />;
  }
  return (
    <div className="overflow-hidden rounded-lg border border-[var(--border-subtle)]">
      <table className="w-full text-sm">
        <thead>
          <tr className="bg-[var(--bg-secondary)] text-left text-xs text-[var(--text-tertiary)]">
            <th className="px-3 py-2 font-medium">实体</th>
            <th className="px-3 py-2 font-medium">类型</th>
            <th className="px-3 py-2 text-right font-medium">提及回答</th>
          </tr>
        </thead>
        <tbody>
          {list.map((node) => (
            <tr key={node.node_id} className="border-t border-[var(--border-subtle)]">
              <td className="px-3 py-2 text-[var(--text-primary)]">{node.term}</td>
              <td className="px-3 py-2 text-xs text-[var(--text-tertiary)]">{node.entity_type}</td>
              <td className="px-3 py-2 text-right tabular-nums text-[var(--text-secondary)]">
                {node.answer_count || 0}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
