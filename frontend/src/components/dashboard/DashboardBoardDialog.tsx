'use client';

import * as Dialog from '@radix-ui/react-dialog';
import { RiBookMarkedLine, RiChatQuoteLine, RiCloseLine, RiRadarLine } from '@remixicon/react';
import type { DashboardHomeData } from '@/types/dashboard';
import type { DashboardBoardId } from './DashboardHomeBoards';
import { MentionBoardReport } from './MentionBoardReport';
import { SourceBoardReport } from './SourceBoardReport';
import { RadarBoardReport } from './RadarBoardReport';
import { modalScrimClassName } from '@/components/ui/modal-scrim';

interface DashboardBoardDialogProps {
  open: boolean;
  board: DashboardBoardId | null;
  home: DashboardHomeData | null | undefined;
  onClose: () => void;
}

const TITLES: Record<DashboardBoardId, string> = {
  mention: '提及率分析',
  source: '内容引用分析',
  radar: '五维雷达分析',
};

const ICONS: Record<DashboardBoardId, typeof RiChatQuoteLine> = {
  mention: RiChatQuoteLine,
  source: RiBookMarkedLine,
  radar: RiRadarLine,
};

const ICON_STYLES: Record<DashboardBoardId, { bg: string; color: string }> = {
  mention: {
    bg: 'color-mix(in srgb, var(--color-primary) 14%, var(--bg-elevated) 86%)',
    color: 'var(--color-primary)',
  },
  source: {
    bg: 'color-mix(in srgb, #d6a05c 16%, var(--bg-elevated) 84%)',
    color: '#b67e38',
  },
  radar: {
    bg: 'color-mix(in srgb, #8bb0a2 16%, var(--bg-elevated) 84%)',
    color: '#568874',
  },
};

export function DashboardBoardDialog({ open, board, home, onClose }: DashboardBoardDialogProps) {
  if (!home || !board) {
    return null;
  }

  const renderContent = () => {
    switch (board) {
      case 'mention':
        return <MentionBoardReport data={home.mention_board} />;
      case 'source':
        return <SourceBoardReport data={home.source_board} />;
      case 'radar':
        return <RadarBoardReport data={home.radar_board} />;
      default:
        return null;
    }
  };

  const Icon = ICONS[board];
  const iconStyle = ICON_STYLES[board];

  return (
    <Dialog.Root open={open} onOpenChange={(next) => !next && onClose()}>
      <Dialog.Portal>
        <Dialog.Overlay className={modalScrimClassName('z-50')} />
        <Dialog.Content className="fixed inset-0 z-50 flex items-center justify-center p-4 md:p-6">
          <div
            className="dashboard-dialog-shell flex h-[min(92vh,1120px)] w-[min(96vw,1640px)] flex-col overflow-hidden rounded-[32px]"
          >
            <div className="flex items-center justify-between border-b border-[var(--border-subtle)] px-7 py-5 md:px-8">
              <div className="flex items-center gap-3">
                <div className="flex h-11 w-11 items-center justify-center rounded-[15px]" style={{ background: iconStyle.bg }}>
                  <Icon className="h-5 w-5" style={{ color: iconStyle.color }} />
                </div>
                <Dialog.Title className="text-[22px] font-semibold tracking-[-0.03em] text-[var(--text-primary)]">
                  {TITLES[board]}
                </Dialog.Title>
              </div>
              <Dialog.Close asChild>
                <button
                  type="button"
                  className="flex h-11 w-11 items-center justify-center rounded-full border transition-colors hover:border-[var(--border-hover)] hover:bg-[var(--bg-tertiary)]"
                  style={{ borderColor: 'var(--border-subtle)', color: 'var(--text-secondary)' }}
                  aria-label="关闭说明报告"
                >
                  <RiCloseLine className="h-5 w-5" />
                </button>
              </Dialog.Close>
            </div>

            <div className="min-h-0 flex-1 overflow-y-auto px-5 py-5 md:px-8 md:py-8">{renderContent()}</div>
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
