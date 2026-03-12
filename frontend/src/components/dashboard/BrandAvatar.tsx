'use client';

import { useState, useMemo } from 'react';
import { useTheme } from '@/hooks/useTheme';

interface BrandAvatarProps {
  name: string;
  domain?: string;
  size?: number;
  className?: string;
}

export function BrandAvatar({ name, domain, size = 40, className = '' }: BrandAvatarProps) {
  const { theme } = useTheme();
  const [srcIndex, setSrcIndex] = useState(0);
  const initial = name.charAt(0).toUpperCase();

  const logoSources = useMemo(() => {
    if (!domain) return [];
    const clean = domain.replace(/^https?:\/\//, '').replace(/\/.*$/, '');
    return [`https://${clean}/apple-touch-icon.png`, `https://${clean}/favicon.ico`];
  }, [domain]);

  const currentSrc = logoSources[srcIndex];
  const isLarge = size > 48;
  const borderRadius = isLarge ? '16px' : '18px';
  const fontSize = isLarge ? '1.5rem' : '1.125rem';
  const isDark = theme === 'dark';

  if (currentSrc) {
    return (
      <div
        className={`flex items-center justify-center overflow-hidden ${className}`}
        style={{
          width: size,
          height: size,
          borderRadius,
          background: isDark
            ? 'linear-gradient(180deg, rgba(255,255,255,0.98), rgba(244,239,231,0.96))'
            : 'linear-gradient(180deg, rgba(255,255,255,0.98), rgba(248,245,238,0.94))',
          border: isDark ? '1px solid rgba(255,255,255,0.14)' : '1px solid rgba(17,24,39,0.06)',
          boxShadow: isDark
            ? '0 16px 32px rgba(0,0,0,0.28), inset 0 1px 0 rgba(255,255,255,0.84)'
            : '0 10px 18px rgba(15,23,42,0.08), inset 0 1px 0 rgba(255,255,255,0.9)',
        }}
      >
        <img
          src={currentSrc}
          alt={name}
          className="object-contain"
          style={{
            width: size - 12,
            height: size - 12,
            filter: isDark
              ? 'drop-shadow(0 4px 10px rgba(15,23,42,0.16))'
              : 'drop-shadow(0 2px 8px rgba(15,23,42,0.12))',
          }}
          onError={() => {
            setSrcIndex((prev) => (prev < logoSources.length - 1 ? prev + 1 : -1));
          }}
        />
      </div>
    );
  }

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
