'use client';

import { motion } from 'framer-motion';
import {
  RiAlertLine,
  RiInformationLine,
  RiErrorWarningLine,
  RiCheckLine,
  RiCloseLine,
  RiShieldLine,
} from '@remixicon/react';
import type { SystemNoticeData } from '@/types/message';

interface DegradationNoticeProps {
  notice: SystemNoticeData;
}

/**
 * DegradationNotice renders system degradation and platform status notifications
 * inline within the chat message flow. It supports two subtypes:
 *
 * - `degradation`: Agent-level fallback notices (A2/A5 degradation)
 * - `platform_status`: A4 platform success/failure grid
 *
 * Color coding by level:
 * - info (blue): Normal partial failure, system handled it
 * - warning (amber): Degraded experience, user should be aware
 * - error (red): Severe failure, limited results
 */
export function DegradationNotice({ notice }: DegradationNoticeProps) {
  const { subtype, level, title, description, impact, platforms } = notice;

  const levelConfig = getLevelConfig(level);

  return (
    <motion.div
      className="my-2 rounded-xl"
      style={{
        background: levelConfig.bg,
        border: `1px solid ${levelConfig.border}`,
        padding: '12px 16px',
      }}
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3 }}
      role="status"
      aria-live="polite"
    >
      {/* Header: icon + title */}
      <div className="flex items-start gap-2">
        <levelConfig.Icon
          className="w-4 h-4 flex-shrink-0 mt-0.5"
          style={{ color: levelConfig.iconColor }}
        />
        <span
          className="text-[13px] font-semibold leading-snug"
          style={{ color: levelConfig.titleColor }}
        >
          {title}
        </span>
      </div>

      {/* Description */}
      {description && (
        <p
          className="text-xs leading-relaxed mt-1.5 ml-6"
          style={{ color: 'var(--text-secondary, #D4D4D4)' }}
        >
          {description}
        </p>
      )}

      {/* Platform status grid (platform_status subtype) */}
      {subtype === 'platform_status' && platforms && platforms.length > 0 && (
        <div className="mt-3 ml-6 space-y-1">
          {platforms.map((platform) => (
            <PlatformStatusRow key={platform.name} platform={platform} />
          ))}
        </div>
      )}

      {/* Impact section */}
      {impact && (
        <div
          className="mt-2 ml-6 pt-2"
          style={{
            borderTop: `1px solid ${levelConfig.divider}`,
          }}
        >
          <p
            className="text-xs leading-relaxed"
            style={{ color: 'var(--text-secondary, #A3A3A3)' }}
          >
            {impact}
          </p>
        </div>
      )}
    </motion.div>
  );
}

/** Platform status row within platform_status notices */
function PlatformStatusRow({
  platform,
}: {
  platform: NonNullable<SystemNoticeData['platforms']>[number];
}) {
  const { name, status, detail } = platform;

  const statusConfig = getStatusConfig(status);

  return (
    <div
      className="grid items-center gap-2 text-xs"
      style={{
        gridTemplateColumns: '16px 72px 48px 1fr',
        lineHeight: '28px',
      }}
    >
      <statusConfig.Icon
        className="w-3.5 h-3.5"
        style={{ color: statusConfig.color }}
      />
      <span style={{ color: 'var(--text-primary, #E5E5E5)' }}>{name}</span>
      <span style={{ color: statusConfig.color, fontSize: '11px' }}>
        {statusConfig.label}
      </span>
      {detail && (
        <span style={{ color: 'var(--text-tertiary, #8A8A8A)', fontSize: '11px' }}>
          {detail}
        </span>
      )}
    </div>
  );
}

/** Level-specific styling configuration */
function getLevelConfig(level: SystemNoticeData['level']) {
  switch (level) {
    case 'info':
      return {
        bg: 'rgba(59, 130, 246, 0.06)',
        border: 'rgba(59, 130, 246, 0.15)',
        divider: 'rgba(59, 130, 246, 0.1)',
        iconColor: 'var(--info, #3B82F6)',
        titleColor: 'var(--info)',
        Icon: RiInformationLine,
      };
    case 'warning':
      return {
        bg: 'rgba(245, 158, 11, 0.08)',
        border: 'rgba(245, 158, 11, 0.2)',
        divider: 'rgba(245, 158, 11, 0.1)',
        iconColor: 'var(--warning, #F59E0B)',
        titleColor: 'var(--warning)',
        Icon: RiAlertLine,
      };
    case 'error':
      return {
        bg: 'rgba(239, 68, 68, 0.08)',
        border: 'rgba(239, 68, 68, 0.2)',
        divider: 'rgba(239, 68, 68, 0.1)',
        iconColor: 'var(--error, #EF4444)',
        titleColor: 'var(--error)',
        Icon: RiErrorWarningLine,
      };
  }
}

/** Platform status icon and label configuration */
function getStatusConfig(status: 'success' | 'failed' | 'skipped') {
  switch (status) {
    case 'success':
      return {
        Icon: RiCheckLine,
        color: 'var(--success, #22C55E)',
        label: '成功',
      };
    case 'failed':
      return {
        Icon: RiCloseLine,
        color: 'var(--error, #EF4444)',
        label: '失败',
      };
    case 'skipped':
      return {
        Icon: RiShieldLine,
        color: 'var(--text-tertiary, #8A8A8A)',
        label: '已跳过',
      };
  }
}

export default DegradationNotice;
