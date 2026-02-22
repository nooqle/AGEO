"use client";

import { useState, useEffect } from "react";

// Breakpoints matching Tailwind defaults
const breakpoints = {
  sm: 640,
  md: 768,
  lg: 1024,
  xl: 1280,
  "2xl": 1536,
};

type Breakpoint = keyof typeof breakpoints;

/**
 * Hook to check if current viewport matches a media query
 */
export function useMediaQuery(query: string): boolean {
  const [matches, setMatches] = useState(() => {
    if (typeof window === "undefined") return false;
    return window.matchMedia(query).matches;
  });

  useEffect(() => {
    const media = window.matchMedia(query);
    const listener = () => setMatches(media.matches);
    const timeout = setTimeout(listener, 0);
    media.addEventListener("change", listener);
    return () => {
      clearTimeout(timeout);
      media.removeEventListener("change", listener);
    };
  }, [query]);

  return matches;
}

/**
 * Hook to check if viewport is at least a certain breakpoint
 */
export function useBreakpoint(breakpoint: Breakpoint): boolean {
  return useMediaQuery(`(min-width: ${breakpoints[breakpoint]}px)`);
}

/**
 * Hook to check if viewport is mobile
 */
export function useIsMobile(): boolean {
  return !useBreakpoint("md");
}

/**
 * Hook to check if viewport is tablet
 */
export function useIsTablet(): boolean {
  const isMd = useBreakpoint("md");
  const isLg = useBreakpoint("lg");
  return isMd && !isLg;
}

/**
 * Hook to check if viewport is desktop
 */
export function useIsDesktop(): boolean {
  return useBreakpoint("lg");
}

/**
 * Hook to get current breakpoint name
 */
export function useCurrentBreakpoint(): Breakpoint | null {
  const is2xl = useBreakpoint("2xl");
  const isXl = useBreakpoint("xl");
  const isLg = useBreakpoint("lg");
  const isMd = useBreakpoint("md");
  const isSm = useBreakpoint("sm");

  if (is2xl) return "2xl";
  if (isXl) return "xl";
  if (isLg) return "lg";
  if (isMd) return "md";
  if (isSm) return "sm";
  return null;
}
