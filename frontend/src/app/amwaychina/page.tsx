'use client';

import { Suspense, useEffect, useState } from 'react';
import { RequireAuth } from '@/components/auth/RequireAuth';
import { AmwayAssociationCircleConsolePage } from '@/components/dashboard/AmwayAssociationCircleConsolePage';
import { api } from '@/services/api';
import type { AmwayChinaEntitlement } from '@/types/controlPlane';

function AmwayChinaAccessGate() {
  const [entitlement, setEntitlement] = useState<AmwayChinaEntitlement | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let active = true;
    void api
      .getAmwayChinaEntitlement()
      .then((payload) => {
        if (active) setEntitlement(payload);
      })
      .catch((reason) => {
        if (active) {
          setEntitlement(null);
          setError(reason instanceof Error ? reason.message : '权限读取失败');
        }
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, []);

  if (loading) {
    return (
      <div className="min-h-screen bg-[var(--bg-secondary)] px-6 py-10 text-[var(--text-primary)]">
        <div className="mx-auto max-w-3xl rounded-2xl border border-[var(--border-subtle)] bg-[var(--bg-primary)] p-8">
          正在校验安利中国专属权限...
        </div>
      </div>
    );
  }

  if (error || !entitlement?.enabled || !entitlement.entity_id) {
    return (
      <div className="min-h-screen bg-[var(--bg-secondary)] px-6 py-10 text-[var(--text-primary)]">
        <div className="mx-auto max-w-3xl rounded-2xl border border-[var(--border-subtle)] bg-[var(--bg-primary)] p-8">
          <div className="text-xs font-medium tracking-[0.14em] text-[var(--text-tertiary)]">
            AMWAY CHINA
          </div>
          <h1 className="mt-2 text-2xl font-semibold">当前账号未开通安利中国专属 Console</h1>
          <p className="mt-3 text-sm leading-6 text-[var(--text-secondary)]">
            请让内部管理员在运营工作台的客户组织详情中打开 amwaychina 权限。普通品牌继续使用标准 Dashboard。
          </p>
          {error ? (
            <p className="mt-3 text-sm text-[var(--text-tertiary)]">{error}</p>
          ) : null}
        </div>
      </div>
    );
  }

  return <AmwayAssociationCircleConsolePage lockedEntityId={entitlement.entity_id} />;
}

export default function AmwayChinaPage() {
  return (
    <Suspense>
      <RequireAuth>
        {() => <AmwayChinaAccessGate />}
      </RequireAuth>
    </Suspense>
  );
}
