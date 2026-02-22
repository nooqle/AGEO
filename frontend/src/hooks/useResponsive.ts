import { useState, useEffect } from 'react';

type Breakpoint = 'mobile' | 'tablet' | 'laptop' | 'desktop';

interface ResponsiveState {
  breakpoint: Breakpoint;
  width: number;
  isMobile: boolean;
  isTablet: boolean;
  isLaptop: boolean;
  isDesktop: boolean;
  canShowSplitCanvas: boolean;
  canShowSideBySide: boolean;
}

const BREAKPOINTS = {
  mobile: 0,
  tablet: 768,
  laptop: 1024,
  desktop: 1440,
};

export function useResponsive(): ResponsiveState {
  const [state, setState] = useState<ResponsiveState>({
    breakpoint: 'desktop',
    width: typeof window !== 'undefined' ? window.innerWidth : 1440,
    isMobile: false,
    isTablet: false,
    isLaptop: false,
    isDesktop: true,
    canShowSplitCanvas: true,
    canShowSideBySide: true,
  });

  useEffect(() => {
    const handleResize = () => {
      const width = window.innerWidth;
      let breakpoint: Breakpoint = 'desktop';

      if (width < BREAKPOINTS.tablet) {
        breakpoint = 'mobile';
      } else if (width < BREAKPOINTS.laptop) {
        breakpoint = 'tablet';
      } else if (width < BREAKPOINTS.desktop) {
        breakpoint = 'laptop';
      }

      setState({
        breakpoint,
        width,
        isMobile: breakpoint === 'mobile',
        isTablet: breakpoint === 'tablet',
        isLaptop: breakpoint === 'laptop',
        isDesktop: breakpoint === 'desktop',
        canShowSplitCanvas: breakpoint === 'laptop' || breakpoint === 'desktop',
        canShowSideBySide: breakpoint === 'desktop',
      });
    };

    handleResize();
    window.addEventListener('resize', handleResize);
    return () => window.removeEventListener('resize', handleResize);
  }, []);

  return state;
}
