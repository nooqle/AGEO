"use client";

import React from "react";
import { motion } from "framer-motion";
import { Button } from "@/components/ui/button";
import { RiSendPlaneLine, RiMicLine, RiImageLine } from "@remixicon/react";

interface MobileInputProps {
  value: string;
  onChange: (value: string) => void;
  onSubmit: () => void;
  isLoading?: boolean;
  placeholder?: string;
}

export function MobileInput({
  value,
  onChange,
  onSubmit,
  isLoading = false,
  placeholder = "输入品牌名称开始分析...",
}: MobileInputProps) {
  const textareaRef = React.useRef<HTMLTextAreaElement>(null);

  // Auto-resize textarea
  React.useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = "auto";
      textareaRef.current.style.height = `${Math.min(textareaRef.current.scrollHeight, 120)}px`;
    }
  }, [value]);

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault();
      onSubmit();
    }
  };

  return (
    <div className="fixed bottom-0 left-0 right-0 bg-[var(--bg-secondary)] border-t border-[var(--border-subtle)] p-3 safe-area-bottom">
      <div className="flex items-end gap-2 max-w-3xl mx-auto">
        {/* Additional Actions */}
        <div className="flex items-center gap-1">
          <Button
            variant="ghost"
            size="icon"
            className="text-[var(--text-tertiary)] hover:text-[var(--text-primary)]"
          >
            <RiImageLine className="w-5 h-5" />
          </Button>
          <Button
            variant="ghost"
            size="icon"
            className="text-[var(--text-tertiary)] hover:text-[var(--text-primary)]"
          >
            <RiMicLine className="w-5 h-5" />
          </Button>
        </div>

        {/* Input Area */}
        <div className="flex-1 relative">
          <textarea
            ref={textareaRef}
            value={value}
            onChange={(e) => onChange(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={placeholder}
            disabled={isLoading}
            rows={1}
            className="w-full bg-[var(--bg-tertiary)] border border-[var(--border-subtle)] rounded-xl px-4 py-3 pr-12 text-[var(--text-primary)] placeholder:text-[var(--text-tertiary)] resize-none focus:outline-none focus:border-[var(--brand-primary)] transition-colors max-h-[120px]"
          />
          {/* Character Count */}
          {value.length > 0 && (
            <span className="absolute right-3 bottom-3 text-xs text-[var(--text-tertiary)]">
              {value.length}
            </span>
          )}
        </div>

        {/* Send Button */}
        <motion.div whileTap={{ scale: 0.95 }}>
          <Button
            onClick={onSubmit}
            disabled={!value.trim() || isLoading}
            size="icon"
            className="h-11 w-11 rounded-xl"
          >
            <RiSendPlaneLine className="w-5 h-5" />
          </Button>
        </motion.div>
      </div>
    </div>
  );
}
