'use client';

import { RiTimeLine, RiLightbulbLine } from '@remixicon/react';

interface WaitingPanelProps {
  tips: string[];
  estimatedTime?: string;
}

export function WaitingPanel({ tips, estimatedTime }: WaitingPanelProps) {
  if (!tips || tips.length === 0) return null;

  return (
    <div className="bg-[--bg-elevated] border border-[--border-subtle] rounded-xl p-4 mt-3">
      <div className="flex items-center gap-2 mb-3">
        <RiTimeLine className="w-4 h-4 text-[#F59E0B]" />
        <span className="text-xs font-medium text-[#F59E0B]">
          等待期间的小提示
        </span>
        {estimatedTime && (
          <span className="text-[10px] text-[--text-tertiary] ml-auto">
            ~{estimatedTime}
          </span>
        )}
      </div>
      <div className="space-y-2">
        {tips.map((tip, index) => (
          <div key={index} className="flex items-start gap-2">
            <RiLightbulbLine className="w-3.5 h-3.5 text-[--text-tertiary] flex-shrink-0 mt-0.5" />
            <span className="text-xs text-[--text-secondary]">{tip}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
