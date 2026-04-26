'use client';

import { useTheme } from '@/hooks/useTheme';

interface BrandAvatarProps {
  name: string;
  domain?: string;
  size?: number;
  className?: string;
}

export function BrandAvatar({ name, size = 40, className = '' }: BrandAvatarProps) {
  const { theme } = useTheme();
  const initial = (name.trim().charAt(0) || '品').toUpperCase();
  const isLarge = size > 48;
  const borderRadius = isLarge ? '16px' : '18px';
  const fontSize = isLarge ? '1.5rem' : '1.125rem';
  const isDark = theme === 'dark';

  return (
    <div
      className={`flex items-center justify-center ${className}`}
      style={{
        width: size,
        height: size,
        borderRadius,
        background: isDark
          ? 'linear-gradient(135deg, color-mix(in srgb, var(--color-primary) 78%, #9aa8ff 22%), color-mix(in srgb, var(--color-primary) 62%, #2d3f95 38%))'
          : 'linear-gradient(135deg, color-mix(in srgb, var(--color-primary) 88%, #a9b8ff 12%), color-mix(in srgb, var(--color-primary) 72%, #4458d7 28%))',
        border: isDark ? '1px solid rgba(255,255,255,0.16)' : '1px solid rgba(67,90,197,0.14)',
        boxShadow: isDark ? '0 14px 28px rgba(45, 61, 141, 0.34)' : '0 10px 20px rgba(67, 90, 197, 0.16)',
      }}
    >
      <span className="font-bold text-white" style={{ fontSize }}>{initial}</span>
    </div>
  );
}
