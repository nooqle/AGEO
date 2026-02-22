import { useEffect, useCallback } from 'react';
import { useConversationStore } from '@/stores/conversationStore';
import { useCanvasStore } from '@/stores/canvasStore';

interface KeyboardShortcutsOptions {
  onStopExecution?: () => void;
  onToggleCanvas?: () => void;
}

export function useKeyboardShortcuts(options: KeyboardShortcutsOptions = {}) {
  const { onStopExecution, onToggleCanvas } = options;
  const { isAgentExecuting } = useConversationStore();
  const { isOpen, closeCanvas, setMode } = useCanvasStore();

  const handleKeyDown = useCallback((e: KeyboardEvent) => {
    // If focused in input, ignore some shortcuts
    const isInputFocused = ['INPUT', 'TEXTAREA'].includes(
      (e.target as HTMLElement).tagName
    );

    // Esc - Stop execution or close Canvas
    if (e.key === 'Escape') {
      e.preventDefault();
      if (isAgentExecuting && onStopExecution) {
        onStopExecution();
      } else if (isOpen) {
        closeCanvas();
      }
      return;
    }

    // If focused in input, following shortcuts don't work
    if (isInputFocused) return;

    // Cmd/Ctrl + \ - Toggle Canvas
    if ((e.metaKey || e.ctrlKey) && e.key === '\\') {
      e.preventDefault();
      if (onToggleCanvas) {
        onToggleCanvas();
      } else if (isOpen) {
        closeCanvas();
      }
      return;
    }

    // Cmd/Ctrl + Shift + F - Focus mode
    if ((e.metaKey || e.ctrlKey) && e.shiftKey && e.key === 'F') {
      e.preventDefault();
      if (isOpen) {
        setMode('focused');
      }
      return;
    }
  }, [isAgentExecuting, isOpen, onStopExecution, onToggleCanvas, closeCanvas, setMode]);

  useEffect(() => {
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [handleKeyDown]);
}
