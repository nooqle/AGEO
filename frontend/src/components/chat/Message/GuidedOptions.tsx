'use client';

interface GuidedOption {
  id: string;
  label: string;
  description?: string;
}

interface GuidedOptionsProps {
  message: string;
  options: GuidedOption[];
  onSelect: (optionId: string) => void;
  selectedId?: string;
}

const OPTION_LETTERS = ['A', 'B', 'C', 'D', 'E', 'F'];

export function GuidedOptions({ message, options, onSelect, selectedId }: GuidedOptionsProps) {
  return (
    <div className="space-y-3">
      {message && (
        <p className="text-sm text-[var(--text-primary)]">{message}</p>
      )}
      <div className="grid gap-2">
        {options.map((option, index) => {
          const isSelected = selectedId === option.id;
          const letter = OPTION_LETTERS[index] || String(index + 1);

          return (
            <button
              key={option.id}
              onClick={() => !selectedId && onSelect(option.id)}
              disabled={!!selectedId}
              className={`flex items-start gap-3 px-4 py-3 rounded-xl border text-left transition-all ${
                isSelected
                  ? 'bg-[#6366F1]/10 border-[#6366F1]/40 text-[var(--text-primary)]'
                  : selectedId
                  ? 'bg-[var(--bg-elevated)] border-[var(--border-subtle)] text-[var(--text-tertiary)] opacity-50'
                  : 'bg-[var(--bg-elevated)] border-[var(--border-subtle)] text-[var(--text-primary)] hover:border-[#6366F1]/30 hover:bg-[#6366F1]/5'
              }`}
            >
              <span
                className={`flex-shrink-0 w-6 h-6 rounded-full flex items-center justify-center text-xs font-bold ${
                  isSelected
                    ? 'bg-[#6366F1] text-white'
                    : 'bg-[var(--bg-tertiary)] text-[var(--text-secondary)]'
                }`}
              >
                {letter}
              </span>
              <div className="flex-1 min-w-0">
                <div className="text-sm font-medium">{option.label}</div>
                {option.description && (
                  <div className="text-xs text-[var(--text-tertiary)] mt-0.5">
                    {option.description}
                  </div>
                )}
              </div>
              {isSelected && (
                <span className="text-xs text-[#6366F1] font-medium flex-shrink-0 mt-0.5">
                  已选择
                </span>
              )}
            </button>
          );
        })}
      </div>
    </div>
  );
}
