'use client';

import { useMemo, useState } from 'react';
import { getApiBaseUrl } from '@/services/api';
import { useTheme } from '@/hooks/useTheme';

interface BrandAvatarProps {
  name: string;
  logoUrl?: string;
  domain?: string;
  size?: number;
  className?: string;
}

function normalizeDomainHost(domain?: string): string | null {
  const raw = (domain || '').trim();
  if (!raw) return null;

  try {
    const parsed = new URL(raw.includes('://') ? raw : `https://${raw}`);
    return parsed.hostname.replace(/^www\./i, '');
  } catch {
    const cleaned = raw
      .replace(/^https?:\/\//i, '')
      .replace(/^www\./i, '')
      .split('/')[0]
      .trim();
    return cleaned.includes('.') ? cleaned : null;
  }
}

function buildCachedFaviconUrl(domain?: string): string | null {
  const host = normalizeDomainHost(domain);
  if (!host) return null;
  return `${getApiBaseUrl()}/favicons?domain=${encodeURIComponent(host)}`;
}

export function BrandAvatar({ name, logoUrl, domain, size = 40, className = '' }: BrandAvatarProps) {
  const { theme } = useTheme();
  const cachedFaviconUrl = useMemo(() => buildCachedFaviconUrl(domain), [domain]);
  const cleanLogoUrl = logoUrl?.trim() || '';
  const imageUrl = cleanLogoUrl || cachedFaviconUrl;
  const [failedImageUrl, setFailedImageUrl] = useState<string | null>(null);
  const avatarLabel = name.trim() || '品牌';
  const isLarge = size > 48;
  const borderRadius = isLarge ? '14px' : '12px';
  const isDark = theme === 'dark';
  const visibleImageUrl = imageUrl && failedImageUrl !== imageUrl ? imageUrl : null;

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
      {visibleImageUrl ? (
        <img
          src={visibleImageUrl}
          alt=""
          className="h-[72%] w-[72%] object-contain"
          loading={size <= 48 ? 'eager' : 'lazy'}
          decoding="async"
          referrerPolicy="no-referrer"
          onError={() => setFailedImageUrl(visibleImageUrl)}
        />
      ) : null}
    </div>
  );
}
