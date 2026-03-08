'use client';

import { useCallback, useEffect, useState } from 'react';

const STORAGE_KEY = 'specta-theme';
type Theme = 'dark' | 'light';
type ThemeListener = (theme: Theme) => void;

const listeners = new Set<ThemeListener>();
let currentTheme: Theme = 'dark';

function applyTheme(theme: Theme) {
  const html = document.documentElement;
  html.classList.add('theme-transitioning');
  html.setAttribute('data-theme', theme);
  setTimeout(() => html.classList.remove('theme-transitioning'), 220);
}

function getDomTheme(): Theme {
  if (typeof document === 'undefined') {
    return 'dark';
  }

  const current = document.documentElement.getAttribute('data-theme');
  return current === 'light' || current === 'dark' ? current : 'dark';
}

function notifyThemeChange(theme: Theme) {
  currentTheme = theme;
  listeners.forEach((listener) => listener(theme));
}

function setGlobalTheme(theme: Theme, persist: boolean) {
  applyTheme(theme);
  notifyThemeChange(theme);

  if (!persist) {
    return;
  }

  try {
    localStorage.setItem(STORAGE_KEY, theme);
  } catch (_) {}
}

export function useTheme() {
  const [theme, setTheme] = useState<Theme>('dark');
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    const initialTheme = getDomTheme();
    currentTheme = initialTheme;
    setTheme(initialTheme);
    setMounted(true);

    const listener: ThemeListener = (nextTheme) => {
      setTheme(nextTheme);
    };
    listeners.add(listener);

    return () => {
      listeners.delete(listener);
    };
  }, []);

  const toggleTheme = useCallback(() => {
    const baseTheme = mounted ? currentTheme : getDomTheme();
    const nextTheme: Theme = baseTheme === 'dark' ? 'light' : 'dark';
    setGlobalTheme(nextTheme, true);
    setMounted(true);
  }, [mounted]);

  return { theme, mounted, toggleTheme };
}
