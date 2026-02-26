'use client';

import { useState, useMemo } from 'react';

interface BrandAvatarProps {
  name: string;
  domain?: string;
  size?: number;
  className?: string;
}

/**
 * Brand avatar that tries to load logo from domain,
 * falls back to first character of brand name.
 */
export function BrandAvatar({ name, domain, size = 40, className = '' }: BrandAvatarProps) {
  const [srcIndex, setSrcIndex] = useState(0);
  const initial = name.charAt(0).toUpperCase();

  // Try multiple favicon sources from the brand's own website (no third-party dependency)
  const logoSources = useMemo(() => {
    if (!domain) return [];
    const clean = domain.replace(/^https?:\/\//, '').replace(/\/.*$/, '');
    return [
      `https://${clean}/apple-touch-icon.png`,
      `https://${clean}/favicon.ico`,
    ];
  }, [domain]);

  const currentSrc = logoSources[srcIndex];

  const isLarge = size > 48;
  const borderRadius = isLarge ? '16px' : '50%';
  const fontSize = isLarge ? '1.5rem' : '1.125rem';

  if (currentSrc) {
    return (
      <img
        src={currentSrc}
        alt={name}
        className={`object-contain ${className}`}
        style={{
          width: size,
          height: size,
          borderRadius,
          background: 'var(--bg-tertiary)',
        }}
        onError={() => {
          if (srcIndex < logoSources.length - 1) {
            setSrcIndex(srcIndex + 1);
          } else {
            setSrcIndex(-1); // all sources failed → fallback
          }
        }}
      />
    );
  }

  return (
    <div
      className={`flex items-center justify-center ${className}`}
      style={{
        width: size,
        height: size,
        borderRadius,
        background: 'var(--gradient-primary)',
      }}
    >
      <span className="font-bold text-white" style={{ fontSize }}>
        {initial}
      </span>
    </div>
  );
}
