'use client';

/**
 * Specta-styled confirm dialog (Wave E2). Prefer over window.confirm for product surfaces.
 */

import * as Dialog from '@radix-ui/react-dialog';
import { modalScrimClassName } from '@/components/ui/modal-scrim';

export type ConfirmDialogProps = {
  open: boolean;
  title: string;
  description: string;
  confirmLabel?: string;
  cancelLabel?: string;
  /** danger = destructive action (delete) */
  tone?: 'default' | 'danger';
  busy?: boolean;
  onConfirm: () => void;
  onOpenChange: (open: boolean) => void;
};

export function ConfirmDialog({
  open,
  title,
  description,
  confirmLabel = '确认',
  cancelLabel = '取消',
  tone = 'default',
  busy = false,
  onConfirm,
  onOpenChange,
}: ConfirmDialogProps) {
  const confirmClass =
    tone === 'danger'
      ? 'border-[var(--error)] bg-[var(--error)] text-white hover:opacity-90'
      : 'border-[var(--brand-primary)] bg-[var(--brand-primary)] text-[var(--brand-contrast)] hover:bg-[var(--brand-hover)]';

  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className={modalScrimClassName('z-[60]')} />
        <Dialog.Content className="fixed inset-0 z-[60] flex items-center justify-center p-4">
          <div
            className="w-full max-w-md rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-primary)] p-5 shadow-lg"
            data-testid="specta-confirm-dialog"
          >
            <Dialog.Title className="text-base font-semibold text-[var(--text-primary)]">
              {title}
            </Dialog.Title>
            <Dialog.Description className="mt-2 text-sm leading-6 text-[var(--text-secondary)]">
              {description}
            </Dialog.Description>
            <div className="mt-5 flex flex-wrap justify-end gap-2">
              <Dialog.Close asChild>
                <button
                  type="button"
                  disabled={busy}
                  className="inline-flex h-9 items-center rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-3 text-sm font-medium text-[var(--text-secondary)] transition hover:border-[var(--border-strong)] disabled:opacity-50"
                >
                  {cancelLabel}
                </button>
              </Dialog.Close>
              <button
                type="button"
                disabled={busy}
                onClick={onConfirm}
                className={`inline-flex h-9 items-center rounded-lg border px-3 text-sm font-semibold transition disabled:opacity-50 ${confirmClass}`}
              >
                {busy ? '处理中…' : confirmLabel}
              </button>
            </div>
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
