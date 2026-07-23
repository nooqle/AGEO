'use client';

/**
 * Wave Switch / M2: legacy Dashboard shell is no longer the product default.
 * Redirect to production-line console unless ?legacy=1 (temporary escape).
 */

import { Suspense, useEffect, useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { DashboardTopBar } from '@/components/layout/DashboardTopBar';
import { DashboardPage } from '@/components/dashboard/DashboardPage';
import { EntityFormDialog } from '@/components/dashboard/EntityFormDialog';
import { RequireAuth } from '@/components/auth/RequireAuth';
import { useEntityStore } from '@/stores/entityStore';
import { api } from '@/services/api';
import { toast } from '@/components/ui/toast';
import {
  isLegacyDashboardAllowed,
  PRODUCT_SHELL_HOME,
} from '@/lib/productShell';
import type { CreateEntityInput } from '@/types/entity';
import type { AuthUser } from '@/types/auth';

function DashboardContent({ currentUser }: { currentUser: AuthUser }) {
  const router = useRouter();
  const searchParams = useSearchParams();
  const allowLegacy = isLegacyDashboardAllowed(searchParams.toString());
  const [entityFormOpen, setEntityFormOpen] = useState(false);
  const addEntity = useEntityStore((s) => s.addEntity);
  const entities = useEntityStore((s) => s.entities);
  const entityError = useEntityStore((s) => s.error);
  const entitiesLoading = useEntityStore((s) => s.isLoading);
  const hasFetchedEntities = useEntityStore((s) => s.hasFetched);

  useEffect(() => {
    if (!allowLegacy) {
      router.replace(PRODUCT_SHELL_HOME);
    }
  }, [allowLegacy, router]);

  const handleNewAnalysis = () => {
    // M2: new brand should land on production line, not Chat main stage
    setEntityFormOpen(true);
  };

  const shouldAutoPrompt =
    allowLegacy &&
    hasFetchedEntities &&
    !entitiesLoading &&
    !entityError &&
    entities.length === 0;

  const handleBlockedAutoPromptClose = () => {
    toast.info('目前还没有任何品牌，需要新建一个品牌。');
  };

  const handleCreateBrand = async (data: CreateEntityInput) => {
    const createdBrandName = data.name;
    try {
      const created = await api.createEntity(data);
      addEntity(created);
      setEntityFormOpen(false);
      // M2: land on production line, not Chat main stage
      router.push(
        `${PRODUCT_SHELL_HOME}?entity_id=${encodeURIComponent(created.id)}&view=flow`,
      );
    } catch {
      toast.error(`「${createdBrandName}」创建或打开生产线失败，请稍后重试。`);
    }
  };

  if (!allowLegacy) {
    return (
      <div className="flex min-h-screen items-center justify-center text-sm text-[var(--text-secondary)]">
        正在进入品牌生产线…
      </div>
    );
  }

  return (
    <div className="flex min-h-screen flex-col" style={{ backgroundColor: 'var(--bg-primary)' }}>
      <div className="border-b border-amber-500/30 bg-amber-50 px-4 py-2 text-center text-xs text-amber-900">
        遗产 Dashboard（?legacy=1）。默认工作台是{' '}
        <a href={PRODUCT_SHELL_HOME} className="font-medium underline">
          品牌生产线
        </a>
        。
      </div>
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
    <Suspense
      fallback={
        <div className="flex min-h-screen items-center justify-center text-sm text-[var(--text-secondary)]">
          加载中…
        </div>
      }
    >
      <RequireAuth>
        {({ currentUser }) => <DashboardContent currentUser={currentUser} />}
      </RequireAuth>
    </Suspense>
  );
}
