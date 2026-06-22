import { redirect } from 'next/navigation';
import { BrandSpaceShell } from '@/components/brand-space/BrandSpaceShell';

export default function BrandSpacePage() {
  if (process.env.NEXT_PUBLIC_BRAND_SPACE_ENABLED === 'false') {
    redirect('/dashboard');
  }

  return <BrandSpaceShell />;
}
