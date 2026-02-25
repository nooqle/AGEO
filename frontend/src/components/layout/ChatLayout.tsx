'use client';

import { ReactNode, useState, useRef, useCallback, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { RiMenuLine } from '@remixicon/react';
import { useCanvasStore } from '@/stores/canvasStore';
import { useResponsive } from '@/hooks/useResponsive';
import { MobileDrawer } from './MobileDrawer';
import { ArtifactNav } from './ArtifactNav';
import { cn } from '@/lib/cn';

interface ChatLayoutProps {
  children: ReactNode;
  canvas?: ReactNode;
  sidebar?: ReactNode;
}

const CANVAS_MIN_W = 360;
const CANVAS_MAX_W = 800;
const CANVAS_DEFAULT_DESKTOP = 800;
const CANVAS_DEFAULT_TABLET = 440;

export function ChatLayout({ children, canvas, sidebar }: ChatLayoutProps) {
  const { isOpen, setOpen } = useCanvasStore();
  const { isMobile, isTablet, canShowSplitCanvas, isDesktop } = useResponsive();
  const [mobileDrawerOpen, setMobileDrawerOpen] = useState(false);

  // Resizable canvas width
  const [canvasWidth, setCanvasWidth] = useState(
    () => isDesktop ? CANVAS_DEFAULT_DESKTOP : CANVAS_DEFAULT_TABLET
  );
  const [prevIsDesktop, setPrevIsDesktop] = useState(isDesktop);
  const isDragging = useRef(false);
  const startX = useRef(0);
  const startWidth = useRef(0);

  // Reset width when switching between desktop/tablet (derived state during render)
  if (prevIsDesktop !== isDesktop) {
    setPrevIsDesktop(isDesktop);
    setCanvasWidth(isDesktop ? CANVAS_DEFAULT_DESKTOP : CANVAS_DEFAULT_TABLET);
  }

  const onDragStart = useCallback((e: React.MouseEvent) => {
    e.preventDefault();
    isDragging.current = true;
    startX.current = e.clientX;
    startWidth.current = canvasWidth;
    document.body.style.cursor = 'col-resize';
    document.body.style.userSelect = 'none';
  }, [canvasWidth]);

  useEffect(() => {
    const onDragMove = (e: MouseEvent) => {
      if (!isDragging.current) return;
      // Dragging left increases canvas width (canvas is on the right)
      const delta = startX.current - e.clientX;
      const newWidth = Math.min(CANVAS_MAX_W, Math.max(CANVAS_MIN_W, startWidth.current + delta));
      setCanvasWidth(newWidth);
    };

    const onDragEnd = () => {
      if (!isDragging.current) return;
      isDragging.current = false;
      document.body.style.cursor = '';
      document.body.style.userSelect = '';
    };

    window.addEventListener('mousemove', onDragMove);
    window.addEventListener('mouseup', onDragEnd);
    return () => {
      window.removeEventListener('mousemove', onDragMove);
      window.removeEventListener('mouseup', onDragEnd);
    };
  }, []);

  const hasSidebar = !!sidebar;
  const showSplitCanvas = isOpen && canShowSplitCanvas && canvas;

  return (
    <div className="h-screen flex" style={{ backgroundColor: 'var(--bg-primary)' }}>
      {/* Main Content Area */}
      <div className="flex-1 flex overflow-hidden">
        {/* Sidebar — fixed 280px on desktop, 240px on laptop, hidden on mobile */}
        {hasSidebar && !isMobile && (
          <motion.div
            className={cn(
              'flex-shrink-0 h-full',
              isTablet ? 'w-[240px]' : 'w-[280px]'
            )}
            style={{
              backgroundColor: 'var(--bg-primary)',
              borderRight: '1px solid var(--border-default)',
            }}
            initial={{ x: -20, opacity: 0 }}
            animate={{ x: 0, opacity: 1 }}
            transition={{ duration: 0.3 }}
          >
            {sidebar}
          </motion.div>
        )}

        {/* Artifact Strip — between sidebar and chat */}
        {hasSidebar && !isMobile && (
          <div
            className="flex-shrink-0 h-full overflow-y-auto py-2"
            style={{
              width: '48px',
              borderRight: '1px solid var(--border-default)',
              backgroundColor: 'var(--bg-primary)',
            }}
          >
            <ArtifactNav compact />
          </div>
        )}

        {/* Content Panel */}
        <motion.div
          className="flex flex-col overflow-hidden flex-1"
          style={{ backgroundColor: 'var(--bg-primary)' }}
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ duration: 0.3, delay: 0.1 }}
        >
          {/* Mobile hamburger menu button */}
          {isMobile && hasSidebar && (
            <div
              className="flex items-center px-3 py-2 flex-shrink-0"
              style={{ borderBottom: '1px solid var(--border-default)' }}
            >
              <button
                onClick={() => setMobileDrawerOpen(true)}
                className="p-2 rounded-lg transition-colors cursor-pointer"
                style={{ color: 'var(--text-secondary)' }}
                title="菜单"
              >
                <RiMenuLine className="w-5 h-5" />
              </button>
            </div>
          )}
          {children}
        </motion.div>

        {/* Canvas Panel — Desktop split view with resize handle */}
        <AnimatePresence>
          {showSplitCanvas && (
            <motion.div
              className="flex-shrink-0 h-full flex"
              initial={{ width: 0, opacity: 0 }}
              animate={{ width: canvasWidth, opacity: 1 }}
              exit={{ width: 0, opacity: 0 }}
              transition={{ duration: 0.3, ease: [0.4, 0, 0.2, 1] }}
            >
              {/* Resize handle */}
              <div
                className="w-1 h-full flex-shrink-0 cursor-col-resize group relative"
                onMouseDown={onDragStart}
                style={{ backgroundColor: 'var(--border-default)' }}
              >
                <div
                  className="absolute inset-y-0 -left-1 -right-1 z-10"
                />
                {/* Visual indicator on hover */}
                <div
                  className="absolute top-1/2 -translate-y-1/2 left-1/2 -translate-x-1/2 w-1 h-8 rounded-full opacity-0 group-hover:opacity-100 transition-opacity"
                  style={{ backgroundColor: 'var(--color-primary)' }}
                />
              </div>
              {/* Canvas content */}
              <div className="flex-1 h-full overflow-hidden">
                {canvas}
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </div>

      {/* Canvas Sheet — Tablet/Mobile overlay */}
      <AnimatePresence>
        {isOpen && !canShowSplitCanvas && canvas && (
          <>
            <motion.div
              className="fixed inset-0 z-40 bg-black/60"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              onClick={() => setOpen(false)}
            />
            <motion.div
              className={cn(
                'fixed z-50 overflow-hidden',
                isMobile
                  ? 'inset-x-0 bottom-0 top-12 rounded-t-2xl'
                  : 'top-0 right-0 bottom-0 w-[400px]'
              )}
              style={{
                backgroundColor: 'var(--bg-primary)',
                borderLeft: isMobile ? undefined : '1px solid var(--border-default)',
                borderTop: isMobile ? '1px solid var(--border-default)' : undefined,
              }}
              initial={isMobile ? { y: '100%' } : { x: '100%' }}
              animate={isMobile ? { y: 0 } : { x: 0 }}
              exit={isMobile ? { y: '100%' } : { x: '100%' }}
              transition={{ duration: 0.3, ease: [0.4, 0, 0.2, 1] }}
            >
              {canvas}
            </motion.div>
          </>
        )}
      </AnimatePresence>

      {/* Mobile Sidebar Drawer */}
      {isMobile && hasSidebar && (
        <MobileDrawer open={mobileDrawerOpen} onClose={() => setMobileDrawerOpen(false)}>
          {sidebar}
        </MobileDrawer>
      )}
    </div>
  );
}

export default ChatLayout;
