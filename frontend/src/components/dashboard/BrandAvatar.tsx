'use client';

import { useMemo, useState } from 'react';
import { useTheme } from '@/hooks/useTheme';
import { getApiBaseUrl } from '@/services/api';

interface BrandAvatarProps {
  name: string;
  domain?: string;
  size?: number;
  className?: string;
}

function normalizeDomainHost(domain?: string): string | null {
  const raw = (domain || '').trim();
  if (!raw) {
    return null;
  }

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

function buildFaviconUrl(domain?: string): string | null {
  const host = normalizeDomainHost(domain);
  if (!host) {
    return null;
  }
  return `${getApiBaseUrl()}/favicons?domain=${encodeURIComponent(host)}`;
}

export function BrandAvatar({ name, domain, size = 40, className = '' }: BrandAvatarProps) {
  const { theme } = useTheme();
  const faviconUrl = useMemo(() => buildFaviconUrl(domain), [domain]);
  const [imageState, setImageState] = useState<{
    url: string | null;
    ready: boolean;
    failed: boolean;
  }>({ url: null, ready: false, failed: false });
  const initial = (name.trim().charAt(0) || '品').toUpperCase();
  const isLarge = size > 48;
  const borderRadius = isLarge ? '14px' : '12px';
  const fontSize = isLarge ? '1.5rem' : '1.125rem';
  const isDark = theme === 'dark';
  const fallbackTextColor = isDark ? 'var(--text-primary)' : 'var(--text-secondary)';
  const imageStateMatches = imageState.url === faviconUrl;
  const imageReady = imageStateMatches && imageState.ready;
  const imageFailed = imageStateMatches && imageState.failed;
  const showFavicon = Boolean(faviconUrl && !imageFailed);

  return (
    <div
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
      <span
        className="font-bold"
        style={{
          fontSize,
          color: fallbackTextColor,
        }}
      >
        {initial}
      </span>

      {showFavicon && faviconUrl ? (
        <img
          src={faviconUrl}
          alt=""
          className="absolute h-[72%] w-[72%] object-contain transition-opacity duration-150"
          style={{ opacity: imageReady ? 1 : 0 }}
          loading={size <= 48 ? 'eager' : 'lazy'}
          decoding="async"
          referrerPolicy="no-referrer"
          onLoad={() => setImageState({ url: faviconUrl, ready: true, failed: false })}
          onError={() => {
            setImageState({ url: faviconUrl, ready: false, failed: true });
          }}
        />
      ) : null}
    </div>
  );
}
