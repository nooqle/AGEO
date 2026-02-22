'use client';

import { useEffect, useState, useCallback } from 'react';
import { create } from 'zustand';
import { cn } from '@/lib/cn';

// --- Toast Store ---

type ToastType = 'success' | 'error' | 'info';

interface ToastItem {
  id: string;
  type: ToastType;
  message: string;
  duration: number;
}

interface ToastState {
  toasts: ToastItem[];
  addToast: (type: ToastType, message: string, duration?: number) => void;
  removeToast: (id: string) => void;
}

const useToastStore = create<ToastState>((set) => ({
  toasts: [],
  addToast: (type, message, duration = 4000) => {
    const id = `toast_${Date.now()}_${Math.random().toString(36).slice(2, 6)}`;
    set((state) => ({
      toasts: [...state.toasts, { id, type, message, duration }],
    }));
  },
  removeToast: (id) => {
    set((state) => ({
      toasts: state.toasts.filter((t) => t.id !== id),
    }));
  },
}));

// --- Public API ---

export const toast = {
  success: (message: string, duration?: number) =>
    useToastStore.getState().addToast('success', message, duration),
  error: (message: string, duration?: number) =>
    useToastStore.getState().addToast('error', message, duration),
  info: (message: string, duration?: number) =>
    useToastStore.getState().addToast('info', message, duration),
};

// --- Single Toast Item ---

function ToastItemView({ item, onDismiss }: { item: ToastItem; onDismiss: (id: string) => void }) {
  const [isExiting, setIsExiting] = useState(false);

  const dismiss = useCallback(() => {
    setIsExiting(true);
    setTimeout(() => onDismiss(item.id), 200);
  }, [item.id, onDismiss]);

  useEffect(() => {
    const timer = setTimeout(dismiss, item.duration);
    return () => clearTimeout(timer);
  }, [item.duration, dismiss]);

  const iconMap: Record<ToastType, string> = {
    success: '\u2713',
    error: '\u2717',
    info: 'i',
  };

  const colorMap: Record<ToastType, { bg: string; border: string; icon: string }> = {
    success: { bg: 'rgba(34,197,94,0.12)', border: 'rgba(34,197,94,0.3)', icon: '#22C55E' },
    error: { bg: 'rgba(239,68,68,0.12)', border: 'rgba(239,68,68,0.3)', icon: '#EF4444' },
    info: { bg: 'rgba(99,102,241,0.12)', border: 'rgba(99,102,241,0.3)', icon: '#6366F1' },
  };

  const colors = colorMap[item.type];

  return (
    <div
      className={cn(
        'flex items-center gap-3 px-4 py-3 rounded-xl shadow-lg backdrop-blur-sm',
        'transition-all duration-200 ease-out cursor-pointer',
        isExiting ? 'opacity-0 translate-x-4' : 'opacity-100 translate-x-0'
      )}
      style={{
        background: 'var(--bg-secondary)',
        border: `1px solid ${colors.border}`,
        minWidth: '280px',
        maxWidth: '420px',
      }}
      onClick={dismiss}
    >
      <div
        className="w-6 h-6 rounded-full flex items-center justify-center flex-shrink-0 text-xs font-bold"
        style={{ background: colors.bg, color: colors.icon }}
      >
        {iconMap[item.type]}
      </div>
      <span className="text-sm" style={{ color: 'var(--text-primary)' }}>
        {item.message}
      </span>
    </div>
  );
}

// --- Container (mount in layout) ---

export function ToastContainer() {
  const { toasts, removeToast } = useToastStore();

  if (toasts.length === 0) return null;

  return (
    <div className="fixed top-4 right-4 z-[9999] flex flex-col gap-2">
      {toasts.map((t) => (
        <ToastItemView key={t.id} item={t} onDismiss={removeToast} />
      ))}
    </div>
  );
}
