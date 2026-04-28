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

interface BrandCardsProps {
  onAddBrand?: () => void;
}

export function BrandCards({ onAddBrand }: BrandCardsProps) {
  const router = useRouter();
  const { entities, addEntity, error, fetchEntities } = useEntityStore();
  const { selectedBrandId, setSelectedBrandId } = useDashboardStore();
  const [manageOpen, setManageOpen] = useState(false);
  const [addOpen, setAddOpen] = useState(false);
  const [detailEntity, setDetailEntity] = useState<Entity | null>(null);
  const [analyzingEntityId, setAnalyzingEntityId] = useState<string | null>(null);
  const [monitoringEntityId, setMonitoringEntityId] = useState<string | null>(null);

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
    if (analyzingEntityId || monitoringEntityId) return;
    setAnalyzingEntityId(entity.id);
    try {
      const session = await api.getOrCreateSessionByEntity(entity.id);
      router.push(`/chat/${session.id}?entity_id=${encodeURIComponent(entity.id)}&brand=${encodeURIComponent(entity.name || '')}`);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : '品牌加载失败');
      setAnalyzingEntityId(null);
    }
  };

  const handleOpenMonitoring = (entity: Entity) => {
    if (analyzingEntityId || monitoringEntityId) return;
    setMonitoringEntityId(entity.id);
    setSelectedBrandId(entity.id);
    const target = `/settings?section=monitoring&entity_id=${encodeURIComponent(entity.id)}`;
    router.push(target);
  };

  const openBrandCreator = () => {
    if (onAddBrand) {
      onAddBrand();
      return;
    }
    setAddOpen(true);
  };

  return (
    <section
      className="dashboard-shell rounded-[26px] px-5 py-4"
    >
      <div>
        <DashboardSectionHeader
          title="品牌"
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

      {error ? (
        <div
          className="mb-4 flex flex-wrap items-center justify-between gap-3 rounded-[20px] border px-4 py-3"
          style={{
            background: 'color-mix(in srgb, var(--bg-elevated) 94%, var(--status-warning-bg) 6%)',
            borderColor: 'color-mix(in srgb, var(--status-warning) 18%, var(--border-subtle) 82%)',
          }}
        >
          <div>
            <div className="text-[13px] font-medium" style={{ color: 'var(--text-primary)' }}>
              品牌数据加载失败
            </div>
            <div className="mt-1 text-[12px] leading-6" style={{ color: 'var(--text-secondary)' }}>
              请重试。
            </div>
          </div>
          <button
            type="button"
            className="cursor-pointer rounded-full border px-3 py-1.5 text-[12px] font-medium transition-opacity hover:opacity-80"
            style={{ color: 'var(--text-secondary)', borderColor: 'var(--border-subtle)' }}
            onClick={() => {
              void fetchEntities();
            }}
          >
            重新加载
          </button>
        </div>
      ) : entities.length === 0 ? (
          <p className="mb-4 text-[13px] leading-7" style={{ color: 'var(--text-tertiary)' }}>
            创建品牌后即可开始分析和设置监测。
          </p>
      ) : null}

      <div className="grid grid-cols-[repeat(auto-fit,minmax(220px,1fr))] gap-3">
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
            isAnalyzeLoading={analyzingEntityId === entity.id}
            isMonitorLoading={monitoringEntityId === entity.id}
          />
        ))}
        <AddBrandCard onClick={openBrandCreator} />
      </div>

      <BrandManageDialog open={manageOpen} onClose={() => setManageOpen(false)} />
      <EntityFormDialog open={addOpen} onClose={() => setAddOpen(false)} onSubmit={handleAddBrand} />
      <BrandDetailDialog entity={detailEntity} open={!!detailEntity} onClose={() => setDetailEntity(null)} />
    </section>
  );
}
