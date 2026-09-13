import { useMemo, useRef, useState } from 'react';
import type { AmwayTopicCoverage, AmwayTopicCoverageStatus } from '@/types/ontology';

interface AmwayTopicCoveragePanelProps {
  coverage?: AmwayTopicCoverage | null;
  scopeLabel: string;
  isLoading?: boolean;
}

const STATUS_LABELS: Record<AmwayTopicCoverageStatus, string> = {
  included: '已入图',
  unmatched: '未识别到',
  relation_filtered: '关联被排除',
  pending_review: '待复核',
  excluded: '其他排除',
};

const REASON_LABELS: Record<string, string> = {
  accepted: '该原文已通过主题识别与关系筛选。',
  included: '识别到符合入图条件的主题证据。',
  no_signal: '按照当时的名称、别名和映射规则未识别到证据，不代表答案没有相关语义。',
  review_excluded: '词条尚未通过审核，不参与答案识别。',
  matching_disabled: '词条在本次分析中已停用匹配。',
  type_excluded: '词条类型不在本次分析的识别范围。',
  market_context_only: '答案提及属于市场背景，未建立与中心品牌的有效关联。',
  risk_denied: '答案否定了该关联，按当前关系规则排除。',
  relation_excluded: '已识别证据均被关系规则排除，详见证据说明。',
  mapping_excluded: '对象未通过主题归属映射规则。',
  graph_policy_excluded: '主题的图谱准入设置不允许此次入图。',
  below_threshold: '已识别有效证据，但评分未达到入图门槛。',
  multiple_run_outcomes: '所选周期内各轮的排除原因不同，需结合对应原文核对。',
  period_filtered: '部分单轮包含该主题，但未进入当前周期图谱。',
};

function reasonLabel(reason: string) {
  return REASON_LABELS[reason] || '已记录排除原因，当前页面暂未提供该原因的说明。';
}

/** Shows only diagnostics frozen into the selected projection, without current lexicon joins. */
export function AmwayTopicCoveragePanel({ coverage, scopeLabel, isLoading }: AmwayTopicCoveragePanelProps) {
  const [filter, setFilter] = useState<AmwayTopicCoverageStatus | 'all'>('all');
  const [query, setQuery] = useState('');
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const detailRef = useRef<HTMLElement>(null);
  const rows = useMemo(() => (coverage?.topics || []).filter((topic) => (
    (filter === 'all' || topic.status === filter)
    && topic.canonical_name.toLocaleLowerCase().includes(query.trim().toLocaleLowerCase())
  )), [coverage, filter, query]);
  const selected = rows.find((topic) => topic.entity_id === selectedId);

  if (isLoading) return <p role="status" className="p-4 text-sm text-[var(--text-secondary)]">正在读取所选分析的主题去向…</p>;
  if (!coverage) return <section className="rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-primary)] p-5">
    <h2 className="font-semibold">主题去向未记录</h2>
    <p className="mt-2 text-sm leading-6 text-[var(--text-secondary)]">{scopeLabel}尚无与当前图谱对应的主题去向数据，无法确认主题入图与排除数量。当前词库不能代替历史分析记录。</p>
  </section>;

  return <section className="space-y-4" aria-label="分析主题去向">
    <header className="rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-primary)] p-5">
      <h2 className="text-lg font-semibold">{scopeLabel} · 主题去向</h2>
      <p className="mt-2 text-sm leading-6 text-[var(--text-secondary)]">{coverage.total_topic_count} 个分析主题中，{coverage.included_topic_count} 个已入图；图中另有 {coverage.anchor_node_count} 个品牌节点{coverage.other_node_count > 0 ? `、${coverage.other_node_count} 个其他节点` : ''}。</p>
      <p className="mt-1 text-xs leading-5 text-[var(--text-tertiary)]">以下名称与状态来自该分析保存的词库。维护当前词库不会改变这里的历史记录。</p>
    </header>
    <div role="group" aria-label="按主题去向筛选" className="flex flex-wrap gap-2">
      {(['all', ...Object.keys(STATUS_LABELS)] as Array<AmwayTopicCoverageStatus | 'all'>).map((status) => <button
        key={status} type="button" aria-pressed={filter === status} onClick={() => setFilter(status)}
        className={`rounded-lg border px-3 py-2 text-sm focus-visible:outline focus-visible:outline-2 focus-visible:outline-[var(--brand-primary)] ${filter === status ? 'border-[var(--brand-border)] bg-[var(--brand-bg)] text-[var(--brand-primary)]' : 'border-[var(--border-subtle)] bg-[var(--bg-primary)] text-[var(--text-secondary)]'}`}
      >{status === 'all' ? '全部主题' : STATUS_LABELS[status]} {status === 'all' ? coverage.total_topic_count : coverage.status_counts[status] ?? 0}</button>)}
    </div>
    <div className="grid min-w-0 gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(18rem,0.8fr)]">
      <div className="min-w-0 rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-primary)] p-4">
        <label className="block text-sm text-[var(--text-secondary)]">搜索本次分析主题
          <input value={query} onChange={(event) => setQuery(event.target.value)} type="search" placeholder="输入主题名称"
            className="mt-2 w-full rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-3 py-2 text-[var(--text-primary)] focus-visible:outline focus-visible:outline-2 focus-visible:outline-[var(--brand-primary)]" />
        </label>
        <p role="status" className="my-3 text-xs text-[var(--text-tertiary)]">显示 {rows.length} 个主题</p>
        <ul className="max-h-[36rem] overflow-y-auto divide-y divide-[var(--border-subtle)]">
          {rows.map((topic) => <li key={topic.entity_id}>
            <button type="button" aria-pressed={selected?.entity_id === topic.entity_id} onClick={() => {
              setSelectedId(topic.entity_id);
              requestAnimationFrame(() => { detailRef.current?.focus(); detailRef.current?.scrollIntoView({ block: 'nearest' }); });
            }} className={`w-full rounded-lg px-2 py-3 text-left focus-visible:outline focus-visible:outline-2 focus-visible:outline-[var(--brand-primary)] ${selected?.entity_id === topic.entity_id ? 'bg-[var(--brand-bg)]' : 'hover:bg-[var(--bg-secondary)]'}`}>
              <span className="flex flex-wrap items-baseline justify-between gap-2"><span className="font-medium">{topic.canonical_name}</span><span className="text-xs text-[var(--text-secondary)]">{STATUS_LABELS[topic.status] || '状态未记录'}</span></span>
              <span className="mt-1 block text-xs leading-5 text-[var(--text-secondary)]">{topic.status === 'pending_review' ? '不参与识别，未核对答案提及' : reasonLabel(topic.reason)}</span>
            </button>
          </li>)}
        </ul>
        {!rows.length && <p className="py-6 text-sm text-[var(--text-secondary)]">没有符合筛选条件的主题。</p>}
      </div>
      <aside ref={detailRef} tabIndex={-1} aria-label="主题去向与原文依据" className="min-w-0 self-start rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-primary)] p-5 focus-visible:outline focus-visible:outline-2 focus-visible:outline-[var(--brand-primary)]">
        {selected ? <div className="space-y-3 text-sm leading-6">
          <h3 className="text-lg font-semibold">{selected.canonical_name}</h3>
          <p>{STATUS_LABELS[selected.status]} · {reasonLabel(selected.reason)}</p>
          {selected.status === 'pending_review' ? <p className="text-[var(--text-secondary)]">该主题未进入识别，因此不能把未记录提及解读为答案没有提到它。</p> : <p className="text-[var(--text-secondary)]">符合主题准入条件的答案：{selected.answer_count} 条{selected.score !== undefined ? ` · 入图评分：${selected.score}` : ''}</p>}
          <h4 className="border-t border-[var(--border-subtle)] pt-3 font-medium">原文依据</h4>
          {selected.evidence_samples.length ? selected.evidence_samples.map((sample, index) => <div key={`${sample.answer_id}-${index}`} className="border-b border-[var(--border-subtle)] pb-3">
            <p className="text-xs text-[var(--text-tertiary)]">{sample.platform} · {sample.question_id || '题号未记录'}</p>
            <p className="mt-1">{sample.question || '题目未记录'}</p>
            <blockquote className="my-2 border-l-2 border-[var(--brand-border)] pl-3 text-[var(--text-secondary)]">{sample.evidence_text || '未记录原文片段'}</blockquote>
            <p className="text-xs text-[var(--text-secondary)]">{reasonLabel(sample.reason)}</p>
          </div>) : <p className="text-[var(--text-secondary)]">未记录可展示的原文片段。</p>}
          {selected.evidence_samples.length > 0 && <p className="text-xs text-[var(--text-tertiary)]">展示最多 3 条已记录片段，片段不是完整答案。</p>}
        </div> : <p className="text-sm leading-6 text-[var(--text-secondary)]">选择左侧主题，查看它是否入图、排除原因和已记录的答案原文。</p>}
      </aside>
    </div>
  </section>;
}
