'use client';

import { useState, KeyboardEvent } from 'react';
import { RiCloseLine } from '@remixicon/react';

interface AliasTagInputProps {
  aliases: string[];
  onChange: (aliases: string[]) => void;
  placeholder?: string;
}

export function AliasTagInput({
  aliases,
  onChange,
  placeholder = '输入后按回车添加...',
}: AliasTagInputProps) {
  const [input, setInput] = useState('');

  const handleKeyDown = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter' && input.trim()) {
      e.preventDefault();
      const trimmed = input.trim();
      if (!aliases.includes(trimmed)) {
        onChange([...aliases, trimmed]);
      }
      setInput('');
    } else if (e.key === 'Backspace' && !input && aliases.length > 0) {
      onChange(aliases.slice(0, -1));
    }
  };

  const removeAlias = (index: number) => {
    onChange(aliases.filter((_, i) => i !== index));
  };

  return (
    <div
      className="flex flex-wrap gap-1.5 p-2 rounded-lg min-h-[38px] transition-colors"
      style={{
        background: 'var(--bg-tertiary)',
        border: '1px solid var(--border-default)',
      }}
    >
      {aliases.map((alias, index) => (
        <span
          key={`${alias}-${index}`}
          className="flex items-center gap-1 px-2 py-0.5 rounded text-xs"
          style={{
            background: 'var(--bg-hover)',
            color: 'var(--text-primary)',
          }}
        >
          {alias}
          <button
            type="button"
            onClick={() => removeAlias(index)}
            className="transition-colors cursor-pointer"
            style={{ color: 'var(--status-error)' }}
          >
            <RiCloseLine className="w-3 h-3" />
          </button>
        </span>
      ))}
      <input
        type="text"
        value={input}
        onChange={(e) => setInput(e.target.value)}
        onKeyDown={handleKeyDown}
        placeholder={aliases.length === 0 ? placeholder : ''}
        className="flex-1 min-w-[120px] bg-transparent text-sm outline-none"
        style={{
          color: 'var(--text-primary)',
          border: 'none',
        }}
      />
    </div>
  );
}
