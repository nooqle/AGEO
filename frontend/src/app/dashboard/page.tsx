'use client';

import { useState, useCallback } from 'react';
import { DashboardTopBar } from '@/components/layout/DashboardTopBar';
import { DashboardPage } from '@/components/dashboard/DashboardPage';
import { EntityFormDialog } from '@/components/dashboard/EntityFormDialog';
import { useEntityStore } from '@/stores/entityStore';
import { api } from '@/services/api';
import { toast } from '@/components/ui/toast';
import type { CreateEntityInput } from '@/types/entity';

export default function Dashboard() {
  const [entityFormOpen, setEntityFormOpen] = useState(false);
  const addEntity = useEntityStore((s) => s.addEntity);

  const handleNewAnalysis = useCallback(() => {
    setEntityFormOpen(true);
  }, []);

  const handleCreateBrand = async (data: CreateEntityInput) => {
    try {
      const created = await api.createEntity(data);
      addEntity(created);
      setEntityFormOpen(false);
    } catch {
      toast.error('品牌创建失败');
    }
  };

  return (
    <div className="h-screen flex flex-col" style={{ backgroundColor: 'var(--bg-primary)' }}>
      <DashboardTopBar onNewAnalysis={handleNewAnalysis} />
      <div className="flex-1 overflow-auto">
        <DashboardPage onNewAnalysis={handleNewAnalysis} />
      </div>
      <EntityFormDialog
        open={entityFormOpen}
        onClose={() => setEntityFormOpen(false)}
        onSubmit={handleCreateBrand}
      />
    </div>
  );
}
