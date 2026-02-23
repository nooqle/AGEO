'use client';

import { useState } from 'react';
import * as Dialog from '@radix-ui/react-dialog';
import { RiCloseLine, RiSearchLine, RiEditLine, RiDeleteBinLine, RiAddLine } from '@remixicon/react';
import { motion, AnimatePresence } from 'framer-motion';
import { EntityFormDialog } from './EntityFormDialog';
import { useEntityStore } from '@/stores/entityStore';
import { api } from '@/services/api';
import type { Entity, CreateEntityInput } from '@/types/entity';

interface BrandManageDialogProps {
  open: boolean;
  onClose: () => void;
}

export function BrandManageDialog({ open, onClose }: BrandManageDialogProps) {
  const { entities, addEntity, updateEntity, removeEntity } = useEntityStore();
  const [search, setSearch] = useState('');
  const [editEntity, setEditEntity] = useState<Entity | null>(null);
  const [formOpen, setFormOpen] = useState(false);

  const filtered = entities.filter((e) =>
    e.name.toLowerCase().includes(search.toLowerCase()) ||
    e.domain.toLowerCase().includes(search.toLowerCase())
  );

  const handleDelete = async (id: string) => {
    if (!confirm('确定要删除该品牌吗？此操作将同时删除该品牌的所有分析会话和聊天记录，且无法恢复。')) return;
    try {
      await api.deleteEntity(id);
      removeEntity(id);
    } catch {
      // silently handle
    }
  };

  const handleSubmit = async (data: CreateEntityInput) => {
    try {
      if (editEntity) {
        const updated = await api.updateEntity(editEntity.id, data);
        updateEntity(editEntity.id, updated);
      } else {
        const created = await api.createEntity(data);
        addEntity(created);
      }
      setFormOpen(false);
      setEditEntity(null);
    } catch {
      // silently handle
    }
  };

  const openEdit = (entity: Entity) => {
    setEditEntity(entity);
    onClose();
    setFormOpen(true);
  };

  // onClose() + setFormOpen(true) 依赖 React 18+ automatic batching，两次 setState 在同一事件回调中合并为一次渲染
  const openAdd = () => {
    setEditEntity(null);
    onClose();
    setFormOpen(true);
  };

  return (
    <>
      <Dialog.Root open={open} onOpenChange={(o) => !o && onClose()}>
        <Dialog.Portal>
          <Dialog.Overlay
            className="fixed inset-0 z-50"
            style={{ background: 'rgba(0,0,0,0.6)' }}
          />
          <Dialog.Content
            className="fixed inset-0 z-50 flex items-center justify-center p-4"
          >
            <motion.div
              className="w-full max-w-4xl max-h-[80vh] flex flex-col rounded-2xl overflow-hidden"
              style={{
                background: 'var(--bg-secondary)',
                border: '1px solid var(--border-default)',
              }}
              initial={{ opacity: 0, scale: 0.96 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0, scale: 0.96 }}
              transition={{ duration: 0.2 }}
            >
              {/* Header */}
              <div
                className="flex items-center justify-between px-6 py-4"
                style={{ borderBottom: '1px solid var(--border-default)' }}
              >
                <Dialog.Title className="text-lg font-semibold" style={{ color: 'var(--text-primary)' }}>
                  品牌管理
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

              {/* Search + Add */}
              <div className="px-6 py-3 flex items-center gap-3">
                <div
                  className="flex items-center gap-2 flex-1 px-3 py-2 rounded-lg"
                  style={{
                    background: 'var(--bg-primary)',
                    border: '1px solid var(--border-default)',
                  }}
                >
                  <RiSearchLine className="w-4 h-4" style={{ color: 'var(--text-muted)' }} />
                  <input
                    type="text"
                    value={search}
                    onChange={(e) => setSearch(e.target.value)}
                    placeholder="搜索品牌名称或域名..."
                    className="bg-transparent text-sm outline-none flex-1"
                    style={{ color: 'var(--text-primary)', border: 'none', background: 'transparent', boxShadow: 'none' }}
                  />
                </div>
                <button
                  className="btn-primary flex items-center gap-1.5 px-4 py-2 text-sm cursor-pointer"
                  onClick={openAdd}
                >
                  <RiAddLine className="w-4 h-4" />
                  新建
                </button>
              </div>

              {/* Brand grid */}
              <div className="flex-1 overflow-auto px-6 py-3">
                {filtered.length === 0 ? (
                  <div className="text-center py-12" style={{ color: 'var(--text-muted)' }}>
                    {search ? '未找到匹配的品牌' : '暂无品牌，点击上方「新建」添加'}
                  </div>
                ) : (
                  <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
                    <AnimatePresence>
                      {filtered.map((entity) => {
                        const initial = entity.name.charAt(0).toUpperCase();
                        return (
                          <motion.div
                            key={entity.id}
                            className="card-modern flex flex-col"
                            style={{ padding: 'var(--space-lg)' }}
                            layout
                            initial={{ opacity: 0, scale: 0.95 }}
                            animate={{ opacity: 1, scale: 1 }}
                            exit={{ opacity: 0, scale: 0.95 }}
                            transition={{ duration: 0.2 }}
                          >
                            <div className="flex items-start gap-3 mb-3">
                              <div
                                className="w-10 h-10 rounded-full flex items-center justify-center flex-shrink-0"
                                style={{ background: 'var(--gradient-primary)' }}
                              >
                                <span className="text-lg font-bold text-white">{initial}</span>
                              </div>
                              <div className="min-w-0 flex-1">
                                <div className="text-sm font-medium truncate" style={{ color: 'var(--text-primary)' }}>
                                  {entity.name}
                                </div>
                                {entity.domain && (
                                  <div className="text-xs truncate mt-0.5" style={{ color: 'var(--text-muted)' }}>
                                    {entity.domain}
                                  </div>
                                )}
                              </div>
                            </div>

                            {entity.industry && (
                              <div className="text-xs mb-3" style={{ color: 'var(--text-tertiary)' }}>
                                {entity.industry}
                              </div>
                            )}

                            {/* Action buttons */}
                            <div className="flex gap-2 mt-auto pt-2" style={{ borderTop: '1px solid var(--border-default)' }}>
                              <button
                                className="p-1.5 rounded-md transition-colors cursor-pointer"
                                style={{ color: 'var(--text-tertiary)' }}
                                onClick={() => openEdit(entity)}
                                title="编辑"
                              >
                                <RiEditLine className="w-4 h-4" />
                              </button>
                              <button
                                className="p-1.5 rounded-md transition-colors cursor-pointer"
                                style={{ color: 'var(--status-error)' }}
                                onClick={() => handleDelete(entity.id)}
                                title="删除"
                              >
                                <RiDeleteBinLine className="w-4 h-4" />
                              </button>
                            </div>
                          </motion.div>
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

      {/* Entity form dialog (edit/add) */}
      <EntityFormDialog
        open={formOpen}
        onClose={() => { setFormOpen(false); setEditEntity(null); }}
        onSubmit={handleSubmit}
        entity={editEntity}
      />
    </>
  );
}
