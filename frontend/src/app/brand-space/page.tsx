'use client';

import { Suspense, useCallback, useEffect, useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { BrandSpaceShell } from '@/components/brand-space/BrandSpaceShell';
import { RequireAuth } from '@/components/auth/RequireAuth';
import { DashboardTopBar } from '@/components/layout/DashboardTopBar';
import { EntityFormDialog } from '@/components/dashboard/EntityFormDialog';
import { toast } from '@/components/ui/toast';
import { preferredDashboardEntity, splitDashboardEntities } from '@/lib/brandEntityHygiene';
import { useDashboardStore } from '@/stores/dashboardStore';
import { useEntityStore } from '@/stores/entityStore';
import { api } from '@/services/api';
import type { AuthUser } from '@/types/auth';
import type { CreateEntityInput } from '@/types/entity';

function BrandSpaceContent({ currentUser }: { currentUser: AuthUser }) {
  const router = useRouter();
  const searchParams = useSearchParams();
  const requestedEntityId = searchParams.get('entity_id');
  const [entityFormOpen, setEntityFormOpen] = useState(false);
  const { selectedBrandId, setSelectedBrandId } = useDashboardStore();
  const {
    entities,
    isLoading: entitiesLoading,
    error: entityError,
    hasFetched: hasFetchedEntities,
    fetchEntities,
    addEntity,
  } = useEntityStore();

  useEffect(() => {
    if (process.env.NEXT_PUBLIC_BRAND_SPACE_ENABLED === 'false') {
      router.replace('/dashboard');
      return;
    }
    void fetchEntities();
  }, [fetchEntities, router]);

  useEffect(() => {
    if (!hasFetchedEntities || entitiesLoading) return;
    if (entities.length === 0) {
      if (selectedBrandId) setSelectedBrandId(null);
      return;
    }
    if (
      requestedEntityId &&
      entities.some((entity) => entity.id === requestedEntityId) &&
      selectedBrandId !== requestedEntityId
    ) {
      setSelectedBrandId(requestedEntityId);
      return;
    }
    const visiblePrimary = splitDashboardEntities(entities, selectedBrandId).primary;
    const selectedIsPrimary = visiblePrimary.some((entity) => entity.id === selectedBrandId);
    if (!selectedBrandId || !selectedIsPrimary) {
      const preferred = preferredDashboardEntity(entities) || entities[0];
      setSelectedBrandId(preferred.id);
    }
  }, [
    entities,
    entitiesLoading,
    hasFetchedEntities,
    requestedEntityId,
    selectedBrandId,
    setSelectedBrandId,
  ]);

  const handleNewBrand = useCallback(() => {
    setEntityFormOpen(true);
  }, []);

  const handleSelectBrand = useCallback((brandId: string) => {
    setSelectedBrandId(brandId);
    const params = new URLSearchParams(searchParams.toString());
    params.set('entity_id', brandId);
    router.replace(`/brand-space?${params.toString()}`);
  }, [router, searchParams, setSelectedBrandId]);

  const shouldAutoPrompt =
    hasFetchedEntities &&
    !entitiesLoading &&
    !entityError &&
    entities.length === 0;

  const handleBlockedAutoPromptClose = useCallback(() => {
    toast.info('进入品牌空间前，需要先新建一个品牌。');
  }, []);

  const handleCreateBrand = async (data: CreateEntityInput) => {
    let createdBrandName = data.name;
    try {
      const created = await api.createEntity(data);
      createdBrandName = created.name || data.name;
      addEntity(created);
      setSelectedBrandId(created.id);
      setEntityFormOpen(false);
      router.replace(`/brand-space?entity_id=${encodeURIComponent(created.id)}`);
      toast.success(`「${createdBrandName}」已创建，正在打开品牌空间。`);
    } catch {
      toast.error(`「${createdBrandName}」创建失败，请稍后重试。`);
    }
  };

  return (
    <div className="flex min-h-screen flex-col" style={{ backgroundColor: 'var(--bg-primary)' }}>
      <DashboardTopBar onNewAnalysis={handleNewBrand} />
      <BrandSpaceShell
        entities={entities}
        selectedEntityId={selectedBrandId}
        entitiesLoading={entitiesLoading}
        hasFetchedEntities={hasFetchedEntities}
        entityError={entityError}
        onSelectBrand={handleSelectBrand}
        onAddBrand={handleNewBrand}
      />
      <EntityFormDialog
        open={entityFormOpen || shouldAutoPrompt}
        onClose={() => setEntityFormOpen(false)}
        onSubmit={handleCreateBrand}
        allowOrganizationScope={Boolean(currentUser.organization_id)}
        preventClose={shouldAutoPrompt}
        onPreventClose={handleBlockedAutoPromptClose}
      />
    </div>
  );
}

export default function BrandSpacePage() {
  return (
    <Suspense>
      <RequireAuth>
        {({ currentUser }) => <BrandSpaceContent currentUser={currentUser} />}
      </RequireAuth>
    </Suspense>
  );
}
