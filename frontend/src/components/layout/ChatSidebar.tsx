'use client';

import { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { motion, AnimatePresence } from 'framer-motion';
import {
  RiArrowLeftSLine,
  RiArrowRightSLine,
  RiDeleteBinLine,
  RiMoreLine,
  RiTimeLine,
} from '@remixicon/react';
import { cn } from '@/lib/cn';
import { BrandAvatar } from '@/components/dashboard/BrandAvatar';
import { NotificationBell } from '@/components/notifications/NotificationBell';
import { ThemeToggle } from '@/components/ui/ThemeToggle';
import { HomeBrandLink } from './HomeBrandLink';
import { useEntityStore } from '@/stores/entityStore';
import { api } from '@/services/api';
import { toast } from '@/components/ui/toast';

interface ChatSidebarProps {
  activeSessionId?: string;
  activeEntityId?: string;
  className?: string;
  collapsed?: boolean;
  onToggleCollapsed?: () => void;
}

export function ChatSidebar({
  activeSessionId,
  activeEntityId,
  className,
  collapsed = false,
  onToggleCollapsed,
}: ChatSidebarProps) {
  const router = useRouter();
  const { entities, fetchEntities, removeEntity } = useEntityStore();
  const [menuOpenId, setMenuOpenId] = useState<string | null>(null);
  const [navigating, setNavigating] = useState(false);

  useEffect(() => {
    fetchEntities();
  }, [fetchEntities]);

  useEffect(() => {
    if (collapsed) {
      setMenuOpenId(null);
    }
  }, [collapsed]);

  void activeSessionId;

  const handleEntityClick = async (entityId: string) => {
    if (navigating) return;
    setNavigating(true);
    try {
      const session = await api.getOrCreateSessionByEntity(entityId);
      const entity = entities.find((item) => item.id === entityId);
      router.push(
        `/chat/${session.id}?entity_id=${encodeURIComponent(entityId)}&brand=${encodeURIComponent(entity?.name || '')}`
      );
    } catch (error) {
      toast.error(error instanceof Error ? error.message : '数据加载失败');
    } finally {
      setNavigating(false);
    }
  };

  const handleDeleteEntity = async (entityId: string) => {
    const confirmed = window.confirm(
      '确定要删除该品牌吗？此操作将同时删除该品牌的所有分析会话和聊天记录，且无法恢复。'
    );
    if (!confirmed) return;
    try {
      await api.deleteEntity(entityId);
      removeEntity(entityId);
      toast.success('品牌已删除');
      if (activeEntityId === entityId) {
        router.push('/dashboard');
      }
    } catch {
      toast.error('删除失败，请重试');
    }
  };

  const formatTime = (dateStr: string | null) => {
    if (!dateStr) return '未分析';
    const date = new Date(dateStr);
    const now = new Date();
    const diff = now.getTime() - date.getTime();
    const days = Math.floor(diff / 86400000);

    if (days === 0) {
      return date.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' });
    } else if (days === 1) {
      return '昨天';
    } else if (days < 7) {
      return `${days}天前`;
    } else {
      return date.toLocaleDateString('zh-CN', { month: 'short', day: 'numeric' });
    }
  };

  const renderMenuButton = (entityId: string, compact = false) => (
    <button
      onClick={(e) => {
        e.stopPropagation();
        setMenuOpenId(menuOpenId === entityId ? null : entityId);
      }}
      className={cn(
        'rounded transition-all',
        compact
          ? 'absolute right-1 top-1 opacity-0 group-hover:opacity-100 p-1'
          : 'opacity-0 group-hover:opacity-100 p-1'
      )}
      onMouseEnter={(e) => {
        e.currentTarget.style.backgroundColor = 'var(--bg-elevated)';
      }}
      onMouseLeave={(e) => {
        e.currentTarget.style.backgroundColor = 'transparent';
      }}
    >
      <RiMoreLine
        className={compact ? 'h-3 w-3' : 'h-3.5 w-3.5'}
        style={{ color: 'var(--text-tertiary)' }}
      />
    </button>
  );

  return (
    <div
      className={cn('flex h-full flex-col', className)}
      style={{ backgroundColor: 'var(--bg-primary)' }}
    >
      <div
        className={cn(
          'p-3',
          collapsed
            ? 'flex flex-col items-center gap-2'
            : 'flex items-center justify-between'
        )}
        style={{ borderBottom: '1px solid var(--border-subtle)' }}
      >
        <HomeBrandLink
          size={24}
          showSubtitle={false}
          requireConfirm
          compact={collapsed}
          className={cn(
            'rounded-lg p-1 transition-colors',
            collapsed
              ? 'flex w-full items-center justify-center'
              : 'flex items-center gap-2'
          )}
        />
        <div
          className={cn(
            'flex',
            collapsed ? 'flex-col items-center gap-2' : 'items-center gap-1'
          )}
        >
          {onToggleCollapsed ? (
            <button
              onClick={onToggleCollapsed}
              className="flex h-8 w-8 items-center justify-center rounded-lg border transition-colors"
              style={{
                borderColor: 'var(--border-subtle)',
                color: 'var(--text-secondary)',
              }}
              title={collapsed ? '展开侧栏' : '收起侧栏'}
              aria-label={collapsed ? '展开侧栏' : '收起侧栏'}
            >
              {collapsed ? (
                <RiArrowRightSLine className="h-4 w-4" />
              ) : (
                <RiArrowLeftSLine className="h-4 w-4" />
              )}
            </button>
          ) : null}
          <ThemeToggle />
          <NotificationBell align="left" />
        </div>
      </div>

      <div className="flex-1 overflow-y-auto py-2">
        <AnimatePresence mode="popLayout">
          {entities.map((entity) => (
            <motion.div
              key={entity.id}
              layout
              initial={{ opacity: 0, x: -20 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: -20 }}
              className="group relative mx-2 mb-2 cursor-pointer rounded-lg transition-colors"
              style={{
                backgroundColor: activeEntityId === entity.id ? 'var(--bg-tertiary)' : undefined,
                border:
                  activeEntityId === entity.id
                    ? '1px solid var(--border-hover)'
                    : '1px solid transparent',
              }}
              onClick={() => handleEntityClick(entity.id)}
              onMouseEnter={(e) => {
                if (activeEntityId !== entity.id) {
                  e.currentTarget.style.backgroundColor = 'var(--bg-tertiary)';
                }
              }}
              onMouseLeave={(e) => {
                if (activeEntityId !== entity.id) {
                  e.currentTarget.style.backgroundColor = 'transparent';
                }
              }}
              title={
                collapsed
                  ? `${entity.name}\n${entity.domain || '未设置域名'}\n${formatTime(entity.lastAnalyzed)}`
                  : undefined
              }
            >
              <div className={cn(collapsed ? 'p-2' : 'p-3')}>
                <div
                  className={cn(
                    collapsed
                      ? 'flex flex-col items-center justify-center gap-2'
                      : 'flex items-start gap-3'
                  )}
                >
                  {collapsed ? (
                    <>
                      <BrandAvatar name={entity.name} domain={entity.domain} size={40} />
                      <span
                        className="w-full truncate text-center text-[11px] font-medium"
                        style={{ color: 'var(--text-secondary)' }}
                      >
                        {entity.name}
                      </span>
                      {renderMenuButton(entity.id, true)}
                    </>
                  ) : (
                    <>
                      <BrandAvatar
                        name={entity.name}
                        domain={entity.domain}
                        size={40}
                        className="mt-0.5 shrink-0"
                      />
                      <div className="min-w-0 flex-1">
                        <h3
                          className="truncate text-sm font-medium"
                          style={{ color: 'var(--text-primary)' }}
                        >
                          {entity.name}
                        </h3>
                        <p
                          className="mt-0.5 truncate text-xs"
                          style={{ color: 'var(--text-secondary)' }}
                        >
                          {entity.domain || '未设置域名'}
                        </p>
                        <div className="mt-1.5 flex items-center gap-2">
                          <RiTimeLine
                            className="h-3 w-3"
                            style={{ color: 'var(--text-muted)' }}
                          />
                          <span
                            className="text-[11px]"
                            style={{ color: 'var(--text-muted)' }}
                            suppressHydrationWarning
                          >
                            {formatTime(entity.lastAnalyzed)}
                          </span>
                        </div>
                      </div>
                      {renderMenuButton(entity.id)}
                    </>
                  )}
                </div>

                {menuOpenId === entity.id && (
                  <motion.div
                    initial={{ opacity: 0, y: -5 }}
                    animate={{ opacity: 1, y: 0 }}
                    className="absolute right-2 top-8 z-10 min-w-[120px] rounded-lg py-1 shadow-lg"
                    style={{
                      backgroundColor: 'var(--bg-tertiary)',
                      border: '1px solid var(--border-hover)',
                    }}
                  >
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        setMenuOpenId(null);
                        handleDeleteEntity(entity.id);
                      }}
                      className="flex w-full items-center gap-2 px-3 py-1.5 text-left text-sm transition-colors"
                      style={{ color: 'var(--status-error)' }}
                      onMouseEnter={(e) => {
                        e.currentTarget.style.backgroundColor = 'rgba(239, 68, 68, 0.1)';
                      }}
                      onMouseLeave={(e) => {
                        e.currentTarget.style.backgroundColor = 'transparent';
                      }}
                    >
                      <RiDeleteBinLine className="h-3.5 w-3.5" />
                      删除
                    </button>
                  </motion.div>
                )}
              </div>
            </motion.div>
          ))}
        </AnimatePresence>
      </div>
    </div>
  );
}
