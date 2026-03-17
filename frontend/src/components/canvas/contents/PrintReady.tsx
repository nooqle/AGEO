'use client';

import { useEffect } from 'react';

export function PrintReady() {
  useEffect(() => {
    let cancelled = false;
    let timeoutId: number | null = null;

    const markReady = () => {
      if (cancelled) {
        return;
      }
      document.documentElement.dataset.pdfReady = 'true';
    };

    const waitForFonts = async () => {
      try {
        if ('fonts' in document) {
          await document.fonts.ready;
        }
      } catch {
        // Ignore font readiness failures and still mark the page ready.
      }

      requestAnimationFrame(() => {
        requestAnimationFrame(markReady);
      });

      timeoutId = window.setTimeout(markReady, 180);
    };

    document.documentElement.dataset.pdfReady = 'false';
    void waitForFonts();

    return () => {
      cancelled = true;
      if (timeoutId !== null) {
        window.clearTimeout(timeoutId);
      }
      delete document.documentElement.dataset.pdfReady;
    };
  }, []);

  return null;
}
