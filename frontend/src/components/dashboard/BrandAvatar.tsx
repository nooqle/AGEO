'use client';

import { useMemo, useState } from 'react';
import { useTheme } from '@/hooks/useTheme';

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

function buildFaviconSources(domain?: string): string[] {
  const host = normalizeDomainHost(domain);
  if (!host) {
    return [];
  }

  return [
    `https://${host}/favicon.ico`,
    `https://www.${host}/favicon.ico`,
    `https://icons.duckduckgo.com/ip3/${host}.ico`,
  ];
}

export function BrandAvatar({ name, domain, size = 40, className = '' }: BrandAvatarProps) {
  const { theme } = useTheme();
  const faviconSources = useMemo(() => buildFaviconSources(domain), [domain]);
  const faviconKey = faviconSources.join('|');
  const [faviconState, setFaviconState] = useState({
    key: faviconKey,
    sourceIndex: 0,
  });
  const initial = (name.trim().charAt(0) || '品').toUpperCase();
  const isLarge = size > 48;
  const borderRadius = isLarge ? '14px' : '12px';
  const fontSize = isLarge ? '1.5rem' : '1.125rem';
  const isDark = theme === 'dark';
  const fallbackTextColor = isDark ? 'var(--text-primary)' : 'var(--text-secondary)';
  const sourceIndex = faviconState.key === faviconKey ? faviconState.sourceIndex : 0;
  const faviconUrl = faviconSources[sourceIndex];
  const showFavicon = Boolean(faviconUrl);

  return (
    <div
      className={`flex items-center justify-center overflow-hidden ${className}`}
      style={{
        width: size,
        height: size,
        borderRadius,
        background: 'transparent',
        border: isDark ? '1px solid rgba(244,241,232,0.12)' : '1px solid var(--border-subtle)',
        boxShadow: 'none',
      }}
    >
      {showFavicon ? (
        <img
          src={faviconUrl}
          alt=""
          className="h-[72%] w-[72%] object-contain"
          loading="lazy"
          referrerPolicy="no-referrer"
          onError={() => {
            setFaviconState((current) => {
              const currentIndex = current.key === faviconKey ? current.sourceIndex : 0;
              return {
                key: faviconKey,
                sourceIndex:
                  currentIndex + 1 < faviconSources.length
                    ? currentIndex + 1
                    : faviconSources.length,
              };
            });
          }}
        />
      ) : (
        <span
          className="font-bold"
          style={{
            fontSize,
            color: fallbackTextColor,
          }}
        >
          {initial}
        </span>
      )}
    </div>
  );
}
