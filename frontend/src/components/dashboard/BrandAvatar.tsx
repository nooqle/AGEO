'use client';

import { useState } from 'react';
import { RiBuilding2Line } from '@remixicon/react';
import { useTheme } from '@/hooks/useTheme';

interface BrandAvatarProps {
  name: string;
  logoUrl?: string;
  /**
   * Kept for existing call sites. Do not derive brand identity from a site
   * favicon: several sub-brands can share the same corporate domain.
   */
  domain?: string;
  size?: number;
  className?: string;
}

export function BrandAvatar({ name, logoUrl, size = 40, className = '' }: BrandAvatarProps) {
  const { theme } = useTheme();
  const [failedLogoUrl, setFailedLogoUrl] = useState<string | null>(null);
  const cleanLogoUrl = logoUrl?.trim() || '';
  const avatarLabel = name.trim() || '品牌';
  const isLarge = size > 48;
  const borderRadius = isLarge ? '14px' : '12px';
  const isDark = theme === 'dark';
  const fallbackIconColor = isDark ? 'var(--text-primary)' : 'var(--text-secondary)';
  const fallbackIconSize = isLarge ? 24 : size <= 38 ? 17 : 19;
  const showLogo = Boolean(cleanLogoUrl && failedLogoUrl !== cleanLogoUrl);

  return (
    <div
      role="img"
      aria-label={avatarLabel}
      className={`relative flex items-center justify-center overflow-hidden ${className}`}
      style={{
        width: size,
        height: size,
        borderRadius,
        background: 'transparent',
        border: isDark ? '1px solid rgba(244,241,232,0.12)' : '1px solid var(--border-subtle)',
        boxShadow: 'none',
      }}
    >
      {showLogo ? (
        <img
          src={cleanLogoUrl}
          alt=""
          className="h-[72%] w-[72%] object-contain"
          loading={size <= 48 ? 'eager' : 'lazy'}
          decoding="async"
          referrerPolicy="no-referrer"
          onError={() => setFailedLogoUrl(cleanLogoUrl)}
        />
      ) : (
        <RiBuilding2Line
          aria-hidden="true"
          size={fallbackIconSize}
          style={{
            color: fallbackIconColor,
          }}
        />
      )}
    </div>
  );
}
