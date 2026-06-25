'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import * as Dialog from '@radix-ui/react-dialog';
import { RiAddLine, RiCloseLine, RiDeleteBinLine, RiEditLine, RiSearchLine } from '@remixicon/react';
import { motion, AnimatePresence } from 'framer-motion';
import { EntityFormDialog } from './EntityFormDialog';
import { BrandAvatar } from './BrandAvatar';
import { useEntityStore } from '@/stores/entityStore';
import { api } from '@/services/api';
import { toast } from '@/components/ui/toast';
import { modalScrimClassName } from '@/components/ui/modal-scrim';
import { useDashboardStore } from '@/stores/dashboardStore';
import { buildBrandMonitoringChatUrl } from '@/lib/dashboardChatEntry';
import type { Entity, CreateEntityInput } from '@/types/entity';

interface BrandManageDialogProps {
  open: boolean;
  onClose: () => void;
}

function getDeleteBrandErrorMessage(error: unknown): string {
  if (!(error instanceof Error) || !error.message) {
    return '删除品牌失败，请稍后重试';
  }
  if (/request failed|status code|network error|failed to fetch/i.test(error.message)) {
    return '删除品牌失败，请稍后重试';
  }
  return error.message;
}

function hasDamagedDisplayText(value?: string | null) {
  return Boolean(value && (/�|\?{2,}/.test(value) || value.trim() === '?'));
}

function entityDisplayName(entity: Entity) {
  return hasDamagedDisplayText(entity.name)
    ? `名称显示异常 · ${entity.id.slice(-6)}`
    : entity.name;
}

function entityDisplayDomain(entity: Entity) {
  return hasDamagedDisplayText(entity.domain)
    ? '域名显示异常'
    : entity.domain;
}

function isLikelyTestEntity(entity: Entity) {
  const text = `${entity.name} ${entity.domain} ${entity.industry ?? ''}`.toLowerCase();
  return /e2e|smoke|test|specta-gate|fixture|同名品牌/.test(text);
}

export function BrandManageDialog({ open, onClose }: BrandManageDialogProps) {
  const router = useRouter();
  const { entities, addEntity, updateEntity, removeEntity } = useEntityStore();
  const { selectedBrandId } = useDashboardStore();
  const [search, setSearch] = useState('');
  const [editEntity, setEditEntity] = useState<Entity | null>(null);
  const [formOpen, setFormOpen] = useState(false);

  const filtered = entities.filter((entity) => {
    const query = search.toLowerCase();
    return entityDisplayName(entity).toLowerCase().includes(query) ||
      entityDisplayDomain(entity).toLowerCase().includes(query) ||
      entity.name.toLowerCase().includes(query) ||
      entity.domain.toLowerCase().includes(query);
  });

  const handleDelete = async (entity: Entity) => {
    const displayName = entityDisplayName(entity);
    const displayDomain = entityDisplayDomain(entity);
    if (!confirm(`确定要删除「${displayName}」吗？域名：${displayDomain || '未填写'}，ID：${entity.id.slice(-6)}。此操作将同时删除该品牌的所有分析会话和聊天记录，且无法恢复。`)) return;
    try {
      await api.deleteEntity(entity.id);
      removeEntity(entity.id);
      toast.success('品牌已删除');
    } catch (error) {
      toast.error(getDeleteBrandErrorMessage(error));
    }
  };

  const handleSubmit = async (data: CreateEntityInput) => {
    try {
      if (editEntity) {
        const updated = await api.updateEntity(editEntity.id, data);
        updateEntity(editEntity.id, updated);
        toast.success('品牌已更新');
      } else {
        const created = await api.createEntity(data);
        addEntity(created);
        toast.success('品牌已创建，正在打开对话');
        setFormOpen(false);
        setEditEntity(null);
        const session = await api.getOrCreateSessionByEntity(created.id);
        router.push(buildBrandMonitoringChatUrl({
          sessionId: session.id,
          entityId: created.id,
          brandName: created.name || data.name,
        }));
        return;
      }
      setFormOpen(false);
      setEditEntity(null);
    } catch (error) {
      const message = error instanceof Error
        ? error.message
        : editEntity
          ? '品牌更新失败'
          : '品牌创建或打开对话失败';
      toast.error(message);
      throw error;
    }
  };

  const openEdit = (entity: Entity) => {
    setEditEntity(entity);
    onClose();
    setFormOpen(true);
  };

  const openAdd = () => {
    setEditEntity(null);
    onClose();
    setFormOpen(true);
  };

  return (
    <>
      <Dialog.Root open={open} onOpenChange={(next) => !next && onClose()}>
        <Dialog.Portal>
          <Dialog.Overlay className={modalScrimClassName('z-50')} />
          <Dialog.Content className="fixed inset-0 z-50 flex items-center justify-center p-4 md:p-6">
            <motion.div
              className="flex h-[min(88vh,980px)] w-[min(94vw,1320px)] flex-col overflow-hidden rounded-[18px] border"
              style={{
                background:
                  'linear-gradient(180deg, color-mix(in srgb, var(--bg-secondary) 96%, #edf1ee 4%), var(--bg-secondary))',
                borderColor: 'color-mix(in srgb, var(--border-subtle) 86%, #7d958c 14%)',
                boxShadow: '0 30px 80px rgba(20, 25, 38, 0.14)',
              }}
              initial={{ opacity: 0, scale: 0.97, y: 8 }}
              animate={{ opacity: 1, scale: 1, y: 0 }}
              exit={{ opacity: 0, scale: 0.97, y: 8 }}
              transition={{ duration: 0.18 }}
            >
              <div className="flex items-center justify-between border-b px-7 py-5" style={{ borderColor: 'var(--border-subtle)' }}>
                <div>
                  <div className="text-[11px] font-medium tracking-[0.16em] text-[var(--text-tertiary)]">品牌列表</div>
                  <Dialog.Title className="mt-2 text-[26px] font-semibold tracking-[-0.03em] text-[var(--text-primary)]">
                    品牌管理
                  </Dialog.Title>
                  <Dialog.Description className="mt-2 text-sm text-[var(--text-secondary)]">
                    搜索、编辑和删除品牌列表；测试数据和显示异常会标记，删除前会再次确认品牌名、域名和 ID。
                  </Dialog.Description>
                </div>
                <Dialog.Close asChild>
                  <button
                    className="flex h-11 w-11 items-center justify-center rounded-lg border transition-colors hover:border-[var(--border-hover)] hover:bg-[var(--bg-tertiary)]"
                    style={{ borderColor: 'var(--border-subtle)', color: 'var(--text-secondary)' }}
                    aria-label="关闭品牌管理"
                  >
                    <RiCloseLine className="h-5 w-5" />
                  </button>
                </Dialog.Close>
              </div>

              <div className="border-b px-7 py-4" style={{ borderColor: 'var(--border-subtle)' }}>
                <div className="flex flex-col gap-3 lg:flex-row lg:items-center">
                  <div
                    className="flex flex-1 items-center gap-3 rounded-lg border px-4 py-3"
                    style={{
                      background: 'color-mix(in srgb, var(--bg-elevated) 96%, #eef1ee 4%)',
                      borderColor: 'var(--border-subtle)',
                    }}
                  >
                    <RiSearchLine className="h-4.5 w-4.5" style={{ color: 'var(--text-tertiary)' }} />
                    <input
                      type="text"
                      value={search}
                      onChange={(event) => setSearch(event.target.value)}
                      placeholder="搜索品牌名称或官网域名"
                      className="w-full bg-transparent text-[14px] outline-none placeholder:text-[var(--text-tertiary)]"
                      style={{ color: 'var(--text-primary)' }}
                    />
                  </div>

                  <button
                    className="flex min-h-11 items-center justify-center gap-2 rounded-lg px-4 py-3 text-[14px] font-medium transition-colors"
                    style={{
                      background: 'color-mix(in srgb, var(--brand-primary) 12%, var(--bg-elevated) 88%)',
                      color: 'color-mix(in srgb, var(--brand-primary) 72%, var(--text-primary) 28%)',
                      border: '1px solid color-mix(in srgb, var(--brand-primary) 18%, var(--border-subtle) 82%)',
                    }}
                    onClick={openAdd}
                  >
                    <RiAddLine className="h-4 w-4" />
                    新建品牌
                  </button>
                </div>
              </div>

              <div className="min-h-0 flex-1 overflow-y-auto px-7 py-6">
                {filtered.length === 0 ? (
                  <div className="rounded-[16px] border border-dashed px-6 py-12 text-center text-[14px] text-[var(--text-tertiary)]" style={{ borderColor: 'var(--border-subtle)' }}>
                    {search ? '未找到匹配的品牌。' : '当前还没有品牌，点击右上角新建品牌即可开始分析。'}
                  </div>
                ) : (
                  <div className="grid gap-5 md:grid-cols-2 xl:grid-cols-3">
                    <AnimatePresence>
                      {filtered.map((entity) => {
                        const displayName = entityDisplayName(entity);
                        const displayDomain = entityDisplayDomain(entity);
                        const damagedText = hasDamagedDisplayText(entity.name) || hasDamagedDisplayText(entity.domain);
                        const testEntity = isLikelyTestEntity(entity);
                        return (
                        <motion.article
                          key={entity.id}
                          className="rounded-[16px] border px-5 py-5"
                          style={{
                            background: 'linear-gradient(180deg, color-mix(in srgb, var(--bg-elevated) 98%, #eef1ee 2%), var(--bg-secondary))',
                            borderColor: 'color-mix(in srgb, var(--border-subtle) 92%, #c9d0c9 8%)',
                          }}
                          layout
                          initial={{ opacity: 0, y: 8 }}
                          animate={{ opacity: 1, y: 0 }}
                          exit={{ opacity: 0, y: 8 }}
                          transition={{ duration: 0.18 }}
                        >
                          <div className="flex items-start gap-3">
                            <BrandAvatar name={entity.name} domain={entity.domain} size={46} className="flex-shrink-0" />
                            <div className="min-w-0 flex-1">
                              <div className="flex flex-wrap items-center gap-2">
                                <div className="truncate text-[15px] font-semibold text-[var(--text-primary)]">{displayName}</div>
                                {entity.id === selectedBrandId ? (
                                  <span className="shrink-0 rounded-md bg-[var(--brand-bg)] px-2 py-0.5 text-[11px] font-medium text-[var(--brand-text)]">
                                    当前品牌
                                  </span>
                                ) : null}
                                {testEntity ? (
                                  <span className="shrink-0 rounded-md bg-[var(--bg-tertiary)] px-2 py-0.5 text-[11px] font-medium text-[var(--text-secondary)]">
                                    测试数据
                                  </span>
                                ) : null}
                                {damagedText ? (
                                  <span className="shrink-0 rounded-md border px-2 py-0.5 text-[11px] font-medium text-[var(--warning)]" style={{ borderColor: 'color-mix(in srgb, var(--warning) 36%, var(--border-subtle) 64%)' }}>
                                    显示异常
                                  </span>
                                ) : null}
                              </div>
                              {displayDomain ? (
                                <div className="mt-1 truncate text-[12px] text-[var(--text-tertiary)]">{displayDomain}</div>
                              ) : null}
                              <div className="mt-1 text-[11px] text-[var(--text-tertiary)]">ID {entity.id.slice(-6)}</div>
                            </div>
                          </div>

                          {entity.industry ? (
                            <div className="mt-4 text-[13px] text-[var(--text-secondary)]">{entity.industry}</div>
                          ) : null}

                          <div className="mt-4 border-t pt-3" style={{ borderColor: 'var(--border-subtle)' }}>
                            <div className="flex items-center gap-2">
                              <button
                                className="flex h-10 w-10 items-center justify-center rounded-lg border transition-colors hover:border-[var(--border-hover)] hover:bg-[var(--bg-secondary)]"
                                style={{ borderColor: 'var(--border-subtle)', color: 'var(--text-secondary)' }}
                                onClick={() => openEdit(entity)}
                                title="编辑品牌"
                                aria-label={`编辑品牌：${displayName} ${displayDomain || ''} ID ${entity.id.slice(-6)}`}
                              >
                                <RiEditLine className="h-4.5 w-4.5" />
                              </button>
                              <button
                                className="flex h-10 w-10 items-center justify-center rounded-lg border transition-colors hover:bg-[var(--bg-secondary)]"
                                style={{ borderColor: 'color-mix(in srgb, var(--border-subtle) 80%, #df8e84 20%)', color: 'var(--status-error)' }}
                                onClick={() => handleDelete(entity)}
                                title="删除品牌"
                                aria-label={`删除品牌：${displayName} ${displayDomain || ''} ID ${entity.id.slice(-6)}`}
                              >
                                <RiDeleteBinLine className="h-4.5 w-4.5" />
                              </button>
                            </div>
                          </div>
                        </motion.article>
                      );
                      })}
                    </AnimatePresence>
                  </div>
                )}
              </div>
            </motion.div>
          </Dialog.Content>
        </Dialog.Portal>
      </Dialog.Root>

      <EntityFormDialog
        open={formOpen}
        onClose={() => {
          setFormOpen(false);
          setEditEntity(null);
        }}
        onSubmit={handleSubmit}
        entity={editEntity}
      />
    </>
  );
}
