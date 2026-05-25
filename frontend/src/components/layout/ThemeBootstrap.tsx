'use client';

import { useLayoutEffect } from 'react';

export function ThemeBootstrap() {
  useLayoutEffect(() => {
    try {
      const theme = window.localStorage.getItem('specta-theme');
      document.documentElement.setAttribute(
        'data-theme',
        theme === 'dark' ? 'dark' : 'light',
      );
    } catch {
      // Theme persistence is optional; keep the server default if storage is unavailable.
    }
  }, []);

  return null;
}
