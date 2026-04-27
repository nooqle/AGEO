'use client';

import { useLayoutEffect } from 'react';

export function ThemeBootstrap() {
  useLayoutEffect(() => {
    try {
      const theme = window.localStorage.getItem('specta-theme');
      if (theme === 'light') {
        document.documentElement.setAttribute('data-theme', 'light');
      } else {
        document.documentElement.removeAttribute('data-theme');
      }
    } catch {
      // Theme persistence is optional; keep the server default if storage is unavailable.
    }
  }, []);

  return null;
}
