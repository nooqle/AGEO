import { redirect } from 'next/navigation';

export default async function LegacyControlPlaneCustomerPage({
  params,
}: {
  params: Promise<{ customerId: string }>;
}) {
  const { customerId } = await params;
  redirect(`/control-plane/customers/${customerId}`);
}
