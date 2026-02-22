'use client';

import { Message } from '@/types/message';
import { formatTime } from '@/lib/utils';

interface UserMessageProps {
  message: Message;
}

export function UserMessage({ message }: UserMessageProps) {
  return (
    <div className="max-w-[85%] md:max-w-[70%]">
      <div className="bg-indigo-600 text-white rounded-2xl rounded-tr-md px-4 py-3 shadow-sm">
        <div className="whitespace-pre-wrap break-words">
          {message.content}
        </div>
      </div>
      <div className="text-xs text-[--text-tertiary] mt-1 text-right">
        {formatTime(message.timestamp)}
      </div>
    </div>
  );
}
