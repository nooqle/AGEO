'use client';

import { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import * as Dialog from '@radix-ui/react-dialog';
import { RiCloseLine, RiEditLine, RiTimeLine, RiArrowRightSLine } from '@remixicon/react';
import { motion } from 'framer-motion';
import { EntityFormDialog } from './EntityFormDialog';
import { BrandAvatar } from './BrandAvatar';
import { useSessionStore } from '@/stores/sessionStore';
import { useEntityStore } from '@/stores/entityStore';
import { api } from '@/services/api';
import { toast } from '@/components/ui/toast';
import { modalScrimClassName } from '@/components/ui/modal-scrim';
import type { Entity, CreateEntityInput } from '@/types/entity';

interface BrandDetailDialogProps {
  entity: Entity | null;
  open: boolean;
  onClose: () => void;
}

function formatRelativeTime(dateStr: string): string {
  const date = new Date(dateStr);
  const now = new Date();
  const diff = now.getTime() - date.getTime();
  const minutes = Math.floor(diff / 60000);
  const hours = Math.floor(diff / 3600000);
  const days = Math.floor(diff / 86400000);

  if (minutes < 1) return '刚刚';
  if (minutes < 60) return `${minutes} 分钟前`;
  if (hours < 24) return `${hours} 小时前`;
  if (days < 7) return `${days} 天前`;
  return date.toLocaleDateString('zh-CN', { month: 'short', day: 'numeric' });
}

function getStatusLabel(status: string): string {
  switch (status) {
    case 'active': return '进行中';
    case 'completed': return '已完成';
    case 'archived': return '已归档';
    default: return status;
  }
}

function getStatusColor(status: string): string {
  switch (status) {
    case 'active': return 'var(--status-success)';
    case 'completed': return 'var(--status-info)';
    default: return 'var(--text-muted)';
  }
}

export function BrandDetailDialog({ entity, open, onClose }: BrandDetailDialogProps) {
  const router = useRouter();
  const { sessionList, fetchSessionList } = useSessionStore();
  const { updateEntity: updateEntityInStore } = useEntityStore();
  const [editOpen, setEditOpen] = useState(false);
  const [isCreating, setIsCreating] = useState(false);

  // Filter sessions belonging to this entity
  const entitySessions = sessionList.filter((s) => s.entity_id === entity?.id);

  // Refresh session list when dialog opens
  useEffect(() => {
    if (open && entity) {
      fetchSessionList({ limit: 50 });
    }
  }, [open, entity, fetchSessionList]);

  const handleNewAnalysis = async () => {
    if (!entity || isCreating) return;
    setIsCreating(true);
    try {
      const session = await api.getOrCreateSessionByEntity(entity.id);
      onClose();
      router.push(`/chat/${session.id}?entity_id=${encodeURIComponent(entity.id)}&brand=${encodeURIComponent(entity.name)}`);
    } catch {
      // silently handle
    } finally {
      setIsCreating(false);
    }
  };

  const handleEditSubmit = async (data: CreateEntityInput) => {
    if (!entity) return;
    try {
      const updated = await api.updateEntity(entity.id, data);
      updateEntityInStore(entity.id, updated);
      setEditOpen(false);
      toast.success('品牌已更新');
    } catch (error) {
      const message = error instanceof Error ? error.message : '品牌更新失败';
      toast.error(message);
      throw error;
    }
  };

  if (!entity) return null;

  return (
    <>
      <Dialog.Root open={open} onOpenChange={(o) => !o && onClose()}>
        <Dialog.Portal>
          <Dialog.Overlay className={modalScrimClassName('z-50')} />
          <Dialog.Content className="fixed inset-0 z-50 flex items-center justify-center p-4">
            <motion.div
              className="w-full max-w-lg flex flex-col rounded-xl overflow-hidden max-h-[80vh]"
              style={{
                background: 'var(--bg-secondary)',
                border: '1px solid var(--border-subtle)',
              }}
              initial={{ opacity: 0, scale: 0.96 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0, scale: 0.96 }}
              transition={{ duration: 0.25 }}
            >
              {/* Header */}
              <div
                className="flex items-center justify-between px-6 py-4"
                style={{ borderBottom: '1px solid var(--border-subtle)' }}
              >
                <Dialog.Title className="text-lg font-semibold" style={{ color: 'var(--text-primary)' }}>
                  品牌详情
                </Dialog.Title>
                <Dialog.Close asChild>
                  <button
                    className="p-1.5 rounded-lg transition-colors cursor-pointer"
                    style={{ color: 'var(--text-tertiary)' }}
                  >
                    <RiCloseLine className="w-5 h-5" />
                  </button>
                </Dialog.Close>
              </div>

              {/* Brand Info */}
              <div className="px-6 py-5 flex items-start gap-4">
                <BrandAvatar name={entity.name} domain={entity.domain} size={60} className="flex-shrink-0" />
                <div className="min-w-0 flex-1">
                  <div className="text-lg font-semibold" style={{ color: 'var(--text-primary)' }}>
                    {entity.name}
                  </div>
                  {entity.domain && (
                    <div className="text-sm mt-0.5" style={{ color: 'var(--text-secondary)' }}>
                      {entity.domain}
                    </div>
                  )}
                  <div className="flex items-center gap-3 mt-2">
                    {entity.industry && (
                      <span className="text-xs px-2 py-0.5 rounded-full" style={{
                        background: 'var(--bg-tertiary)',
                        color: 'var(--text-tertiary)',
                      }}>
                        {entity.industry}
                      </span>
                    )}
                    <div className="flex items-center gap-1.5">
                      <div
                        className="status-dot"
                        style={{ backgroundColor: entity.status === 'active' ? 'var(--status-success)' : 'var(--text-muted)' }}
                      />
                      <span className="text-xs" style={{ color: 'var(--text-tertiary)' }}>
                        {entity.status === 'active' ? '活跃' : entity.status === 'pending' ? '待分析' : '未激活'}
                      </span>
                    </div>
                  </div>
                  {entity.lastAnalyzed && (
                    <div className="flex items-center gap-1 mt-2">
                      <RiTimeLine className="w-3 h-3" style={{ color: 'var(--text-muted)' }} />
                      <span className="text-xs" style={{ color: 'var(--text-muted)' }}>
                        最近分析: {formatRelativeTime(entity.lastAnalyzed)}
                      </span>
                    </div>
                  )}
                </div>
              </div>

              {/* Session List */}
              <div
                className="flex-1 overflow-auto px-6 pb-4"
                style={{ borderTop: '1px solid var(--border-subtle)' }}
              >
                <div className="text-sm font-medium py-3" style={{ color: 'var(--text-secondary)' }}>
                  分析记录 ({entitySessions.length})
                </div>
                {entitySessions.length === 0 ? (
                  <div className="text-center py-8">
                    <p className="text-sm mb-1" style={{ color: 'var(--text-muted)' }}>
                      暂无分析记录
                    </p>
                    <p className="text-xs" style={{ color: 'var(--text-muted)' }}>
                      点击下方「新建分析」开始首次品牌分析
                    </p>
                  </div>
                ) : (
                  <div className="space-y-2">
                    {entitySessions.map((session) => (
                      <button
                        key={session.id}
                        className="w-full text-left p-3 rounded-xl transition-colors cursor-pointer flex items-center gap-3"
                        style={{
                          background: 'var(--bg-tertiary)',
                          border: '1px solid var(--border-subtle)',
                        }}
                        onClick={() => {
                          onClose();
                          router.push(`/chat/${session.id}`);
                        }}
                        onMouseEnter={(e) => {
                          e.currentTarget.style.borderColor = 'var(--border-hover)';
                        }}
                        onMouseLeave={(e) => {
                          e.currentTarget.style.borderColor = 'var(--border-subtle)';
                        }}
                      >
                        <div className="flex-1 min-w-0">
                          <div className="text-sm font-medium truncate" style={{ color: 'var(--text-primary)' }}>
                            {session.title || '未命名分析'}
                          </div>
                          <div className="flex items-center gap-2 mt-1">
                            <div
                              className="w-1.5 h-1.5 rounded-full"
                              style={{ backgroundColor: getStatusColor(session.status) }}
                            />
                            <span className="text-xs" style={{ color: 'var(--text-tertiary)' }}>
                              {getStatusLabel(session.status)}
                            </span>
                            <span className="text-xs" style={{ color: 'var(--text-muted)' }}>
                              {formatRelativeTime(session.updated_at)}
                            </span>
                          </div>
                        </div>
                        <RiArrowRightSLine className="w-4 h-4 flex-shrink-0" style={{ color: 'var(--text-muted)' }} />
                      </button>
                    ))}
                  </div>
                )}
              </div>

              {/* Footer Actions */}
              <div
                className="flex items-center justify-between px-6 py-4"
                style={{ borderTop: '1px solid var(--border-subtle)' }}
              >
                <button
                  className="flex items-center gap-1.5 px-4 py-2 text-sm rounded-lg transition-colors cursor-pointer"
                  style={{
                    color: 'var(--text-secondary)',
                    border: '1px solid var(--border-subtle)',
                  }}
                  onClick={() => setEditOpen(true)}
                >
                  <RiEditLine className="w-4 h-4" />
                  编辑品牌
                </button>
                <button
                  className="btn-primary px-5 py-2 text-sm cursor-pointer"
                  onClick={handleNewAnalysis}
                  disabled={isCreating}
                  style={{ opacity: isCreating ? 0.6 : 1 }}
                >
                  {isCreating ? '创建中...' : '新建分析'}
                </button>
              </div>
            </motion.div>
          </Dialog.Content>
        </Dialog.Portal>
      </Dialog.Root>

      <EntityFormDialog
        open={editOpen}
        onClose={() => setEditOpen(false)}
        onSubmit={handleEditSubmit}
        entity={entity}
      />
    </>
  );
}
