'use client';

import { useState } from 'react';
import { createPortal } from 'react-dom';
import { RiCloseLine } from '@remixicon/react';
import { ThemedLogo } from '@/components/ui/ThemedLogo';
import { Button } from '@/components/ui/button';
import { modalScrimClassName } from '@/components/ui/modal-scrim';

interface HomeBrandLinkProps {
  size?: number;
  showSubtitle?: boolean;
  requireConfirm?: boolean;
  className?: string;
  compact?: boolean;
}

export function HomeBrandLink({
  size = 26,
  showSubtitle = true,
  requireConfirm = false,
  className,
  compact = false,
}: HomeBrandLinkProps) {
  const [confirmOpen, setConfirmOpen] = useState(false);

  const handleNavigate = () => {
    setConfirmOpen(false);
    if (typeof window === 'undefined') {
      return;
    }

    if (window.history.length > 1) {
      window.history.back();
      return;
    }

    window.location.assign('/dashboard');
  };

  const handleClick = () => {
    if (!requireConfirm) {
      handleNavigate();
      return;
    }
    setConfirmOpen(true);
  };

  return (
    <>
      <button
        type="button"
        onClick={handleClick}
        className={className || 'flex items-center gap-3 rounded-xl px-1 py-1 transition-colors'}
        title="返回首页"
        style={{ color: 'var(--text-primary)' }}
        onMouseEnter={(e) => {
          e.currentTarget.style.backgroundColor = 'var(--bg-tertiary)';
        }}
        onMouseLeave={(e) => {
          e.currentTarget.style.backgroundColor = 'transparent';
        }}
      >
        <ThemedLogo size={size} />
        {compact ? null : (
          <div className="text-left">
            <div
              className="text-[13px] font-semibold tracking-tight"
              style={{ color: 'var(--text-primary)' }}
            >
              Specta AI
            </div>
            {showSubtitle ? (
              <div
                className="text-[10px] tracking-[0.12em]"
                style={{ color: 'var(--text-tertiary)' }}
              >
                品牌AI助手
              </div>
            ) : null}
          </div>
        )}
      </button>

      {confirmOpen && typeof document !== 'undefined'
        ? createPortal(
            <div className={modalScrimClassName('z-50 flex items-center justify-center px-4 py-6')}>
              <div
                className="w-full max-w-[520px] rounded-[24px] border bg-[var(--bg-primary)] p-5 shadow-[0_24px_60px_rgba(15,23,42,0.28)]"
                style={{ borderColor: 'var(--border-subtle)' }}
              >
                <div className="flex items-start justify-between gap-4">
                  <div>
                    <div className="text-[18px] font-semibold text-[var(--text-primary)]">
                      返回首页？
                    </div>
                    <div className="mt-2 text-[14px] leading-7 text-[var(--text-secondary)]">
                      当前正在分析流程中。现在返回首页，可能会打断你对当前任务的持续观察与操作。
                    </div>
                    <div className="mt-2 text-[13px] leading-6 text-[var(--text-tertiary)]">
                      仅弹出这个确认框不会停止任何正在进行的任务；只有在你确认返回后才会离开当前页面。
                    </div>
                  </div>
                  <button
                    type="button"
                    onClick={() => setConfirmOpen(false)}
                    className="rounded-lg p-2 text-[var(--text-tertiary)] transition-colors hover:bg-[var(--bg-secondary)] hover:text-[var(--text-primary)]"
                    title="关闭"
                  >
                    <RiCloseLine className="h-4 w-4" />
                  </button>
                </div>

                <div className="mt-5 flex items-center justify-end gap-2">
                  <Button variant="ghost" onClick={() => setConfirmOpen(false)}>
                    留在当前页
                  </Button>
                  <Button onClick={handleNavigate}>返回首页</Button>
                </div>
              </div>
            </div>,
            document.body
          )
        : null}
    </>
  );
}
