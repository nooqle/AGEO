'use client';

import { ReactNode } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { modalScrimClassName } from '@/components/ui/modal-scrim';

interface MobileDrawerProps {
  open: boolean;
  onClose: () => void;
  children: ReactNode;
}

export function MobileDrawer({ open, onClose, children }: MobileDrawerProps) {
  return (
    <AnimatePresence>
      {open && (
        <>
          {/* Overlay */}
          <motion.div
            className={modalScrimClassName('z-40')}
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.15 }}
            onClick={onClose}
          />

          {/* Drawer from left */}
          <motion.div
            className="fixed top-0 left-0 bottom-0 w-[280px] z-50 flex flex-col overflow-hidden"
            style={{
              backgroundColor: 'var(--bg-primary)',
              borderRight: '1px solid var(--border-subtle)',
            }}
            initial={{ x: '-100%' }}
            animate={{ x: 0 }}
            exit={{ x: '-100%' }}
            transition={{ duration: 0.3, ease: [0.4, 0, 0.2, 1] }}
          >
            {children}
          </motion.div>
        </>
      )}
    </AnimatePresence>
  );
}
