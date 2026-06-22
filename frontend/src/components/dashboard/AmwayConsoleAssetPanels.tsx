import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react';
import {
  Edit3,
  FileText,
  Loader2,
  Plus,
  RefreshCw,
  Search,
  Trash2,
  X,
} from 'lucide-react';
import { api } from '@/services/api';
import type {
  AmwayEntityLexiconEntry,
  AmwayEntityLexiconMutationInput,
  AmwayEntityLexiconResponse,
  AmwayQuestionHistoryResponse,
  AmwayQuestionHistorySet,
} from '@/types/amwayChina';

interface AssetPanelProps {
  entityId: string | null;
  entityName?: string;
}

type LexiconFormState = {
  canonical_name: string;
  entity_type: string;
  aliases: string;
  description: string;
  related_terms: string;
  review_status: string;
};

const EMPTY_FORM: LexiconFormState = {
  canonical_name: '',
  entity_type: '',
  aliases: '',
  description: '',
  related_terms: '',
  review_status: 'approved',
};

const REVIEW_STATUS_LABELS: Record<string, string> = {
  approved: '已确认',
  pending_review: '待复核',
  rejected: '已排除',
  merged: '已合并',
};

const ORIGIN_LABELS: Record<string, string> = {
  default: '内置',
  overridden: '已调整',
  custom: '新增',
};

export function AmwayEntityLexiconPanel({ entityId, entityName }: AssetPanelProps) {
  const [data, setData] = useState<AmwayEntityLexiconResponse | null>(null);
  const [query, setQuery] = useState('');
  const [typeFilter, setTypeFilter] = useState('all');
  const [editingId, setEditingId] = useState<string | null>(null);
  const [form, setForm] = useState<LexiconFormState>(EMPTY_FORM);
  const [isLoading, setIsLoading] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [formError, setFormError] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!entityId) return;
    setIsLoading(true);
    setError(null);
    try {
      setData(await api.getAmwayEntityLexicon(entityId));
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : '实体词库读取失败');
    } finally {
      setIsLoading(false);
    }
  }, [entityId]);

  useEffect(() => {
    void load();
  }, [load]);

  const entries = useMemo(() => data?.entries || [], [data?.entries]);
  const entityTypes = useMemo(() => data?.entity_types || [], [data?.entity_types]);
  const typeLabelById = useMemo(
    () => new Map(entityTypes.map((item) => [item.type_id, item.label])),
    [entityTypes],
  );
  const filteredEntries = useMemo(() => {
    const keyword = query.trim().toLowerCase();
    return entries.filter((entry) => {
      if (typeFilter !== 'all' && entry.entity_type !== typeFilter) return false;
      if (!keyword) return true;
      return [
        entry.canonical_name,
        entry.entity_type,
        entry.description,
        ...entry.aliases,
        ...entry.related_terms,
      ]
        .join(' ')
        .toLowerCase()
        .includes(keyword);
    });
  }, [entries, query, typeFilter]);

  const beginCreate = () => {
    setEditingId('__new__');
    setForm({
      ...EMPTY_FORM,
      entity_type: entityTypes[0]?.type_id || '',
    });
    setFormError(null);
  };

  const beginEdit = (entry: AmwayEntityLexiconEntry) => {
    setEditingId(entry.id);
    setForm({
      canonical_name: entry.canonical_name,
      entity_type: entry.entity_type,
      aliases: entry.aliases.join('，'),
      description: entry.description,
      related_terms: entry.related_terms.join('，'),
      review_status: entry.review_status || 'approved',
    });
    setFormError(null);
  };

  const saveEntry = async () => {
    if (!entityId) return;
    const payload: AmwayEntityLexiconMutationInput = {
      canonical_name: form.canonical_name.trim(),
      entity_type: form.entity_type,
      aliases: splitTextList(form.aliases),
      description: form.description.trim(),
      related_terms: splitTextList(form.related_terms),
      review_status: form.review_status,
    };
    if (!payload.canonical_name) {
      setFormError('实体名称不能为空');
      return;
    }
    if (!payload.entity_type) {
      setFormError('请选择实体类型');
      return;
    }
    setIsSaving(true);
    setFormError(null);
    try {
      if (editingId === '__new__') {
        await api.createAmwayEntityLexiconEntry(entityId, payload);
      } else if (editingId) {
        await api.updateAmwayEntityLexiconEntry(entityId, editingId, payload);
      }
      setEditingId(null);
      setForm(EMPTY_FORM);
      await load();
    } catch (saveError) {
      setFormError(saveError instanceof Error ? saveError.message : '实体词保存失败');
    } finally {
      setIsSaving(false);
    }
  };

  const deleteEntry = async (entry: AmwayEntityLexiconEntry) => {
    if (!entityId) return;
    const confirmed = window.confirm(`确认删除实体词“${entry.canonical_name}”？`);
    if (!confirmed) return;
    setIsSaving(true);
    try {
      await api.deleteAmwayEntityLexiconEntry(entityId, entry.id);
      if (editingId === entry.id) setEditingId(null);
      await load();
    } catch (deleteError) {
      setError(deleteError instanceof Error ? deleteError.message : '实体词删除失败');
    } finally {
      setIsSaving(false);
    }
  };

  if (!entityId) {
    return <AssetEmptyState title="未选择安利实体" description="请先进入一个已开通安利权限的品牌实体。" />;
  }

  return (
    <section className="space-y-4">
      <AssetPanelHeader
        eyebrow="实体词库"
        title="安利实体词库"
        description="这里维护抓取回答后的实体识别边界。新增或调整后，后续 A4 实体抽取会读取这份词库。"
        meta={`${entityName || data?.entity_name || '安利实体'} · ${entries.length} 个实体词`}
        action={
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={load}
              className="inline-flex h-9 items-center gap-2 rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-primary)] px-3 text-sm text-[var(--text-secondary)] hover:bg-[var(--bg-secondary)]"
            >
              <RefreshCw size={14} />
              刷新
            </button>
            <button
              type="button"
              onClick={beginCreate}
              className="inline-flex h-9 items-center gap-2 rounded-xl bg-[var(--brand-primary)] px-3 text-sm font-semibold text-[var(--brand-contrast)] hover:bg-[var(--brand-hover)]"
            >
              <Plus size={14} />
              新增实体
            </button>
          </div>
        }
      />

      {error ? <InlineError message={error} /> : null}

      <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_420px]">
        <div className="rounded-2xl border border-[var(--border-subtle)] bg-[var(--bg-primary)]">
          <div className="flex flex-col gap-3 border-b border-[var(--border-subtle)] p-4 md:flex-row md:items-center md:justify-between">
            <label className="flex h-10 min-w-0 flex-1 items-center gap-2 rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-3 text-sm text-[var(--text-secondary)]">
              <Search size={15} />
              <input
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder="搜索实体名、别名、相关词"
                className="min-w-0 flex-1 bg-transparent text-[var(--text-primary)] outline-none placeholder:text-[var(--text-tertiary)]"
              />
            </label>
            <select
              value={typeFilter}
              onChange={(event) => setTypeFilter(event.target.value)}
              className="h-10 rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-primary)] px-3 text-sm text-[var(--text-secondary)] outline-none"
            >
              <option value="all">全部类型</option>
              {entityTypes.map((item) => (
                <option key={item.type_id} value={item.type_id}>
                  {item.label}
                </option>
              ))}
            </select>
          </div>

          <div className="max-h-[640px] overflow-auto">
            {isLoading ? (
              <LoadingRows label="正在读取实体词库" />
            ) : filteredEntries.length ? (
              <div className="divide-y divide-[var(--border-subtle)]">
                {filteredEntries.map((entry) => (
                  <article
                    key={entry.id}
                    className="grid gap-3 p-4 transition hover:bg-[var(--bg-secondary)] lg:grid-cols-[minmax(0,1fr)_220px_140px]"
                  >
                    <div className="min-w-0">
                      <div className="flex flex-wrap items-center gap-2">
                        <h3 className="text-base font-semibold text-[var(--text-primary)]">
                          {entry.canonical_name}
                        </h3>
                        <StatusPill label={typeLabelById.get(entry.entity_type) || entry.entity_type} />
                        <StatusPill label={ORIGIN_LABELS[entry.origin] || entry.origin} tone="neutral" />
                        <StatusPill
                          label={REVIEW_STATUS_LABELS[entry.review_status] || entry.review_status}
                          tone={entry.review_status === 'approved' ? 'success' : 'warning'}
                        />
                      </div>
                      <p className="mt-2 line-clamp-2 text-sm leading-6 text-[var(--text-secondary)]">
                        {entry.description || '暂无定义说明'}
                      </p>
                      {entry.aliases.length ? (
                        <p className="mt-2 text-xs leading-5 text-[var(--text-tertiary)]">
                          别名：{entry.aliases.slice(0, 8).join('、')}
                        </p>
                      ) : null}
                    </div>
                    <div className="text-sm leading-6 text-[var(--text-secondary)]">
                      <div>主图谱：{graphPolicyLabel(entry.graph_policy?.main_orbit)}</div>
                      <div>风险图：{graphPolicyLabel(entry.graph_policy?.risk_view)}</div>
                    </div>
                    <div className="flex items-start justify-end gap-2">
                      <button
                        type="button"
                        onClick={() => beginEdit(entry)}
                        className="inline-flex h-9 items-center gap-1 rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-primary)] px-3 text-sm text-[var(--text-secondary)] hover:bg-[var(--bg-secondary)]"
                      >
                        <Edit3 size={14} />
                        编辑
                      </button>
                      <button
                        type="button"
                        onClick={() => void deleteEntry(entry)}
                        className="inline-flex h-9 items-center gap-1 rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-primary)] px-3 text-sm text-[var(--error)] hover:bg-[var(--status-error-bg)]"
                      >
                        <Trash2 size={14} />
                        删除
                      </button>
                    </div>
                  </article>
                ))}
              </div>
            ) : (
              <AssetEmptyState title="没有匹配的实体词" description="换一个关键词或实体类型再看。" />
            )}
          </div>
        </div>

        <aside className="rounded-2xl border border-[var(--border-subtle)] bg-[var(--bg-primary)] p-4">
          {editingId ? (
            <div className="space-y-4">
              <div className="flex items-start justify-between gap-3">
                <div>
                  <div className="text-xs font-medium text-[var(--text-tertiary)]">
                    {editingId === '__new__' ? '新增实体' : '编辑实体'}
                  </div>
                  <h2 className="mt-1 text-lg font-semibold">词库维护</h2>
                </div>
                <button
                  type="button"
                  onClick={() => setEditingId(null)}
                  className="flex h-9 w-9 items-center justify-center rounded-xl border border-[var(--border-subtle)] text-[var(--text-secondary)] hover:bg-[var(--bg-secondary)]"
                  aria-label="关闭编辑"
                >
                  <X size={16} />
                </button>
              </div>
              <LexiconField label="实体名称">
                <input
                  value={form.canonical_name}
                  onChange={(event) => setForm((current) => ({ ...current, canonical_name: event.target.value }))}
                  className="w-full rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-3 py-2 text-sm text-[var(--text-primary)] outline-none focus:border-[var(--brand-primary)]"
                  placeholder="例如：营养早餐"
                />
              </LexiconField>
              <LexiconField label="实体类型">
                <select
                  value={form.entity_type}
                  onChange={(event) => setForm((current) => ({ ...current, entity_type: event.target.value }))}
                  className="w-full rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-3 py-2 text-sm text-[var(--text-primary)] outline-none focus:border-[var(--brand-primary)]"
                >
                  <option value="">选择类型</option>
                  {entityTypes.map((item) => (
                    <option key={item.type_id} value={item.type_id}>
                      {item.label}
                    </option>
                  ))}
                </select>
              </LexiconField>
              <LexiconField label="别名">
                <textarea
                  value={form.aliases}
                  onChange={(event) => setForm((current) => ({ ...current, aliases: event.target.value }))}
                  className="min-h-20 w-full rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-3 py-2 text-sm leading-6 text-[var(--text-primary)] outline-none focus:border-[var(--brand-primary)]"
                  placeholder="用逗号或顿号分隔"
                />
              </LexiconField>
              <LexiconField label="定义说明">
                <textarea
                  value={form.description}
                  onChange={(event) => setForm((current) => ({ ...current, description: event.target.value }))}
                  className="min-h-24 w-full rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-3 py-2 text-sm leading-6 text-[var(--text-primary)] outline-none focus:border-[var(--brand-primary)]"
                  placeholder="说明这个实体在安利图谱中的含义"
                />
              </LexiconField>
              <LexiconField label="相关词">
                <textarea
                  value={form.related_terms}
                  onChange={(event) => setForm((current) => ({ ...current, related_terms: event.target.value }))}
                  className="min-h-20 w-full rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-3 py-2 text-sm leading-6 text-[var(--text-primary)] outline-none focus:border-[var(--brand-primary)]"
                  placeholder="用于辅助识别的相关表达"
                />
              </LexiconField>
              <LexiconField label="状态">
                <select
                  value={form.review_status}
                  onChange={(event) => setForm((current) => ({ ...current, review_status: event.target.value }))}
                  className="w-full rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-3 py-2 text-sm text-[var(--text-primary)] outline-none focus:border-[var(--brand-primary)]"
                >
                  {Object.entries(REVIEW_STATUS_LABELS).map(([value, label]) => (
                    <option key={value} value={value}>
                      {label}
                    </option>
                  ))}
                </select>
              </LexiconField>
              {formError ? <InlineError message={formError} /> : null}
              <button
                type="button"
                onClick={() => void saveEntry()}
                disabled={isSaving}
                className="inline-flex h-10 w-full items-center justify-center gap-2 rounded-xl bg-[var(--brand-primary)] px-4 text-sm font-semibold text-[var(--brand-contrast)] hover:bg-[var(--brand-hover)] disabled:opacity-60"
              >
                {isSaving ? <Loader2 size={15} className="animate-spin" /> : null}
                保存词库
              </button>
            </div>
          ) : (
            <div className="rounded-xl bg-[var(--bg-secondary)] p-4 text-sm leading-6 text-[var(--text-secondary)]">
              <div className="text-base font-semibold text-[var(--text-primary)]">如何使用</div>
              <p className="mt-2">
                先用搜索定位实体，再编辑名称、别名和定义。删除会在当前安利实体下隐藏该词，内置 JSON 不会被改写。
              </p>
              <p className="mt-3">
                后续抓取会读取当前实体的合并词库，所以这里的变更会影响下一轮抽词和图谱。
              </p>
            </div>
          )}
        </aside>
      </div>
    </section>
  );
}

export function AmwayQuestionHistoryPanel({ entityId, entityName }: AssetPanelProps) {
  const [data, setData] = useState<AmwayQuestionHistoryResponse | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [page, setPage] = useState(1);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!entityId) return;
    setIsLoading(true);
    setError(null);
    try {
      const nextData = await api.listAmwayQuestionHistory(entityId, 80);
      setData(nextData);
      setSelectedId((current) => {
        if (current && nextData.question_sets.some((item) => item.id === current)) return current;
        return nextData.question_sets[0]?.id || null;
      });
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : '历史题库读取失败');
    } finally {
      setIsLoading(false);
    }
  }, [entityId]);

  useEffect(() => {
    void load();
  }, [load]);

  const questionSets = data?.question_sets || [];
  const selectedSet = questionSets.find((item) => item.id === selectedId) || questionSets[0] || null;
  const questions = selectedSet?.questions || [];
  const pageSize = 8;
  const totalPages = Math.max(1, Math.ceil(questions.length / pageSize));
  const visibleQuestions = questions.slice((page - 1) * pageSize, page * pageSize);

  useEffect(() => {
    setPage(1);
  }, [selectedId]);

  if (!entityId) {
    return <AssetEmptyState title="未选择安利实体" description="请先进入一个已开通安利权限的品牌实体。" />;
  }

  return (
    <section className="space-y-4">
      <AssetPanelHeader
        eyebrow="历史题库"
        title="上传问题列表"
        description="这里保留每次上传或启动图谱时使用的问题清单，用来复盘问题定义、追踪报告来源。"
        meta={`${entityName || '安利实体'} · ${questionSets.length} 组题库`}
        action={
          <button
            type="button"
            onClick={load}
            className="inline-flex h-9 items-center gap-2 rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-primary)] px-3 text-sm text-[var(--text-secondary)] hover:bg-[var(--bg-secondary)]"
          >
            <RefreshCw size={14} />
            刷新
          </button>
        }
      />
      {error ? <InlineError message={error} /> : null}
      <div className="grid gap-4 xl:grid-cols-[360px_minmax(0,1fr)]">
        <aside className="rounded-2xl border border-[var(--border-subtle)] bg-[var(--bg-primary)]">
          <div className="border-b border-[var(--border-subtle)] p-4 text-sm font-semibold">
            题库批次
          </div>
          <div className="max-h-[680px] overflow-auto p-3">
            {isLoading ? (
              <LoadingRows label="正在读取历史题库" />
            ) : questionSets.length ? (
              <div className="space-y-2">
                {questionSets.map((item) => (
                  <button
                    key={item.id}
                    type="button"
                    onClick={() => setSelectedId(item.id)}
                    className="w-full rounded-xl border p-3 text-left transition"
                    style={{
                      borderColor: item.id === selectedSet?.id ? 'var(--brand-primary)' : 'var(--border-subtle)',
                      background: item.id === selectedSet?.id ? 'var(--brand-bg)' : 'var(--bg-primary)',
                    }}
                  >
                    <div className="flex items-start justify-between gap-2">
                      <div className="min-w-0">
                        <div className="truncate text-sm font-semibold text-[var(--text-primary)]">
                          {item.title || item.source_file_name || '安利上传题库'}
                        </div>
                        <div className="mt-1 text-xs text-[var(--text-tertiary)]">
                          {formatDateTime(item.created_at)} · {sourceTypeLabel(item)}
                        </div>
                      </div>
                      <span className="rounded-full bg-[var(--bg-secondary)] px-2 py-1 text-xs text-[var(--text-secondary)]">
                        {item.question_count} 题
                      </span>
                    </div>
                  </button>
                ))}
              </div>
            ) : (
              <AssetEmptyState title="暂无历史题库" description="上传问题并启动图谱后，这里会留下可审阅的问题批次。" />
            )}
          </div>
        </aside>

        <section className="rounded-2xl border border-[var(--border-subtle)] bg-[var(--bg-primary)]">
          {selectedSet ? (
            <>
              <div className="border-b border-[var(--border-subtle)] p-5">
                <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
                  <div>
                    <div className="text-xs font-medium text-[var(--text-tertiary)]">
                      {sourceTypeLabel(selectedSet)}
                    </div>
                    <h2 className="mt-1 text-xl font-semibold">{selectedSet.title}</h2>
                    <p className="mt-2 text-sm text-[var(--text-secondary)]">
                      {selectedSet.question_count} 道问题 · {formatDateTime(selectedSet.created_at)}
                      {selectedSet.source_file_name ? ` · ${selectedSet.source_file_name}` : ''}
                    </p>
                  </div>
                  <div className="flex flex-wrap gap-2">
                    {(selectedSet.center_terms || []).map((term) => (
                      <StatusPill key={term} label={term} />
                    ))}
                  </div>
                </div>
              </div>
              <div className="divide-y divide-[var(--border-subtle)]">
                {visibleQuestions.map((question, index) => (
                  <article key={`${selectedSet.id}-${page}-${index}`} className="p-5">
                    <div className="flex items-start gap-3">
                      <span className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-[var(--bg-secondary)] text-xs font-semibold text-[var(--text-secondary)]">
                        {(page - 1) * pageSize + index + 1}
                      </span>
                      <div className="min-w-0 flex-1">
                        <p className="text-base leading-7 text-[var(--text-primary)]">
                          {questionText(question)}
                        </p>
                        <div className="mt-3 flex flex-wrap gap-2">
                          {questionMetaChips(question).map((chip) => (
                            <span
                              key={chip}
                              className="rounded-full border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-2 py-1 text-xs text-[var(--text-tertiary)]"
                            >
                              {chip}
                            </span>
                          ))}
                        </div>
                      </div>
                    </div>
                  </article>
                ))}
              </div>
              <div className="flex items-center justify-between border-t border-[var(--border-subtle)] p-4 text-sm text-[var(--text-secondary)]">
                <span>
                  第 {page} / {totalPages} 页
                </span>
                <div className="flex gap-2">
                  <button
                    type="button"
                    onClick={() => setPage((current) => Math.max(1, current - 1))}
                    disabled={page <= 1}
                    className="h-9 rounded-xl border border-[var(--border-subtle)] px-3 disabled:opacity-40"
                  >
                    上一页
                  </button>
                  <button
                    type="button"
                    onClick={() => setPage((current) => Math.min(totalPages, current + 1))}
                    disabled={page >= totalPages}
                    className="h-9 rounded-xl border border-[var(--border-subtle)] px-3 disabled:opacity-40"
                  >
                    下一页
                  </button>
                </div>
              </div>
            </>
          ) : (
            <AssetEmptyState title="暂无可审阅的问题" description="上传 32 题并启动图谱后，可以从这里回看完整问题列表。" />
          )}
        </section>
      </div>
    </section>
  );
}

function AssetPanelHeader({
  eyebrow,
  title,
  description,
  meta,
  action,
}: {
  eyebrow: string;
  title: string;
  description: string;
  meta: string;
  action?: ReactNode;
}) {
  return (
    <div className="rounded-2xl border border-[var(--border-subtle)] bg-[var(--bg-primary)] p-5">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
        <div className="max-w-4xl">
          <div className="text-xs font-medium text-[var(--text-tertiary)]">{eyebrow}</div>
          <h1 className="mt-1 text-2xl font-semibold">{title}</h1>
          <p className="mt-2 text-sm leading-6 text-[var(--text-secondary)]">{description}</p>
          <div className="mt-3 inline-flex rounded-full border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-3 py-1 text-xs text-[var(--text-tertiary)]">
            {meta}
          </div>
        </div>
        {action}
      </div>
    </div>
  );
}

function LexiconField({ label, children }: { label: string; children: ReactNode }) {
  return (
    <label className="block text-sm">
      <span className="mb-2 block text-xs font-medium text-[var(--text-tertiary)]">{label}</span>
      {children}
    </label>
  );
}

function InlineError({ message }: { message: string }) {
  return (
    <div className="rounded-xl border border-[var(--error)] bg-[var(--status-error-bg)] px-4 py-3 text-sm text-[var(--error)]">
      {message}
    </div>
  );
}

function LoadingRows({ label }: { label: string }) {
  return (
    <div className="flex items-center gap-2 p-5 text-sm text-[var(--text-secondary)]">
      <Loader2 size={16} className="animate-spin" />
      {label}
    </div>
  );
}

function AssetEmptyState({ title, description }: { title: string; description: string }) {
  return (
    <div className="rounded-2xl border border-[var(--border-subtle)] bg-[var(--bg-primary)] p-8 text-center">
      <FileText className="mx-auto text-[var(--text-tertiary)]" size={26} />
      <h2 className="mt-3 text-base font-semibold">{title}</h2>
      <p className="mt-2 text-sm text-[var(--text-secondary)]">{description}</p>
    </div>
  );
}

function StatusPill({ label, tone = 'success' }: { label: string; tone?: 'success' | 'warning' | 'neutral' }) {
  const className =
    tone === 'success'
      ? 'border-[var(--brand-border)] bg-[var(--brand-bg)] text-[var(--brand-primary)]'
      : tone === 'warning'
        ? 'border-[var(--warning)] bg-[var(--status-warning-bg)] text-[var(--warning)]'
        : 'border-[var(--border-subtle)] bg-[var(--bg-secondary)] text-[var(--text-secondary)]';
  return (
    <span className={`rounded-full border px-2 py-1 text-xs ${className}`}>
      {label}
    </span>
  );
}

function splitTextList(value: string): string[] {
  return value
    .split(/[，,、\n]/)
    .map((item) => item.trim())
    .filter(Boolean);
}

function graphPolicyLabel(value?: string) {
  const labels: Record<string, string> = {
    always_center: '中心',
    allowed_with_answer_evidence: '回答证据',
    evidence_only: '证据后入图',
    not_allowed: '不入图',
    allowed: '允许',
  };
  return labels[value || ''] || value || '-';
}

function sourceTypeLabel(item: AmwayQuestionHistorySet) {
  if (item.source_type === 'run_input') return '运行输入';
  if (item.source === 'amwaychina_upload') return '上传题库';
  return item.source || '题库';
}

function questionText(question: Record<string, unknown>) {
  return String(question.question_text || question.text || question.question || '').trim() || '未命名问题';
}

function questionMetaChips(question: Record<string, unknown>) {
  const fields = [
    ['人群', question.audience_segment],
    ['场景', question.life_scene],
    ['机会点', question.opportunity_point],
    ['探针', question.probe_type],
    ['四有', question.four_have],
    ['目标品牌', Array.isArray(question.center_terms) ? question.center_terms.join('、') : question.center_terms],
  ];
  return fields
    .map(([label, value]) => {
      const text = String(value || '').trim();
      return text ? `${label}：${text}` : '';
    })
    .filter(Boolean)
    .slice(0, 8);
}

function formatDateTime(value?: string | null) {
  if (!value) return '时间未知';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  });
}
