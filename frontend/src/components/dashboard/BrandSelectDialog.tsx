'use client';

import { useState, useMemo } from 'react';
import { useRouter } from 'next/navigation';
import * as Dialog from '@radix-ui/react-dialog';
import { RiCloseLine, RiSearchLine, RiAddLine, RiCheckLine } from '@remixicon/react';
import { motion } from 'framer-motion';
import { EntityFormDialog } from './EntityFormDialog';
import { BrandAvatar } from './BrandAvatar';
import { useEntityStore } from '@/stores/entityStore';
import { api } from '@/services/api';
import { toast } from '@/components/ui/toast';
import { modalScrimClassName } from '@/components/ui/modal-scrim';
import { buildBrandMonitoringChatUrl } from '@/lib/dashboardChatEntry';
import type { CreateEntityInput } from '@/types/entity';

interface BrandSelectDialogProps {
  open: boolean;
  onClose: () => void;
}

function formatRelativeTime(dateStr: string | null): string {
  if (!dateStr) return '未分析';
  const date = new Date(dateStr);
  const now = new Date();
  const diff = now.getTime() - date.getTime();
  const days = Math.floor(diff / 86400000);

  if (days === 0) return '今天';
  if (days === 1) return '昨天';
  if (days < 7) return `${days} 天前`;
  return date.toLocaleDateString('zh-CN', { month: 'short', day: 'numeric' });
}

export function BrandSelectDialog({ open, onClose }: BrandSelectDialogProps) {
  const router = useRouter();
  const { entities, addEntity } = useEntityStore();
  const [search, setSearch] = useState('');
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [formOpen, setFormOpen] = useState(false);
  const [isCreating, setIsCreating] = useState(false);

  const filtered = useMemo(() => {
    if (!search.trim()) return entities;
    const q = search.toLowerCase();
    return entities.filter(
      (e) => e.name.toLowerCase().includes(q) || e.domain.toLowerCase().includes(q)
    );
  }, [entities, search]);

  const selectedEntity = entities.find((e) => e.id === selectedId) || null;

  const handleStartAnalysis = async () => {
    if (!selectedEntity || isCreating) return;
    setIsCreating(true);
    try {
      const session = await api.getOrCreateSessionByEntity(selectedEntity.id);
      onClose();
      router.push(`/chat/${session.id}?entity_id=${encodeURIComponent(selectedEntity.id)}&brand=${encodeURIComponent(selectedEntity.name)}`);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : '品牌加载失败');
    } finally {
      setIsCreating(false);
    }
  };

  const handleAddBrand = async (data: CreateEntityInput) => {
    try {
      const created = await api.createEntity(data);
      addEntity(created);
      setFormOpen(false);
      onClose();
      const session = await api.getOrCreateSessionByEntity(created.id);
      router.push(buildBrandMonitoringChatUrl({
        sessionId: session.id,
        entityId: created.id,
        brandName: created.name || data.name,
      }));
    } catch {
      toast.error('品牌创建或打开对话失败');
    }
  };

  return (
    <>
      <Dialog.Root open={open} onOpenChange={(o) => !o && onClose()}>
        <Dialog.Portal>
          <Dialog.Overlay className={modalScrimClassName('z-50')} />
          <Dialog.Content className="fixed inset-0 z-50 flex items-center justify-center p-4">
            <motion.div
              className="w-full max-w-2xl flex flex-col rounded-xl overflow-hidden max-h-[80vh]"
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
                className="px-6 py-4"
                style={{ borderBottom: '1px solid var(--border-subtle)' }}
              >
                <div className="flex items-center justify-between">
                  <div>
                    <Dialog.Title className="text-lg font-semibold" style={{ color: 'var(--text-primary)' }}>
                      选择品牌
                    </Dialog.Title>
                    <Dialog.Description className="text-sm mt-0.5" style={{ color: 'var(--text-tertiary)' }}>
                      选择要分析的品牌，或创建新品牌
                    </Dialog.Description>
                  </div>
                  <Dialog.Close asChild>
                    <button
                      className="p-1.5 rounded-lg transition-colors cursor-pointer"
                      style={{ color: 'var(--text-tertiary)' }}
                    >
                      <RiCloseLine className="w-5 h-5" />
                    </button>
                  </Dialog.Close>
                </div>

                {/* Search */}
                {entities.length > 0 && (
                  <div
                    className="flex items-center gap-2 px-3 py-2 rounded-lg mt-3"
                    style={{
                      background: 'var(--bg-tertiary)',
                      border: '1px solid var(--border-subtle)',
                    }}
                  >
                    <RiSearchLine className="w-4 h-4" style={{ color: 'var(--text-muted)' }} />
                    <input
                      type="text"
                      value={search}
                      onChange={(e) => setSearch(e.target.value)}
                      placeholder="搜索品牌名称或域名..."
                      className="bg-transparent text-sm outline-none flex-1"
                      style={{ color: 'var(--text-primary)', border: 'none' }}
                    />
                  </div>
                )}
              </div>

              {/* Brand Grid */}
              <div className="flex-1 overflow-auto px-6 py-4">
                {entities.length === 0 ? (
                  <div className="text-center py-12">
                    <p className="text-base mb-2" style={{ color: 'var(--text-secondary)' }}>
                      暂无品牌
                    </p>
                    <p className="text-sm mb-6" style={{ color: 'var(--text-muted)' }}>
                      创建首个品牌，开始跟踪答案可见度
                    </p>
                    <button
                      className="btn-primary px-5 py-2.5 text-sm cursor-pointer"
                      onClick={() => setFormOpen(true)}
                    >
                      创建首个品牌
                    </button>
                  </div>
                ) : (
                  <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
                    {filtered.map((entity) => {
                      const isSelected = selectedId === entity.id;
                      return (
                        <motion.button
                          key={entity.id}
                          className="text-left p-4 rounded-xl cursor-pointer transition-all relative"
                          style={{
                            background: 'var(--bg-tertiary)',
                            border: isSelected ? '1px solid var(--brand-primary)' : '1px solid var(--border-subtle)',
                            boxShadow: isSelected ? '0 0 0 1px color-mix(in srgb, var(--brand-primary) 28%, transparent)' : 'none',
                          }}
                          onClick={() => setSelectedId(isSelected ? null : entity.id)}
                          whileHover={{ scale: 1.02 }}
                          transition={{ duration: 0.15 }}
                        >
                          {/* Selected check */}
                          {isSelected && (
                            <div
                              className="absolute top-2 right-2 w-5 h-5 rounded-full flex items-center justify-center"
                              style={{ background: 'var(--brand-primary)' }}
                            >
                              <RiCheckLine className="w-3 h-3 text-[var(--brand-contrast)]" />
                            </div>
                          )}

                          {/* Avatar */}
                          <BrandAvatar name={entity.name} domain={entity.domain} size={40} className="mb-3" />

                          <div className="text-sm font-medium truncate" style={{ color: 'var(--text-primary)' }}>
                            {entity.name}
                          </div>
                          {entity.domain && (
                            <div className="text-xs truncate mt-0.5" style={{ color: 'var(--text-muted)' }}>
                              {entity.domain}
                            </div>
                          )}
                          <div className="text-xs mt-2" style={{ color: 'var(--text-muted)' }}>
                            {formatRelativeTime(entity.lastAnalyzed)}
                          </div>
                        </motion.button>
                      );
                    })}

                    {/* Add new brand card */}
                    <motion.button
                      className="flex flex-col items-center justify-center p-4 rounded-xl cursor-pointer"
                      style={{
                        border: '1px dashed var(--border-subtle)',
                        minHeight: '140px',
                      }}
                      onClick={() => setFormOpen(true)}
                      whileHover={{ scale: 1.02, borderColor: 'var(--border-hover)' }}
                      transition={{ duration: 0.15 }}
                    >
                      <div
                        className="w-10 h-10 rounded-full flex items-center justify-center mb-2"
                        style={{ background: 'var(--bg-elevated)' }}
                      >
                        <RiAddLine className="w-5 h-5" style={{ color: 'var(--text-tertiary)' }} />
                      </div>
                      <span className="text-sm" style={{ color: 'var(--text-tertiary)' }}>
                        新品牌
                      </span>
                    </motion.button>
                  </div>
                )}
              </div>

              {/* Footer */}
              {entities.length > 0 && (
                <div
                  className="flex items-center justify-end px-6 py-4"
                  style={{ borderTop: '1px solid var(--border-subtle)' }}
                >
                  <button
                    className="btn-primary px-5 py-2 text-sm cursor-pointer"
                    onClick={handleStartAnalysis}
                    disabled={!selectedEntity || isCreating}
                    style={{ opacity: !selectedEntity || isCreating ? 0.5 : 1 }}
                  >
                    {isCreating ? '创建中...' : '开始分析'}
                  </button>
                </div>
              )}
            </motion.div>
          </Dialog.Content>
        </Dialog.Portal>
      </Dialog.Root>

      <EntityFormDialog
        open={formOpen}
        onClose={() => setFormOpen(false)}
        onSubmit={handleAddBrand}
      />
    </>
  );
}
