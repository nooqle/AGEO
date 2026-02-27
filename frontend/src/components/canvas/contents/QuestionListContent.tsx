'use client';

import { useMemo } from 'react';
import type { QuestionListCanvasContent, QuestionItem } from '@/types/canvas';

interface QuestionListContentProps {
  content: QuestionListCanvasContent;
}

export function QuestionListContent({ content }: QuestionListContentProps) {
  const { questions, simulatedQuestions, generationMode } = content.data;

  // Group questions by category
  const groupedQuestions = useMemo(() => {
    const qs = questions || [];
    const groups: Record<string, QuestionItem[]> = {};
    
    qs.forEach((q) => {
      const category = q.category || '未分类';
      if (!groups[category]) {
        groups[category] = [];
      }
      groups[category].push(q);
    });
    
    return groups;
  }, [questions]);

  // Get simulated questions for detailed view
  const simulatedQs = simulatedQuestions?.simulated_questions || [];
  const mode = generationMode || simulatedQuestions?.generation_mode || '品牌全景模式';

  return (
    <div className="p-6 space-y-6">
      {/* Header */}
      <div className="border-b border-[--border-subtle] pb-4">
        <h2 className="text-xl font-semibold text-[--text-primary]">模拟问题列表</h2>
        <p className="text-sm text-[--text-secondary] mt-1">
          生成模式: <span className="font-medium text-blue-300">{mode}</span>
        </p>
        <p className="text-sm text-[--text-secondary]">
          共 {questions?.length || 0} 个问题
        </p>
      </div>

      {/* Detailed Simulated Questions */}
      {simulatedQs.length > 0 && (
        <div className="space-y-4">
          <h3 className="text-lg font-medium text-[--text-primary]">详细问题列表</h3>
          {simulatedQs.map((sq, index) => (
            <div
              key={sq.question_id || index}
              className="bg-[--bg-elevated] rounded-lg border border-[--border-subtle] p-4 transition-colors hover:border-[--border-hover] hover:bg-[--bg-tertiary]"
            >
              <div className="flex items-start justify-between mb-3">
                <div>
                  <span className="inline-block px-2 py-1 text-xs font-medium bg-blue-500/10 text-blue-500 rounded mb-2 border border-blue-500/20">
                    {sq.category}
                  </span>
                  {sq.subcategory && (
                    <span className="inline-block px-2 py-1 text-xs font-medium bg-[--bg-tertiary] text-[--text-secondary] rounded mb-2 ml-2 border border-[--border-subtle]">
                      {sq.subcategory}
                    </span>
                  )}
                </div>
                <span className="text-xs text-[--text-secondary]">#{index + 1}</span>
              </div>

              <h4 className="font-medium text-[--text-primary] mb-2">{sq.core_question}</h4>

              {(sq.user_intent || sq.decision_stage) && (
                <div className="flex gap-4 text-xs text-[--text-secondary] mb-3">
                  {sq.user_intent && <span>意图: {sq.user_intent}</span>}
                  {sq.decision_stage && <span>决策阶段: {sq.decision_stage}</span>}
                </div>
              )}

              {/* Variants */}
              {sq.question_variants && (
                <div className="mt-3 pt-3 border-t border-[--border-subtle] space-y-2">
                  {sq.question_variants.variant_a && (
                    <div className="flex items-start gap-2">
                      <span className="text-xs font-medium text-purple-300 whitespace-nowrap">
                        {sq.question_variants.variant_a.type}
                      </span>
                      <p className="text-sm text-[--text-secondary]">
                        {sq.question_variants.variant_a.question}
                      </p>
                    </div>
                  )}
                  {sq.question_variants.variant_b && (
                    <div className="flex items-start gap-2">
                      <span className="text-xs font-medium text-emerald-300 whitespace-nowrap">
                        {sq.question_variants.variant_b.type}
                      </span>
                      <p className="text-sm text-[--text-secondary]">
                        {sq.question_variants.variant_b.question}
                      </p>
                    </div>
                  )}
                  {sq.question_variants.variant_c && (
                    <div className="flex items-start gap-2">
                      <span className="text-xs font-medium text-orange-300 whitespace-nowrap">
                        {sq.question_variants.variant_c.type}
                      </span>
                      <p className="text-sm text-[--text-secondary]">
                        {sq.question_variants.variant_c.question}
                      </p>
                    </div>
                  )}
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      {/* Grouped Questions Summary */}
      {Object.keys(groupedQuestions).length > 0 && (
        <div className="space-y-4">
          <h3 className="text-lg font-medium text-[--text-primary]">问题分类统计</h3>
          {Object.entries(groupedQuestions).map(([category, qs]) => (
            <div key={category} className="bg-[--bg-elevated] border border-[--border-subtle] rounded-lg p-4">
              <h4 className="font-medium text-[--text-primary] mb-2">
                {category} <span className="text-sm text-[--text-secondary]">({qs.length})</span>
              </h4>
              <ul className="space-y-1">
                {qs.slice(0, 5).map((q, idx) => (
                  <li key={q.id || idx} className="text-sm text-[--text-secondary] truncate">
                    • {q.text}
                  </li>
                ))}
                {qs.length > 5 && (
                  <li className="text-sm text-[--text-secondary]">
                    ... 还有 {qs.length - 5} 个问题
                  </li>
                )}
              </ul>
            </div>
          ))}
        </div>
      )}

      {/* Empty State */}
      {(!questions || questions.length === 0) && (!simulatedQs || simulatedQs.length === 0) && (
        <div className="text-center py-8 text-[--text-secondary]">
          <p>暂无问题数据</p>
        </div>
      )}
    </div>
  );
}
