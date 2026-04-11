'use client';

import { useCallback, useSyncExternalStore } from 'react';

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
  } catch {}
}

function subscribeTheme(listener: ThemeListener) {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

function getThemeSnapshot(): Theme {
  const theme = getDomTheme();
  currentTheme = theme;
  return theme;
}

function getServerThemeSnapshot(): Theme {
  return 'dark';
}

function subscribeMounted() {
  return () => {};
}

export function useTheme() {
  const theme = useSyncExternalStore(
    subscribeTheme,
    getThemeSnapshot,
    getServerThemeSnapshot,
  );
  const mounted = useSyncExternalStore(
    subscribeMounted,
    () => true,
    () => false,
  );

  const toggleTheme = useCallback(() => {
    const baseTheme = mounted ? currentTheme : getDomTheme();
    const nextTheme: Theme = baseTheme === 'dark' ? 'light' : 'dark';
    setGlobalTheme(nextTheme, true);
  }, [mounted]);

  return { theme, mounted, toggleTheme };
}
