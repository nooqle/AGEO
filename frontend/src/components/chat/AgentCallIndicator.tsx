'use client';

import { RiRobotLine, RiLoader4Line, RiCheckLine, RiCloseLine } from '@remixicon/react';
import { cn } from '@/lib/cn';

export type AgentStatus = 'running' | 'completed' | 'error';

export interface AgentCall {
  id: string;
  agentName: string;
  agentCode?: string;
  input: Record<string, unknown>;
  status: AgentStatus;
  output?: unknown;
  error?: string;
  startTime?: string;
  endTime?: string;
}

interface AgentCallIndicatorProps {
  call: AgentCall;
  showInput?: boolean;
  className?: string;
}

// Agent 名称映射
const agentNameMap: Record<string, string> = {
  'A1': '品牌档案分析',
  'A2': '用户画像分析',
  'A3': '问题生成',
  'A4': '答案抓取',
  'A5': '报告生成',
  'BrandCompetitionAgent': '品牌档案分析',
  'MarketingPersonaAgent': '用户画像分析',
  'QuestionSimulationAgent': '问题生成',
  'FetchAgent': '答案抓取',
  'DataAnalyticsAgent': '报告生成',
};

function looksInternalAgentLabel(label?: string): boolean {
  if (!label) return false;
  if (/^A\d+$/i.test(label)) return true;
  return /(BrandCompetitionAgent|MarketingPersonaAgent|QuestionSimulationAgent|FetchAgent|DataAnalyticsAgent)/i.test(
    label
  );
}

function resolveAgentDisplayName(call: AgentCall): string {
  const byCode = agentNameMap[call.agentCode || ''];
  if (byCode) return byCode;

  const byName = agentNameMap[call.agentName];
  if (byName) return byName;

  if (looksInternalAgentLabel(call.agentName)) {
    return '分析助手';
  }

  return call.agentName || '分析助手';
}

// 状态配置
const statusConfig = {
  running: {
    icon: RiLoader4Line,
    iconClass: 'text-[#F59E0B] animate-spin',
    bgClass: 'bg-[#F59E0B15]',
    borderClass: 'border-[#F59E0B30]',
    label: '运行中',
    labelClass: 'text-[#F59E0B]',
  },
  completed: {
    icon: RiCheckLine,
    iconClass: 'text-[#22C55E]',
    bgClass: 'bg-[#22C55E15]',
    borderClass: 'border-[#22C55E30]',
    label: '已完成',
    labelClass: 'text-[#22C55E]',
  },
  error: {
    icon: RiCloseLine,
    iconClass: 'text-[#EF4444]',
    bgClass: 'bg-[#EF444415]',
    borderClass: 'border-[#EF444430]',
    label: '执行出错',
    labelClass: 'text-[#EF4444]',
  },
};

// 格式化输入参数显示
function formatInput(input: Record<string, unknown>): string {
  const entries = Object.entries(input);
  if (entries.length === 0) return '无输入参数';
  
  return entries
    .map(([key, value]) => {
      let displayValue: string;
      if (typeof value === 'string') {
        displayValue = value.length > 30 ? `${value.slice(0, 30)}...` : value;
      } else if (Array.isArray(value)) {
        displayValue = `[${value.length} 项]`;
      } else if (typeof value === 'object' && value !== null) {
        displayValue = '{...}';
      } else {
        displayValue = String(value);
      }
      return `${key}=${displayValue}`;
    })
    .join(', ');
}

export function AgentCallIndicator({
  call,
  showInput = true,
  className,
}: AgentCallIndicatorProps) {
  const config = statusConfig[call.status];
  const Icon = config.icon;
  const displayName = resolveAgentDisplayName(call);

  return (
    <div
      className={cn(
        'rounded-lg overflow-hidden border',
        'bg-[var(--bg-elevated)]',
        config.borderClass,
        className
      )}
    >
      {/* 头部 */}
      <div className="px-4 py-3 flex items-center justify-between">
        <div className="flex items-center gap-3">
          {/* Agent 图标 */}
          <div
            className={cn(
              'w-7 h-7 rounded-lg flex items-center justify-center',
              config.bgClass
            )}
          >
            {call.status === 'running' ? (
              <Icon className={cn('w-4 h-4', config.iconClass)} />
            ) : (
              <RiRobotLine className={cn('w-4 h-4', config.iconClass)} />
            )}
          </div>

          {/* Agent 名称 */}
          <div>
            <span className="text-sm font-medium text-[var(--text-primary)]">
              {displayName}
            </span>
          </div>
        </div>

        {/* 状态标签 */}
        <div className="flex items-center gap-2">
          {call.status === 'running' && (
            <Icon className={cn('w-4 h-4', config.iconClass)} />
          )}
          <span className={cn('text-xs font-medium', config.labelClass)}>
            {config.label}
          </span>
        </div>
      </div>

      {/* 输入参数 */}
      {showInput && Object.keys(call.input).length > 0 && (
        <div className="px-4 py-2 bg-[var(--bg-primary)] border-t border-[var(--border-subtle)]">
          <div className="text-xs text-[var(--text-tertiary)]">
            <span className="text-[var(--text-disabled)]">输入: </span>
            <code className="text-[var(--text-secondary)] font-mono">
              {formatInput(call.input)}
            </code>
          </div>
        </div>
      )}

      {/* 错误信息 */}
      {call.status === 'error' && call.error && (
        <div className="px-4 py-2 bg-[#EF444410] border-t border-[#EF444430]">
          <div className="text-xs text-[#EF4444]">
            错误: {call.error}
          </div>
        </div>
      )}
    </div>
  );
}

// Agent 调用列表（用于展示多个 Agent 调用）
interface AgentCallListProps {
  calls: AgentCall[];
  title?: string;
  className?: string;
}

export function AgentCallList({
  calls,
  title = '执行步骤',
  className,
}: AgentCallListProps) {
  const runningCount = calls.filter(c => c.status === 'running').length;
  const completedCount = calls.filter(c => c.status === 'completed').length;

  return (
    <div className={cn('bg-[var(--bg-primary)] rounded-lg border border-[var(--border-subtle)] overflow-hidden', className)}>
      {/* 头部 */}
      <div className="px-4 py-3 border-b border-[var(--border-subtle)]">
        <div className="flex items-center justify-between">
          <span className="text-sm font-medium text-[var(--text-primary)]">{title}</span>
          <div className="flex items-center gap-3 text-xs">
            {runningCount > 0 && (
              <span className="text-[#F59E0B]">
                {runningCount} 运行中
              </span>
            )}
            <span className="text-[#22C55E]">
              {completedCount}/{calls.length} 完成
            </span>
          </div>
        </div>
      </div>

      {/* 列表 */}
      <div className="p-2 space-y-2">
        {calls.map((call) => (
          <AgentCallIndicator
            key={call.id}
            call={call}
            showInput={false}
          />
        ))}
      </div>
    </div>
  );
}

export default AgentCallIndicator;
