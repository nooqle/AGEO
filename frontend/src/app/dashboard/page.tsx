'use client';

import { Suspense, useState, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import { DashboardTopBar } from '@/components/layout/DashboardTopBar';
import { DashboardPage } from '@/components/dashboard/DashboardPage';
import { EntityFormDialog } from '@/components/dashboard/EntityFormDialog';
import { RequireAuth } from '@/components/auth/RequireAuth';
import { useEntityStore } from '@/stores/entityStore';
import { api } from '@/services/api';
import { toast } from '@/components/ui/toast';
import { buildBrandMonitoringChatUrl } from '@/lib/dashboardChatEntry';
import type { CreateEntityInput } from '@/types/entity';
import type { AuthUser } from '@/types/auth';

function DashboardContent({ currentUser }: { currentUser: AuthUser }) {
  const router = useRouter();
  const [entityFormOpen, setEntityFormOpen] = useState(false);
  const addEntity = useEntityStore((s) => s.addEntity);
  const entities = useEntityStore((s) => s.entities);
  const entityError = useEntityStore((s) => s.error);
  const entitiesLoading = useEntityStore((s) => s.isLoading);
  const hasFetchedEntities = useEntityStore((s) => s.hasFetched);

  const handleNewAnalysis = useCallback(() => {
    setEntityFormOpen(true);
  }, []);
  const shouldAutoPrompt =
    hasFetchedEntities &&
    !entitiesLoading &&
    !entityError &&
    entities.length === 0;

  const handleBlockedAutoPromptClose = useCallback(() => {
    toast.info('目前还没有任何品牌，需要新建一个品牌。');
  }, []);

  const handleCreateBrand = async (data: CreateEntityInput) => {
    let createdBrandName = data.name;
    try {
      const created = await api.createEntity(data);
      createdBrandName = created.name || data.name;
      addEntity(created);
      setEntityFormOpen(false);
      const session = await api.getOrCreateSessionByEntity(created.id);
      router.push(buildBrandMonitoringChatUrl({
        sessionId: session.id,
        entityId: created.id,
        brandName: createdBrandName,
      }));
    } catch {
      toast.error(`「${createdBrandName}」创建或打开对话失败，请稍后重试。`);
    }
  };

  return (
    <div className="flex min-h-screen flex-col" style={{ backgroundColor: 'var(--bg-primary)' }}>
      <DashboardTopBar onNewAnalysis={handleNewAnalysis} />
      <div className="flex-1">
        <DashboardPage onNewAnalysis={handleNewAnalysis} />
      </div>
      <EntityFormDialog
        open={entityFormOpen || shouldAutoPrompt}
        onClose={() => {
          setEntityFormOpen(false);
        }}
        onSubmit={handleCreateBrand}
        allowOrganizationScope={Boolean(currentUser.organization_id)}
        preventClose={shouldAutoPrompt}
        onPreventClose={handleBlockedAutoPromptClose}
      />
    </div>
  );
}

export default function Dashboard() {
  return (
    <Suspense>
      <RequireAuth>
        {({ currentUser }) => <DashboardContent currentUser={currentUser} />}
      </RequireAuth>
    </Suspense>
  );
}
