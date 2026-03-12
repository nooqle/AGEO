'use client';

import { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { motion, AnimatePresence } from 'framer-motion';
import { RiTimeLine, RiMoreLine, RiDeleteBinLine, RiEditLine } from '@remixicon/react';
import { cn } from '@/lib/cn';
import { ArtifactNav } from './ArtifactNav';
import { NotificationBell } from '@/components/notifications/NotificationBell';
import { ThemeToggle } from '@/components/ui/ThemeToggle';
import { ThemedLogo } from '@/components/ui/ThemedLogo';
import { useEntityStore } from '@/stores/entityStore';
import { api } from '@/services/api';
import { toast } from '@/components/ui/toast';
import type { TaskStatus } from '@/types/task';

interface ChatSidebarProps {
  activeSessionId?: string;
  className?: string;
}

export function ChatSidebar({
  activeSessionId,
  className,
}: ChatSidebarProps) {
  const router = useRouter();
  const { entities, fetchEntities, removeEntity } = useEntityStore();
  const [menuOpenId, setMenuOpenId] = useState<string | null>(null);
  const [navigating, setNavigating] = useState(false);
  const [entitySessionMap, setEntitySessionMap] = useState<Record<string, string>>({});
  const [entityTaskStatus, setEntityTaskStatus] = useState<Record<string, TaskStatus | null>>({});

  useEffect(() => {
    fetchEntities();
  }, [fetchEntities]);

  // Build entity→sessionId map and query active task status for each entity
  useEffect(() => {
    if (entities.length === 0) return;
    let cancelled = false;
    const buildMap = async () => {
      const map: Record<string, string> = {};
      const taskMap: Record<string, TaskStatus | null> = {};
      for (const entity of entities) {
        try {
          const session = await api.getSessionByEntity(entity.id);
          if (cancelled) return;
          map[entity.id] = session.id;
          // Query active task status for this entity's session
          try {
            const task = await api.getActiveTask(session.id);
            if (cancelled) return;
            taskMap[entity.id] = task ? task.status : null;
          } catch {
            taskMap[entity.id] = null;
          }
        } catch {
          // No session yet for this entity
          taskMap[entity.id] = null;
        }
      }
      if (!cancelled) {
        setEntitySessionMap(map);
        setEntityTaskStatus(taskMap);
      }
    };
    buildMap();
    return () => { cancelled = true; };
  }, [entities]);

  const activeEntityId = activeSessionId
    ? Object.entries(entitySessionMap).find(([, sid]) => sid === activeSessionId)?.[0]
    : undefined;

  const handleEntityClick = async (entityId: string) => {
    if (navigating) return;
    setNavigating(true);
    try {
      const session = await api.getOrCreateSessionByEntity(entityId);
      const entity = entities.find((item) => item.id === entityId);
      router.push(`/chat/${session.id}?entity_id=${encodeURIComponent(entityId)}&brand=${encodeURIComponent(entity?.name || '')}`);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : '数据加载失败');
    } finally {
      setNavigating(false);
    }
  };

  const handleDeleteEntity = async (entityId: string) => {
    const confirmed = window.confirm('确定要删除该品牌吗？此操作将同时删除该品牌的所有分析会话和聊天记录，且无法恢复。');
    if (!confirmed) return;
    try {
      await api.deleteEntity(entityId);
      removeEntity(entityId);
      toast.success('品牌已删除');
      // If currently on this brand's chat page, redirect to dashboard
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

  const getStatusColor = (status: string, entityId?: string) => {
    // Task status takes priority over entity status
    if (entityId) {
      const taskStatus = entityTaskStatus[entityId];
      if (taskStatus === 'running') return 'var(--warning)';
      if (taskStatus === 'completed') return 'var(--success)';
    }
    switch (status) {
      case 'active':
        return 'var(--status-success)';
      case 'inactive':
        return 'var(--status-warning)';
      default:
        return 'var(--text-muted)';
    }
  };

  const getStatusAnimationClass = (entityId: string) => {
    const taskStatus = entityTaskStatus[entityId];
    if (taskStatus === 'running') return 'animate-pulse';
    if (taskStatus === 'completed') return 'animate-glow-pulse';
    return '';
  };

  return (
    <div
      className={cn('flex flex-col h-full', className)}
      style={{
        backgroundColor: 'var(--bg-primary)',
      }}
    >
      {/* Header: Logo + New button */}
      <div
        className="flex items-center justify-between p-3"
        style={{ borderBottom: '1px solid var(--border-subtle)' }}
      >
        <button
          onClick={() => router.push('/dashboard')}
          className="flex items-center gap-2 p-1 rounded-lg transition-colors"
          title="返回数据面板"
          style={{ color: 'var(--text-primary)' }}
          onMouseEnter={(e) => { e.currentTarget.style.backgroundColor = 'var(--bg-tertiary)'; }}
          onMouseLeave={(e) => { e.currentTarget.style.backgroundColor = 'transparent'; }}
        >
          <ThemedLogo size={24} />
        </button>
        <div className="flex items-center gap-1">
          <ThemeToggle />
          <NotificationBell align="left" />
        </div>
      </div>

      {/* Entity List */}
      <div className="flex-1 overflow-y-auto py-2">
        <AnimatePresence mode="popLayout">
          {entities.map((entity) => (
            <motion.div
              key={entity.id}
              layout
              initial={{ opacity: 0, x: -20 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: -20 }}
              className={cn(
                'group relative mx-2 mb-2 rounded-lg cursor-pointer transition-colors'
              )}
              style={{
                backgroundColor: activeEntityId === entity.id ? 'var(--bg-tertiary)' : undefined,
                border: activeEntityId === entity.id ? '1px solid var(--border-hover)' : '1px solid transparent',
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
            >
              <div className="p-3">
                <div className="flex items-start gap-3">
                  <div
                    className={cn('w-2 h-2 rounded-full mt-1.5 flex-shrink-0', getStatusAnimationClass(entity.id))}
                    style={{ backgroundColor: getStatusColor(entity.status, entity.id) }}
                  />
                  <div className="flex-1 min-w-0">
                    <h3
                      className="text-sm font-medium truncate"
                      style={{ color: 'var(--text-primary)' }}
                    >
                      {entity.name}
                    </h3>
                    <p
                      className="text-xs truncate mt-0.5"
                      style={{ color: 'var(--text-secondary)' }}
                    >
                      {entity.domain || '未设置域名'}
                    </p>
                    <div className="flex items-center gap-2 mt-1.5">
                      <RiTimeLine className="w-3 h-3" style={{ color: 'var(--text-muted)' }} />
                      <span className="text-[11px]" style={{ color: 'var(--text-muted)' }} suppressHydrationWarning>
                        {formatTime(entity.lastAnalyzed)}
                      </span>
                    </div>
                  </div>

                  {/* Menu button */}
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      setMenuOpenId(menuOpenId === entity.id ? null : entity.id);
                    }}
                    className="opacity-0 group-hover:opacity-100 p-1 rounded transition-all"
                    onMouseEnter={(e) => { e.currentTarget.style.backgroundColor = 'var(--bg-elevated)'; }}
                    onMouseLeave={(e) => { e.currentTarget.style.backgroundColor = 'transparent'; }}
                  >
                    <RiMoreLine className="w-3.5 h-3.5" style={{ color: 'var(--text-tertiary)' }} />
                  </button>
                </div>

                {/* Dropdown menu */}
                {menuOpenId === entity.id && (
                  <motion.div
                    initial={{ opacity: 0, y: -5 }}
                    animate={{ opacity: 1, y: 0 }}
                    className="absolute right-2 top-8 rounded-lg shadow-lg py-1 z-10 min-w-[120px]"
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
                      className="w-full px-3 py-1.5 text-left text-sm flex items-center gap-2 transition-colors"
                      style={{ color: 'var(--status-error)' }}
                      onMouseEnter={(e) => { e.currentTarget.style.backgroundColor = 'rgba(239, 68, 68, 0.1)'; }}
                      onMouseLeave={(e) => { e.currentTarget.style.backgroundColor = 'transparent'; }}
                    >
                      <RiDeleteBinLine className="w-3.5 h-3.5" />
                      删除
                    </button>
                  </motion.div>
                )}
              </div>
            </motion.div>
          ))}
        </AnimatePresence>
      </div>

      {/* Artifact Navigation — moved to ChatLayout as vertical strip */}
    </div>
  );
}
