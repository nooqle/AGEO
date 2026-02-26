'use client';

import React, { useState, useMemo, useCallback } from 'react';
import { motion } from 'framer-motion';
import { RiCheckLine } from '@remixicon/react';
import { BrandCompetitionGraph } from '@/components/graph/BrandCompetitionGraph';

import { cn } from '@/lib/cn';
import { useConversationStore } from '@/stores/conversationStore';
import type {
  WorkflowBrandProfile,
  WorkflowCompetitor,
  WorkflowPersona,
  WorkflowCanvasContent,
  WorkflowSelectionData,
} from '@/types/canvas';

/** Safely convert a value to a display string (prevents [object Object] in UI). */
function safeString(value: unknown): string {
  if (value == null) return '';
  if (typeof value === 'string') return value;
  if (typeof value === 'number' || typeof value === 'boolean') return String(value);
  try { return JSON.stringify(value); } catch { return String(value); }
}

interface WorkflowContentProps {
  content: WorkflowCanvasContent;
  showSectionTitles?: boolean;
}

function getScoreColor(score: number): string {
  if (score <= 3) return '#FCA5A5';
  if (score <= 5) return '#FDBA74';
  if (score <= 7) return '#FCD34D';
  return '#86EFAC';
}

const priorityColors: Record<string, string> = {
  '核心人群': '#EF4444',
  '重点人群': '#F59E0B',
  '增长人群': '#F59E0B',
  '机会人群': '#22C55E',
};

const typeLabels: Record<string, string> = {
  'all': '全部',
  '直接竞争': '直接',
  '间接竞争': '间接',
  '潜在竞争': '潜在'
};

function BrandProfileCard({ profile }: { profile: WorkflowBrandProfile }) {
  return (
    <div className="bg-[--bg-secondary] border border-[--border-subtle] rounded-lg p-4 space-y-3">
      <div className="flex items-center justify-between">
        <h5 className="text-sm font-medium text-[--text-primary]">
          {profile.brand_name}
          {profile.brand_name_en && (
            <span className="text-[--text-secondary] ml-2 font-normal">
              {profile.brand_name_en}
            </span>
          )}
        </h5>
        {profile.industry && (
          <span className="text-xs px-2 py-0.5 rounded-full bg-[#7C3AED]/15 text-[#A78BFA]">
            {profile.industry}
          </span>
        )}
      </div>
      {profile.description && (
        <p className="text-sm text-[--text-primary] leading-relaxed">
          {safeString(profile.description)}
        </p>
      )}
      <div className="grid grid-cols-2 gap-2 text-sm">
        {profile.brand_positioning && (
          <div>
            <span className="text-[--text-tertiary]">定位：</span>
            <span className="text-[--text-primary]">{safeString(profile.brand_positioning)}</span>
          </div>
        )}
        {profile.target_audience && (
          <div>
            <span className="text-[--text-tertiary]">受众：</span>
            <span className="text-[--text-primary]">{safeString(profile.target_audience)}</span>
          </div>
        )}
        {profile.price_positioning && (
          <div>
            <span className="text-[--text-tertiary]">价格：</span>
            <span className="text-[--text-primary]">{safeString(profile.price_positioning)}</span>
          </div>
        )}
        {profile.founded_year && (
          <div>
            <span className="text-[--text-tertiary]">成立：</span>
            <span className="text-[--text-primary]">{safeString(profile.founded_year)}</span>
          </div>
        )}
      </div>
      {profile.core_products && profile.core_products.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {profile.core_products.map((p, i) => (
            <span
              key={i}
              className="text-sm px-2 py-0.5 rounded bg-[--bg-tertiary] text-[--text-primary]"
            >
              {p}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}

function CompetitorTable({ competitors }: { competitors: WorkflowCompetitor[] }) {
  return (
    <div className="overflow-x-auto rounded-lg border border-[--border-subtle]">
      <table className="w-full text-sm min-w-[600px]">
        <thead>
          <tr className="bg-[--bg-secondary] border-b border-[--border-subtle]">
            <th className="text-left py-3 px-4 text-[--text-secondary] font-medium text-xs uppercase tracking-wide w-[160px]">品牌</th>
            <th className="text-left py-3 px-4 text-[--text-secondary] font-medium text-xs uppercase tracking-wide w-[80px]">类型</th>
            <th className="text-center py-3 px-4 text-[--text-secondary] font-medium text-xs uppercase tracking-wide w-[60px]">相关度</th>
            <th className="text-left py-3 px-4 text-[--text-secondary] font-medium text-xs uppercase tracking-wide">核心产品</th>
            <th className="text-left py-3 px-4 text-[--text-secondary] font-medium text-xs uppercase tracking-wide">竞争优势</th>
          </tr>
        </thead>
        <tbody>
          {competitors.map((c, i) => (
            <motion.tr
              key={i}
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              transition={{ delay: i * 0.03 }}
              className="border-b border-[--border-subtle] last:border-b-0 hover:bg-[--bg-secondary]/60 transition-colors"
            >
              <td className="py-3 px-4">
                <div className="flex flex-col gap-0.5">
                  <span className="text-[--text-primary] font-semibold">{c.name}</span>
                  {c.name_en && (
                    <span className="text-[--text-secondary] text-xs">{c.name_en}</span>
                  )}
                  {c.website && /[.]/.test(c.website) ? (
                    <a
                      href={c.website.startsWith('http') ? c.website : `https://www.${c.website}`}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-[#A78BFA] hover:text-[#C4B5FD] underline decoration-[#A78BFA]/30 hover:decoration-[#C4B5FD]/50 text-xs truncate max-w-[140px]"
                    >
                      {c.website.replace(/^https?:\/\/(www\.)?/, '')}
                    </a>
                  ) : c.website ? (
                    <span className="text-[--text-tertiary] text-xs">{c.website}</span>
                  ) : null}
                </div>
              </td>
              <td className="py-3 px-4">
                <span className={cn(
                  'px-2 py-0.5 rounded text-xs whitespace-nowrap',
                  c.competition_type === '直接竞争' ? 'bg-[#EF4444]/15 text-[#FCA5A5]' :
                  c.competition_type === '间接竞争' ? 'bg-[#F59E0B]/15 text-[#FCD34D]' :
                  'bg-[#8B5CF6]/15 text-[#C4B5FD]'
                )}>
                  {c.competition_type}
                </span>
              </td>
              <td className="py-3 px-4 text-center">
                <div className="inline-flex items-center justify-center w-8 h-8 rounded bg-[--bg-tertiary]">
                  <span className="text-sm font-semibold" style={{ color: getScoreColor(c.relevance_score ?? 0) }}>{c.relevance_score}</span>
                </div>
              </td>
              <td className="py-3 px-4">
                {c.core_products && c.core_products.length > 0 ? (
                  <div className="flex flex-wrap gap-1.5">
                    {c.core_products.slice(0, 3).map((p, j) => (
                      <span key={j} className="px-2 py-0.5 rounded bg-[--bg-tertiary] text-[--text-primary] text-xs">
                        {p}
                      </span>
                    ))}
                    {c.core_products.length > 3 && (
                      <span className="text-[--text-secondary] text-xs self-center">+{c.core_products.length - 3}</span>
                    )}
                  </div>
                ) : (
                  <span className="text-[--text-disabled]">-</span>
                )}
              </td>
              <td className="py-3 px-4">
                {c.competitive_advantage ? (
                  <p className="text-[--text-primary] max-w-[240px]">{safeString(c.competitive_advantage)}</p>
                ) : (
                  <span className="text-[--text-disabled]">-</span>
                )}
              </td>
            </motion.tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function CompetitorList({ competitors }: { competitors: WorkflowCompetitor[] }) {
  const [filterType, setFilterType] = useState<string>('all');

  const filteredCompetitors = useMemo(() => {
    if (filterType === 'all') return competitors;
    return competitors.filter(c => c.competition_type === filterType);
  }, [competitors, filterType]);

  const competitionTypes = ['all', '直接竞争', '间接竞争', '潜在竞争'];

  const typeCounts = useMemo(() => ({
    'all': competitors.length,
    '直接竞争': competitors.filter(c => c.competition_type === '直接竞争').length,
    '间接竞争': competitors.filter(c => c.competition_type === '间接竞争').length,
    '潜在竞争': competitors.filter(c => c.competition_type === '潜在竞争').length,
  }), [competitors]);

  return (
    <div className="space-y-3">
      {/* 筛选栏 */}
      <div className="flex items-center gap-1.5 flex-wrap">
        {competitionTypes.map(type => (
          <button
            key={type}
            onClick={() => setFilterType(type)}
            className={cn(
              'px-2 py-1 rounded text-xs transition-colors',
              filterType === type
                ? 'bg-[#7C3AED] text-white'
                : 'bg-[--bg-tertiary] text-[--text-secondary] hover:bg-[--bg-elevated]'
            )}
          >
            {typeLabels[type]}
            <span className="ml-1 text-[10px] opacity-80">
              ({typeCounts[type as keyof typeof typeCounts]})
            </span>
          </button>
        ))}
      </div>

      {/* 竞品表格 */}
      <CompetitorTable competitors={filteredCompetitors} />
    </div>
  );
}

function PriorityTag({ priority }: { priority?: string }) {
  if (!priority) {
    return (
      <span className="text-xs px-1.5 py-0.5 rounded" style={{ backgroundColor: 'var(--bg-tertiary)', color: 'var(--text-tertiary)' }}>
        未分类
      </span>
    );
  }
  const color = priorityColors[priority] || 'var(--text-tertiary)';
  return (
    <span className="text-xs px-1.5 py-0.5 rounded" style={{ backgroundColor: `${color}15`, color }}>
      {priority}
    </span>
  );
}

interface PersonaCardProps {
  persona: WorkflowPersona;
  selectable?: boolean;
  selected?: boolean;
  disabled?: boolean;
  onToggle?: () => void;
}

function PersonaCard({ persona, selectable, selected, disabled, onToggle }: PersonaCardProps) {
  const demo = persona.demographics;
  const scenarios = persona.usage_scenarios;
  const keyQuestions = persona.key_questions;

  // Pain points: prefer marketing_pain_points (object array), fallback to
  // psychographics.pain_points (string array) which is what the simplified A2 schema produces
  const structuredPainPoints = persona.marketing_pain_points;
  const psychoPainPoints = persona.psychographics?.pain_points;
  const painPoints: Array<{ pain_point_category: string; pain_point_description: string }> | undefined =
    structuredPainPoints && structuredPainPoints.length > 0
      ? structuredPainPoints
      : psychoPainPoints && psychoPainPoints.length > 0
        ? psychoPainPoints.map(pp => ({ pain_point_category: pp, pain_point_description: '' }))
        : undefined;

  const hasScenarios = scenarios && scenarios.length > 0;
  const hasPainPoints = painPoints && painPoints.length > 0;
  const hasKeyQuestions = keyQuestions && keyQuestions.length > 0;

  return (
    <div
      role={selectable ? 'button' : undefined}
      tabIndex={selectable ? 0 : undefined}
      onClick={selectable && !disabled ? onToggle : undefined}
      onKeyDown={selectable && !disabled ? (e) => {
        if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onToggle?.(); }
      } : undefined}
      className={cn(
        'bg-[--bg-secondary] border rounded-lg p-4 space-y-3 transition-all',
        selectable && !disabled && 'cursor-pointer hover:border-[--border-hover]',
        selectable && disabled && 'opacity-40 cursor-not-allowed',
        selected
          ? 'border-indigo-500 bg-indigo-500/10'
          : 'border-[--border-subtle]',
      )}
    >
      {/* Header: checkbox (if selectable) + name */}
      <div className="flex items-center gap-3">
        {selectable && (
          <div className={cn(
            'w-5 h-5 rounded-full border-2 flex items-center justify-center flex-shrink-0',
            selected
              ? 'border-indigo-500 bg-indigo-500'
              : 'border-[--border-hover]'
          )}>
            {selected && <RiCheckLine className="w-3 h-3 text-white" />}
          </div>
        )}
        <div className="flex-1 min-w-0">
          <span className="text-sm font-semibold text-[--text-primary]">
            {persona.persona_name}
          </span>
        </div>
        <PriorityTag priority={persona.persona_priority} />
      </div>

      {/* Demographics grid */}
      {demo && (demo.age_range || demo.gender || demo.city_tier || demo.occupation) && (
        <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-sm">
          {demo.age_range && (
            <div>
              <span className="text-[--text-tertiary]">年龄：</span>
              <span className="text-[--text-primary]">{demo.age_range}</span>
            </div>
          )}
          {demo.gender && (
            <div>
              <span className="text-[--text-tertiary]">性别：</span>
              <span className="text-[--text-primary]">{demo.gender}</span>
            </div>
          )}
          {demo.city_tier && (
            <div>
              <span className="text-[--text-tertiary]">城市：</span>
              <span className="text-[--text-primary]">{demo.city_tier}</span>
            </div>
          )}
          {demo.occupation && (
            <div>
              <span className="text-[--text-tertiary]">职业：</span>
              <span className="text-[--text-primary]">{demo.occupation}</span>
            </div>
          )}
        </div>
      )}

      {/* Description */}
      {persona.persona_description && (
        <p className="text-sm text-[--text-primary] leading-relaxed">
          {safeString(persona.persona_description)}
        </p>
      )}

      {/* Three-column layout: Scenarios / Pain Points / Key Questions */}
      {(hasScenarios || hasPainPoints || hasKeyQuestions) && (
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
          {/* Usage scenarios */}
          {hasScenarios && (
            <div className="space-y-1.5">
              <h6 className="text-xs font-medium text-[--text-secondary] uppercase tracking-wide">使用场景</h6>
              <div className="space-y-1.5">
                {scenarios.map((s, i) => (
                  <div key={i} className="bg-[--bg-tertiary] rounded px-2.5 py-1.5">
                    <div className="text-xs font-medium text-[--text-primary]">{s.scenario_name}</div>
                    {s.scenario_description && (
                      <div className="text-xs text-[--text-secondary] mt-0.5">{s.scenario_description}</div>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Marketing pain points — description shown directly */}
          {hasPainPoints && (
            <div className="space-y-1.5">
              <h6 className="text-xs font-medium text-[--text-secondary] uppercase tracking-wide">营销痛点</h6>
              <div className="space-y-1.5">
                {painPoints.map((pp, i) => (
                  <div key={i} className="bg-[--bg-tertiary] rounded px-2.5 py-1.5">
                    <div className="text-xs font-medium text-[#F9A8D4]">{pp.pain_point_category}</div>
                    {pp.pain_point_description && (
                      <div className="text-xs text-[--text-secondary] mt-0.5">{pp.pain_point_description}</div>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Key questions — renamed */}
          {hasKeyQuestions && (
            <div className="space-y-1.5">
              <h6 className="text-xs font-medium text-[--text-secondary] uppercase tracking-wide">AI搜索中的典型提问</h6>
              <p className="text-xs text-[--text-disabled] -mt-0.5">用户在AI搜索引擎中可能提出的问题</p>
              <ol className="list-decimal list-inside space-y-0.5 text-xs text-[--text-primary]">
                {keyQuestions.map((q, i) => (
                  <li key={i}>{q}</li>
                ))}
              </ol>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

interface SelectionBarProps {
  selectedCount: number;
  minSelection: number;
  maxSelection: number;
  isConfirmed: boolean;
  onConfirm: () => void;
  onSkip: () => void;
}

function SelectionBar({ selectedCount, minSelection, maxSelection, isConfirmed, onConfirm, onSkip }: SelectionBarProps) {
  if (isConfirmed) {
    return (
      <div className="sticky bottom-0 bg-[--bg-primary]/95 backdrop-blur border-t border-[--border-subtle] px-5 py-3">
        <p className="text-sm text-[--text-secondary] text-center">
          已确认 {selectedCount} 个画像，正在生成模拟问题...
        </p>
      </div>
    );
  }

  return (
    <div className="sticky bottom-0 bg-[--bg-primary]/95 backdrop-blur border-t border-[--border-subtle] px-5 py-3">
      <div className="flex items-center justify-between mb-2">
        <span className="text-sm text-[--text-secondary]">
          已选择 {selectedCount}/{maxSelection} 个画像
        </span>
      </div>
      <div className="flex gap-3">
        <button
          className={cn(
            'flex-1 py-2.5 rounded-lg text-sm font-medium transition-colors',
            selectedCount >= minSelection
              ? 'bg-indigo-600 text-white hover:bg-indigo-500'
              : 'bg-[--bg-tertiary] text-[--text-disabled] cursor-not-allowed'
          )}
          onClick={onConfirm}
          disabled={selectedCount < minSelection}
        >
          确认选择
        </button>
        <button
          className="flex-1 py-2.5 rounded-lg text-sm font-medium bg-[--bg-secondary] border border-[--border-subtle] text-[--text-primary] hover:bg-[--bg-tertiary] transition-colors"
          onClick={onSkip}
        >
          全景分析所有画像
        </button>
      </div>
    </div>
  );
}

export const WorkflowContent = React.memo(function WorkflowContent({ content, showSectionTitles = true }: WorkflowContentProps) {
  const { data } = content;

  // Support both camelCase and snake_case keys from backend
  const brandProfile = data?.brandProfile || data?.brand_profile;
  const competitors = data?.competitors || [];
  const personas = data?.personas || data?.user_personas || [];

  // Inline selection support
  const selection: WorkflowSelectionData | undefined = data?.selection;
  const hasSelection = selection && Array.isArray(selection.personas) && selection.personas.length > 0;
  const maxSelection = selection?.maxSelection ?? 3;
  const minSelection = selection?.minSelection ?? 1;

  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [isConfirmed, setIsConfirmed] = useState(false);

  const sendConfirmation = useConversationStore(s => s.wsConfirmation);

  // Build a set of selectable persona names (from selection data) for quick lookup
  const selectableNames = useMemo(() => {
    if (!hasSelection) return new Set<string>();
    return new Set(selection.personas!.map(p => p.name));
  }, [hasSelection, selection]);

  const toggleSelection = useCallback((personaName: string) => {
    if (isConfirmed) return;
    setSelectedIds(prev => {
      const next = new Set(prev);
      if (next.has(personaName)) {
        next.delete(personaName);
      } else if (next.size < maxSelection) {
        next.add(personaName);
      }
      return next;
    });
  }, [isConfirmed, maxSelection]);

  const handleConfirm = useCallback(() => {
    if (!sendConfirmation || selectedIds.size < minSelection) return;
    const selectedPersonas = personas.filter(p =>
      selectedIds.has(p.persona_name)
    );
    const requestId = `persona_selection_${Date.now()}`;
    sendConfirmation(requestId, {
      type: 'persona_path_selection',
      selectedPersonaIds: Array.from(selectedIds),
      selectedPersonaNames: selectedPersonas.map(p => p.persona_name),
    });
    setIsConfirmed(true);
  }, [selectedIds, minSelection, personas, sendConfirmation]);

  const handleSkip = useCallback(() => {
    if (!sendConfirmation) return;
    const requestId = `persona_selection_skip_${Date.now()}`;
    sendConfirmation(requestId, { type: 'skip' });
    setIsConfirmed(true);
  }, [sendConfirmation]);

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      className="space-y-6 p-5"
    >
      {/* Brand Profile Card */}
      {brandProfile && (
        <div>
          {showSectionTitles && (
            <h4 className="text-sm font-medium text-[--text-primary] mb-3">品牌档案</h4>
          )}
          <BrandProfileCard profile={brandProfile} />
        </div>
      )}

      {/* Brand Competition Graph */}
      {brandProfile && competitors.length > 0 && (
        <div>
          {showSectionTitles && (
            <h4 className="text-sm font-medium text-[--text-primary] mb-3">品牌竞品图谱</h4>
          )}
          <BrandCompetitionGraph
            brandProfile={brandProfile}
            competitors={competitors}
          />
        </div>
      )}

      {/* Competitor List */}
      {competitors.length > 0 && (
        <div>
          <h4 className="text-sm font-medium text-[--text-primary] mb-3">
            竞品列表（{competitors.length}）
          </h4>
          <CompetitorList competitors={competitors} />
        </div>
      )}

      {/* Persona Cards (with optional inline selection) */}
      {personas.length > 0 && (
        <div>
          <h4 className="text-sm font-medium text-[--text-primary] mb-1">
            用户画像（{personas.length}）
          </h4>
          {hasSelection && (
            <p className="text-xs text-[--text-tertiary] mb-3">
              {selection.description || '请选择您希望重点分析的用户画像（可多选）'}
            </p>
          )}
          <div className="space-y-2">
            {personas.map((p, i) => {
              const isSelectable = hasSelection && selectableNames.has(p.persona_name);
              return (
                <PersonaCard
                  key={p.persona_id || p.id || i}
                  persona={p}
                  selectable={isSelectable}
                  selected={isSelectable ? selectedIds.has(p.persona_name) : undefined}
                  disabled={isSelectable && isConfirmed}
                  onToggle={isSelectable ? () => toggleSelection(p.persona_name) : undefined}
                />
              );
            })}
          </div>
        </div>
      )}

      {/* Selection action bar */}
      {hasSelection && (
        <SelectionBar
          selectedCount={selectedIds.size}
          minSelection={minSelection}
          maxSelection={maxSelection}
          isConfirmed={isConfirmed}
          onConfirm={handleConfirm}
          onSkip={handleSkip}
        />
      )}

    </motion.div>
  );
});

WorkflowContent.displayName = 'WorkflowContent';

export default WorkflowContent;
