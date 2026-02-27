'use client';

import { useTheme } from '@/hooks/useTheme';

interface ThemedLogoProps {
  size?: number;
  className?: string;
}

export function ThemedLogo({ size = 28, className }: ThemedLogoProps) {
  const { theme } = useTheme();
  const src = theme === 'light' ? '/logo-light.png' : '/logo-dark.png';

  return (
    <img
      src={src}
      alt="Specta AI"
      width={size}
      height={size}
      className={className}
    />
  );
}
