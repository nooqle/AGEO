'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { BrandCard, AddBrandCard } from './BrandCard';
import { BrandManageDialog } from './BrandManageDialog';
import { BrandDetailDialog } from './BrandDetailDialog';
import { EntityFormDialog } from './EntityFormDialog';
import { useEntityStore } from '@/stores/entityStore';
import { useDashboardStore } from '@/stores/dashboardStore';
import { api } from '@/services/api';
import { toast } from '@/components/ui/toast';
import type { Entity, CreateEntityInput } from '@/types/entity';
import { DashboardSectionHeader } from './DashboardSectionHeader';

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
      const session = await api.getSessionByEntity(entity.id);
      router.push(`/chat/${session.id}?brand=${encodeURIComponent(entity.name || '')}`);
    } catch {
      try {
        const session = await api.createSession(entity.id);
        router.push(`/chat/${session.id}?brand=${encodeURIComponent(entity.name || '')}`);
      } catch {
        toast.error('品牌加载失败');
      }
    } finally {
      setNavigating(false);
    }
  };

  const handleOpenMonitoring = (entity: Entity) => {
    setSelectedBrandId(entity.id);
    router.push('/dashboard?tab=monitoring');
  };

  return (
    <section
      className="dashboard-shell rounded-[28px] px-6 py-5"
    >
      <div>
        <DashboardSectionHeader
          title="品牌与监测入口"
          action={
            entities.length > 0 ? (
              <button
                className="cursor-pointer rounded-full border px-3 py-1.5 text-[12px] font-medium transition-opacity hover:opacity-80"
                style={{ color: 'var(--text-secondary)', borderColor: 'var(--border-subtle)' }}
                onClick={() => setManageOpen(true)}
              >
                管理全部
              </button>
            ) : null
          }
        />
      </div>

      {entities.length === 0 && (
        <p className="mb-4 text-[13px] leading-7" style={{ color: 'var(--text-tertiary)' }}>
          添加品牌后，即可开始 AI 搜索可见度分析与持续监测。
        </p>
      )}

      <div className="grid grid-cols-[repeat(auto-fit,minmax(232px,1fr))] gap-4">
        {entities.map((entity) => (
          <BrandCard
            key={entity.id}
            entity={entity}
            isSelected={selectedBrandId === entity.id}
            onClick={() => setSelectedBrandId(selectedBrandId === entity.id ? null : entity.id)}
            onAnalyze={() => {
              void handleBrandClick(entity);
            }}
            onMonitor={() => handleOpenMonitoring(entity)}
          />
        ))}
        <AddBrandCard onClick={() => setAddOpen(true)} />
      </div>

      <BrandManageDialog open={manageOpen} onClose={() => setManageOpen(false)} />
      <EntityFormDialog open={addOpen} onClose={() => setAddOpen(false)} onSubmit={handleAddBrand} />
      <BrandDetailDialog entity={detailEntity} open={!!detailEntity} onClose={() => setDetailEntity(null)} />
    </section>
  );
}
