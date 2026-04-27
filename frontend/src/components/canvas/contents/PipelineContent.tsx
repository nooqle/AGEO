'use client';

import { useState, useCallback } from 'react';
import { RiCheckLine } from '@remixicon/react';
import type { PipelineCanvasContent } from '@/types/canvas';
import type { PipelineData } from '@/types/touchpoint';
import { PersonaPipeline } from '@/components/touchpoints/PersonaPipeline';
import { useConversationStore } from '@/stores/conversationStore';
import { cn } from '@/lib/cn';

interface PipelineContentProps {
  content: PipelineCanvasContent;
}

export function PipelineContent({ content }: PipelineContentProps) {
  const [checkedIds, setCheckedIds] = useState<Set<string>>(new Set());
  const [isConfirmed, setIsConfirmed] = useState(false);
  const { pendingConfirmation, wsConfirmation: sendConfirmation } = useConversationStore();

  const pipeline: PipelineData | undefined = content.data.pipeline;
  const requestId = content.data.requestId || pendingConfirmation?.requestId || '';
  const maxSelection = content.data.maxSelection ?? 3;
  const minSelection = content.data.minSelection ?? 1;
  const canAct = !isConfirmed;

  const handleCheckChange = useCallback((nodeId: string, checked: boolean) => {
    if (isConfirmed) return;
    setCheckedIds((prev) => {
      const next = new Set(prev);
      if (checked) {
        if (next.size < maxSelection) next.add(nodeId);
      } else {
        next.delete(nodeId);
      }
      return next;
    });
  }, [isConfirmed, maxSelection]);

  const handleConfirm = () => {
    if (!sendConfirmation || checkedIds.size < minSelection) return;
    if (!pipeline) return;

    // Find selected profile node labels for downstream matching
    const profileCol = pipeline.columns.find((c) => c.key === 'profile');
    const selectedNames = profileCol
      ? profileCol.nodes.filter((n) => checkedIds.has(n.id)).map((n) => n.label)
      : [];

    sendConfirmation(requestId || '', {
      type: 'persona_path_selection',
      selectedPersonaIds: Array.from(checkedIds),
      selectedPersonaNames: selectedNames,
    });
    setIsConfirmed(true);
  };

  const handleSkip = () => {
    if (!sendConfirmation) return;
    sendConfirmation(requestId || '', {
      type: 'skip',
    });
    setIsConfirmed(true);
  };

  if (!pipeline) {
    return (
      <div className="flex items-center justify-center h-full">
        <span className="text-sm" style={{ color: 'var(--text-muted)' }}>暂无管道数据</span>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full">
      {/* Pipeline visualization */}
      <div className="flex-1 overflow-auto">
        <PersonaPipeline
          data={pipeline}
          selectionMode={!isConfirmed}
          checkedIds={checkedIds}
          onCheckChange={handleCheckChange}
        />
      </div>

      {/* Bottom action bar */}
      <div
        className="flex-shrink-0 px-4 pb-4 pt-3"
        style={{ borderTop: '1px solid var(--border-subtle)' }}
      >
        <div className="text-sm mb-3" style={{ color: 'var(--text-secondary)' }}>
          {isConfirmed ? (
            <span className="flex items-center gap-1.5">
              <RiCheckLine className="w-4 h-4 text-green-500" />
              已确认 {checkedIds.size} 个画像，正在生成模拟问题...
            </span>
          ) : (
            <>
              {checkedIds.size === 0
                ? `请在左侧画像列选择至少 ${minSelection} 个画像`
                : `已选择 ${checkedIds.size} / ${maxSelection} 个画像`}
            </>
          )}
        </div>

        {canAct && (
          <div className="flex gap-3">
            <button
              className={cn(
                'flex-1 py-2.5 rounded-lg text-sm font-medium transition-colors',
                checkedIds.size >= minSelection
                  ? 'bg-[var(--brand-primary)] text-[var(--brand-contrast)] hover:bg-[var(--brand-hover)]'
                  : 'bg-[var(--bg-tertiary)] text-[var(--text-secondary)] cursor-not-allowed'
              )}
              onClick={handleConfirm}
              disabled={checkedIds.size < minSelection}
            >
              {checkedIds.size >= minSelection
                ? `确认选择（${checkedIds.size}）`
                : '确认选择'}
            </button>
            <button
              className="py-2.5 px-4 rounded-lg text-sm font-medium bg-[var(--bg-secondary)] border border-[var(--border-subtle)] text-[var(--text-primary)] hover:bg-[var(--bg-tertiary)] transition-colors"
              onClick={handleSkip}
            >
              跳过此步
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
