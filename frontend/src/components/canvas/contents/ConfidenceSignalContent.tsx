'use client';

import { useState } from 'react';
import {
  RiAlarmWarningLine,
  RiArticleLine,
  RiArrowRightUpLine,
  RiCalendarLine,
  RiCheckDoubleLine,
  RiFlashlightLine,
  RiLinkM,
  RiShieldCheckLine,
  RiSparklingLine,
} from '@remixicon/react';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { useConversationStore } from '@/stores/conversationStore';
import { cn } from '@/lib/cn';
import type {
  ConfidenceSignalItem,
  ConfidenceSignalLevel,
  ConfidenceSignalStatus,
  ReportCanvasContent,
} from '@/types/canvas';

interface ConfidenceSignalContentProps {
  content: ReportCanvasContent;
}

const LEVEL_STYLES: Record<ConfidenceSignalLevel, { label: string; tone: string; ring: string }> = {
  high: {
    label: '高置信',
    tone: 'bg-emerald-500/12 text-emerald-200',
    ring: 'border-emerald-500/30',
  },
  neutral: {
    label: '中性',
    tone: 'bg-amber-500/12 text-amber-100',
    ring: 'border-amber-500/30',
  },
  caution: {
    label: '需审慎',
    tone: 'bg-rose-500/12 text-rose-100',
    ring: 'border-rose-500/30',
  },
};

function formatScore(value?: number) {
  if (typeof value !== 'number' || Number.isNaN(value)) {
    return '--';
  }
  return value.toFixed(1);
}

function formatConfidence(value?: number) {
  if (typeof value !== 'number' || Number.isNaN(value)) {
    return '--';
  }
  const percent = value <= 1 ? value * 100 : value;
  return `${Math.round(percent)}%`;
}

function formatUpdatedAt(value?: string) {
  if (!value) {
    return '刚刚更新';
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return date.toLocaleString('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  });
}

function statusTone(status?: ConfidenceSignalStatus) {
  switch (status?.phase) {
    case 'running':
      return 'border-amber-500/30 bg-amber-500/10 text-amber-100';
    case 'error':
      return 'border-rose-500/30 bg-rose-500/10 text-rose-100';
    default:
      return 'border-[var(--border-subtle)] bg-[var(--bg-secondary)] text-[var(--text-secondary)]';
  }
}

function MetricCard({
  label,
  value,
  hint,
}: {
  label: string;
  value: string | number;
  hint?: string;
}) {
  return (
    <Card
      padding="none"
      className="rounded-[20px] border bg-[var(--bg-secondary)] p-4"
      style={{ borderColor: 'var(--border-subtle)' }}
    >
      <div className="text-[12px] tracking-[0.14em] text-[var(--text-tertiary)]">{label}</div>
      <div className="mt-3 text-[28px] font-semibold tracking-[-0.04em] text-[var(--text-primary)]">{value}</div>
      {hint ? <div className="mt-2 text-[12px] leading-6 text-[var(--text-secondary)]">{hint}</div> : null}
    </Card>
  );
}

function SignalBadge({ level }: { level?: ConfidenceSignalLevel }) {
  const resolved = level ? LEVEL_STYLES[level] : LEVEL_STYLES.neutral;
  return (
    <span className={cn('inline-flex items-center rounded-full border px-2.5 py-1 text-[11px] font-medium', resolved.tone, resolved.ring)}>
      {resolved.label}
    </span>
  );
}

function SignalCard({ item }: { item: ConfidenceSignalItem }) {
  const level = item.signal_level ?? 'neutral';
  const score = formatScore(item.overall_score);
  const confidence = formatConfidence(item.overall_confidence);
  const recommendation = item.recommendations?.[0];
  const hasPageEvidence =
    item.input_type === 'url' &&
    (
      typeof item.crawl_readable === 'boolean' ||
      typeof item.has_h1 === 'boolean' ||
      typeof item.has_main === 'boolean' ||
      typeof item.has_article === 'boolean' ||
      Boolean(item.schema_types && item.schema_types.length > 0) ||
      Boolean(item.published_at)
    );

  return (
    <Card
      padding="none"
      className="overflow-hidden rounded-[24px] border bg-[linear-gradient(180deg,rgba(255,255,255,0.02),rgba(255,255,255,0))]"
      style={{ borderColor: 'var(--border-subtle)' }}
    >
      <div className="border-b px-5 py-4" style={{ borderColor: 'var(--border-subtle)' }}>
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-2">
              <SignalBadge level={level} />
              <span className="inline-flex items-center rounded-full border border-[var(--border-subtle)] px-2.5 py-1 text-[11px] text-[var(--text-tertiary)]">
                {item.item_origin === 'manual_extra' ? '额外评估' : '引用来源'}
              </span>
              <span className="inline-flex items-center rounded-full border border-[var(--border-subtle)] px-2.5 py-1 text-[11px] text-[var(--text-tertiary)]">
                {item.input_type === 'url' ? '链接' : '文本'}
              </span>
            </div>
            <h3 className="mt-3 line-clamp-2 text-[18px] font-semibold tracking-[-0.03em] text-[var(--text-primary)]">
              {item.label}
            </h3>
            <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-[12px] text-[var(--text-tertiary)]">
              {item.domain ? <span>{item.domain}</span> : null}
              {item.site_name ? <span>{item.site_name}</span> : null}
              {typeof item.occurrences === 'number' ? <span>引用 {item.occurrences} 次</span> : null}
              {item.is_official ? <span>官方来源</span> : null}
            </div>
          </div>

          <div className="grid min-w-[180px] grid-cols-2 gap-2 rounded-[18px] border bg-[var(--bg-secondary)] p-3" style={{ borderColor: 'var(--border-subtle)' }}>
            <div>
              <div className="text-[11px] text-[var(--text-tertiary)]">AICE 信号分</div>
              <div className="mt-1 text-[22px] font-semibold tracking-[-0.04em] text-[var(--text-primary)]">{score}</div>
            </div>
            <div>
              <div className="text-[11px] text-[var(--text-tertiary)]">置信度</div>
              <div className="mt-1 text-[22px] font-semibold tracking-[-0.04em] text-[var(--text-primary)]">{confidence}</div>
            </div>
          </div>
        </div>
      </div>

      <CardContent className="grid gap-5 px-5 pb-5 pt-5 lg:grid-cols-[1.1fr_0.9fr]">
        <div>
          <div className="text-[12px] tracking-[0.14em] text-[var(--text-tertiary)]">主要信号</div>
          <div className="mt-3 flex flex-wrap gap-2">
            {(item.top_signals && item.top_signals.length > 0 ? item.top_signals : ['尚未生成信号']).map((signal) => (
              <span
                key={signal}
                className="inline-flex rounded-full bg-[var(--bg-tertiary)] px-3 py-1.5 text-[12px] text-[var(--text-secondary)]"
              >
                {signal}
              </span>
            ))}
          </div>

          {item.question_samples && item.question_samples.length > 0 ? (
            <div className="mt-4">
              <div className="text-[12px] tracking-[0.14em] text-[var(--text-tertiary)]">关联问题</div>
              <div className="mt-3 space-y-2">
                {item.question_samples.map((sample) => (
                  <div
                    key={sample}
                    className="rounded-[16px] border bg-[var(--bg-secondary)] px-3 py-2 text-[13px] leading-6 text-[var(--text-secondary)]"
                    style={{ borderColor: 'var(--border-subtle)' }}
                  >
                    {sample}
                  </div>
                ))}
              </div>
            </div>
          ) : null}

          {item.raw_text ? (
            <div className="mt-4 rounded-[18px] border bg-[var(--bg-secondary)] p-4 text-[13px] leading-7 text-[var(--text-secondary)]" style={{ borderColor: 'var(--border-subtle)' }}>
              {item.raw_text.length > 220 ? `${item.raw_text.slice(0, 220)}...` : item.raw_text}
            </div>
          ) : null}
        </div>

        <div className="space-y-4">
          {item.url ? (
            <a
              href={item.url}
              target="_blank"
              rel="noreferrer"
              className="flex items-center justify-between rounded-[18px] border bg-[var(--bg-secondary)] px-4 py-3 text-[13px] text-[var(--text-secondary)] transition-colors hover:bg-[var(--bg-tertiary)]"
              style={{ borderColor: 'var(--border-subtle)' }}
            >
              <span className="truncate pr-4">{item.url}</span>
              <RiArrowRightUpLine className="h-4 w-4 flex-none" />
            </a>
          ) : null}

          {hasPageEvidence ? (
            <div className="rounded-[18px] border bg-[var(--bg-secondary)] p-4" style={{ borderColor: 'var(--border-subtle)' }}>
              <div className="flex items-center gap-2 text-[12px] tracking-[0.14em] text-[var(--text-tertiary)]">
                <RiFlashlightLine className="h-4 w-4" />
                页面证据
              </div>
              <div className="mt-3 grid gap-2 sm:grid-cols-2">
                <div className="rounded-[14px] bg-[var(--bg-tertiary)] px-3 py-2 text-[12px] text-[var(--text-secondary)]">
                  可抓取性：{item.crawl_readable ? '可访问' : item.http_status ? `失败 (${item.http_status})` : '未知'}
                </div>
                <div className="rounded-[14px] bg-[var(--bg-tertiary)] px-3 py-2 text-[12px] text-[var(--text-secondary)]">
                  H1：{item.has_h1 ? `已发现${item.h1_count && item.h1_count > 1 ? ` (${item.h1_count})` : ''}` : '未发现'}
                </div>
                <div className="rounded-[14px] bg-[var(--bg-tertiary)] px-3 py-2 text-[12px] text-[var(--text-secondary)]">
                  主结构：{item.has_main || item.has_article ? [item.has_main ? 'main' : '', item.has_article ? 'article' : ''].filter(Boolean).join(' + ') : '未发现'}
                </div>
                <div className="rounded-[14px] bg-[var(--bg-tertiary)] px-3 py-2 text-[12px] text-[var(--text-secondary)]">
                  Schema：{item.schema_types && item.schema_types.length > 0 ? item.schema_types.slice(0, 2).join(' / ') : '未发现'}
                </div>
              </div>
              {item.published_at ? (
                <div className="mt-3 inline-flex items-center gap-2 rounded-full bg-[var(--bg-tertiary)] px-3 py-1.5 text-[12px] text-[var(--text-secondary)]">
                  <RiCalendarLine className="h-4 w-4" />
                  日期线索：{item.published_at}
                </div>
              ) : null}
            </div>
          ) : null}

          <div className="rounded-[18px] border bg-[var(--bg-secondary)] p-4" style={{ borderColor: 'var(--border-subtle)' }}>
            <div className="text-[12px] tracking-[0.14em] text-[var(--text-tertiary)]">建议动作</div>
            <div className="mt-3 text-[15px] font-medium text-[var(--text-primary)]">
              {recommendation?.title || '补充结构化和来源信息'}
            </div>
            <div className="mt-2 text-[13px] leading-7 text-[var(--text-secondary)]">
              {recommendation?.action || '优先补充来源主体、日期、结构标签与可核查证据。'}
            </div>
            {recommendation?.reason ? (
              <div className="mt-2 text-[12px] leading-6 text-[var(--text-tertiary)]">{recommendation.reason}</div>
            ) : null}
          </div>

          {item.dimension_scores && item.dimension_scores.length > 0 ? (
            <div className="rounded-[18px] border bg-[var(--bg-secondary)] p-4" style={{ borderColor: 'var(--border-subtle)' }}>
              <div className="text-[12px] tracking-[0.14em] text-[var(--text-tertiary)]">维度得分</div>
              <div className="mt-3 space-y-2">
                {item.dimension_scores.map((dimension) => (
                  <div key={dimension.key || dimension.label} className="flex items-center justify-between gap-3 rounded-[14px] bg-[var(--bg-tertiary)] px-3 py-2">
                    <div>
                      <div className="text-[13px] text-[var(--text-primary)]">{dimension.label || dimension.key}</div>
                      {dimension.reasoning ? <div className="text-[11px] text-[var(--text-tertiary)]">{dimension.reasoning}</div> : null}
                    </div>
                    <div className="text-[13px] font-medium text-[var(--text-secondary)]">
                      {typeof dimension.score === 'number' ? dimension.score : '--'}
                      {typeof dimension.max_score === 'number' ? `/${dimension.max_score}` : ''}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          ) : null}
        </div>
      </CardContent>
    </Card>
  );
}

export function ConfidenceSignalContent({ content }: ConfidenceSignalContentProps) {
  const sendArtifactAction = useConversationStore((state) => state.wsArtifactAction);
  const [inputValue, setInputValue] = useState('');

  const summary = content.data.summary;
  const autoItems = content.data.auto_items ?? [];
  const manualItems = content.data.manual_items ?? [];
  const findings = content.data.aggregate_findings ?? [];
  const composer = content.data.composer;
  const status = content.data.status;
  const isRunning = status?.phase === 'running';

  const handleSubmit = () => {
    const rawInput = inputValue.trim();
    if (!sendArtifactAction || !rawInput || isRunning) {
      return;
    }
    setInputValue('');
    sendArtifactAction(content.id, 'extra_evaluate', { raw_input: rawInput });
  };

  return (
    <div className="mx-auto max-w-[1180px] space-y-6 px-6 py-6 md:px-8 md:py-8">
      <section
        className="overflow-hidden rounded-[30px] border"
        style={{
          borderColor: 'rgba(148, 163, 184, 0.18)',
          background:
            'radial-gradient(circle at top left, rgba(16,185,129,0.16), transparent 30%), radial-gradient(circle at top right, rgba(245,158,11,0.14), transparent 28%), linear-gradient(180deg, rgba(15,23,42,0.95), rgba(17,24,39,0.92))',
        }}
      >
        <div className="grid gap-6 px-6 py-6 md:px-7 md:py-7 lg:grid-cols-[1.25fr_0.75fr]">
          <div>
            <div className="flex flex-wrap items-center gap-2">
              <span className="inline-flex items-center gap-2 rounded-full border border-white/10 bg-white/[0.06] px-3 py-1 text-[11px] tracking-[0.16em] text-white/70">
                <RiSparklingLine className="h-3.5 w-3.5" />
                CONFIDENCE SIGNAL
              </span>
              <span className={cn('inline-flex items-center rounded-full border px-3 py-1 text-[12px]', statusTone(status))}>
                {status?.message || '引用来源信号已就绪'}
              </span>
            </div>

            <h1 className="mt-5 text-[clamp(2.2rem,4vw,3.6rem)] font-semibold tracking-[-0.05em] text-white">
              {content.data.headline || '置信度信号'}
            </h1>
            <p className="mt-4 max-w-3xl text-[15px] leading-8 text-white/70">
              {content.data.subtitle || '围绕 A4 抓取答案中的引用来源，建立一个可持续追加的内容可信信号工作面板。'}
            </p>

            <div className="mt-5 flex flex-wrap items-center gap-x-5 gap-y-2 text-[12px] text-white/50">
              <span>自动评估 A4 引用链接</span>
              <span>额外评估支持链接和文本</span>
              <span>最近更新 {formatUpdatedAt(summary?.updated_at || content.data.updated_at)}</span>
            </div>
          </div>

          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-1">
            <div className="rounded-[24px] border border-white/10 bg-white/[0.06] p-5">
              <div className="text-[12px] tracking-[0.16em] text-white/60">平均信号分</div>
              <div className="mt-3 text-[42px] font-semibold tracking-[-0.06em] text-white">
                {formatScore(summary?.average_score)}
              </div>
              <div className="mt-2 text-[13px] leading-6 text-white/70">
                这是当前自动引用与手动追加项的整体均值，用来快速判断内容源是否稳。
              </div>
            </div>

            <div className="rounded-[24px] border border-white/10 bg-white/[0.06] p-5">
              <div className="text-[12px] tracking-[0.16em] text-white/60">当前构成</div>
              <div className="mt-4 flex items-center gap-6">
                <div>
                  <div className="text-[24px] font-semibold tracking-[-0.05em] text-white">{summary?.high_confidence_count ?? 0}</div>
                  <div className="text-[12px] text-white/60">高置信</div>
                </div>
                <div>
                  <div className="text-[24px] font-semibold tracking-[-0.05em] text-white">{summary?.caution_count ?? 0}</div>
                  <div className="text-[12px] text-white/60">需审慎</div>
                </div>
                <div>
                  <div className="text-[24px] font-semibold tracking-[-0.05em] text-white">{summary?.manual_count ?? 0}</div>
                  <div className="text-[12px] text-white/60">额外评估</div>
                </div>
              </div>
            </div>
          </div>
        </div>

        <div className="grid gap-3 border-t px-6 py-5 md:grid-cols-4 md:px-7" style={{ borderColor: 'rgba(255,255,255,0.08)' }}>
          <MetricCard label="引用来源数" value={summary?.total_citations ?? 0} hint="自动从 A4 citation 中提取" />
          <MetricCard label="已评估" value={summary?.evaluated_count ?? 0} hint="可直接进入详情查看" />
          <MetricCard label="高置信" value={summary?.high_confidence_count ?? 0} hint="优先用于可信样本观察" />
          <MetricCard label="需审慎" value={summary?.caution_count ?? 0} hint="优先补结构、时间和信源" />
        </div>
      </section>

      <section className="grid gap-6 xl:grid-cols-[0.92fr_1.08fr]">
        <Card
          padding="none"
          className="rounded-[28px] border bg-[var(--bg-tertiary)] p-5"
          style={{ borderColor: 'var(--border-subtle)' }}
        >
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-2xl bg-emerald-500/12 text-emerald-200">
              <RiFlashlightLine className="h-5 w-5" />
            </div>
            <div>
              <div className="text-[18px] font-semibold tracking-[-0.03em] text-[var(--text-primary)]">信号摘要</div>
              <div className="text-[13px] text-[var(--text-secondary)]">从自动引用和手动追加项里抽出的全局观察。</div>
            </div>
          </div>

          <div className="mt-5 space-y-3">
            {findings.map((finding, index) => (
              <div
                key={`${finding.title}_${index}`}
                className="rounded-[20px] border bg-[var(--bg-secondary)] p-4"
                style={{ borderColor: 'var(--border-subtle)' }}
              >
                <div className="text-[15px] font-medium text-[var(--text-primary)]">{finding.title || `发现 ${index + 1}`}</div>
                <div className="mt-2 text-[13px] leading-7 text-[var(--text-secondary)]">{finding.description}</div>
              </div>
            ))}
          </div>
        </Card>

        <Card
          padding="none"
          className="rounded-[28px] border bg-[var(--bg-tertiary)] p-5"
          style={{ borderColor: 'var(--border-subtle)' }}
        >
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-2xl bg-sky-500/12 text-sky-200">
              <RiArticleLine className="h-5 w-5" />
            </div>
            <div>
              <div className="text-[18px] font-semibold tracking-[-0.03em] text-[var(--text-primary)]">额外评估</div>
              <div className="text-[13px] text-[var(--text-secondary)]">
                在当前 Artifact 内追加一个链接或一段文本，直接驱动 A7 生成新的信号项。
              </div>
            </div>
          </div>

          <div className="mt-5 rounded-[24px] border border-dashed bg-[var(--bg-secondary)] p-4" style={{ borderColor: 'var(--border-subtle)' }}>
            <textarea
              value={inputValue}
              onChange={(event) => setInputValue(event.target.value)}
              placeholder={composer?.placeholder || '粘贴链接或文本，生成额外评估'}
              className="min-h-[160px] w-full resize-y rounded-[18px] border bg-[var(--bg-primary)] px-4 py-4 text-[14px] leading-7 text-[var(--text-primary)] outline-none transition-colors placeholder:text-[var(--text-tertiary)] focus:border-[var(--brand-primary)]"
              style={{ borderColor: 'var(--border-subtle)' }}
            />

            <div className="mt-3 flex flex-wrap items-center gap-2 text-[12px] text-[var(--text-tertiary)]">
              <span className="inline-flex items-center rounded-full bg-[var(--bg-tertiary)] px-3 py-1.5">支持链接</span>
              <span className="inline-flex items-center rounded-full bg-[var(--bg-tertiary)] px-3 py-1.5">支持文本</span>
              <span className="inline-flex items-center rounded-full bg-[var(--bg-tertiary)] px-3 py-1.5">不支持混合提交</span>
            </div>

            <div className="mt-4 flex flex-wrap items-center justify-between gap-3">
              <div className="text-[12px] leading-6 text-[var(--text-secondary)]">
                {composer?.helper_text || '支持单个链接、多个链接或一段文本；当前不支持问题抓取命令。'}
              </div>
              <Button
                onClick={handleSubmit}
                disabled={!composer?.enabled || !sendArtifactAction || !inputValue.trim() || isRunning}
                isLoading={isRunning}
                leftIcon={<RiLinkM className="h-4 w-4" />}
              >
                开始额外评估
              </Button>
            </div>
          </div>
        </Card>
      </section>

      <section className="space-y-4">
        <div className="flex items-end justify-between gap-4">
          <div>
            <div className="text-[22px] font-semibold tracking-[-0.03em] text-[var(--text-primary)]">自动引用评估</div>
            <div className="mt-1 text-[13px] text-[var(--text-secondary)]">这些条目来自 A4 抓取答案中的 citation 链接，是本次分析的默认置信度样本。</div>
          </div>
          <div className="inline-flex items-center gap-2 rounded-full border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-3 py-2 text-[12px] text-[var(--text-secondary)]">
            <RiCheckDoubleLine className="h-4 w-4" />
            {autoItems.length} 个自动来源
          </div>
        </div>

        {autoItems.length > 0 ? (
          <div className="space-y-4">
            {autoItems.map((item) => (
              <SignalCard key={item.item_id} item={item} />
            ))}
          </div>
        ) : (
          <Card
            padding="none"
            className="rounded-[24px] border bg-[var(--bg-tertiary)] p-6 text-[14px] leading-7 text-[var(--text-secondary)]"
            style={{ borderColor: 'var(--border-subtle)' }}
          >
            当前回答尚未识别到可用引用链接。你仍然可以在上方粘贴链接或文本，手动生成额外评估。
          </Card>
        )}
      </section>

      <section className="space-y-4">
        <div className="flex items-end justify-between gap-4">
          <div>
            <div className="text-[22px] font-semibold tracking-[-0.03em] text-[var(--text-primary)]">手动追加结果</div>
            <div className="mt-1 text-[13px] text-[var(--text-secondary)]">这里承接 artifact 内的额外评估结果，用户不需要回到 Chat 再切换模式。</div>
          </div>
          <div className="inline-flex items-center gap-2 rounded-full border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-3 py-2 text-[12px] text-[var(--text-secondary)]">
            <RiShieldCheckLine className="h-4 w-4" />
            {manualItems.length} 个手动项
          </div>
        </div>

        {manualItems.length > 0 ? (
          <div className="space-y-4">
            {manualItems.map((item) => (
              <SignalCard key={item.item_id} item={item} />
            ))}
          </div>
        ) : (
          <Card
            padding="none"
            className="rounded-[24px] border bg-[var(--bg-tertiary)] p-6"
            style={{ borderColor: 'var(--border-subtle)' }}
          >
            <div className="flex items-start gap-3">
              <div className="flex h-10 w-10 items-center justify-center rounded-2xl bg-amber-500/12 text-amber-100">
                <RiAlarmWarningLine className="h-5 w-5" />
              </div>
              <div>
                <div className="text-[16px] font-medium text-[var(--text-primary)]">还没有额外评估项</div>
                <div className="mt-2 text-[13px] leading-7 text-[var(--text-secondary)]">
                  你可以粘贴一个外部网页，或者直接粘贴一段需要评估的文本。系统会把结果追加到当前独立交付物里。
                </div>
              </div>
            </div>
          </Card>
        )}
      </section>
    </div>
  );
}
