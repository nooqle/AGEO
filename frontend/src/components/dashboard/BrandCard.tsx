'use client';

import { useMemo } from 'react';
import { motion } from 'framer-motion';
import { RiAddLine } from '@remixicon/react';
import type { Entity } from '@/types/entity';
import { BrandAvatar } from './BrandAvatar';

interface BrandCardProps {
  entity: Entity;
  isSelected?: boolean;
  onClick?: () => void;
}

interface AddBrandCardProps {
  onClick: () => void;
}

export function BrandCard({ entity, isSelected, onClick }: BrandCardProps) {
  const lastAnalyzedLabel = useMemo(() => {
    if (!entity.lastAnalyzed) return '未分析';
    // eslint-disable-next-line react-hooks/purity -- Date.now() is intentional for "time ago" display
    const diff = Date.now() - new Date(entity.lastAnalyzed).getTime();
    const days = Math.floor(diff / 86400000);
    if (days === 0) return '今天分析';
    if (days === 1) return '昨天分析';
    if (days < 7) return `${days} 天前分析`;
    return new Date(entity.lastAnalyzed).toLocaleDateString('zh-CN', { month: 'short', day: 'numeric' }) + ' 分析';
  }, [entity.lastAnalyzed]);

  return (
    <motion.div
      className="w-[200px] flex-shrink-0 card-modern cursor-pointer snap-start"
      style={{
        padding: 'var(--space-lg)',
        border: isSelected ? '2px solid var(--color-primary)' : undefined,
      }}
      onClick={onClick}
    >
      {/* Avatar / Logo */}
      <BrandAvatar name={entity.name} domain={entity.domain} size={40} className="mb-3" />

      {/* Brand name */}
      <div className="text-sm font-medium truncate" style={{ color: 'var(--text-primary)' }}>
        {entity.name}
      </div>

      {/* Domain */}
      {entity.domain && (
        <div className="text-xs truncate mt-0.5" style={{ color: 'var(--text-muted)' }}>
          {entity.domain}
        </div>
      )}

      {/* Industry + Last analyzed */}
      <div className="flex items-center gap-2 mt-2">
        {entity.industry && (
          <span className="text-xs" style={{ color: 'var(--text-tertiary)' }}>
            {entity.industry}
          </span>
        )}
      </div>
      <div className="text-xs mt-1" style={{ color: 'var(--text-muted)' }}>
        {lastAnalyzedLabel}
      </div>
    </motion.div>
  );
}

export function AddBrandCard({ onClick }: AddBrandCardProps) {
  return (
    <motion.div
      className="w-[200px] flex-shrink-0 rounded-xl cursor-pointer snap-start flex flex-col items-center justify-center"
      style={{
        padding: 'var(--space-lg)',
        border: '1px dashed var(--border-subtle)',
        minHeight: '140px',
      }}
      onClick={onClick}
      whileHover={{ scale: 1.02, borderColor: 'var(--border-hover)' }}
      transition={{ duration: 0.2 }}
    >
      <div
        className="w-10 h-10 rounded-full flex items-center justify-center mb-2"
        style={{ background: 'var(--bg-tertiary)' }}
      >
        <RiAddLine className="w-5 h-5" style={{ color: 'var(--text-tertiary)' }} />
      </div>
      <span className="text-sm" style={{ color: 'var(--text-tertiary)' }}>
        新建品牌
      </span>
    </motion.div>
  );
}
