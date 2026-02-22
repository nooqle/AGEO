'use client';

import { useRouter } from 'next/navigation';
import { motion } from 'framer-motion';
import type { SessionListItem } from '@/types/session';

interface SessionCardProps {
  session: SessionListItem;
}

function formatRelativeTime(dateStr: string): string {
  const now = Date.now();
  const d = new Date(dateStr).getTime();
  const diff = now - d;
  const minutes = Math.floor(diff / 60000);
  if (minutes < 1) return '刚刚';
  if (minutes < 60) return `${minutes} 分钟前`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours} 小时前`;
  const days = Math.floor(hours / 24);
  if (days < 30) return `${days} 天前`;
  return new Date(dateStr).toLocaleDateString('zh-CN');
}

export function SessionCard({ session }: SessionCardProps) {
  const router = useRouter();
  const isActive = session.status === 'active';

  return (
    <motion.div
      className="w-[280px] flex-shrink-0 card-modern hover-lift cursor-pointer snap-start"
      style={{ padding: 'var(--space-lg)' }}
      onClick={() => router.push(`/chat/${session.id}`)}
      whileHover={{ scale: 1.01 }}
      transition={{ duration: 0.2 }}
    >
      {/* Top: brand name + status */}
      <div className="flex items-center gap-2 mb-2">
        <span className="text-sm font-medium truncate" style={{ color: 'var(--text-primary)' }}>
          {session.brand_name || session.title || '未命名分析'}
        </span>
        <span
          className="w-1.5 h-1.5 rounded-full flex-shrink-0"
          style={{
            background: isActive ? 'var(--status-success)' : 'var(--text-muted)',
            boxShadow: isActive ? '0 0 6px var(--color-secondary-glow)' : 'none',
          }}
        />
      </div>

      {/* Preview */}
      <div
        className="text-xs truncate mb-3"
        style={{ color: 'var(--text-tertiary)' }}
      >
        {session.last_message_preview || '暂无消息'}
      </div>

      {/* Bottom: timestamp */}
      <div className="text-xs" style={{ color: 'var(--text-muted)' }}>
        {formatRelativeTime(session.updated_at)}
      </div>
    </motion.div>
  );
}
