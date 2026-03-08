'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { RiChat1Line } from '@remixicon/react';
import { BrandCard, AddBrandCard } from './BrandCard';
import { BrandManageDialog } from './BrandManageDialog';
import { BrandDetailDialog } from './BrandDetailDialog';
import { EntityFormDialog } from './EntityFormDialog';
import { useEntityStore } from '@/stores/entityStore';
import { useDashboardStore } from '@/stores/dashboardStore';
import { api } from '@/services/api';
import { toast } from '@/components/ui/toast';
import type { Entity, CreateEntityInput } from '@/types/entity';

export function BrandCards() {
  const router = useRouter();
  const { entities, addEntity } = useEntityStore();
  const { selectedBrandId, setSelectedBrandId } = useDashboardStore();
  const [manageOpen, setManageOpen] = useState(false);
  const [addOpen, setAddOpen] = useState(false);
  const [detailEntity, setDetailEntity] = useState<Entity | null>(null);
  const [navigating, setNavigating] = useState(false);

  const handleAddBrand = async (data: CreateEntityInput) => {
    try {
      const created = await api.createEntity(data);
      addEntity(created);
      setAddOpen(false);
    } catch {
      toast.error('品牌创建失败');
    }
  };

  const handleBrandClick = async (entity: Entity) => {
    if (navigating) return;
    setNavigating(true);
    try {
      // 先查已有 Session — 有历史对话，直接进入，不自动发送品牌名
      const session = await api.getSessionByEntity(entity.id);
      router.push(`/chat/${session.id}?brand=${encodeURIComponent(entity.name || '')}`);
    } catch {
      // 404 — 创建新 Session，带品牌名参数自动开始分析
      try {
        const session = await api.createSession(entity.id);
        const brandName = entity.name || '';
        router.push(`/chat/${session.id}?brand=${encodeURIComponent(brandName)}`);
      } catch {
        toast.error('品牌加载失败');
      }
    } finally {
      setNavigating(false);
    }
  };

  return (
    <div>
      {/* Section header */}
      <div className="flex items-center justify-between mb-3">
        <h2 className="text-lg font-semibold" style={{ color: 'var(--text-primary)' }}>
          品牌管理
        </h2>
        {entities.length > 0 && (
          <button
            className="text-xs font-medium cursor-pointer hover:opacity-80 transition-opacity"
            style={{ color: 'var(--color-primary)' }}
            onClick={() => setManageOpen(true)}
          >
            管理全部
          </button>
        )}
      </div>

      {/* Empty state hint */}
      {entities.length === 0 && (
        <p className="text-sm mb-3" style={{ color: 'var(--text-tertiary)' }}>
          添加品牌后，即可开始 AI 搜索可见度分析
        </p>
      )}

      {/* Horizontal scroll */}
      <div className="flex overflow-x-auto snap-x snap-mandatory gap-4 pb-2">
        {entities.map((entity) => (
          <div key={entity.id} className="flex flex-col gap-2">
            <BrandCard
              entity={entity}
              isSelected={selectedBrandId === entity.id}
              onClick={() => setSelectedBrandId(selectedBrandId === entity.id ? null : entity.id)}
            />
            <button
              className="w-[200px] flex items-center justify-center gap-1.5 px-3 py-2 rounded-lg text-xs font-medium cursor-pointer"
              style={{ background: 'var(--bg-elevated)', color: 'var(--text-secondary)', border: '1px solid var(--border-subtle)' }}
              onClick={() => handleBrandClick(entity)}
            >
              <RiChat1Line className="w-3.5 h-3.5" />
              进入对话分析
            </button>
          </div>
        ))}
        <div>
          <AddBrandCard onClick={() => setAddOpen(true)} />
        </div>
      </div>

      {/* Dialogs */}
      <BrandManageDialog open={manageOpen} onClose={() => setManageOpen(false)} />
      <EntityFormDialog
        open={addOpen}
        onClose={() => setAddOpen(false)}
        onSubmit={handleAddBrand}
      />
      <BrandDetailDialog
        entity={detailEntity}
        open={!!detailEntity}
        onClose={() => setDetailEntity(null)}
      />
    </div>
  );
}
