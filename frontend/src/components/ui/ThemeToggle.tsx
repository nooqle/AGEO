'use client';

import { RiSunLine, RiMoonLine } from '@remixicon/react';
import { useTheme } from '@/hooks/useTheme';

export function ThemeToggle() {
  const { theme, toggleTheme } = useTheme();

  return (
    <button
      onClick={toggleTheme}
      aria-label={theme === 'dark' ? '切换到浅色模式' : '切换到深色模式'}
      title={theme === 'dark' ? '切换到浅色模式' : '切换到深色模式'}
      style={{
        width: '32px',
        height: '32px',
        borderRadius: '8px',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        color: theme === 'light' ? '#D97706' : 'var(--text-secondary)',
        backgroundColor: 'transparent',
        border: '1px solid var(--border-default)',
        cursor: 'pointer',
        flexShrink: 0,
      }}
    >
      {theme === 'dark' ? (
        <RiMoonLine style={{ width: '16px', height: '16px' }} />
      ) : (
        <RiSunLine style={{ width: '16px', height: '16px' }} />
      )}
    </button>
  );
}
