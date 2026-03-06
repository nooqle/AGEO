'use client';

import { useCallback, useState } from 'react';

const STORAGE_KEY = 'specta-theme';
type Theme = 'dark' | 'light';

function applyTheme(theme: Theme) {
  const html = document.documentElement;
  html.classList.add('theme-transitioning');
  html.setAttribute('data-theme', theme);
  setTimeout(() => html.classList.remove('theme-transitioning'), 220);
}

function getInitialTheme(): Theme {
  if (typeof document === 'undefined') {
    return 'dark';
  }
  const current = document.documentElement.getAttribute('data-theme');
  return current === 'light' || current === 'dark' ? current : 'dark';
}

export function useTheme() {
  const [theme, setTheme] = useState<Theme>(getInitialTheme);

  const toggleTheme = useCallback(() => {
    setTheme((prev) => {
      const next: Theme = prev === 'dark' ? 'light' : 'dark';
      applyTheme(next);
      try {
        localStorage.setItem(STORAGE_KEY, next);
      } catch (_) {}
      return next;
    });
  }, []);

  return { theme, toggleTheme };
}