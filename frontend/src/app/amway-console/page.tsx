'use client';

import { Suspense } from 'react';
import { RequireAuth } from '@/components/auth/RequireAuth';
import { AmwayAssociationCircleConsolePage } from '@/components/dashboard/AmwayAssociationCircleConsolePage';

export default function AmwayConsolePage() {
  return (
    <Suspense>
      <RequireAuth>
        {() => <AmwayAssociationCircleConsolePage />}
      </RequireAuth>
    </Suspense>
  );
}
