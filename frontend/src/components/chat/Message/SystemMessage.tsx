'use client';

import { RiInformationLine, RiErrorWarningLine, RiCheckboxCircleLine } from '@remixicon/react';
import { Message } from '@/types/message';
import { cn } from '@/lib/cn';

interface SystemMessageProps {
  message: Message;
}

export function SystemMessage({ message }: SystemMessageProps) {
  // 根据内容判断类型
  const isError = message.content.includes('错误') || message.content.includes('失败');
  const isSuccess = message.content.includes('完成') || message.content.includes('成功');

  const Icon = isError ? RiErrorWarningLine : isSuccess ? RiCheckboxCircleLine : RiInformationLine;
  const colors = isError
    ? 'bg-red-500/10 border border-red-500/20 text-[--error]'
    : isSuccess
    ? 'bg-green-500/10 border border-green-500/20 text-[--success]'
    : 'bg-[--bg-secondary] border border-[--border-subtle] text-[--text-secondary]';

  return (
    <div className="flex justify-center my-4">
      <div
        className={cn(
          'inline-flex items-center gap-2 px-4 py-2 rounded-full text-sm',
          colors
        )}
      >
        <Icon className="w-4 h-4" />
        <span>{message.content}</span>
      </div>
    </div>
  );
}
