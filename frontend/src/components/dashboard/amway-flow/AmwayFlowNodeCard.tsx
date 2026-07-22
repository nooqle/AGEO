'use client';

import {
  Handle,
  Position,
  type NodeProps,
} from '@xyflow/react';
import {
  ChartNoAxesColumn,
  CheckCircle2,
  Database,
  FileText,
  ListChecks,
  Orbit,
  PenLine,
  ScanSearch,
  Workflow,
} from 'lucide-react';
import { STATUS_TEXT } from './constants';
import type {
  AmwayFlowNode,
  AmwayFlowNodeData,
  CustomFlowNodeType,
  FlowNodeStatus,
} from './types';

export function flowNodeIcon(icon: string) {
  const props = { size: 15, 'aria-hidden': true as const };
  switch (icon) {
    case 'list':
      return <ListChecks {...props} />;
    case 'database':
      return <Database {...props} />;
    case 'workflow':
      return <Workflow {...props} />;
    case 'scan':
      return <ScanSearch {...props} />;
    case 'orbit':
      return <Orbit {...props} />;
    case 'file':
      return <FileText {...props} />;
    case 'chart':
      return <ChartNoAxesColumn {...props} />;
    case 'pen':
      return <PenLine {...props} />;
    default:
      return <Workflow {...props} />;
  }
}

/**
 * 节点图标底色角色（Wave A 色表）：
 * asset → brand teal soft；analysis → 石色/中性（禁止 violet）；content → 克制橙；其余中性。
 */
export function iconBadgeClass(variant: AmwayFlowNodeData['variant'] | CustomFlowNodeType): string {
  switch (variant) {
    case 'asset':
      return 'bg-[var(--brand-bg)] text-[var(--brand-primary)]';
    case 'analysis':
      return 'bg-[var(--bg-secondary)] text-[var(--text-secondary)] ring-1 ring-inset ring-[var(--border-subtle)]';
    case 'content':
      return 'bg-[rgba(249,115,22,0.12)] text-[rgb(194,65,12)] dark:text-[rgb(251,146,60)]';
    default:
      return 'bg-[var(--bg-secondary)] text-[var(--text-secondary)]';
  }
}

function statusDotClass(status: FlowNodeStatus): string {
  switch (status) {
    case 'active':
      return 'bg-[var(--brand-primary)] amway-flow-node-pulse';
    case 'done':
      return 'bg-[var(--brand-primary)]';
    case 'failed':
      return 'bg-[var(--error)]';
    case 'skipped':
      return 'bg-[var(--text-tertiary)] opacity-50';
    default:
      return 'bg-[var(--border-strong)]';
  }
}

function statusBarClass(status: FlowNodeStatus): string {
  switch (status) {
    case 'active':
      return 'bg-[var(--brand-primary)]';
    case 'done':
      return 'bg-[var(--brand-primary)] opacity-60';
    case 'failed':
      return 'bg-[var(--error)]';
    case 'skipped':
      return 'bg-[var(--text-tertiary)] opacity-40';
    default:
      return 'bg-transparent';
  }
}

export function AmwayFlowNodeCard({ id, data, selected }: NodeProps<AmwayFlowNode>) {
  const isPlatform = data.variant === 'platform';
  const disabled = data.enabled === false;
  const skipped = data.status === 'skipped';
  const plannedIdle = data.status === 'idle' && Boolean(data.planned);
  return (
    <div
      className={`group relative rounded-xl border bg-[var(--bg-primary)] text-left shadow-sm transition-all duration-150 hover:-translate-y-px hover:shadow-md ${
        selected
          ? 'border-[var(--brand-primary)]'
          : plannedIdle
            ? 'border-[var(--brand-primary)]/45 hover:border-[var(--brand-primary)]'
            : 'border-[var(--border-subtle)] hover:border-[var(--border-strong)]'
      } ${isPlatform ? 'w-[148px] px-3 py-2' : 'w-[208px] px-3.5 py-3'} ${disabled || skipped ? 'opacity-45' : ''}`}
    >
      <Handle type="target" position={Position.Left} className="!h-2 !w-2 !border-0 !bg-[var(--border-strong)]" />
      <span
        aria-hidden="true"
        className={`absolute left-0 top-2.5 bottom-2.5 w-[3px] rounded-full ${statusBarClass(data.status)}`}
      />
      {data.status === 'done' && !isPlatform ? (
        <CheckCircle2
          size={14}
          aria-hidden="true"
          className="absolute -right-1.5 -top-1.5 rounded-full bg-[var(--bg-primary)] text-[var(--brand-primary)]"
        />
      ) : null}
      <div className="flex items-center gap-2">
        <span
          className={`flex shrink-0 items-center justify-center rounded-lg ${
            iconBadgeClass(data.variant)
          } ${isPlatform ? '!h-5 !w-5' : 'h-7 w-7'}`}
        >
          {flowNodeIcon(data.icon)}
        </span>
        <div className="min-w-0 flex-1">
          <div className={`font-semibold text-[var(--text-primary)] ${isPlatform ? 'text-xs' : 'text-sm'}`}>
            {data.label}
          </div>
          {!isPlatform && data.subtitle ? (
            <div className="mt-0.5 truncate text-[11px] tabular-nums text-[var(--text-tertiary)]">{data.subtitle}</div>
          ) : null}
        </div>
        {isPlatform && data.onToggle ? (
          <button
            type="button"
            role="switch"
            aria-checked={!disabled}
            aria-label={`${data.label} 采集开关`}
            title={disabled ? '已停用，下一轮不采集该平台' : '已启用'}
            onClick={(event) => {
              event.stopPropagation();
              data.onToggle?.(id);
            }}
            className={`relative h-4 w-7 shrink-0 rounded-full transition-colors ${
              disabled ? 'bg-[var(--border-strong)]' : 'bg-[var(--brand-primary)]'
            }`}
          >
            <span
              className={`absolute top-0.5 h-3 w-3 rounded-full bg-white shadow transition-all ${
                disabled ? 'left-0.5' : 'left-3.5'
              }`}
            />
          </button>
        ) : (
          <span className={`h-2 w-2 shrink-0 rounded-full ${statusDotClass(data.status)}`} title={STATUS_TEXT[data.status]} />
        )}
      </div>
      {!isPlatform && data.outputs.length ? (
        <div className="mt-2 flex flex-wrap gap-1">
          {data.outputs.map((output) => (
            <button
              key={output.key}
              type="button"
              disabled={output.disabled}
              onClick={(event) => {
                event.stopPropagation();
                data.onOutput?.(id, output.key);
              }}
              className="rounded-full border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-2 py-0.5 text-[10px] font-medium text-[var(--text-secondary)] transition-all hover:scale-105 hover:border-[var(--brand-primary)] hover:text-[var(--brand-primary)] disabled:cursor-not-allowed disabled:opacity-40 disabled:hover:scale-100 disabled:hover:border-[var(--border-subtle)] disabled:hover:text-[var(--text-secondary)]"
            >
              {output.label}
              {typeof output.count === 'number' && output.count > 0 ? ` ${output.count}` : ''}
            </button>
          ))}
        </div>
      ) : null}
      <Handle type="source" position={Position.Right} className="!h-2 !w-2 !border-0 !bg-[var(--border-strong)]" />
    </div>
  );
}

