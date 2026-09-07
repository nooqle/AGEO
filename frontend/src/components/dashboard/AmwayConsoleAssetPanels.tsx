import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
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
import { AmwayLexiconRepairControls } from './AmwayLexiconRepairControls';
import { semanticTypeLabels, semanticRelationLabels, lexiconStatusLabels } from './amwaySemanticLabels';
import { indexLexiconViews, matchesLexiconQuery, type LexiconView } from './amwayLexiconViews';
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

interface QuestionHistoryPanelProps extends AssetPanelProps {
  selectedForRunId?: string | null;
  onSelectForRun?: (questionSet: AmwayQuestionHistorySet) => void;
  onQuestionSetsChanged?: () => void;
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
  const [view, setView] = useState<LexiconView>('topics');
  const [topicFilter, setTopicFilter] = useState('all');
  const [selectedEntryId, setSelectedEntryId] = useState<string | null>(null);
  const detailRef = useRef<HTMLElement | null>(null);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [form, setForm] = useState<LexiconFormState>(EMPTY_FORM);
  const [isLoading, setIsLoading] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [formError, setFormError] = useState<string | null>(null);
  const [deleteConfirmId, setDeleteConfirmId] = useState<string | null>(null);

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
  const legacyEntityTypes = useMemo(() => entityTypes.filter((item) => item.type_id !== 'Object'), [entityTypes]);
  const typeLabelById = useMemo(
    () => new Map(entityTypes.map((item) => [item.type_id, item.label])),
    [entityTypes],
  );
  const { groups, byId, objectsByTopic } = useMemo(() => indexLexiconViews(entries), [entries]);
  const selectedEntry = selectedEntryId ? byId.get(selectedEntryId) : undefined;
  const editingEntry = entries.find((entry) => entry.id === editingId);
  const objectTypes = useMemo(() => [...new Set(groups.objects.map((entry) => entry.semantic_definition!.semantic_type))], [groups.objects]);
  const filteredEntries = useMemo(() => {
    return groups[view].filter((entry) => {
      if (view === 'objects') {
        if (typeFilter !== 'all' && entry.semantic_definition?.semantic_type !== typeFilter) return false;
        const mappedTopics = entry.semantic_definition?.topic_mappings.filter((mapping) => mapping.review_status === 'approved' && byId.get(mapping.target_entity_id)?.semantic_definition?.graph_role === 'topic') || [];
        if (topicFilter === 'unmapped' && mappedTopics.length) return false;
        if (topicFilter !== 'all' && topicFilter !== 'unmapped' && !mappedTopics.some((mapping) => mapping.target_entity_id === topicFilter)) return false;
      }
      return matchesLexiconQuery(entry, query) || (view === 'topics' && (objectsByTopic.get(entry.entity_id) || []).some((object) => matchesLexiconQuery(object, query)));
    });
  }, [groups, view, query, typeFilter, topicFilter, byId, objectsByTopic]);

  const openDetails = (entry: AmwayEntityLexiconEntry) => {
    setSelectedEntryId(entry.entity_id);
    setEditingId(null);
    requestAnimationFrame(() => { detailRef.current?.scrollIntoView({ block: 'nearest' }); detailRef.current?.focus(); });
  };

  const beginCreate = () => {
    setSelectedEntryId(null);
    setEditingId('__new__');
    setForm({
      ...EMPTY_FORM,
      entity_type: legacyEntityTypes[0]?.type_id || '',
    });
    setFormError(null);
  };

  const beginEdit = (entry: AmwayEntityLexiconEntry) => {
    setSelectedEntryId(entry.entity_id);
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
      entity_type: editingEntry?.semantic_definition ? editingEntry.entity_type : form.entity_type,
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
    if (deleteConfirmId !== entry.id) {
      setDeleteConfirmId(entry.id);
      return;
    }
    setDeleteConfirmId(null);
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
        title="安利主题与对象索引"
        description="主图按分析主题聚合；产品、原料、工具等对象保留独立身份，通过主题下钻查看。"
        meta={`${entityName || data?.entity_name || '安利实体'} · 名称与同义名称调整后，下一轮分析生效`}
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
          </div>
        }
      />
      <details className="rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-primary)] p-3 text-sm">
        <summary className="cursor-pointer text-[var(--text-secondary)]">批量维护</summary>
        <div className="mt-3"><AmwayLexiconRepairControls key={entityId} entityId={entityId} onApplied={load} /></div>
        <button
          type="button"
          onClick={beginCreate}
          className="mt-3 inline-flex h-9 items-center gap-2 rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-primary)] px-3 text-sm text-[var(--text-secondary)] hover:bg-[var(--bg-secondary)]"
        >
          <Plus size={14} />
          新增旧版词条
        </button>
      </details>

      {error ? <InlineError message={error} /> : null}

      <div role="group" aria-label="词库浏览视图" className="flex flex-wrap gap-2">
        {([
          ['topics', '分析主题'], ['objects', '对象索引'], ['context', '品牌与上下文'], ['unclassified', '未分类（旧版）'],
        ] as const).filter(([key]) => key !== 'unclassified' || groups.unclassified.length > 0).map(([key, label]) => (
          <button key={key} type="button" aria-pressed={view === key} onClick={() => setView(key)}
            className={`rounded-lg border px-3 py-2 text-sm ${view === key ? 'border-[var(--brand-border)] bg-[var(--brand-bg)] text-[var(--brand-primary)]' : 'border-[var(--border-subtle)] bg-[var(--bg-primary)] text-[var(--text-secondary)]'}`}>
            {label} {groups[key].length}
          </button>
        ))}
      </div>

      <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_420px]">
        <div className="amway-surface rounded-2xl border border-[var(--border-subtle)] bg-[var(--bg-primary)]">
          <div className="flex flex-col gap-3 border-b border-[var(--border-subtle)] p-4 md:flex-row md:items-center md:justify-between">
            <label className="flex h-10 min-w-0 flex-1 items-center gap-2 rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-3 text-sm text-[var(--text-secondary)]">
              <Search size={15} />
              <input
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                aria-label="搜索主题或对象名称、别名"
                placeholder={view === 'topics' ? '搜索主题或关联对象，例如丹参' : '搜索名称、别名、相关词'}
                className="min-w-0 flex-1 bg-transparent text-[var(--text-primary)] outline-none placeholder:text-[var(--text-tertiary)]"
              />
            </label>
            {view === 'objects' && <select
              aria-label="对象类型"
              value={typeFilter}
              onChange={(event) => setTypeFilter(event.target.value)}
              className="h-10 rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-primary)] px-3 text-sm text-[var(--text-secondary)] outline-none"
            >
              <option value="all">全部对象类型</option>
              {objectTypes.map((type) => (
                <option key={type} value={type}>
                  {semanticTypeLabels[type] || type}
                </option>
              ))}
            </select>}
            {view === 'objects' && <select aria-label="归属主题" value={topicFilter} onChange={(event) => setTopicFilter(event.target.value)}
              className="h-10 max-w-full rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-primary)] px-3 text-sm text-[var(--text-secondary)]">
              <option value="all">全部主题归属</option><option value="unmapped">未归组</option>
              {groups.topics.map((topic) => <option key={topic.entity_id} value={topic.entity_id}>{topic.canonical_name}</option>)}
            </select>}
          </div>
          <p role="status" className="px-4 py-2 text-xs text-[var(--text-secondary)]">当前显示 {filteredEntries.length} 项{view === 'topics' ? '分析主题；主题下的对象不另计为主题。' : view === 'context' ? '，品牌锚点与上下文分别标注。' : view === 'unclassified' ? '旧版词条，尚未设置语义身份与主图角色。' : '独立对象；主题归属不会合并对象身份。'}</p>

          <div className="max-h-[640px] overflow-auto">
            {isLoading ? (
              <LoadingRows label="正在读取实体词库" />
            ) : filteredEntries.length ? (
              <div className="divide-y divide-[var(--border-subtle)]">
                {filteredEntries.map((entry) => (
                  <article
                    key={entry.id}
                    className="grid gap-3 p-4 transition hover:bg-[var(--bg-secondary)] lg:grid-cols-[minmax(0,1fr)_auto]"
                  >
                    <div className="min-w-0">
                      <div className="flex flex-wrap items-center gap-2">
                        <h3 className="text-base font-semibold text-[var(--text-primary)]">
                          {entry.canonical_name}
                        </h3>
                        <StatusPill label={entry.semantic_definition ? view === 'topics' ? '分析主题' : view === 'context' ? entry.semantic_definition.graph_role === 'anchor' ? '品牌锚点' : '上下文' : semanticTypeLabels[entry.semantic_definition.semantic_type] || entry.semantic_definition.semantic_type : '未分类（旧版）'} tone="neutral" />
                        <StatusPill
                          label={lexiconStatusLabels[entry.review_status] || entry.review_status}
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
                      {view === 'topics' && <details key={`${entry.entity_id}-${query}`} open={query.trim() ? true : undefined} className="mt-3 text-sm leading-6 text-[var(--text-secondary)]">
                        <summary className="cursor-pointer">关联对象 {(objectsByTopic.get(entry.entity_id) || []).length} 项</summary>
                        {(objectsByTopic.get(entry.entity_id) || []).length ? (objectsByTopic.get(entry.entity_id) || []).map((object) => (
                          <div key={object.entity_id} className="mt-2 border-l-2 border-[var(--border-subtle)] pl-3">
                            <button type="button" onClick={() => openDetails(object)} className="text-left font-medium text-[var(--brand-primary)] underline underline-offset-2">{object.canonical_name}</button>
                            <span className="ml-2 text-xs">{semanticTypeLabels[object.semantic_definition!.semantic_type] || object.semantic_definition!.semantic_type}</span>
                            <p className="text-xs">别名：{object.aliases.join('、') || '无'}</p>
                            {object.semantic_definition!.topic_mappings.filter((mapping) => mapping.review_status === 'approved' && mapping.target_entity_id === entry.entity_id).map((mapping, index) => <div key={index} className="text-xs">
                              <p>归组状态：{REVIEW_STATUS_LABELS[mapping.review_status] || mapping.review_status}</p>
                              {mapping.source_refs.length ? mapping.source_refs.map((source, sourceIndex) => <p key={sourceIndex}>归组依据：{source.source_id} / {source.locator}：{source.quote}</p>) : <p>归组依据：未提供</p>}
                            </div>)}
                          </div>
                        )) : <p className="mt-2 text-xs">暂无关联对象，主题自身的直接命中仍可参与分析。</p>}
                      </details>}
                      {view === 'objects' && <p className="mt-2 text-xs leading-5 text-[var(--text-secondary)]">已确认主题归属：{entry.semantic_definition?.topic_mappings.filter((mapping) => mapping.review_status === 'approved' && byId.get(mapping.target_entity_id)?.semantic_definition?.graph_role === 'topic').map((mapping) => byId.get(mapping.target_entity_id)!.canonical_name).join('、') || '未归组'}</p>}
                    </div>
                    <div className="flex items-start justify-end gap-2">
                      <button
                        type="button"
                        onClick={() => openDetails(entry)}
                        className="inline-flex h-9 items-center gap-1 rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-primary)] px-3 text-sm text-[var(--text-secondary)] hover:bg-[var(--bg-secondary)]"
                      >
                        查看详情
                      </button>
                      <button
                        type="button"
                        disabled={isSaving}
                        onClick={() => void deleteEntry(entry)}
                        className={`inline-flex h-9 items-center gap-1 rounded-xl border px-3 text-sm ${
                          deleteConfirmId === entry.id
                            ? 'border-[var(--error)] bg-[var(--status-error-bg)] font-semibold text-[var(--error)]'
                            : 'border-[var(--border-subtle)] bg-[var(--bg-primary)] text-[var(--error)] hover:bg-[var(--status-error-bg)]'
                        }`}
                      >
                        <Trash2 size={14} />
                        {deleteConfirmId === entry.id ? '确认删除' : '删除'}
                      </button>
                    </div>
                  </article>
                ))}
              </div>
            ) : (
              <AssetEmptyState title="当前视图没有匹配项" description="可切换视图，或调整关键词与筛选条件。" />
            )}
          </div>
        </div>

        <aside ref={detailRef} tabIndex={-1} aria-label="词条详情与名称维护" className="amway-surface min-w-0 rounded-2xl border border-[var(--border-subtle)] bg-[var(--bg-primary)] p-4 focus-visible:outline focus-visible:outline-2 focus-visible:outline-[var(--brand-primary)]">
          {editingId ? (
            <div className="space-y-4">
              <div className="flex items-start justify-between gap-3">
                <div>
                  <div className="text-xs font-medium text-[var(--text-tertiary)]">
                    {editingId === '__new__' ? '新增旧版词条' : '名称与同义名称维护'}
                  </div>
                  <h2 className="mt-1 text-lg font-semibold">{editingId === '__new__' ? '旧版词条维护' : editingEntry?.canonical_name}</h2>
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
              <p className="text-sm leading-6 text-[var(--text-secondary)]">{editingEntry?.semantic_definition ? '此处维护名称、同义名称、说明与审核状态；对象身份、主题归属和主图角色保持不变。' : '此入口维护旧版分类。保存后进入未分类（旧版）视图，尚未配置对象身份与主题归属。'}</p>
              <LexiconField label="实体名称">
                <input
                  value={form.canonical_name}
                  onChange={(event) => setForm((current) => ({ ...current, canonical_name: event.target.value }))}
                  className="w-full rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-3 py-2 text-sm text-[var(--text-primary)] outline-none focus:border-[var(--brand-primary)]"
                  placeholder="例如：营养早餐"
                />
              </LexiconField>
              {editingEntry?.semantic_definition ? <div className="text-sm text-[var(--text-secondary)]">
                <p>对象类型：{semanticTypeLabels[editingEntry.semantic_definition.semantic_type] || editingEntry.semantic_definition.semantic_type}</p>
                <details className="mt-2"><summary>旧业务分类（只读）</summary><p>{typeLabelById.get(form.entity_type) || form.entity_type}</p></details>
              </div> : <LexiconField label="旧业务分类（不设置语义身份）">
                <select
                  value={form.entity_type}
                  onChange={(event) => setForm((current) => ({ ...current, entity_type: event.target.value }))}
                  className="w-full rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-3 py-2 text-sm text-[var(--text-primary)] outline-none focus:border-[var(--brand-primary)]"
                >
                  <option value="">选择类型</option>
                  {legacyEntityTypes.map((item) => (
                    <option key={item.type_id} value={item.type_id}>
                      {item.label}
                    </option>
                  ))}
                </select>
              </LexiconField>}
              <LexiconField label="同义名称（必须指向同一对象）">
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
              <LexiconField label="关联线索（不直接计实体命中）">
                <textarea
                  value={form.related_terms}
                  onChange={(event) => setForm((current) => ({ ...current, related_terms: event.target.value }))}
                  className="min-h-20 w-full rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-3 py-2 text-sm leading-6 text-[var(--text-primary)] outline-none focus:border-[var(--brand-primary)]"
                  placeholder="仅供复核参考，不参与实体命中"
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
          ) : selectedEntry ? (
            <div className="space-y-3 break-words text-sm leading-6 text-[var(--text-secondary)]">
              <div className="flex items-start justify-between gap-3">
                <h2 className="text-lg font-semibold text-[var(--text-primary)]">{selectedEntry.canonical_name}</h2>
                <button type="button" aria-label="关闭词条详情" onClick={() => setSelectedEntryId(null)} className="rounded-lg border border-[var(--border-subtle)] p-2"><X size={16} /></button>
              </div>
              <p>别名：{selectedEntry.aliases.join('、') || '无'}</p>
              <p>{selectedEntry.description || '暂无定义说明'}</p>
              {selectedEntry.semantic_definition ? <>
                <p>对象类型：{semanticTypeLabels[selectedEntry.semantic_definition.semantic_type] || selectedEntry.semantic_definition.semantic_type}</p>
                <p>主图角色：{{ topic: '分析主题', object: '独立对象下钻', anchor: '品牌锚点', context: '上下文' }[selectedEntry.semantic_definition.graph_role]}</p>
                <p>身份范围：{selectedEntry.semantic_definition.identity_scope}</p>
                <p>匹配方式：{selectedEntry.semantic_definition.match_policy === 'disabled' ? '停用全局匹配' : selectedEntry.semantic_definition.match_policy === 'contextual' ? '须近邻上下文' : '标准名与同义名称'}</p>
                <div className="border-t border-[var(--border-subtle)] pt-3">
                  <h3 className="font-semibold">主题归属与归组依据</h3>
                  {selectedEntry.semantic_definition.topic_mappings.length ? selectedEntry.semantic_definition.topic_mappings.map((mapping, index) => <div key={index} className="mt-2">
                    <p>{byId.get(mapping.target_entity_id)?.canonical_name || mapping.target_entity_id}（{REVIEW_STATUS_LABELS[mapping.review_status] || mapping.review_status}）</p>
                    {mapping.source_refs.length ? mapping.source_refs.map((source, sourceIndex) => <p key={sourceIndex} className="text-xs">归组依据：{source.source_id} / {source.locator}：{source.quote}</p>) : <p className="text-xs">归组依据：未提供</p>}
                  </div>) : <p>{selectedEntry.semantic_definition.graph_role === 'object' ? '未归组，独立身份仍保留在对象索引中。' : '无上级主题归属。'}</p>}
                </div>
                <div className="border-t border-[var(--border-subtle)] pt-3">
                  <h3 className="font-semibold">对象关系</h3>
                  {selectedEntry.semantic_definition.relations.length ? selectedEntry.semantic_definition.relations.map((relation, index) => <div key={index} className="mt-2">
                    <p>{semanticRelationLabels[relation.relation_type] || relation.relation_type} → {byId.get(relation.target_entity_id)?.canonical_name || relation.target_entity_id}（{REVIEW_STATUS_LABELS[relation.review_status] || relation.review_status}）</p>
                    {relation.source_refs.map((source, sourceIndex) => <p key={sourceIndex} className="text-xs">{source.source_id} / {source.locator}：{source.quote}</p>)}
                  </div>) : <p>暂无已记录关系。</p>}
                </div>
                <details><summary>查看对象来源</summary>
                  {selectedEntry.semantic_definition.source_refs.map((source, index) => <p key={index} className="mt-2 text-xs">{source.source_id} / {source.locator}：{source.quote}</p>)}
                </details>
              </> : <p>未分类（旧版）：尚未设置语义身份与主图角色。</p>}
              <details className="border-t border-[var(--border-subtle)] pt-3"><summary>历史配置与记录标识（只读）</summary>
                <p className="break-all">唯一身份：{selectedEntry.entity_id}</p>
                <p>来源：{ORIGIN_LABELS[selectedEntry.origin] || selectedEntry.origin}</p>
                <p>旧业务分类：{typeLabelById.get(selectedEntry.entity_type) || selectedEntry.entity_type}</p>
                <p>旧主图策略：{graphPolicyLabel(selectedEntry.graph_policy?.main_orbit)}</p>
                <p>旧风险图策略：{graphPolicyLabel(selectedEntry.graph_policy?.risk_view)}</p>
              </details>
              <button type="button" disabled={isSaving} onClick={() => beginEdit(selectedEntry)} className="inline-flex items-center gap-2 rounded-lg border border-[var(--border-subtle)] px-3 py-2 text-sm"><Edit3 size={14} />名称与同义名称维护</button>
            </div>
          ) : (
            <div className="rounded-xl bg-[var(--bg-secondary)] p-4 text-sm leading-6 text-[var(--text-secondary)]">
              <div className="text-base font-semibold text-[var(--text-primary)]">如何使用</div>
              <p className="mt-2">
                先查看分析主题，再展开关联对象。点击对象名称可查看其独立身份、主题归属与来源；对象索引支持按类型和主题筛选。
              </p>
              <p className="mt-3">
                名称与同义名称维护会影响下一轮分析。删除会在当前品牌下隐藏词条；旧业务分类仅保留在历史详情中。
              </p>
            </div>
          )}
        </aside>
      </div>
    </section>
  );
}

export function AmwayQuestionHistoryPanel({
  entityId,
  entityName,
  selectedForRunId,
  onSelectForRun,
  onQuestionSetsChanged,
}: QuestionHistoryPanelProps) {
  const [data, setData] = useState<AmwayQuestionHistoryResponse | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [page, setPage] = useState(1);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [editorMode, setEditorMode] = useState<'new' | 'edit' | null>(null);
  const [draftTitle, setDraftTitle] = useState('');
  const [draftQuestions, setDraftQuestions] = useState('');
  const [isSaving, setIsSaving] = useState(false);
  const [deleteConfirmId, setDeleteConfirmId] = useState<string | null>(null);
  const titleInputRef = useRef<HTMLInputElement | null>(null);

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
    setEditorMode(null);
    setDeleteConfirmId(null);
  }, [selectedId]);

  const beginCreate = () => {
    setDraftTitle(`安利圈层题库 ${new Date().toLocaleDateString('zh-CN')}`);
    setDraftQuestions('');
    setEditorMode('new');
    setError(null);
  };

  const beginEdit = (questionSet: AmwayQuestionHistorySet) => {
    setDraftTitle(questionSet.title || '安利圈层题库');
    setDraftQuestions(questionSet.questions.map(questionText).filter(Boolean).join('\n'));
    setEditorMode(questionSet.source_type === 'question_set' ? 'edit' : 'new');
    setError(null);
  };

  useEffect(() => {
    if (editorMode) titleInputRef.current?.focus();
  }, [editorMode]);

  const saveQuestionSet = async () => {
    if (!entityId || (editorMode === 'edit' && !selectedSet)) return;
    const questions = draftQuestions
      .split(/\r?\n/)
      .map((text) => text.trim())
      .filter(Boolean);
    if (!draftTitle.trim()) {
      setError('请输入题库名称。');
      return;
    }
    if (!questions.length) {
      setError('请至少保留一道问题；每行填写一道。');
      return;
    }
    setIsSaving(true);
    setError(null);
    try {
      const saved = editorMode === 'edit' && selectedSet?.source_type === 'question_set'
        ? await api.updateAmwayQuestionHistory(entityId, selectedSet.id, {
            title: draftTitle.trim(),
            center_terms: selectedSet.center_terms,
            questions,
          })
        : await api.saveAmwayQuestionHistory({
            entity_id: entityId,
            title: draftTitle.trim(),
            center_terms: selectedSet?.center_terms || [],
            questions,
          });
      setEditorMode(null);
      await load();
      setSelectedId(saved.id);
      onQuestionSetsChanged?.();
    } catch (saveError) {
      setError(saveError instanceof Error ? saveError.message : '题库保存失败');
    } finally {
      setIsSaving(false);
    }
  };

  const deleteQuestionSet = async (questionSet: AmwayQuestionHistorySet) => {
    if (!entityId || questionSet.source_type !== 'question_set') return;
    if (deleteConfirmId !== questionSet.id) {
      setDeleteConfirmId(questionSet.id);
      return;
    }
    setIsSaving(true);
    setError(null);
    try {
      await api.deleteAmwayQuestionHistory(entityId, questionSet.id);
      setDeleteConfirmId(null);
      setSelectedId(null);
      await load();
      onQuestionSetsChanged?.();
    } catch (deleteError) {
      setError(deleteError instanceof Error ? deleteError.message : '题库删除失败');
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
        eyebrow="问题集"
        title="问题集管理"
        description="新建、编辑或选择本轮采集使用的问题集；历史运行仍保留当时使用的问题快照。"
        meta={`${entityName || '安利实体'} · ${questionSets.length} 组题库`}
        action={(
          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              onClick={beginCreate}
              className="inline-flex h-9 items-center gap-2 rounded-xl bg-[var(--brand-primary)] px-3 text-sm font-semibold text-[var(--brand-contrast)] hover:bg-[var(--brand-hover)]"
            >
              <Plus size={14} />
              新建题库
            </button>
            <button
              type="button"
              onClick={load}
              className="inline-flex h-9 items-center gap-2 rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-primary)] px-3 text-sm text-[var(--text-secondary)] hover:bg-[var(--bg-secondary)]"
            >
              <RefreshCw size={14} />
              刷新
            </button>
          </div>
        )}
      />
      {error ? <InlineError message={error} /> : null}
      {editorMode ? (
        <section className="rounded-2xl border border-[var(--brand-border)] bg-[var(--bg-primary)] p-5">
          <div className="flex flex-col gap-4 xl:flex-row xl:items-start">
            <div className="xl:w-80">
              <div className="text-xs font-medium text-[var(--brand-primary)]">
                {editorMode === 'edit' ? '编辑当前题库' : '新建可复用题库'}
              </div>
              <input
                ref={titleInputRef}
                value={draftTitle}
                onChange={(event) => setDraftTitle(event.target.value)}
                aria-label="题库名称"
                className="mt-2 h-10 w-full rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-3 text-sm outline-none focus:border-[var(--brand-primary)]"
                placeholder="题库名称"
              />
              <p className="mt-3 text-xs leading-5 text-[var(--text-tertiary)]">
                每行一道问题。保存后可在品牌图谱页选为本轮题库；已经完成的历史运行不会被改写。
              </p>
            </div>
            <textarea
              value={draftQuestions}
              onChange={(event) => setDraftQuestions(event.target.value)}
              aria-label="题库问题列表"
              className="min-h-48 flex-1 rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-3 py-2 text-sm leading-6 outline-none focus:border-[var(--brand-primary)]"
              placeholder={'每行填写一道问题\n例如：提到日常营养补充，你会想到哪些品牌？'}
            />
            <div className="flex shrink-0 gap-2 xl:flex-col">
              <button
                type="button"
                onClick={() => void saveQuestionSet()}
                disabled={isSaving}
                className="inline-flex h-10 items-center justify-center gap-2 rounded-xl bg-[var(--brand-primary)] px-4 text-sm font-semibold text-[var(--brand-contrast)] disabled:opacity-60"
              >
                {isSaving ? <Loader2 size={14} className="animate-spin" /> : null}
                保存题库
              </button>
              <button
                type="button"
                onClick={() => setEditorMode(null)}
                disabled={isSaving}
                className="h-10 rounded-xl border border-[var(--border-subtle)] px-4 text-sm text-[var(--text-secondary)]"
              >
                取消
              </button>
            </div>
          </div>
        </section>
      ) : null}
      <div className="grid gap-4 xl:grid-cols-[360px_minmax(0,1fr)]">
        <aside className="amway-surface rounded-2xl border border-[var(--border-subtle)] bg-[var(--bg-primary)]">
          <div className="border-b border-[var(--border-subtle)] p-4 text-sm font-semibold">
            题库批次
          </div>
          <div className="max-h-[680px] overflow-auto p-3">
            {isLoading ? (
              <LoadingRows label="正在读取问题集" />
            ) : questionSets.length ? (
              <div className="space-y-2">
                {questionSets.map((item) => (
                  <button
                    key={item.id}
                    type="button"
                    onClick={() => setSelectedId(item.id)}
                    aria-pressed={item.id === selectedSet?.id}
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
              <AssetEmptyState title="暂无问题集" description="可在上方新建，或上传问题后保存为本轮问题集。" />
            )}
          </div>
        </aside>

        <section className="amway-surface rounded-2xl border border-[var(--border-subtle)] bg-[var(--bg-primary)]">
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
                      {selectedSet.question_count} 道问题
                      {selectedSet.version ? ` · 版本 ${selectedSet.version}` : ''}
                      {' · '}{formatDateTime(selectedSet.created_at)}
                      {selectedSet.source_file_name ? ` · ${selectedSet.source_file_name}` : ''}
                    </p>
                  </div>
                  <div className="flex flex-wrap justify-end gap-2">
                    <button
                      type="button"
                      onClick={() => onSelectForRun?.(selectedSet)}
                      className="h-9 rounded-xl border px-3 text-sm font-semibold"
                      style={{
                        borderColor: selectedForRunId === selectedSet.id ? 'var(--brand-primary)' : 'var(--brand-border)',
                        background: selectedForRunId === selectedSet.id ? 'var(--brand-bg)' : 'var(--bg-primary)',
                        color: 'var(--brand-primary)',
                      }}
                    >
                      {selectedForRunId === selectedSet.id ? '本轮已选' : '设为本轮题库'}
                    </button>
                    <button
                      type="button"
                      onClick={() => beginEdit(selectedSet)}
                      className="inline-flex h-9 items-center gap-2 rounded-xl border border-[var(--border-subtle)] px-3 text-sm text-[var(--text-secondary)]"
                    >
                      <Edit3 size={14} />
                      {selectedSet.source_type === 'question_set' ? '编辑' : '另存为'}
                    </button>
                    {selectedSet.source_type === 'question_set' ? (
                      <button
                        type="button"
                        onClick={() => void deleteQuestionSet(selectedSet)}
                        disabled={isSaving}
                        className="inline-flex h-9 items-center gap-2 rounded-xl border border-[var(--border-subtle)] px-3 text-sm text-[var(--error)] disabled:opacity-60"
                      >
                        <Trash2 size={14} />
                        {deleteConfirmId === selectedSet.id ? '确认删除' : '删除'}
                      </button>
                    ) : null}
                  </div>
                </div>
                <div className="mt-3 flex flex-wrap gap-2">
                  {(selectedSet.center_terms || []).map((term) => (
                    <StatusPill key={term} label={term} />
                  ))}
                  {deleteConfirmId === selectedSet.id ? (
                    <button
                      type="button"
                      onClick={() => setDeleteConfirmId(null)}
                      className="text-xs text-[var(--text-tertiary)] underline underline-offset-2"
                    >
                      取消删除
                    </button>
                  ) : null}
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
            <AssetEmptyState title="暂无可审阅的问题" description="上传问题集文件并运行分析后，完整问题列表会显示在这里。" />
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
    <div className="amway-surface rounded-2xl border border-[var(--border-subtle)] bg-[var(--bg-primary)] p-5">
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
    <div className="amway-surface rounded-2xl border border-[var(--border-subtle)] bg-[var(--bg-primary)] p-8 text-center">
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
