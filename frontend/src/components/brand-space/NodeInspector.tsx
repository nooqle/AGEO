'use client';

import { FileText, SlidersHorizontal, TerminalSquare, Timer } from 'lucide-react';
import type { ArtifactRef, BoardNode, InspectorTab, RuntimeEvent } from '@/types/brandSpace';

interface NodeInspectorProps {
  node: BoardNode;
  artifacts: ArtifactRef[];
  events: RuntimeEvent[];
  activeTab: InspectorTab;
  onTabChange: (tab: InspectorTab) => void;
}

const tabs: Array<{ id: InspectorTab; label: string }> = [
  { id: 'overview', label: '概览' },
  { id: 'events', label: '事件' },
  { id: 'output', label: '输出' },
  { id: 'config', label: '配置' },
];

const statusLabels: Record<BoardNode['status'], string> = {
  idle: '未开始',
  queued: '排队中',
  running: '运行中',
  paused: '已暂停',
  completed: '已完成',
  needs_review: '待审阅',
  failed: '失败',
};

const nodeKindLabels: Record<BoardNode['kind'], string> = {
  input: '输入',
  prepare: '准备',
  fetch: '抓取',
  extract: '抽取',
  review: '审阅',
  graph_update: '图谱更新',
};

const artifactTypeLabels: Record<string, string> = {
  entity_lexicon: '实体词表',
  question_set: '问题集',
  raw_answers: '原始答案',
  parsed_answers: '标准化回答',
  entity_relation_set: '实体关系集',
  graph_patch_set: '图谱补丁集',
  graph_update: '图谱更新',
  graph_patch: '图谱补丁',
  report: '报告',
};

const eventTypeLabels: Record<string, string> = {
  started: '开始',
  progress: '进度',
  artifact: '产物',
  warning: '提醒',
  review: '审阅',
  graph_patch: '图谱补丁',
  run_started: '运行启动',
  artifact_written: '资产写入',
  node_progress: '节点进度',
  graph_patch_needs_review: '图谱补丁待审',
};

export function NodeInspector({ node, artifacts, events, activeTab, onTabChange }: NodeInspectorProps) {
  const nodeArtifacts = artifacts.filter((artifact) => node.outputArtifactIds.includes(artifact.id));
  const nodeEvents = events.filter((event) => !event.nodeId || event.nodeId === node.id);

  return (
    <aside className="flex min-h-0 flex-col border-l bg-[var(--bg-secondary)]" style={{ borderColor: 'var(--border-subtle)' }}>
      <div className="border-b p-5" style={{ borderColor: 'var(--border-subtle)' }}>
        <div className="flex items-start justify-between gap-3">
          <div>
            <p className="text-xs font-medium uppercase text-[var(--text-tertiary)]">节点检查器</p>
            <h2 className="mt-2 text-lg font-semibold text-[var(--text-primary)]">{node.title}</h2>
            <p className="mt-1 text-sm text-[var(--text-secondary)]">{node.subtitle}</p>
          </div>
          <span className="rounded-lg border px-2 py-1 text-xs font-medium capitalize" style={{ borderColor: 'var(--brand-border)', color: 'var(--brand-text)', background: 'var(--brand-bg)' }}>
            {statusLabels[node.status]}
          </span>
        </div>

        <div className="mt-4 grid grid-cols-4 gap-1 rounded-lg bg-[var(--bg-tertiary)] p-1">
          {tabs.map((tab) => (
            <button
              key={tab.id}
              type="button"
              onClick={() => onTabChange(tab.id)}
              className="rounded-md px-2 py-2 text-xs font-medium transition-colors"
              style={{
                background: activeTab === tab.id ? 'var(--bg-elevated)' : 'transparent',
                color: activeTab === tab.id ? 'var(--text-primary)' : 'var(--text-tertiary)',
              }}
            >
              {tab.label}
            </button>
          ))}
        </div>
      </div>

      <div className="min-h-0 flex-1 overflow-auto p-5">
        {activeTab === 'overview' ? (
          <div className="space-y-4">
            <div>
              <div className="mb-2 flex items-center justify-between text-xs">
                <span className="text-[var(--text-tertiary)]">进度</span>
                <span className="font-semibold text-[var(--text-primary)]">{node.progress}%</span>
              </div>
              <div className="h-2 rounded-full bg-[var(--bg-tertiary)]">
                <div className="h-full rounded-full bg-[var(--brand-primary)]" style={{ width: `${node.progress}%` }} />
              </div>
            </div>

            <div className="grid grid-cols-2 gap-3">
              {node.metrics.map((metric) => (
                <div key={metric.label} className="rounded-xl border p-3" style={{ borderColor: 'var(--border-subtle)', background: 'var(--bg-elevated)' }}>
                  <p className="text-xs text-[var(--text-tertiary)]">{metric.label}</p>
                  <p className="mt-1 text-sm font-semibold text-[var(--text-primary)]">{metric.value}</p>
                </div>
              ))}
            </div>

            <div className="rounded-xl border p-3" style={{ borderColor: 'var(--border-subtle)' }}>
              <div className="flex items-center gap-2 text-xs font-medium text-[var(--text-secondary)]">
                <Timer className="h-3.5 w-3.5" />
                运行策略
              </div>
              <p className="mt-2 text-xs leading-5 text-[var(--text-tertiary)]">
                节点状态由真实运行事件驱动；图谱补丁、审阅结果和报告产物由后端写入并保留追溯。
              </p>
            </div>
          </div>
        ) : null}

        {activeTab === 'events' ? (
          <div className="space-y-3">
            {nodeEvents.map((event) => (
              <div key={event.id} className="rounded-xl border p-3" style={{ borderColor: 'var(--border-subtle)', background: 'var(--bg-elevated)' }}>
                <div className="flex items-center justify-between gap-3">
                  <span className="text-xs font-medium text-[var(--text-primary)]">{eventTypeLabels[event.type] ?? event.type}</span>
                  <span className="text-xs text-[var(--text-tertiary)]">{event.timestamp}</span>
                </div>
                <p className="mt-2 text-xs leading-5 text-[var(--text-secondary)]">{event.message}</p>
              </div>
            ))}
          </div>
        ) : null}

        {activeTab === 'output' ? (
          <div className="space-y-3">
            {nodeArtifacts.map((artifact) => (
              <div key={artifact.id} className="rounded-xl border p-3" style={{ borderColor: 'var(--border-subtle)', background: 'var(--bg-elevated)' }}>
                <div className="flex items-center gap-2">
                  <FileText className="h-4 w-4 text-[var(--brand-primary)]" />
                  <span className="text-sm font-semibold text-[var(--text-primary)]">{artifact.label}</span>
                </div>
                <p className="mt-2 break-all text-xs leading-5 text-[var(--text-tertiary)]">{artifact.path}</p>
                <div className="mt-3 flex items-center justify-between text-xs text-[var(--text-secondary)]">
                  <span>{artifactTypeLabels[artifact.type] ?? artifact.type}</span>
                  <span>{artifact.rowCount ?? 1} 行</span>
                </div>
              </div>
            ))}
          </div>
        ) : null}

        {activeTab === 'config' ? (
          <div className="space-y-3">
            <div className="rounded-xl border p-3" style={{ borderColor: 'var(--border-subtle)', background: 'var(--bg-elevated)' }}>
              <div className="flex items-center gap-2">
                <SlidersHorizontal className="h-4 w-4 text-[var(--brand-primary)]" />
                <span className="text-sm font-semibold text-[var(--text-primary)]">节点契约</span>
              </div>
              <dl className="mt-3 space-y-2 text-xs">
                <div className="flex justify-between gap-3">
                  <dt className="text-[var(--text-tertiary)]">节点类型</dt>
                  <dd className="font-medium text-[var(--text-primary)]">{nodeKindLabels[node.kind]}</dd>
                </div>
                <div className="flex justify-between gap-3">
                  <dt className="text-[var(--text-tertiary)]">结构版本</dt>
                  <dd className="font-medium text-[var(--text-primary)]">v0.1</dd>
                </div>
                <div className="flex justify-between gap-3">
                  <dt className="text-[var(--text-tertiary)]">写入方式</dt>
                  <dd className="font-medium text-[var(--text-primary)]">事件驱动</dd>
                </div>
              </dl>
            </div>
            <div className="rounded-xl border p-3" style={{ borderColor: 'var(--border-subtle)' }}>
              <div className="flex items-center gap-2 text-xs font-medium text-[var(--text-secondary)]">
                <TerminalSquare className="h-3.5 w-3.5" />
                运行说明
              </div>
              <p className="mt-2 text-xs leading-5 text-[var(--text-tertiary)]">
                运行中调整配置只影响后续调度。已经保存的输出保持不可变。
              </p>
            </div>
          </div>
        ) : null}
      </div>
    </aside>
  );
}
