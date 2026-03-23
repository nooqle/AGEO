'use client';

import { useParams } from 'next/navigation';

import { ControlPlaneCustomerDetailView } from '@/components/control-plane/ControlPlaneCustomerDetailView';

export default function ControlPlaneCustomerDetailRoutePage() {
  const params = useParams<{ customerId: string }>();
  return <ControlPlaneCustomerDetailView customerId={params.customerId} />;
}
