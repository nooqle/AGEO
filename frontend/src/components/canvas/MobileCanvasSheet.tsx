'use client';

import { ReactNode } from 'react';
import { motion, AnimatePresence, PanInfo } from 'framer-motion';
import { useCanvasStore } from '@/stores/canvasStore';
import { mobileCanvasVariants, overlayVariants } from '@/lib/animations';

interface MobileCanvasSheetProps {
  isOpen: boolean;
  children: ReactNode;
}

export function MobileCanvasSheet({ isOpen, children }: MobileCanvasSheetProps) {
  const { closeCanvas } = useCanvasStore();

  // Pull down to close gesture
  const handleDragEnd = (event: MouseEvent | TouchEvent | PointerEvent, info: PanInfo) => {
    if (info.offset.y > 100 || info.velocity.y > 500) {
      closeCanvas();
    }
  };

  return (
    <AnimatePresence>
      {isOpen && (
        <>
          {/* Overlay */}
          <motion.div
            className="fixed inset-0 bg-black/50 z-40"
            variants={overlayVariants}
            initial="hidden"
            animate="visible"
            exit="exit"
            onClick={closeCanvas}
          />

          {/* Canvas panel */}
          <motion.div
            className="fixed inset-x-0 bottom-0 top-16 bg-[--bg-primary] rounded-t-2xl z-50 flex flex-col border-t border-[--border-subtle]"
            variants={mobileCanvasVariants}
            initial="hidden"
            animate="visible"
            exit="hidden"
            drag="y"
            dragConstraints={{ top: 0, bottom: 0 }}
            dragElastic={{ top: 0, bottom: 0.5 }}
            onDragEnd={handleDragEnd}
          >
            {/* Drag handle */}
            <div className="flex justify-center py-3">
              <div className="w-10 h-1 bg-[--bg-tertiary] rounded-full" />
            </div>

            {/* Content */}
            <div className="flex-1 overflow-hidden">
              {children}
            </div>
          </motion.div>
        </>
      )}
    </AnimatePresence>
  );
}
