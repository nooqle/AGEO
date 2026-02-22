'use client';

import { useCallback, useEffect, useState } from 'react';

const STORAGE_KEY = 'specta-theme';
type Theme = 'dark' | 'light';

function applyTheme(theme: Theme) {
  const html = document.documentElement;
  html.classList.add('theme-transitioning');
  html.setAttribute('data-theme', theme);
  setTimeout(() => html.classList.remove('theme-transitioning'), 220);
}

export function useTheme() {
  const [theme, setTheme] = useState<Theme>('dark');

  useEffect(() => {
    // 读取当前 html 的 data-theme（由 FOUC 脚本已设置）
    const current = document.documentElement.getAttribute('data-theme');
    if (current === 'light' || current === 'dark') {
      setTheme(current);
    }
  }, []);

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
