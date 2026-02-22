'use client';

import { memo, useState, useRef, useEffect } from 'react';
import { Handle, Position, type Node, type NodeProps } from '@xyflow/react';
import { motion } from 'framer-motion';
import {
  RiBuilding2Line,
  RiUserLine,
  RiCompass3Line,
  RiTargetLine,
  RiFlashlightLine,
} from '@remixicon/react';
import { cn } from '@/lib/cn';

const NODE_STYLES: Record<
  string,
  { bg: string; border: string; iconColor: string; accentColor: string; icon: React.ComponentType<{ className?: string }> }
> = {
  brand: {
    bg: 'bg-[#6366F1]/10',
    border: 'border-[#6366F1]/30',
    iconColor: 'text-[#6366F1]',
    accentColor: '#6366F1',
    icon: RiBuilding2Line,
  },
  profile: {
    bg: 'bg-[#8B5CF6]/10',
    border: 'border-[#8B5CF6]/30',
    iconColor: 'text-[#8B5CF6]',
    accentColor: '#8B5CF6',
    icon: RiUserLine,
  },
  scenario: {
    bg: 'bg-[#06B6D4]/10',
    border: 'border-[#06B6D4]/30',
    iconColor: 'text-[#06B6D4]',
    accentColor: '#06B6D4',
    icon: RiCompass3Line,
  },
  intent: {
    bg: 'bg-[#F59E0B]/10',
    border: 'border-[#F59E0B]/30',
    iconColor: 'text-[#F59E0B]',
    accentColor: '#F59E0B',
    icon: RiTargetLine,
  },
  optimization: {
    bg: 'bg-[#22C55E]/10',
    border: 'border-[#22C55E]/30',
    iconColor: 'text-[#22C55E]',
    accentColor: '#22C55E',
    icon: RiFlashlightLine,
  },
};

const CHILD_LABELS: Record<string, string> = {
  brand: '画像',
  profile: '场景',
  scenario: '意图',
  intent: '优化项',
};

interface TouchpointNodeData {
  label: string;
  nodeType: string;
  description?: string;
  isSelected?: boolean;
  hasData?: boolean;
  isSelectable?: boolean;
  isChecked?: boolean;
  isNew?: boolean;
  childCount?: number;
  tags?: string[];
  direction?: 'TB' | 'LR';
  metrics?: {
    visibility?: number;
    prompts?: number;
    articles?: number;
  };
  onFocus?: (nodeId: string) => void;
  onChatAnalysis?: (label: string) => void;
  onViewDetails?: (nodeId: string) => void;
  [key: string]: unknown;
}

type TouchpointNode = Node<TouchpointNodeData, 'touchpoint'>;

function truncate(text: string, maxLen: number): string {
  if (text.length <= maxLen) return text;
  return text.slice(0, maxLen) + '...';
}

function TouchpointNodeCardInner({ id, data }: NodeProps<TouchpointNode>) {
  const style = NODE_STYLES[data.nodeType] || NODE_STYLES.brand;
  const Icon = style.icon;
  const hasData = data.hasData !== false;
  const metrics = data.metrics;
  const direction = (data.direction as 'TB' | 'LR') || 'LR';
  const targetPos = direction === 'LR' ? Position.Left : Position.Top;
  const sourcePos = direction === 'LR' ? Position.Right : Position.Bottom;
  const childCount = (data.childCount as number) ?? 0;
  const tags = (data.tags as string[] | undefined)?.slice(0, 2);
  const [menuOpen, setMenuOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);

  // Close menu when clicking outside
  useEffect(() => {
    if (!menuOpen) return;
    const handler = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as HTMLElement)) {
        setMenuOpen(false);
      }
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, [menuOpen]);

  const onFocus = data.onFocus as ((nodeId: string) => void) | undefined;
  const onChatAnalysis = data.onChatAnalysis as ((label: string) => void) | undefined;
  const onViewDetails = data.onViewDetails as ((nodeId: string) => void) | undefined;

  const cardContent = (
    <div
      className={cn(
        'group rounded-xl border overflow-visible',
        style.bg,
        style.border,
        data.isSelected && 'ring-2 ring-[#6366F1]',
        data.isChecked && 'border-indigo-500',
        'min-w-[180px] max-w-[260px] transition-all hover:shadow-lg cursor-pointer relative'
      )}
    >
      {/* Left accent bar */}
      <div
        className="absolute left-0 top-0 bottom-0 w-[2px] rounded-l-xl"
        style={{ backgroundColor: style.accentColor }}
      />

      <div className="px-3 py-2 pl-3.5">
        <Handle type="target" position={targetPos} className="!bg-[--border-default] !w-2 !h-2 !border-0" />

        {/* Selectable checkbox */}
        {data.isSelectable && (
          <div className="absolute top-2 left-3.5 z-10">
            <div
              className={cn(
                'w-4 h-4 rounded-full border-2 flex items-center justify-center cursor-pointer transition-colors',
                data.isChecked
                  ? 'border-indigo-500 bg-indigo-500'
                  : 'border-[--border-default] bg-transparent hover:border-[--border-hover]'
              )}
            >
              {data.isChecked && (
                <svg width="10" height="10" viewBox="0 0 10 10" fill="none">
                  <path d="M2 5L4 7L8 3" stroke="white" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
                </svg>
              )}
            </div>
          </div>
        )}

        {/* Status indicator dot */}
        <div
          className={`absolute top-1.5 right-1.5 w-2 h-2 rounded-full ${
            hasData ? 'bg-[#22C55E]' : 'bg-[--border-hover]'
          }`}
          title={hasData ? '有数据' : '无数据'}
        />

        {/* More menu button (hover) */}
        {!data.isSelectable && (
          <div ref={menuRef} className="absolute top-1 right-4 z-20">
            <button
              onClick={(e) => {
                e.stopPropagation();
                setMenuOpen((prev) => !prev);
              }}
              className="w-5 h-5 flex items-center justify-center rounded text-[--text-disabled] hover:text-[--text-secondary] hover:bg-black/5 opacity-0 group-hover:opacity-100 transition-opacity"
            >
              <svg width="12" height="12" viewBox="0 0 12 12" fill="currentColor">
                <circle cx="2" cy="6" r="1.2" />
                <circle cx="6" cy="6" r="1.2" />
                <circle cx="10" cy="6" r="1.2" />
              </svg>
            </button>
            {menuOpen && (
              <div className="absolute right-0 top-6 w-28 rounded-lg border border-[--border-default] bg-[--bg-secondary] shadow-xl py-1 z-30">
                {childCount > 0 && onFocus && (
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      setMenuOpen(false);
                      onFocus(id);
                    }}
                    className="w-full text-left px-3 py-1.5 text-[11px] text-[--text-primary] hover:bg-white/5 transition-colors"
                  >
                    聚焦此节点
                  </button>
                )}
                {onChatAnalysis && (
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      setMenuOpen(false);
                      onChatAnalysis(data.label);
                    }}
                    className="w-full text-left px-3 py-1.5 text-[11px] text-[--text-primary] hover:bg-white/5 transition-colors"
                  >
                    对话分析
                  </button>
                )}
                {onViewDetails && (
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      setMenuOpen(false);
                      onViewDetails(id);
                    }}
                    className="w-full text-left px-3 py-1.5 text-[11px] text-[--text-primary] hover:bg-white/5 transition-colors"
                  >
                    查看详情
                  </button>
                )}
              </div>
            )}
          </div>
        )}

        {/* Header: icon + label */}
        <div className={cn('flex items-center gap-2 pr-3', data.isSelectable && 'pl-5')}>
          <Icon className={`w-4 h-4 ${style.iconColor} flex-shrink-0`} />
          <span className="text-xs font-medium text-[--text-primary] truncate">
            {data.label}
          </span>
        </div>

        {/* Description (15 char limit) */}
        {data.description && (
          <p className={cn('text-[10px] text-[--text-tertiary] mt-1 truncate', data.isSelectable && 'pl-5')}>
            {truncate(data.description, 15)}
          </p>
        )}

        {/* Tags (max 2 pills) */}
        {tags && tags.length > 0 && (
          <div className="flex items-center gap-1 mt-1.5">
            {tags.map((tag) => (
              <span
                key={tag}
                className="inline-block px-1.5 py-0.5 text-[9px] rounded-full bg-white/5 text-[--text-secondary] truncate max-w-[80px]"
              >
                {tag}
              </span>
            ))}
          </div>
        )}

        {/* Child count indicator */}
        {childCount > 0 && (
          <div className="mt-1.5">
            <span className="text-[10px] text-[--text-disabled]">
              {childCount}个{CHILD_LABELS[data.nodeType] || '子项'}
            </span>
          </div>
        )}

        {/* Bottom metrics bar */}
        {metrics && (
          <div className="flex items-center gap-2 mt-2 pt-1.5 border-t border-white/5">
            {metrics.visibility !== undefined && (
              <span className="text-[9px] text-[--text-secondary]" title="可见度">
                <span className="text-[#6366F1] font-medium">{metrics.visibility}</span> vis
              </span>
            )}
            {metrics.prompts !== undefined && (
              <span className="text-[9px] text-[--text-secondary]" title="提示词">
                <span className="text-[#8B5CF6] font-medium">{metrics.prompts}</span> prm
              </span>
            )}
            {metrics.articles !== undefined && (
              <span className="text-[9px] text-[--text-secondary]" title="文章">
                <span className="text-[#06B6D4] font-medium">{metrics.articles}</span> art
              </span>
            )}
          </div>
        )}

        <Handle type="source" position={sourcePos} className="!bg-[--border-default] !w-2 !h-2 !border-0" />
      </div>
    </div>
  );

  // Wrap with motion.div for new node entrance animation
  if (data.isNew) {
    return (
      <motion.div
        initial={{ scale: 0.8, opacity: 0 }}
        animate={{ scale: 1, opacity: 1 }}
        transition={{ duration: 0.3, ease: [0.4, 0, 0.2, 1] }}
      >
        {cardContent}
      </motion.div>
    );
  }

  return cardContent;
}

export const TouchpointNodeCard = memo(TouchpointNodeCardInner);
