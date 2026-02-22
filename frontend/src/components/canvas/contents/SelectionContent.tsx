'use client';

import { useState } from 'react';
import { motion } from 'framer-motion';
import { RiStarLine, RiCheckLine } from '@remixicon/react';
import type { PersonaSelectionItem, SelectionCanvasContent } from '@/types/canvas';
import { useConversationStore } from '@/stores/conversationStore';
import { selectionCardVariants } from '@/lib/animations';
import { cn } from '@/lib/cn';
import { getCircledNumber } from '@/lib/utils';

interface SelectionContentProps {
  content: SelectionCanvasContent;
}

const PRIORITY_CONFIG: Record<string, { label: string; color: string }> = {
  core: { label: '核心人群', color: '#EF4444' },
  growth: { label: '增长人群', color: '#F59E0B' },
  opportunity: { label: '机会人群', color: '#22C55E' },
};

const PRIORITY_ORDER: Array<'core' | 'growth' | 'opportunity' | 'other'> = [
  'core',
  'growth',
  'opportunity',
  'other',
];

function groupByPriority(personas: PersonaSelectionItem[]) {
  const groups: Record<string, PersonaSelectionItem[]> = {};
  for (const persona of personas) {
    const key = persona.priority || 'other';
    if (!groups[key]) groups[key] = [];
    groups[key].push(persona);
  }
  return groups;
}

export function SelectionContent({ content }: SelectionContentProps) {
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [isConfirmed, setIsConfirmed] = useState(false);
  const { pendingConfirmation, wsConfirmation: sendConfirmation } = useConversationStore();

  const personas: PersonaSelectionItem[] = content.data.personas ?? [];
  const maxSelection = content.data.maxSelection ?? 3;
  const minSelection = content.data.minSelection ?? 1;

  // Check if any persona has a priority — if so, render grouped
  const hasPriority = personas.some((p) => p.priority);

  // Toggle selection
  const toggleSelection = (id: string) => {
    if (isConfirmed) return;
    const newSelected = new Set(selectedIds);
    if (newSelected.has(id)) {
      newSelected.delete(id);
    } else if (newSelected.size < maxSelection) {
      newSelected.add(id);
    }
    setSelectedIds(newSelected);
  };

  // Confirm selection
  const handleConfirm = () => {
    if (!pendingConfirmation || !sendConfirmation || selectedIds.size < minSelection) return;

    const selectedPersonas = personas.filter((p) => selectedIds.has(p.id));
    sendConfirmation(pendingConfirmation.requestId, {
      type: 'persona_path_selection',
      selectedPersonaIds: Array.from(selectedIds),
      selectedPersonaNames: selectedPersonas.map((p) => p.name),
    });
    setIsConfirmed(true);
  };

  // Skip
  const handleSkip = () => {
    if (!pendingConfirmation || !sendConfirmation) return;
    sendConfirmation(pendingConfirmation.requestId, {
      type: 'skip',
    });
    setIsConfirmed(true);
  };

  const description = content.data.description;
  const estimatedTime = content.data.estimatedTime;

  const renderPersonaCard = (persona: PersonaSelectionItem, index: number) => {
    const priorityColor = persona.priority
      ? PRIORITY_CONFIG[persona.priority]?.color
      : 'var(--text-tertiary)';

    return (
      <motion.button
        key={persona.id}
        className={cn(
          'w-full text-left rounded-lg border transition-all',
          isConfirmed && !selectedIds.has(persona.id) && 'opacity-30 scale-[0.98]',
          selectedIds.has(persona.id)
            ? 'border-indigo-500 bg-indigo-500/10'
            : 'border-[--border-default] bg-[--bg-secondary] hover:border-[--border-hover] hover:bg-[--bg-tertiary]'
        )}
        style={{
          borderLeftWidth: '3px',
          borderLeftColor: priorityColor,
        }}
        variants={selectionCardVariants}
        initial="unselected"
        animate={selectedIds.has(persona.id) ? 'selected' : 'unselected'}
        onClick={() => toggleSelection(persona.id)}
        disabled={isConfirmed}
      >
        <div className="p-4">
          <div className="flex items-start gap-3">
            {/* Checkbox */}
            <div className={cn(
              'w-6 h-6 rounded border-2 flex items-center justify-center flex-shrink-0 mt-0.5',
              selectedIds.has(persona.id)
                ? 'border-indigo-500 bg-indigo-500'
                : 'border-[--border-hover]'
            )}>
              {selectedIds.has(persona.id) && (
                <RiCheckLine className="w-4 h-4 text-white" />
              )}
            </div>

            {/* Content */}
            <div className="flex-1">
              <div className="flex items-center gap-2 mb-1">
                {persona.emoji && <span className="text-lg">{persona.emoji}</span>}
                <span className="font-medium text-[--text-primary]">
                  {getCircledNumber(index + 1)} {persona.name}
                </span>

                {/* Stars — only show if recommendationScore is provided */}
                {typeof persona.recommendationScore === 'number' && persona.recommendationScore > 0 && (
                  <div className="flex items-center gap-0.5 ml-auto">
                    {Array.from({ length: 5 }).map((_, i) => (
                      <RiStarLine
                        key={i}
                        className={cn(
                          'w-3 h-3',
                          i < persona.recommendationScore
                            ? 'text-amber-400 fill-amber-400'
                            : 'text-[--border-hover]'
                        )}
                      />
                    ))}
                  </div>
                )}
              </div>

              <p className="text-sm text-[--text-secondary] mb-2">
                {persona.ageRange ? `${persona.ageRange} | ` : ''}{persona.description}
              </p>

              {/* Scenario tags */}
              {persona.scenarios && persona.scenarios.length > 0 && (
                <div className="flex flex-wrap gap-1.5 mb-2">
                  {persona.scenarios.slice(0, 3).map((scenario, si) => (
                    <span
                      key={si}
                      className="text-xs px-2 py-0.5 rounded-full bg-blue-500/10 text-[--text-secondary]"
                    >
                      {scenario}
                    </span>
                  ))}
                </div>
              )}

              {/* Related weakness */}
              {persona.relatedWeakness && (
                <div className="text-xs text-amber-500 bg-amber-500/10 border border-amber-500/20 px-2 py-1 rounded inline-block">
                  关联薄弱点：{persona.relatedWeakness}
                </div>
              )}

              {/* Recommendation reason */}
              {persona.recommendationReason && (
                <p className="text-xs text-[--text-secondary] mt-2">
                  {persona.recommendationReason}
                </p>
              )}
            </div>
          </div>
        </div>
      </motion.button>
    );
  };

  const renderGroupedList = () => {
    const groups = groupByPriority(personas);
    let globalIndex = 0;

    return (
      <div className="space-y-4">
        {PRIORITY_ORDER.map((priorityKey) => {
          const items = groups[priorityKey];
          if (!items || items.length === 0) return null;

          const config = PRIORITY_CONFIG[priorityKey];

          return (
            <div key={priorityKey}>
              {config && (
                <div className="flex items-center gap-2 mb-2">
                  <div
                    className="w-2 h-2 rounded-full"
                    style={{ backgroundColor: config.color }}
                  />
                  <span className="text-xs uppercase tracking-wider text-[--text-tertiary]">
                    {config.label}
                  </span>
                </div>
              )}
              <div className="space-y-3">
                {items.map((persona) => {
                  const idx = globalIndex++;
                  return renderPersonaCard(persona, idx);
                })}
              </div>
            </div>
          );
        })}
      </div>
    );
  };

  const renderFlatList = () => (
    <div className="space-y-3">
      {personas.map((persona, index) => renderPersonaCard(persona, index))}
    </div>
  );

  return (
    <div className="flex flex-col h-full">
      {/* 可滚动内容区 */}
      <div className="flex-1 overflow-y-auto px-4 pt-4 pb-2">
        {/* Description */}
        {description && (
          <p className="text-sm text-[--text-secondary] mb-4">
            {description}
          </p>
        )}

        {/* Persona list */}
        {hasPriority ? renderGroupedList() : renderFlatList()}
      </div>

      {/* 底部固定区（不随卡片列表滚动）*/}
      <div
        className="flex-shrink-0 px-4 pb-4 pt-3"
        style={{ borderTop: '1px solid var(--border-default)' }}
      >
        {/* Selection count */}
        <div className="text-sm mb-3 text-[--text-secondary]">
          {isConfirmed
            ? `已确认 ${selectedIds.size} 个画像，正在生成模拟问题...`
            : (
              <>
                {selectedIds.size === 0
                  ? '请至少选择 1 个画像'
                  : `已选择 ${selectedIds.size} / ${maxSelection} 个画像`}
                {estimatedTime && selectedIds.size > 0 && (
                  <span className="ml-2">
                    | 预计额外耗时：{estimatedTime}
                  </span>
                )}
              </>
            )}
        </div>

        {/* Action buttons */}
        {!isConfirmed && (
          <div className="flex gap-3">
            <button
              className={cn(
                'flex-1 py-2.5 rounded-lg text-sm font-medium transition-colors',
                selectedIds.size >= minSelection
                  ? 'bg-indigo-600 text-white hover:bg-indigo-500'
                  : 'bg-[--bg-tertiary] text-[--text-secondary] cursor-not-allowed'
              )}
              onClick={handleConfirm}
              disabled={selectedIds.size < minSelection}
            >
              {selectedIds.size >= minSelection
                ? `确认选择（${selectedIds.size}）`
                : '确认选择'}
            </button>
            <button
              className="py-2.5 px-4 rounded-lg text-sm font-medium bg-[--bg-secondary] border border-[--border-default] text-[--text-primary] hover:bg-[--bg-tertiary] transition-colors"
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
