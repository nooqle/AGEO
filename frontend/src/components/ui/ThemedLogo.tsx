'use client';

import Image from 'next/image';
import { useTheme } from '@/hooks/useTheme';

interface ThemedLogoProps {
  size?: number;
  className?: string;
}

export function ThemedLogo({ size = 28, className }: ThemedLogoProps) {
  const { theme } = useTheme();
  const src = theme === 'light' ? '/logo-light.png' : '/logo-dark.png';

  return (
    <Image
      src={src}
      alt="Specta AI"
      width={size}
      height={size}
      className={className}
    />
  );
}
